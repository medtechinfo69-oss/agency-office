"""All REST endpoints. Secrets (API token) are read/written only here and
never serialized back to the client — the frontend only sees `token_set`."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, Request, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import agents as agentreg
from .. import compliance, db, exporter, orchestration as orch, trends
from ..config import settings
from ..events import bus
from ..images import generate_image
from ..provider import provider, reset_provider

router = APIRouter(prefix="/api")


# ----------------------------------------------------------------- helpers
def _project_or_404(pid: str) -> dict:
    row = db.one("SELECT * FROM projects WHERE id=?", (pid,))
    if not row:
        raise HTTPException(404, "project not found")
    d = dict(row)
    d["meta"] = db.jload(d.get("meta"), {})
    return d


def _task_dict(r) -> dict:
    d = dict(r)
    for k in ("depends", "acceptance", "qa_notes"):
        d[k] = db.jload(d.get(k), [])
    d["output"] = db.jload(d.get("output"), None)
    return d


# ----------------------------------------------------------------- health
@router.get("/health")
def health() -> dict:
    from .. import provider as provider_mod
    from ..hosted_settings import refresh
    refresh()
    demo = settings.is_demo or provider_mod.session_fallback
    reason = ""
    if provider_mod.session_fallback:
        reason = "billing"
    elif settings.is_demo:
        reason = "no_token"
    ac = provider_mod.active_config()
    return {
        "ok": True,
        "demo": demo,
        "demo_reason": reason,
        "token_set": bool(settings.api_token),
        "provider": ac.key if ac else None,
        "provider_label": ac.label if ac else None,
        "model": "demo-provider" if demo else (ac.model if ac else "-"),
        "image_model": "demo" if demo else settings.image_model,
        "meta_configured": exporter.meta_configured(),
    }


# ------------------------------------------------------------- providers
def _providers_payload() -> list[dict]:
    from ..hosted_settings import refresh
    refresh()
    from ..config import PROVIDER_PRESETS
    out = []
    for key, preset in PROVIDER_PRESETS.items():
        creds = (settings.provider_creds or {}).get(key) or {}
        out.append({
            "key": key,
            "label": preset.get("label", key),
            "base_url": creds.get("base_url") or preset["base_url"],
            "model": creds.get("model") or preset["model"],
            "site": preset.get("site", ""),
            "free": bool(preset.get("free")),
            "token_set": bool(creds.get("token")) or key == "ollama",
            "last4": (creds.get("token") or "")[-4:],
            "disconnected": db.kv_get("disconnected_" + key) == "1",
            "active": settings.active_provider == key,
            "image_model": creds.get("image_model")
                           or db.kv_get(f"image_{key}", "") or "",
            "images_api": bool(preset.get("images_api")),
        })
    return out


class ProviderIn(BaseModel):
    provider: str = Field(max_length=40)
    token: Optional[str] = Field(default=None,max_length=4096)
    model: Optional[str] = Field(default=None,max_length=200)
    base_url: Optional[str] = Field(default=None,max_length=500)
    image_model: Optional[str] = Field(default=None,max_length=200)


@router.get("/providers")
def list_providers() -> list[dict]:
    return _providers_payload()


@router.put("/providers")
def save_provider(body: ProviderIn) -> list[dict]:
    from ..config import PROVIDER_PRESETS
    if body.provider not in PROVIDER_PRESETS:
        raise HTTPException(400, "unknown provider")
    if body.base_url:
        from ..ai_hub import validate_endpoint
        validate_endpoint(body.base_url.strip(),local=body.provider=='ollama')
    creds = settings.provider_creds.setdefault(body.provider, {})
    preset = PROVIDER_PRESETS[body.provider]
    if body.token is not None:
        token = body.token.strip()
        creds["token"] = token
        if token:  # persist server-side only (never returned by any endpoint)
            db.kv_set(f"token_{body.provider}", token)
        else:
            # explicit clear — stored as "" so .env can't resurrect it on restart
            db.kv_set(f"token_{body.provider}", "")
    if body.model is not None and body.model.strip():
        creds["model"] = body.model.strip()
        db.kv_set(f"model_{body.provider}", creds["model"])
    if body.base_url is not None and body.base_url.strip():
        from ..ai_hub import validate_endpoint
        from ..config import provider_base_url
        creds["base_url"] = validate_endpoint(provider_base_url(body.provider, body.base_url), local=body.provider == "ollama")
        db.kv_set(f"base_{body.provider}", creds["base_url"])
    if body.image_model is not None:
        img = body.image_model.strip()
        creds["image_model"] = img
        db.kv_set(f"image_{body.provider}", img)
        if settings.active_provider == body.provider and img:
            settings.image_model = img
            db.kv_set("image_model", img)
    creds.setdefault("base_url", preset["base_url"])
    creds.setdefault("model", preset["model"])
    # keep flat mirrors in sync if this is the active provider
    if settings.active_provider == body.provider:
        settings.api_base_url = creds["base_url"]
        settings.api_token = creds.get("token", "")
        settings.text_model = creds["model"]
    from ..provider import reset_provider
    reset_provider()
    db.log_activity(f"Provider config saved: {preset['label']}", "info")
    return _providers_payload()


class ActivateIn(BaseModel):
    provider: str


@router.post("/providers/activate")
def activate_provider(body: ActivateIn) -> list[dict]:
    from ..config import PROVIDER_PRESETS
    if body.provider not in PROVIDER_PRESETS:
        raise HTTPException(400, "unknown provider")
    db.kv_set("disconnected_" + body.provider, "0")
    settings.active_provider = body.provider
    db.kv_set("active_provider", body.provider)
    creds = (settings.provider_creds or {}).get(body.provider) or {}
    preset = PROVIDER_PRESETS[body.provider]
    settings.api_base_url = creds.get("base_url") or preset["base_url"]
    settings.api_token = creds.get("token") or ""
    settings.text_model = creds.get("model") or preset["model"]
    # image model follows the provider automatically: the saved per-provider
    # choice, else the preset default, else the keyless auto backend
    from ..config import AUTO_IMAGE_MODEL
    img = (creds.get("image_model") or db.kv_get(f"image_{body.provider}", "")
           or db.kv_get("image_model", "") or preset.get("image_model") or AUTO_IMAGE_MODEL)
    creds["image_model"] = img
    settings.image_model = img
    db.kv_set("image_model", img)
    from ..provider import reset_provider
    reset_provider()
    label = preset["label"]
    has_token = bool(creds.get("token")) or body.provider == "ollama"
    db.log_activity(
        f"Switched AI provider → {label} "
        f"({'token set' if has_token else 'NO TOKEN — add one in Settings'})",
        "success" if has_token else "warn")
    bus.publish_sync("log", {
        "level": "success" if has_token else "warn",
        "text": f"🔌 Active provider: {label} ({settings.text_model})"})
    return _providers_payload()


class ModelsIn(BaseModel):
    token: Optional[str] = Field(default=None,max_length=4096)
    base_url: Optional[str] = Field(default=None,max_length=500)


@router.post("/providers/{key}/models")
async def provider_models(key: str, request: Request, body: ModelsIn = Body(default_factory=ModelsIn)) -> dict:
    """Validate an API key (typed now or already stored) and list its models.
    Used by the UI to auto-populate the model dropdowns. Never logs/echoes
    the token — only the result travels back."""
    from ..config import PROVIDER_PRESETS
    from ..provider import fetch_models
    if key not in PROVIDER_PRESETS:
        raise HTTPException(404, "unknown provider")
    from ..hosted_settings import refresh
    refresh()
    preset = PROVIDER_PRESETS[key]
    creds = (settings.provider_creds or {}).get(key) or {}
    base = ((body.base_url or creds.get("base_url") or preset["base_url"])
            .strip().rstrip("/"))
    from .. import admin
    identity = getattr(request.state, 'identity', None)
    saved_base = (creds.get('base_url') or preset['base_url']).strip().rstrip('/')
    if identity and not admin.permits(identity, 'connections', True) and (base != saved_base or body.token):
        raise HTTPException(403, 'Manage connections permission is required to test edited credentials or endpoints.')
    from ..ai_hub import validate_endpoint
    validate_endpoint(base, local=key == "ollama", resolve=True)
    token = (body.token or creds.get("token") or "").strip()
    result = await fetch_models(key, base, token)
    from ..ai_hub import tags
    for item in result.get('models', []): item['tags'] = tags(item, key)
    result.update(provider=key, label=preset['label'], checked_at=__import__('time').time())
    db.kv_set('catalog_'+key, json.dumps(result))
    return result


# ----------------------------------------------------------------- settings
class SettingsIn(BaseModel):
    api_base_url: Optional[str] = None
    api_token: Optional[str] = None
    text_model: Optional[str] = None
    image_model: Optional[str] = None
    demo_mode: Optional[str] = None
    auto_approve: Optional[str] = None
    language: Optional[str] = None
    sound: Optional[str] = None
    speed: Optional[float] = None
    day_night: Optional[str] = None


@router.get("/settings")
def get_settings() -> dict:
    from ..hosted_settings import refresh
    refresh()
    return {
        # secrets are NEVER returned — only whether they exist
        "api_base_url": settings.api_base_url,
        "token_set": bool(settings.api_token),
        "text_model": settings.text_model,
        "image_model": settings.image_model,
        "demo_mode": settings.demo_mode,
        "is_demo": settings.is_demo,
        "meta_configured": exporter.meta_configured(),
        "auto_approve": db.kv_get("auto_approve", "0"),
        "language": db.kv_get("language", "en"),
        "sound": db.kv_get("sound", "on"),
        "speed": float(db.kv_get("speed", "1") or 1),
        "day_night": db.kv_get("day_night", "day"),
        "max_retries": settings.max_retries,
        "request_timeout": settings.request_timeout,
    }


@router.put("/settings")
def put_settings(body: SettingsIn) -> dict:
    # env-backed fields are persisted to kv so they survive restarts even
    # without editing .env (the token is stored server-side only)
    if body.api_base_url is not None:
        settings.api_base_url = body.api_base_url.strip().rstrip("/")
        db.kv_set("api_base_url", settings.api_base_url)
    if body.api_token is not None and body.api_token.strip():
        settings.api_token = body.api_token.strip()
        db.kv_set("api_token", settings.api_token)  # server-side only, never returned
        reset_provider()
    if body.text_model:
        settings.text_model = body.text_model.strip()
        db.kv_set("text_model", settings.text_model)
    if body.image_model:
        settings.image_model = body.image_model.strip()
        db.kv_set("image_model", settings.image_model)
    if body.demo_mode:
        settings.demo_mode = body.demo_mode.strip()
        db.kv_set("demo_mode", settings.demo_mode)
        reset_provider()
    if body.auto_approve is not None:
        db.kv_set("auto_approve", "1" if body.auto_approve in ("1", "true", "on") else "0")
    if body.language:
        db.kv_set("language", body.language)
    if body.sound:
        db.kv_set("sound", body.sound)
    if body.speed:
        db.kv_set("speed", str(max(0.25, min(4.0, float(body.speed)))))
    if body.day_night:
        db.kv_set("day_night", body.day_night)
    bus.publish_sync("settings", {"language": db.kv_get("language", "en")})
    return get_settings()


# ----------------------------------------------------------------- agents
@router.get("/agents")
def get_agents() -> list[dict]:
    out = []
    for a in agentreg.list_agents():
        mem = db.get_memory("agent", a["id"], 5)
        a["enabled"] = db.kv_get("agent_enabled_" + a["id"], "1") != "0"
        a["memory"] = mem
        a["next_level_xp"] = (a["level"]) * 100
        out.append(a)
    return out


class AgentIn(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1,max_length=100)
    role: str = Field(min_length=1,max_length=200)
    personality: str = Field(default="",max_length=2000)
    system_prompt: str = Field(default="",max_length=20000)
    skills: list[str] = []
    color: str = "#2dd4bf"
    strictness: int = Field(default=3,ge=1,le=5)
    avatar: dict = {}


@router.post("/agents")
def create_agent(body: AgentIn) -> dict:
    try:
        a = agentreg.upsert_custom_agent(body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    bus.publish_sync("agent_created", {"agent_id": a["id"]})
    db.log_activity(f"New agent hired: {a['name']} ({a['role']})", "success")
    bus.publish_sync("log", {"level": "success", "text": f"🆕 New hire: {a['name']} — {a['role']}"})
    bus.publish_sync("new_hire", {"agent_id": a["id"], "name": a["name"]})
    return a


@router.put("/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentIn) -> dict:
    if not agentreg.get_agent(agent_id):
        raise HTTPException(404, "agent not found")
    data = body.model_dump()
    data["id"] = agent_id
    try:
        a = agentreg.upsert_custom_agent(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    bus.publish_sync("agent_updated", {"agent_id": agent_id})
    return a


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str) -> dict:
    if not agentreg.delete_custom_agent(agent_id):
        raise HTTPException(400, "only custom agents can be removed")
    bus.publish_sync("agent_removed", {"agent_id": agent_id})
    return {"deleted": True}


@router.get("/prompts")
def list_prompts() -> list[dict]:
    return [dict(r) for r in db.query("SELECT * FROM agents_prompts ORDER BY created_at DESC")]


class PromptIn(BaseModel):
    name: str
    category: str = "general"
    content: str


@router.post("/prompts")
def create_prompt(body: PromptIn) -> dict:
    pid = db.new_id("pr")
    db.execute("INSERT INTO agents_prompts (id, name, category, content, created_at) VALUES (?,?,?,?,?)",
               (pid, body.name, body.category, body.content, db.now()))
    return {"id": pid, **body.model_dump(), "created_at": db.now()}


@router.delete("/prompts/{pid}")
def delete_prompt(pid: str) -> dict:
    db.execute("DELETE FROM agents_prompts WHERE id=?", (pid,))
    return {"deleted": True}


# ----------------------------------------------------------------- projects
class ProjectIn(BaseModel):
    name: str
    brief: str
    template: str = ""


@router.get("/projects")
def list_projects() -> list[dict]:
    rows = db.query("SELECT * FROM projects ORDER BY created_at DESC")
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = db.jload(d.get("meta"), {})
        out.append(d)
    return out


@router.post("/projects")
def create_project(body: ProjectIn) -> dict:
    template = None
    if body.template:
        template = db.one("SELECT * FROM templates WHERE id=?", (body.template,))
    brief = body.brief
    name = body.name
    if template:
        brief = brief or template["brief"]
        name = name or template["name"]
        meta = db.jload(template["meta"], {})
    else:
        meta = {}
    if not brief.strip():
        raise HTTPException(400, "brief is required")
    pid = db.new_id("prj")
    db.execute(
        "INSERT INTO projects (id, name, brief, status, created_at, updated_at, meta) "
        "VALUES (?,?,?,'planning',?,?,?)",
        (pid, name or "Untitled project", brief, db.now(), db.now(), db.jdump(meta)))
    from ..scheduler import seed_defaults
    seed_defaults(pid)
    db.log_activity(f"Project created: {name or brief[:30]}", "info", pid)
    return _project_or_404(pid)


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict:
    d = _project_or_404(pid)
    d["tasks"] = [_task_dict(r) for r in db.query(
        "SELECT * FROM tasks WHERE project_id=? ORDER BY created_at", (pid,))]
    d["brand_kit"] = _brand_dict(pid)
    return d


class ChatIn(BaseModel):
    text: str


@router.post("/projects/{pid}/chat")
async def boss_chat(pid: str, body: ChatIn) -> dict:
    _project_or_404(pid)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "empty message")
    msg = db.add_message(text, channel="boss", project_id=pid)
    bus.publish_sync("message", msg, pid)

    from .. import cloud
    if cloud.enabled():
        cloud.enqueue(pid, text)
        return {'ok': True, 'message': msg, 'queued': True}

    proj = db.one("SELECT status FROM projects WHERE id=?", (pid,))
    status = proj["status"] if proj else "planning"

    # if manager is waiting for an escalation answer, route it there
    run = orch.get_run(pid)
    if run and not run.approved_plan:
        # plan stage: fold replies into the plan revision or start run
        pass
    if run:
        orch.push_boss_reply(pid, text)

    # auto-start a run when the project is fresh and no run is active
    if run is None and status in ("planning", "error", "stopped"):
        # extract the brief: first message becomes the brief unless project already has one
        proj = db.one("SELECT brief FROM projects WHERE id=?", (pid,))
        existing = (proj["brief"] or "").strip() if proj else ""
        brief = existing if existing and status != "planning" else (
            existing + "\n\n" + text if existing else text)
        if status == "planning":
            brief = text if not existing else existing  # brief set at creation
            if existing:
                brief = existing + "\n\n[Boss update] " + text
        asyncio.create_task(orch.run_project(pid, brief))
    elif run is None and status in ("awaiting_approval", "review", "delivered"):
        # plain conversation with Nora — give a lightweight reply
        asyncio.create_task(_nora_reply(pid, text))
    elif run is None:
        asyncio.create_task(_nora_reply(pid, text))

    return {"ok": True, "message": msg}


async def _nora_reply(pid: str, text: str) -> None:
    """Lightweight Manager chat when no pipeline run is active."""
    from ..agents import get_agent
    try:
        reply = await orch.call_llm(
            "nora", get_agent("nora")["system_prompt"],  # type: ignore[arg-type]
            f"Boss says: {text}\nProject brief: "
            f"{(db.one('SELECT brief FROM projects WHERE id=?', (pid,)) or {'brief': ''})['brief'][:1500]}\n"
            "Reply as the Manager: short, concrete, no invented facts.",
            pid, json_mode=False)
    except Exception as e:
        reply = f"I couldn't reach my brain right now ({e}). Please check Settings → API."
    msg = db.add_message(reply.strip(), channel="agent", project_id=pid, agent_id="nora")
    bus.publish_sync("message", msg, pid)
    # already stored above — bubble + log only, no second copy
    orch.agent_say("nora", reply.strip()[:60], pid, persist=False)


@router.get("/projects/{pid}/messages")
def get_messages(pid: str) -> list[dict]:
    rows = db.query(
        "SELECT * FROM messages WHERE project_id=? OR project_id IS NULL ORDER BY created_at",
        (pid,))
    return [dict(r) for r in rows]


@router.get("/projects/{pid}/activity")
def get_activity(pid: str) -> list[dict]:
    rows = db.query(
        "SELECT * FROM activity WHERE project_id=? OR project_id IS NULL "
        "ORDER BY created_at DESC LIMIT 200", (pid,))
    return [dict(r) for r in rows]


# ----------------------------------------------------------------- controls
class ControlIn(BaseModel):
    action: str  # pause|resume|stop


@router.post("/projects/{pid}/control")
def control(pid: str, body: ControlIn) -> dict:
    _project_or_404(pid)
    a = body.action
    from .. import cloud
    if cloud.enabled():
        if a not in ('pause', 'resume', 'stop'): raise HTTPException(400, 'unknown action')
        return {'ok': cloud.control(pid, a), 'action': a}
    if a == "pause":
        ok = orch.pause_run(pid)
    elif a == "resume":
        ok = orch.resume_run(pid)
    elif a == "stop":
        ok = orch.stop_run(pid)
    else:
        raise HTTPException(400, "unknown action")
    return {"ok": ok, "action": a}


class ApprovalIn(BaseModel):
    kind: str  # plan|deliverable
    approved: bool
    comment: str = ""


@router.post("/projects/{pid}/approve")
def approve(pid: str, body: ApprovalIn) -> dict:
    _project_or_404(pid)
    from .. import cloud
    if cloud.enabled():
        if body.kind not in ('plan', 'deliverable'): raise HTTPException(400, 'unknown kind')
        return {'ok': cloud.approve(pid, body.kind, body.approved, body.comment)}
    if body.kind == "plan":
        ok = orch.approve_plan(pid, body.approved, body.comment)
    elif body.kind == "deliverable":
        ok = orch.approve_deliverable(pid, body.approved, body.comment)
    else:
        raise HTTPException(400, "unknown kind")
    return {"ok": ok}


# ----------------------------------------------------------------- brand kit
class BrandIn(BaseModel):
    name: str = ""
    colors: list[str] = []
    fonts: list[str] = []
    tone: str = ""
    rules: list[str] = []


def _brand_dict(pid: str) -> dict:
    row = db.one("SELECT * FROM brand_kit WHERE project_id=?", (pid,))
    if not row:
        return {"name": "", "colors": [], "fonts": [], "tone": "", "rules": [],
                "logo_url": None}
    d = dict(row)
    extra = db.jload(d.get("extra"), {})
    return {
        "name": extra.get("name", ""),
        "colors": db.jload(d.get("colors"), []),
        "fonts": db.jload(d.get("fonts"), []),
        "tone": d.get("tone", ""),
        "rules": db.jload(d.get("rules"), []),
        "logo_url": f"/media/{pid}/{Path(d['logo_path']).name}" if d.get("logo_path") else None,
    }


@router.get("/projects/{pid}/brand")
def get_brand(pid: str) -> dict:
    _project_or_404(pid)
    return _brand_dict(pid)


@router.put("/projects/{pid}/brand")
def put_brand(pid: str, body: BrandIn) -> dict:
    _project_or_404(pid)
    row = db.one("SELECT logo_path FROM brand_kit WHERE project_id=?", (pid,))
    extra = {}
    if row:
        prev = db.one("SELECT extra FROM brand_kit WHERE project_id=?", (pid,))
        extra = db.jload(prev["extra"], {}) if prev else {}
    extra["name"] = body.name
    if row:
        db.execute(
            "UPDATE brand_kit SET colors=?, fonts=?, tone=?, rules=?, extra=? WHERE project_id=?",
            (db.jdump(body.colors), db.jdump(body.fonts), body.tone,
             db.jdump(body.rules), db.jdump(extra), pid))
    else:
        db.execute(
            "INSERT INTO brand_kit (project_id, colors, fonts, tone, rules, extra) VALUES (?,?,?,?,?,?)",
            (pid, db.jdump(body.colors), db.jdump(body.fonts), body.tone,
             db.jdump(body.rules), db.jdump(extra)))
    db.add_memory("project", pid,
                  f"Brand kit updated: {body.name} · colors {', '.join(body.colors)} · tone: {body.tone}",
                  "brand")
    bus.publish_sync("brand", {"project_id": pid}, pid)
    return _brand_dict(pid)


@router.post("/projects/{pid}/brand/logo")
async def upload_logo(pid: str, file: UploadFile = File(...)) -> dict:
    _project_or_404(pid)
    if file.content_type not in ("image/png", "image/jpeg", "image/svg+xml", "image/webp"):
        raise HTTPException(400, "logo must be png/jpg/svg/webp")
    dest = settings.media_dir / pid
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"logo{Path(file.filename or 'logo').suffix or '.png'}"
    from ..media import MAX_FILE_BYTES, persist_file
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, 'Logo must be 10 MB or smaller.')
    path.write_bytes(content)
    persist_file(path)
    row = db.one("SELECT project_id FROM brand_kit WHERE project_id=?", (pid,))
    if row:
        db.execute("UPDATE brand_kit SET logo_path=? WHERE project_id=?", (str(path), pid))
    else:
        db.execute("INSERT INTO brand_kit (project_id, logo_path) VALUES (?,?)", (pid, str(path)))
    return {"logo_url": f"/media/{pid}/{path.name}"}


# ----------------------------------------------------------------- templates
@router.get("/templates")
def list_templates() -> list[dict]:
    rows = db.query("SELECT * FROM templates")
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = db.jload(d.get("meta"), {})
        out.append(d)
    return out


# ----------------------------------------------------------------- deliverables
@router.get("/projects/{pid}/deliverables")
def list_deliverables(pid: str) -> list[dict]:
    rows = db.query("SELECT * FROM deliverables WHERE project_id=? ORDER BY created_at", (pid,))
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = db.jload(d.get("data"), {})
        out.append(d)
    return out


@router.get("/projects/{pid}/export")
def export_zip(pid: str) -> FileResponse:
    _project_or_404(pid)
    try:
        path = exporter.project_export_zip(pid)
    except Exception as e:
        raise HTTPException(500, f"export failed: {e}")
    return FileResponse(path, media_type="application/zip",
                        filename=f"agency_office_{pid}.zip")


@router.get("/deliverables/{did}/versions")
def versions(did: str) -> list[dict]:
    rows = db.query(
        "SELECT id, version, note, created_at FROM deliverable_versions "
        "WHERE deliverable_id=? ORDER BY version", (did,))
    return [dict(r) for r in rows]


class RollbackIn(BaseModel):
    version: int


@router.post("/deliverables/{did}/rollback")
def rollback(did: str, body: RollbackIn) -> dict:
    cur = db.one("SELECT * FROM deliverables WHERE id=?", (did,))
    if not cur:
        raise HTTPException(404, "deliverable not found")
    ver = db.one("SELECT * FROM deliverable_versions WHERE deliverable_id=? AND version=?",
                 (did, body.version))
    if not ver:
        raise HTTPException(404, "version not found")
    # current data already has its own version row, so we can roll back directly
    db.execute("UPDATE deliverables SET data=?, version=?, status='pending', updated_at=? WHERE id=?",
               (ver["data"], body.version, db.now(), did))
    db.log_activity(f"Rolled back deliverable to v{body.version}", "warn",
                    cur["project_id"])
    bus.publish_sync("log", {"level": "warn",
                             "text": f"⏪ Rolled back “{cur['title']}” to v{body.version}"},
                     cur["project_id"])
    return {"ok": True, "version": body.version}


# ----------------------------------------------------------------- meetings / standup
class MeetingIn(BaseModel):
    topic: str = "Brainstorm"


@router.post("/projects/{pid}/meeting")
async def meeting(pid: str, body: MeetingIn) -> dict:
    _project_or_404(pid)
    return await orch.run_meeting(pid, body.topic)


@router.get("/projects/{pid}/meetings")
def meetings(pid: str) -> list[dict]:
    rows = db.query("SELECT * FROM meetings WHERE project_id=? ORDER BY created_at DESC", (pid,))
    out = []
    for r in rows:
        d = dict(r)
        d["ideas"] = db.jload(d["ideas"], [])
        out.append(d)
    return out


@router.post("/projects/{pid}/standup")
async def standup(pid: str) -> dict:
    _project_or_404(pid)
    return await orch.run_standup(pid)


@router.get("/projects/{pid}/standups")
def standups(pid: str) -> list[dict]:
    rows = db.query("SELECT * FROM standups WHERE project_id=? ORDER BY created_at DESC LIMIT 30", (pid,))
    return [dict(r) for r in rows]


# ----------------------------------------------------------------- images (Zed)
class ImageIn(BaseModel):
    title: str
    ratio: str = "1:1"
    prompt: str = ""
    slug: str = "asset"


@router.post("/projects/{pid}/images")
async def make_image(pid: str, body: ImageIn) -> dict:
    _project_or_404(pid)
    try:
        return await generate_image(pid, body.title, body.ratio, body.prompt, body.slug)
    except Exception as e:
        raise HTTPException(502, f"image generation failed: {e}")


# ----------------------------------------------------------------- trends
class TrendsIn(BaseModel):
    query: str = ""


@router.post("/projects/{pid}/trends")
async def scan_trends(pid: str, body: TrendsIn) -> dict:
    proj = _project_or_404(pid)
    result = await trends.scan(proj["brief"], query=body.query)
    db.add_memory("project", pid, f"Trend scan: {result.get('summary','')[:200]}", "note")
    db.log_activity("Trend/competitor scan completed", "info", pid)
    return result


# ----------------------------------------------------------------- analytics
class AnalyticsIn(BaseModel):
    campaign: str
    metrics: dict = {}
    notes: str = ""


@router.post("/projects/{pid}/analytics")
def add_analytics(pid: str, body: AnalyticsIn) -> dict:
    _project_or_404(pid)
    aid = db.new_id("an")
    db.execute(
        "INSERT INTO analytics (id, project_id, campaign, metrics, notes, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (aid, pid, body.campaign, db.jdump(body.metrics), body.notes, db.now()))
    # store a learning memory for the team
    m = ", ".join(f"{k}={v}" for k, v in list(body.metrics.items())[:8])
    db.add_memory("project", pid, f"Results for '{body.campaign}': {m}. {body.notes}".strip(), "result")
    bus.publish_sync("log", {"level": "info",
                             "text": f"📈 Results pasted for '{body.campaign}' — team will learn from them."}, pid)
    return {"id": aid}


@router.get("/projects/{pid}/analytics")
def get_analytics(pid: str) -> list[dict]:
    rows = db.query("SELECT * FROM analytics WHERE project_id=? ORDER BY created_at DESC", (pid,))
    out = []
    for r in rows:
        d = dict(r)
        d["metrics"] = db.jload(d["metrics"], {})
        out.append(d)
    return out


@router.post("/projects/{pid}/analytics/insight")
async def analytics_insight(pid: str) -> dict:
    rows = [dict(r) for r in db.query(
        "SELECT campaign, metrics, notes FROM analytics WHERE project_id=?", (pid,))]
    for r in rows:
        r["metrics"] = db.jload(r["metrics"], {})
    if not rows:
        raise HTTPException(400, "no campaign results yet — paste some first")
    try:
        text = await orch.call_llm(
            "nora", agentreg.get_agent("nora")["system_prompt"],  # type: ignore[arg-type]
            "ROLE: Manager analysing campaign results. Which creatives/audiences performed best "
            "and what should we do next? No invented numbers.\n"
            f"DATA:\n{json.dumps(rows, ensure_ascii=False)[:6000]}",
            pid, json_mode=False)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"insight": text.strip()}


# ----------------------------------------------------------------- schedules
class ScheduleIn(BaseModel):
    name: str
    kind: str = "weekly_posts"
    interval_hours: float = 168
    enabled: bool = False
    payload: dict = {}


@router.get("/projects/{pid}/schedules")
def get_schedules(pid: str) -> list[dict]:
    rows = db.query("SELECT * FROM schedules WHERE project_id=? OR project_id IS NULL", (pid,))
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = db.jload(d["payload"], {})
        d["enabled"] = bool(d["enabled"])
        out.append(d)
    return out


@router.post("/projects/{pid}/schedules")
def create_schedule(pid: str, body: ScheduleIn) -> dict:
    _project_or_404(pid)
    from ..cloud import enabled
    if enabled() and body.enabled:
        raise HTTPException(409, 'Unattended schedules require a durable worker; this Vercel deployment only runs jobs while the office is open.')
    sid = db.new_id("sch")
    db.execute(
        "INSERT INTO schedules (id, name, kind, project_id, interval_hours, enabled, payload, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (sid, body.name, body.kind, pid, body.interval_hours, 1 if body.enabled else 0,
         db.jdump(body.payload), db.now()))
    return {"id": sid, **body.model_dump()}


class SchedulePatch(BaseModel):
    enabled: Optional[bool] = None
    interval_hours: Optional[float] = None


@router.patch("/schedules/{sid}")
def patch_schedule(sid: str, body: SchedulePatch) -> dict:
    row = db.one("SELECT * FROM schedules WHERE id=?", (sid,))
    if not row:
        raise HTTPException(404, "schedule not found")
    from ..cloud import enabled
    if enabled() and body.enabled:
        raise HTTPException(409, 'Unattended schedules require a durable worker; this Vercel deployment only runs jobs while the office is open.')
    if body.enabled is not None:
        db.execute("UPDATE schedules SET enabled=? WHERE id=?", (1 if body.enabled else 0, sid))
    if body.interval_hours is not None:
        db.execute("UPDATE schedules SET interval_hours=? WHERE id=?",
                   (max(0.1, body.interval_hours), sid))
    return {"ok": True}


# ----------------------------------------------------------------- memory
@router.get("/projects/{pid}/memory")
def project_memory(pid: str) -> list[dict]:
    return db.get_memory("project", pid, 100)


# ----------------------------------------------------------------- Meta module
class CampaignIn(BaseModel):
    brief_override: str = ""


@router.post("/projects/{pid}/campaign")
async def build_campaign(pid: str, body: CampaignIn) -> dict:
    """Adam builds the full campaign package + Zed images + compliance report."""
    proj = _project_or_404(pid)
    brief = body.brief_override or proj["brief"]
    try:
        text = await orch.call_llm(
            "adam", agentreg.get_agent("adam")["system_prompt"],  # type: ignore[arg-type]
            f"ROLE: Ads Manager (Adam)\n<<<BRIEF>>>{brief}<<<ENDBRIEF>>>\n"
            f"<<<BRAND_KIT>>>{orch.brand_block(pid)}<<<ENDBRAND_KIT>>>\n"
            "Build the full Facebook/Instagram campaign package. Return JSON with keys: "
            "objective, audience{age,location,interests,placements}, budget_plan, "
            "variants[3]{label,headline,primary_text,cta,image_brief,utm}, kpi[], compliance_notes[].",
            pid, marker="campaign")
        campaign = orch.parse_json(text)
    except Exception as e:
        raise HTTPException(502, f"campaign generation failed: {e}")

    # compliance pass
    report = compliance.check_campaign(campaign)
    campaign["compliance_report"] = report

    # generate images for each variant (Zed)
    colors, name, _ = _brand_simple(pid)
    images = []
    for v in campaign.get("variants", [])[:3]:
        for ratio in ("1:1", "4:5"):
            try:
                img = await generate_image(pid, v.get("headline", "ad"), ratio,
                                           v.get("image_brief", ""), f"ad_{v.get('label','x')}_{ratio.replace(':','')}")
                images.append({"label": v.get("label"), "ratio": ratio, **img})
            except Exception:
                continue
    campaign["images"] = images

    # save as deliverable + meta draft (approval-gated)
    tid = db.new_id("task")
    db.execute(
        """INSERT INTO tasks (id, project_id, title, description, assignee, status,
           depends, acceptance, output, created_at, updated_at)
           VALUES (?,?,?,?,'adam','done','[]','[]',?,?,?)""",
        (tid, pid, "Ads campaign package", "Built via Meta module", db.jdump(campaign),
         db.now(), db.now()))
    did = db.new_id("dlv")
    db.execute(
        """INSERT INTO deliverables (id, project_id, task_id, kind, title, data, version, status, created_at, updated_at)
           VALUES (?,?,?,'campaign',?,?,1,'pending',?,?)""",
        (did, pid, tid, "Facebook/Instagram campaign", db.jdump(campaign), db.now(), db.now()))
    db.execute(
        "INSERT INTO deliverable_versions (deliverable_id, version, data, note, created_at) VALUES (?,?,?,?,?)",
        (did, 1, db.jdump(campaign), "initial", db.now()))
    for v in campaign.get("variants", []):
        exporter.create_meta_draft(pid, {
            "kind": "ad", "label": v.get("label"), "headline": v.get("headline"),
            "caption": v.get("primary_text"), "cta": v.get("cta"),
            "utm": v.get("utm"), "link": "https://example.com?" + str(v.get("utm", "")).split("?")[-1],
        })
    agentreg.add_xp("adam", 25)
    agentreg.add_xp("rami", 10)
    bus.publish_sync("log", {"level": "success",
                             "text": f"📣 Campaign ready ({len(campaign.get('variants',[]))} variants) — "
                                     f"compliance: {'PASS' if report['passed'] else 'ISSUES FOUND'}"}, pid)
    db.log_activity("Campaign package built", "success", pid)
    return campaign


class CalendarIn(BaseModel):
    days: int = 30
    brief_override: str = ""


@router.post("/projects/{pid}/calendar")
async def build_calendar(pid: str, body: CalendarIn) -> dict:
    proj = _project_or_404(pid)
    brief = body.brief_override or proj["brief"]
    try:
        text = await orch.call_llm(
            "mona", agentreg.get_agent("mona")["system_prompt"],  # type: ignore[arg-type]
            f"ROLE: Social Media (Mona)\n<<<BRIEF>>>{brief}<<<ENDBRIEF>>>\n"
            f"<<<BRAND_KIT>>>{orch.brand_block(pid)}<<<ENDBRAND_KIT>>>\n"
            f"Create a {body.days}-day content calendar. Return JSON with days[{body.days}] "
            "{day,channel,format,theme,caption,hashtags,best_time}, reels_scripts, carousels.",
            pid, marker="calendar", max_tokens=4096)
        cal = orch.parse_json(text)
    except Exception as e:
        raise HTTPException(502, f"calendar generation failed: {e}")

    report = compliance.check_calendar(cal.get("days", []))
    cal["compliance_report"] = report

    tid = db.new_id("task")
    db.execute(
        """INSERT INTO tasks (id, project_id, title, description, assignee, status,
           depends, acceptance, output, created_at, updated_at)
           VALUES (?,?,?,?,'mona','done','[]','[]',?,?,?)""",
        (tid, pid, f"{body.days}-day content calendar", "Built via Meta module",
         db.jdump(cal), db.now(), db.now()))
    did = db.new_id("dlv")
    db.execute(
        """INSERT INTO deliverables (id, project_id, task_id, kind, title, data, version, status, created_at, updated_at)
           VALUES (?,?,?,'calendar',?,?,1,'pending',?,?)""",
        (did, pid, tid, f"{body.days}-day content calendar", db.jdump(cal), db.now(), db.now()))
    db.execute(
        "INSERT INTO deliverable_versions (deliverable_id, version, data, note, created_at) VALUES (?,?,?,?,?)",
        (did, 1, db.jdump(cal), "initial", db.now()))
    agentreg.add_xp("mona", 25)
    bus.publish_sync("log", {"level": "success",
                             "text": f"🗓️ {body.days}-day calendar ready ({len(cal.get('days',[]))} days)"}, pid)
    return cal


@router.get("/projects/{pid}/meta/drafts")
def meta_drafts(pid: str) -> dict:
    return {"configured": exporter.meta_configured(),
            "drafts": exporter.list_meta_drafts(pid)}


class DraftIn(BaseModel):
    payload: dict


@router.post("/projects/{pid}/meta/drafts")
def create_draft(pid: str, body: DraftIn) -> dict:
    _project_or_404(pid)
    return exporter.create_meta_draft(pid, body.payload)


class PublishIn(BaseModel):
    draft_id: str
    approve: bool = False


@router.post("/projects/{pid}/meta/publish")
async def publish(pid: str, body: PublishIn) -> dict:
    _project_or_404(pid)
    if not body.approve:
        raise HTTPException(400, "publishing requires explicit approval")
    try:
        return await exporter.publish_meta_draft(body.draft_id)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


def _brand_simple(pid: str) -> tuple[list[str], str, None]:
    row = db.one("SELECT * FROM brand_kit WHERE project_id=?", (pid,))
    if not row:
        return ["#0f172a", "#2dd4bf"], "BRAND", None
    d = dict(row)
    extra = db.jload(d.get("extra"), {}) or {}
    return (db.jload(d.get("colors"), ["#0f172a", "#2dd4bf"]) or ["#0f172a", "#2dd4bf"],
            extra.get("name", "BRAND"), None)
