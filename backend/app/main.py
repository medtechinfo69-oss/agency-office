"""AGENCY OFFICE — FastAPI entrypoint.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000   (from backend/)
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from .media import DurableMedia

from . import agents as agentreg
from . import db, scheduler
from .config import settings
from .events import bus
from .access import OwnerAccess, OwnerAccessMiddleware, auth_router
from .routers import api
from . import sitebuilder

app = FastAPI(title="AGENCY OFFICE", version="1.0.0")
access = OwnerAccess.from_env()
app.add_middleware(OwnerAccessMiddleware, access=access)
app.include_router(auth_router(access))

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(access.origins) if access.production else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# compress JSON/HTML/CSS/JS on the wire — faster first load
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(api.router)
from .cloud import router as cloud_router
app.include_router(cloud_router)
app.include_router(sitebuilder.router, prefix="/api/sitebuilder", tags=["site builder"])

# generated images / logos / exports
app.mount("/media", DurableMedia(directory=str(settings.media_dir)), name="media")


@app.get('/', response_class=HTMLResponse)
def backend_status():
    try:
        db.one('SELECT 1')
    except Exception:
        return HTMLResponse('<h1>Agency Office API</h1><p>Database connection unavailable. Check the backend deployment logs.</p>', status_code=503)
    mode = 'Supabase Postgres' if os.getenv('DATABASE_URL') else 'local SQLite'
    return HTMLResponse('<h1>Agency Office API is running</h1><p>Database: ' + mode + '</p>'
        '<p><a href="https://agency-office-indol.vercel.app/">Open Agency Office</a></p>')


# ---------------------------------------------------------------- WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await bus.connect(ws)
    try:
        while True:
            # clients may send pings; ignore payload
            await ws.receive_text()
    except WebSocketDisconnect:
        bus.disconnect(ws)
    except Exception:
        with contextlib.suppress(Exception):
            bus.disconnect(ws)


# ---------------------------------------------------------------- lifecycle
@app.on_event("startup")
async def on_startup() -> None:
    # Settings-page values (kv) override env seeds for provider creds —
    # the UI is the source of truth once a key/model was saved there.
    import os
    from .config import PROVIDER_PRESETS
    for key in PROVIDER_PRESETS:
        if (v := db.kv_get(f"token_{key}")) is not None:
            settings.provider_creds.setdefault(key, {})["token"] = v
        if (v := db.kv_get(f"model_{key}")):
            settings.provider_creds.setdefault(key, {})["model"] = v
        if (v := db.kv_get(f"base_{key}")):
            settings.provider_creds.setdefault(key, {})["base_url"] = v
    if (v := db.kv_get("active_provider")) and v in PROVIDER_PRESETS:
        settings.active_provider = v
    # re-resolve flat mirrors from the active provider
    ac_key = settings.active_provider
    creds = settings.provider_creds.get(ac_key) or {}
    preset = PROVIDER_PRESETS.get(ac_key, {})
    settings.api_base_url = creds.get("base_url") or settings.api_base_url
    settings.api_token = creds.get("token") or ""
    settings.text_model = creds.get("model") or settings.text_model
    if not os.environ.get("IMAGE_MODEL") and (v := db.kv_get("image_model")):
        settings.image_model = v
    if not os.environ.get("DEMO_MODE") and (v := db.kv_get("demo_mode")):
        settings.demo_mode = v
    from .provider import reset_provider, active_config
    reset_provider()
    _ac = active_config()
    if _ac:
        db.log_activity(f"AI provider ready: {_ac.label} · {_ac.model}", "success")
    else:
        db.log_activity(
            "No AI provider configured — add an API key in Settings → Providers",
            "error")

    agentreg.seed_agents()
    seed_templates()
    seed_prompts()
    if os.getenv('VERCEL') != '1':
        await scheduler.start()
    bus.publish_sync("log", {"level": "success",
                             "text": "🏢 Agency office is open."})


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await scheduler.stop()


# ---------------------------------------------------------------- seed data
def seed_templates() -> None:
    if db.one("SELECT id FROM templates LIMIT 1"):
        return
    templates = [
        ("tpl_fb_launch", "Facebook launch",
         "Launch campaign on Facebook for a new offer: audience research, 3 ad variants, "
         "landing page, tracking.",
         {"channel": "facebook", "deliverables": ["campaign", "landing", "images"]}),
        ("tpl_ig_growth", "Instagram growth",
         "30-day Instagram growth plan: content calendar, Reels ideas, hashtag sets, "
         "engagement tactics.",
         {"channel": "instagram", "deliverables": ["calendar", "images"]}),
        ("tpl_landing", "Landing page",
         "Conversion-focused landing page: copy, design direction, responsive build, SEO meta.",
         {"deliverables": ["copy", "design", "code", "seo"]}),
        ("tpl_rebrand", "Full rebrand",
         "Full rebrand: brand identity, messaging house, visual system, launch assets, "
         "campaign to announce the new brand.",
         {"deliverables": ["design", "copy", "images", "campaign"]}),
    ]
    for tid, name, brief, meta in templates:
        db.execute("INSERT INTO templates (id, name, brief, meta) VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING",
                   (tid, name, brief, db.jdump(meta)))


def seed_prompts() -> None:
    if db.one("SELECT id FROM agents_prompts LIMIT 1"):
        return
    prompts = [
        ("pr_1", "Ad headline (compliance-safe)", "ads",
         "Write 5 Facebook ad headlines ≤40 chars. No superlatives, no guarantees, "
         "no invented numbers. Benefit-led, specific, on-brand."),
        ("pr_2", "Instagram caption", "social",
         "Write an Instagram caption: hook line, 2-3 short lines of value, CTA, "
         "3-5 relevant hashtags. Match the brand tone from the brand kit."),
        ("pr_3", "Landing hero copy", "copy",
         "Hero section: headline ≤12 words, subheadline ≤25 words, CTA button label. "
         "Pain → promise → proof structure. Only claims present in the brief."),
        ("pr_4", "SEO meta description", "seo",
         "Meta description ≤155 chars including target keyword, clear benefit, and a CTA. "
         "No clickbait, no keyword stuffing."),
        ("pr_5", "Reel script 30s", "social",
         "30-second Reel script: 0-3s hook, 3-20s value, 20-30s CTA. Include on-screen "
         "text suggestions and voiceover lines."),
        ("pr_6", "QA checklist", "qa",
         "Review this deliverable: brief compliance, brand kit, acceptance criteria, "
         "no invented facts/prices, format validity. Output approved + issues list."),
    ]
    for pid, name, cat, content in prompts:
        db.execute("INSERT INTO agents_prompts (id, name, category, content, created_at) "
                   "VALUES (?,?,?,?,?) ON CONFLICT(id) DO NOTHING", (pid, name, cat, content, db.now()))


# NOTE: no demo project is seeded — the app opens on an empty office and the
# first screen walks the Boss through creating a real project (New Project).
    db.add_memory("project", pid,
                  "Client preference: all numbers must come from the client; "
                  "the team must ask instead of guessing.", "preference")
    from .scheduler import seed_defaults
    seed_defaults(pid)


# ---------------------------------------------------------------- run
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
