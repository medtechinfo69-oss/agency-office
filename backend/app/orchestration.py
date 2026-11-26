"""Orchestration engine.

Flow:  Brief → Manager plan (JSON) → approval gate → parallel agent work
       → QA review (rejections → fixes, max 3 rounds) → Manager final check
       → deliverable approval gate → delivery to the Boss.

Also handles: pause/resume/stop, inter-agent messages (speech bubbles + log),
XP awards, token/cost accounting, stuck-agent detection, meetings, stand-ups.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional

from . import agents as agentreg
from . import db
from .config import settings
from .events import bus
from .provider import ProviderError, provider

MAX_REVISIONS = 3
AGENT_TIMEOUT = 120  # seconds before an agent is declared "stuck"
LOCAL_TIMEOUT = 900  # local CPU models (Ollama) need a bigger budget than
                     # cloud — includes time spent queued behind parallel agents
                     # and a full 4096-token generation at ~6 tok/s (~700s observed)


# --------------------------------------------------------------------------
@dataclass
class RunControl:
    """Mutable control flags for one project run."""
    project_id: str
    pause: asyncio.Event = field(default_factory=asyncio.Event)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    approval: asyncio.Event = field(default_factory=asyncio.Event)
    deliverable_approval: asyncio.Event = field(default_factory=asyncio.Event)
    plan: dict = field(default_factory=dict)
    approved_plan: bool = False
    deliverable_ready: bool = False
    questions: list = field(default_factory=list)
    boss_replies: asyncio.Queue = field(default_factory=asyncio.Queue)
    tasks: dict = field(default_factory=dict)   # task_id -> asyncio.Task
    started_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.pause.set()  # running by default


RUNS: dict[str, RunControl] = {}


def get_run(project_id: str) -> Optional[RunControl]:
    return RUNS.get(project_id)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def emit(etype: str, data: dict, project_id: Optional[str] = None) -> None:
    bus.publish_sync(etype, data, project_id)


def agent_say(agent_id: str, text: str, project_id: Optional[str] = None,
              to_agent: Optional[str] = None, bubble: bool = True,
              persist: Optional[bool] = None) -> None:
    """Speech bubble + log line. Routine status chatter stays out of the Boss
    chat (it would flood the Manager conversation) — substantive messages
    (agent→agent, anything from Nora, long-form notes) are persisted.
    persist=False → caller already stored the message (no duplicates)."""
    substantive = (persist if persist is not None else
                   (bool(to_agent) or agent_id == "nora" or len(text) > 48))
    if substantive:
        db.add_message(text, channel="agent", project_id=project_id,
                       agent_id=agent_id, to_agent=to_agent)
    if bubble:
        agentreg.set_status(agent_id, "working", text)
        emit("agent_message", {"agent_id": agent_id, "text": text,
                               "to_agent": to_agent, "persist": substantive}, project_id)
    target = f" → {to_agent}" if to_agent else ""
    db.log_activity(f"{agent_id.upper()}{target}: {text}", "info", project_id)
    emit("log", {"level": "info", "text": f"{agent_id.upper()}{target}: {text}"}, project_id)


def set_agent_state(agent_id: str, state: str, message: str = "",
                    task: str = "", project_id: Optional[str] = None) -> None:
    agentreg.set_status(agent_id, state, message, task)
    emit("agent_state", {"agent_id": agent_id, "state": state,
                         "message": message, "task": task}, project_id)


def bump_project(project_id: str, **cols: Any) -> None:
    if not cols:
        return
    keys = ", ".join(f"{k}=?" for k in cols)
    db.execute(f"UPDATE projects SET {keys}, updated_at=? WHERE id=?",
               (*cols.values(), db.now(), project_id))
    row = db.one("SELECT * FROM projects WHERE id=?", (project_id,))
    if row:
        emit("project", dict(row), project_id)


def add_cost(project_id: str, usage) -> None:
    db.execute(
        """UPDATE projects SET cost_usd=cost_usd+?, tokens_in=tokens_in+?,
           tokens_out=tokens_out+? WHERE id=?""",
        (usage.cost_usd, usage.tokens_in, usage.tokens_out, project_id),
    )


def progress_update(project_id: str) -> None:
    rows = db.query("SELECT status FROM tasks WHERE project_id=?", (project_id,))
    if not rows:
        return
    done = sum(1 for r in rows if r["status"] == "done")
    pct = round(100.0 * done / len(rows), 1)
    bump_project(project_id, progress=pct)
    emit("progress", {"progress": pct, "done": done, "total": len(rows)}, project_id)


# --------------------------------------------------------------------------
# LLM call wrapper (stuck-state + cost + speech)
# --------------------------------------------------------------------------
async def call_llm(agent_id: str, system: str, user: str, project_id: str,
                   *, json_mode: bool = True, marker: str = "",
                   max_tokens: int = 2400) -> str:
    sys_prompt = (f"[TASK:{marker}]\n" if marker else "") + system

    async def _call(p):
        cfg = getattr(p, "cfg", None)
        budget = LOCAL_TIMEOUT if (cfg and cfg.key == "ollama") else AGENT_TIMEOUT
        return await asyncio.wait_for(
            p.chat([{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user}],
                   json_mode=json_mode, temperature=0.4, max_tokens=max_tokens),
            timeout=budget,
        )

    p = provider()
    try:
        result = await _call(p)
    except ProviderError as e:
        from . import provider as provider_mod
        handled = False

        # 1) failover chain: billing / auth / rate-limit / network / server /
        #    missing-model → try the next configured provider (own model each)
        failoverable = (
            e.kind in ("payment", "auth", "rate_limit", "network", "server")
            or (e.kind == "bad_request" and e.status == 404)
        )
        if failoverable:
            current = getattr(p, "cfg", None)
            for cfg in provider_mod.failover_configs(
                    exclude_key=current.key if current else None):
                try:
                    result = await _call(provider_mod.OpenAIProvider(cfg))
                    handled = True
                    msg = (f"⚠ {e.kind} on {(current.label if current else '?')} → "
                           f"failed over to {cfg.label} ({cfg.model})")
                    db.log_activity(msg, "warn", project_id)
                    emit("log", {"level": "warn", "text": msg}, project_id)
                    break
                except (ProviderError, asyncio.TimeoutError):
                    continue

        if not handled:
            # every provider failed → clear, actionable error (no demo mode)
            set_agent_state(agent_id, "error", e.friendly(), project_id=project_id)
            db.log_activity(f"{agent_id.upper()} error: {e.friendly()}", "error", project_id)
            emit("log", {"level": "error", "text": f"{agent_id.upper()}: {e.friendly()}"}, project_id)
            raise
    except asyncio.TimeoutError:
        _cfg = getattr(p, "cfg", None)
        _budget = int(LOCAL_TIMEOUT if (_cfg and _cfg.key == "ollama") else AGENT_TIMEOUT)
        set_agent_state(agent_id, "error", "Stuck: provider timeout", project_id=project_id)
        db.log_activity(f"{agent_id.upper()} is stuck (timeout)", "error", project_id)
        emit("log", {"level": "error", "text": f"{agent_id.upper()} is stuck: provider timeout"}, project_id)
        raise ProviderError("timeout", f"{agent_id} timed out after {_budget}s")
    except ProviderError as e:
        set_agent_state(agent_id, "error", e.friendly(), project_id=project_id)
        db.log_activity(f"{agent_id.upper()} error: {e.friendly()}", "error", project_id)
        emit("log", {"level": "error", "text": f"{agent_id.upper()}: {e.friendly()}"}, project_id)
        raise

    add_cost(project_id, result.usage)
    agentreg.track_tokens(agent_id, result.usage.tokens_in, result.usage.tokens_out)
    emit("cost", {"cost_usd": _proj_cost(project_id), "tokens_in": _proj_tok(project_id, "in"),
                  "tokens_out": _proj_tok(project_id, "out")}, project_id)
    return result.text


def _proj_cost(pid: str) -> float:
    r = db.one("SELECT cost_usd, tokens_in, tokens_out FROM projects WHERE id=?", (pid,))
    return float(r["cost_usd"]) if r else 0.0


def _proj_tok(pid: str, which: str) -> int:
    r = db.one("SELECT tokens_in, tokens_out FROM projects WHERE id=?", (pid,))
    if not r:
        return 0
    return int(r[f"tokens_{which}"])


def parse_json(text: str) -> dict:
    """Robust JSON extraction (handles code fences and leading prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"model did not return JSON: {text[:200]}")


# --------------------------------------------------------------------------
# brand kit / memory context
# --------------------------------------------------------------------------
def brand_block(project_id: str) -> str:
    row = db.one("SELECT * FROM brand_kit WHERE project_id=?", (project_id,))
    if not row:
        return ""
    d = dict(row)
    parts = [f"Brand name: {d.get('extra') and db.jload(d['extra'], {}).get('name', '') or 'n/a'}"]
    if d.get("colors"):
        parts.append("Colors: " + ", ".join(db.jload(d["colors"], [])))
    if d.get("fonts"):
        parts.append("Fonts: " + ", ".join(db.jload(d["fonts"], [])))
    if d.get("tone"):
        parts.append(f"Tone: {d['tone']}")
    rules = db.jload(d.get("rules"), [])
    if rules:
        parts.append("Rules: " + "; ".join(rules))
    return "\n".join(parts)


def memory_block(project_id: str, agent_id: str) -> str:
    items = db.get_memory("project", project_id, 20) + db.get_memory("agent", agent_id, 10)
    if not items:
        return "(no memory yet)"
    return "\n".join(f"- [{i['kind']}] {i['content']}" for i in items[:25])


# --------------------------------------------------------------------------
# 1) PLAN
# --------------------------------------------------------------------------
async def manager_plan(run: RunControl, brief: str) -> dict:
    pid = run.project_id
    set_agent_state("nora", "thinking", "Analysing brief…", project_id=pid)
    agent_say("nora", "Assign task", pid)

    user = (
        f"ROLE: Manager (Nora)\n"
        f"<<<BRIEF>>>{brief}<<<ENDBRIEF>>>\n"
        f"<<<BRAND_KIT>>>{brand_block(pid)}<<<ENDBRAND_KIT>>>\n"
        f"<<<MEMORY>>>{memory_block(pid, 'nora')}<<<ENDMEMORY>>>\n"
        "Split this brief into tasks. Available agents and ids: "
        + ", ".join(f"{a['id']} ({a['role']})" for a in agentreg.list_agents())
        + ". Independent tasks must be parallelisable (empty depends)."
        "Return JSON with keys summary, questions, tasks[{id,title,description,assignee,depends,acceptance}], risks."
    )
    set_agent_state("nora", "working", "Writing plan", project_id=pid)
    text = await call_llm("nora", agentreg.get_agent("nora")["system_prompt"],  # type: ignore[index]
                          user, pid, marker="plan")
    plan = parse_json(text)
    # validate assignees
    known = {a["id"] for a in agentreg.list_agents()}
    for t in plan.get("tasks", []):
        if t.get("assignee") not in known:
            t["assignee"] = "nora"
    run.plan = plan
    bump_project(pid, status="awaiting_approval")
    db.add_memory("project", pid, f"Plan: {plan.get('summary','')}", "decision")
    emit("plan_ready", {"plan": plan}, pid)
    db.log_activity(f"Manager produced plan with {len(plan.get('tasks',[]))} tasks", "info", pid)
    emit("log", {"level": "info", "text": f"NORA: plan ready — {len(plan.get('tasks',[]))} tasks. Awaiting your approval."}, pid)
    return plan


# --------------------------------------------------------------------------
# 2) TASK EXECUTION
# --------------------------------------------------------------------------
def _task_acceptance(task: dict) -> str:
    acc = task.get("acceptance") or []
    return "\n".join(f"- {a}" for a in acc) if acc else "- meets brief"


async def execute_task(run: RunControl, task: dict) -> None:
    pid = run.project_id
    tid = task["id"]
    assignee = task["assignee"]
    try:
        # wait while paused / stopped
        while not run.pause.is_set():
            if run.stop.is_set():
                return
            await asyncio.sleep(0.2)
        if run.stop.is_set():
            return

        db.execute("UPDATE tasks SET status='progress', updated_at=? WHERE id=?", (db.now(), tid))
        emit("task", _task_row(tid), pid)

        agent = agentreg.get_agent(assignee)
        if not agent:
            raise ProviderError("bad_request", f"unknown agent {assignee}")

        set_agent_state(assignee, "working", task["title"], task["title"], pid)
        agent_say(assignee, _bubble_for(task), pid)

        # dependency check message (visible delegation)
        deps = db.jload(task.get("depends"), []) if isinstance(task, dict) else []
        # (depends stored on row; task dict from plan may have it too)

        context = (
            f"ROLE: {agent['name']} — {agent['role']}\n"
            f"<<<BRIEF>>>{db.one('SELECT brief FROM projects WHERE id=?', (pid,))['brief']}<<<ENDBRIEF>>>\n"
            f"<<<BRAND_KIT>>>{brand_block(pid)}<<<ENDBRAND_KIT>>>\n"
            f"<<<MEMORY>>>{memory_block(pid, assignee)}<<<ENDMEMORY>>>\n"
            f"TASK: {task['title']}\nDESCRIPTION: {task['description']}\n"
            f"ACCEPTANCE:\n{_task_acceptance(task)}\n"
            "Deliver JSON output for this task plus a short human-readable summary field."
        )
        last_output: Optional[dict] = None
        qa_notes: list = []

        for round_no in range(1, MAX_REVISIONS + 1):
            if run.stop.is_set():
                return
            while not run.pause.is_set():
                if run.stop.is_set():
                    return
                await asyncio.sleep(0.2)

            if last_output is None:
                system = agent["system_prompt"]
                if round_no > 1:
                    issues = qa_notes[-1].get("issues", [])
                    system += "\n\nQA REJECTED your previous output. Fix EXACTLY these issues:\n" + \
                              "\n".join(f"- {i}" for i in issues)
                set_agent_state(assignee, "working", f"{task['title']} (round {round_no})", task["title"], pid)
                text = await call_llm(assignee, system, context, pid,
                                      marker=_marker_for(task))
                try:
                    output = parse_json(text)
                except Exception:
                    output = {"summary": text, "raw": text}
            else:
                # revision round
                issues = qa_notes[-1].get("issues", [])
                set_agent_state(assignee, "working", f"Fixing QA notes (round {round_no})", task["title"], pid)
                agent_say(assignee, f"Fixing QA notes ({round_no}/{MAX_REVISIONS})", pid)
                revise_ctx = context + "\n\nPREVIOUS OUTPUT:\n" + json.dumps(last_output, ensure_ascii=False)[:6000] + \
                    "\n\nQA ISSUES TO FIX:\n" + "\n".join(f"- {i}" for i in issues)
                text = await call_llm(assignee, agent["system_prompt"], revise_ctx, pid,
                                      marker=_marker_for(task))
                try:
                    output = parse_json(text)
                except Exception:
                    output = {"summary": text, "raw": text}

            # ---- QA gate
            set_agent_state("rami", "reviewing", f"Reviewing: {task['title']}", task["title"], pid)
            agent_say("rami", "Reviewing…", pid)
            qa = await qa_review(task, output, pid)
            qa_notes.append(qa)
            db.execute("UPDATE tasks SET output=?, qa_notes=?, revision=?, updated_at=? WHERE id=?",
                       (db.jdump(output), db.jdump(qa_notes), round_no, db.now(), tid))
            last_output = output

            if qa.get("approved"):
                break
            # rejection path — visible in office
            agent_say("rami", f"REJECTED: {qa.get('issues',[''])[0][:60]}", pid, to_agent=assignee)
            set_agent_state(assignee, "error", "Rejected by QA — fixing", task["title"], pid)
            emit("log", {"level": "warn",
                         "text": f"RAMI rejected {task['title']} (round {round_no}): " +
                                 "; ".join(qa.get("issues", []))[:160]}, pid)
            db.log_activity(f"QA rejected {task['title']} (round {round_no})", "warn", pid)
            db.execute("UPDATE tasks SET status='rejected', updated_at=? WHERE id=?", (db.now(), tid))
            emit("task", _task_row(tid), pid)
            agentreg.add_xp(assignee, 5)  # learning from rejection
        else:
            # 3 rounds exhausted → escalate to Boss with a clear question
            await escalate(run, task, qa_notes)
            return

        # ---- success
        db.execute("UPDATE tasks SET status='done', updated_at=? WHERE id=?", (db.now(), tid))
        deliverable = _save_deliverable(pid, tid, task, last_output or {})
        set_agent_state(assignee, "done", "Done ✓", task["title"], pid)
        emit("agent_state", {"agent_id": assignee, "state": "done",
                             "message": "Done ✓", "task": task["title"]}, pid)
        emit("confetti", {"agent_id": assignee}, pid)
        emit("task", _task_row(tid), pid)
        emit("deliverable", {"task_id": tid, "title": task["title"],
                             "kind": deliverable["kind"]}, pid)
        db.log_activity(f"{task['title']} done by {agent['name']} ✓", "success", pid)
        emit("log", {"level": "success", "text": f"{task['title']} ✓ done by {agent['name']}"}, pid)
        xp = 30 if assignee != "pixel" else 20
        info = agentreg.add_xp(assignee, xp)
        if info.get("leveled"):
            emit("level_up", info, pid)
            db.log_activity(f"{agent['name']} reached level {info['level']}!", "success", pid)
        if info.get("promoted"):
            emit("promotion", info, pid)
            db.log_activity(f"🎉 PIXEL promoted to {info['role']}!", "success", pid)
            agent_say("nora", "PIXEL promoted! 🎉", pid)
        agentreg.add_xp("rami", 10)
        progress_update(pid)

    except asyncio.CancelledError:
        db.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE id=?", (db.now(), tid))
        emit("task", _task_row(tid), pid)
        raise
    except ProviderError as e:
        db.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE id=?", (db.now(), tid))
        emit("task", _task_row(tid), pid)
        emit("agent_stuck", {"agent_id": assignee, "task": task["title"],
                             "message": e.friendly()}, pid)
        db.log_activity(f"{task['title']} blocked: {e.friendly()}", "error", pid)
        agentreg.add_xp(assignee, 0)
    except Exception as e:  # unexpected — keep the office alive
        db.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE id=?", (db.now(), tid))
        emit("task", _task_row(tid), pid)
        emit("log", {"level": "error", "text": f"{task['title']} crashed: {e}"}, pid)
        traceback.print_exc()


async def qa_review(task: dict, output: dict, project_id: str) -> dict:
    user = (
        f"ROLE: QA (Rami)\n"
        f"<<<BRIEF>>>{db.one('SELECT brief FROM projects WHERE id=?', (project_id,))['brief']}<<<ENDBRIEF>>>\n"
        f"<<<BRAND_KIT>>>{brand_block(project_id)}<<<ENDBRAND_KIT>>>\n"
        f"TASK: {task['title']}\nACCEPTANCE:\n{_task_acceptance(task)}\n"
        f"OUTPUT TO REVIEW:\n{json.dumps(output, ensure_ascii=False)[:8000]}\n"
        'Return JSON {"approved": bool, "issues": [str], "score": int, "notes": str}.'
    )
    # extra hard rule: outputs must not contain TODO/placeholder
    text = await call_llm("rami", agentreg.get_agent("rami")["system_prompt"],  # type: ignore[index]
                          user, project_id, marker="qa")
    try:
        qa = parse_json(text)
    except Exception:
        qa = {"approved": False, "issues": ["QA response was not valid JSON"], "score": 0, "notes": ""}
    # deterministic safety net (works even if model is sloppy)
    blob = json.dumps(output, ensure_ascii=False)
    hard = []
    if re.search(r"\bTODO\b|\bTBD\b|\bplaceholder text\b", blob, re.I):
        hard.append("Contains TODO/TBD/placeholder markers.")
    if len(blob) < 40:
        hard.append("Output is empty.")
    if hard:
        qa["approved"] = False
        qa["issues"] = list(qa.get("issues", [])) + hard
    return qa


async def escalate(run: RunControl, task: dict, qa_notes: list) -> None:
    pid = run.project_id
    last = qa_notes[-1] if qa_notes else {"issues": ["unknown"]}
    question = (f"I could not get \"{task['title']}\" past QA after {MAX_REVISIONS} rounds. "
                f"Outstanding issues: {'; '.join(last.get('issues', []))[:300]} "
                f"How would you like to proceed?")
    set_agent_state("nora", "error", "Need clarification", project_id=pid)
    agent_say("nora", "Need clarification", pid)
    db.add_message(question, channel="agent", project_id=pid, agent_id="nora")
    emit("escalation", {"task_id": task["id"], "question": question}, pid)
    db.log_activity(f"ESCALATION to Boss: {question[:120]}", "warn", pid)
    emit("log", {"level": "warn", "text": f"NORA escalated: {question[:140]}"}, pid)
    db.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE id=?", (db.now(), task["id"]))
    emit("task", _task_row(task["id"]), pid)
    # Serverless requests cannot wait for a human. The persisted cloud job
    # remains blocked and the next Boss message supplies guidance/resumes it.
    if os.getenv('VERCEL') == '1':
        return
    # wait for boss reply (max 10 min, then mark blocked)
    try:
        reply = await asyncio.wait_for(run.boss_replies.get(), timeout=600)
    except asyncio.TimeoutError:
        return
    db.add_message(f"Boss → Nora: {reply}", channel="boss", project_id=pid)
    set_agent_state("nora", "working", "Applying your guidance", project_id=pid)
    # one more attempt with the boss guidance folded in
    agent = agentreg.get_agent(task["assignee"])
    if not agent:
        return
    ctx = (f"ROLE: {agent['name']} — {agent['role']}\n"
           f"TASK: {task['title']}\nDESCRIPTION: {task['description']}\n"
           f"BOSS GUIDANCE: {reply}\n"
           "Deliver the corrected JSON output.")
    try:
        text = await call_llm(task["assignee"], agent["system_prompt"], ctx, pid,
                              marker=_marker_for(task))
        output = parse_json(text)
        db.execute("UPDATE tasks SET status='done', output=?, updated_at=? WHERE id=?",
                   (db.jdump(output), db.now(), task["id"]))
        _save_deliverable(pid, task["id"], task, output)
        set_agent_state(task["assignee"], "done", "Done ✓", task["title"], pid)
        emit("confetti", {"agent_id": task["assignee"]}, pid)
        emit("task", _task_row(task["id"]), pid)
        db.log_activity(f"{task['title']} delivered after escalation ✓", "success", pid)
        progress_update(pid)
    except Exception as e:
        db.log_activity(f"Escalated task still failing: {e}", "error", pid)


def _bubble_for(task: dict) -> str:
    mapping = {"nora": "Assign task", "karim": "Execute code", "lina": "Design…",
               "sami": "Writing copy", "yara": "Search keywords", "adam": "Building ads",
               "mona": "Planning posts", "zed": "Generate image", "rami": "Approved ✓" }
    t = (task.get("title", "") + " " + task.get("description", "")).lower()
    if "image" in t or "visual" in t:
        return "Generate image"
    if "code" in t or "page" in t or "landing" in t or "bug" in t:
        return "Execute code"
    if "keyword" in t or "seo" in t or "meta" in t:
        return "Search web"
    if "caption" in t or "copy" in t or "slogan" in t or "email" in t:
        return "Writing copy"
    if "calendar" in t or "reel" in t or "post" in t:
        return "Planning posts"
    if "campaign" in t or "ad " in t or "ads" in t:
        return "Building ads"
    if "review" in t or "qa" in t:
        return "Reviewing"
    return mapping.get(task.get("assignee", ""), "Working…")


def _marker_for(task: dict) -> str:
    t = (task.get("title", "") + " " + task.get("description", "")).lower()
    if "image" in t and "campaign" not in t:
        return "images"
    if "campaign" in t or ("ad " in t and "calendar" not in t):
        return "campaign"
    if "calendar" in t:
        return "calendar"
    if "review" in t or "qa" in t:
        return "qa"
    return ""


def _save_deliverable(pid: str, tid: str, task: dict, output: dict) -> dict:
    kind = _marker_for(task) or ("package" if "deliver" in task.get("title", "").lower() else "copy")
    if isinstance(output, dict):
        if "campaign" in output:
            kind = "campaign"
        elif "days" in output:
            kind = "calendar"
        elif "files" in output:
            kind = "code"
        elif "image_prompts" in output or "design_direction" in output:
            kind = "design"
        elif "keywords" in output:
            kind = "seo"
        # attach compliance reports so the Preview screen always has them
        try:
            if kind == "campaign" and "compliance_report" not in output and "variants" in output:
                from . import compliance
                output["compliance_report"] = compliance.check_campaign(output)
            if kind == "calendar" and "compliance_report" not in output and "days" in output:
                from . import compliance
                output["compliance_report"] = compliance.check_calendar(output.get("days", []))
        except Exception:
            pass
    existing = db.one(
        "SELECT id, version FROM deliverables WHERE project_id=? AND task_id=? ORDER BY updated_at DESC LIMIT 1",
        (pid, tid))
    title = task.get("title", "Deliverable")
    if existing:
        new_ver = existing["version"] + 1
        db.execute(
            "UPDATE deliverables SET data=?, version=?, status='pending', updated_at=? WHERE id=?",
            (db.jdump(output), new_ver, db.now(), existing["id"]))
        db.execute(
            "INSERT INTO deliverable_versions (deliverable_id, version, data, note, created_at) VALUES (?,?,?,?,?)",
            (existing["id"], new_ver, db.jdump(output), "revision", db.now()))
        did = existing["id"]
    else:
        did = db.new_id("dlv")
        db.execute(
            """INSERT INTO deliverables (id, project_id, task_id, kind, title, data, version, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,1,'pending',?,?)""",
            (did, pid, tid, kind, title, db.jdump(output), db.now(), db.now()))
        db.execute(
            "INSERT INTO deliverable_versions (deliverable_id, version, data, note, created_at) VALUES (?,?,?,?,?)",
            (did, 1, db.jdump(output), "initial", db.now()))
    return {"id": did, "kind": kind, "title": title}


def _load_version_data(did: str) -> str:
    r = db.one("SELECT data FROM deliverables WHERE id=?", (did,))
    return r["data"] if r else "{}"


def _task_row(tid: str) -> dict:
    r = db.one("SELECT * FROM tasks WHERE id=?", (tid,))
    d = dict(r) if r else {"id": tid}
    d["depends"] = db.jload(d.get("depends"), [])
    d["acceptance"] = db.jload(d.get("acceptance"), [])
    d["qa_notes"] = db.jload(d.get("qa_notes"), [])
    return d


# --------------------------------------------------------------------------
# 3) FULL RUN
# --------------------------------------------------------------------------
async def run_project(project_id: str, brief: str) -> None:
    """Main pipeline invoked by the chat endpoint (in a background task)."""
    run = RunControl(project_id=project_id)
    RUNS[project_id] = run
    pid = project_id
    try:
        bump_project(pid, status="planning", brief=brief)
        emit("log", {"level": "info", "text": "NORA received the brief — analysing…"}, pid)
        db.log_activity("Project started", "info", pid)

        # --- plan
        plan = await manager_plan(run, brief)

        # --- plan approval gate (unless auto-approve is on)
        auto = db.kv_get("auto_approve", "0") == "1"
        if not auto:
            emit("approval_required", {"kind": "plan", "plan": plan}, pid)
            try:
                await asyncio.wait_for(run.approval.wait(), timeout=1800)
            except asyncio.TimeoutError:
                bump_project(pid, status="error")
                emit("log", {"level": "error", "text": "Plan approval timed out (30 min)."}, pid)
                return
            if run.stop.is_set():
                bump_project(pid, status="stopped")
                return
        else:
            emit("log", {"level": "info", "text": "Auto-approve ON — plan approved automatically."}, pid)

        run.approved_plan = True
        bump_project(pid, status="running")
        agent_say("nora", "Plan approved — delegating", pid)

        # --- create task rows
        task_rows = []
        for t in plan.get("tasks", []):
            tid = db.new_id("task")
            # keep planner id mapping so depends resolve
            t["_row_id"] = tid
            db.execute(
                """INSERT INTO tasks (id, project_id, title, description, assignee, status,
                   depends, acceptance, created_at, updated_at) VALUES (?,?,?,?,?,'todo',?,?,?,?)""",
                (tid, pid, t.get("title", "Task"), t.get("description", ""),
                 t.get("assignee", "nora"), db.jdump(t.get("depends", [])),
                 db.jdump(t.get("acceptance", [])), db.now(), db.now()))
            task_rows.append((t, tid))
            emit("task", _task_row(tid), pid)

        # map planner ids → row ids
        id_map = {t.get("id"): tid for t, tid in task_rows}
        for t, tid in task_rows:
            deps = [id_map.get(d, d) for d in (t.get("depends") or [])]
            deps = [d for d in deps if d in id_map.values()]
            db.execute("UPDATE tasks SET depends=? WHERE id=?", (db.jdump(deps), tid))
            t["depends"] = deps

        # --- schedule waves respecting dependencies (parallel inside a wave)
        remaining = list(task_rows)
        launched: dict[str, asyncio.Task] = {}
        completed: set[str] = set()
        while remaining and not run.stop.is_set():
            ready = [(t, tid) for t, tid in remaining
                     if all(d in completed for d in (t.get("depends") or []))]
            if not ready:
                # dependency deadlock safety
                ready = remaining[:1]
            coros = []
            for t, tid in ready:
                t2 = dict(t)
                t2["id"] = tid
                coros.append(execute_task(run, t2))
                remaining.remove((t, tid))
            # wait for this wave (parallel)
            results = await asyncio.gather(*coros, return_exceptions=True)
            for (t, tid), res in zip(ready, results):
                completed.add(tid)
                if isinstance(res, Exception) and not isinstance(res, asyncio.CancelledError):
                    emit("log", {"level": "error", "text": f"Task {t.get('title')} error: {res}"}, pid)

        if run.stop.is_set():
            bump_project(pid, status="stopped")
            emit("log", {"level": "warn", "text": "Project stopped by Boss."}, pid)
            return

        # --- manager final check
        set_agent_state("nora", "reviewing", "Final check…", project_id=pid)
        agent_say("nora", "Final check", pid)
        deliverables = [dict(r) for r in db.query(
            "SELECT * FROM deliverables WHERE project_id=? ORDER BY created_at", (pid,))]
        for d in deliverables:
            d["data"] = db.jload(d["data"], {})
        package = {
            "summary": plan.get("summary", ""),
            "tasks_total": len(task_rows),
            "tasks_done": sum(1 for _, tid in task_rows
                              if (db.one("SELECT status FROM tasks WHERE id=?", (tid,)) or {"status": ""})["status"] == "done"),
            "deliverables": [{"id": d["id"], "kind": d["kind"], "title": d["title"],
                              "version": d["version"]} for d in deliverables],
            "notes": "All outputs passed QA. Facts and prices come strictly from the brief.",
        }
        pkg_row = db.one("SELECT id FROM deliverables WHERE project_id=? AND kind='package'", (pid,))
        if not pkg_row:
            db.execute(
                """INSERT INTO deliverables (id, project_id, task_id, kind, title, data, version, status, created_at, updated_at)
                   VALUES (?,?,NULL,'package',?,?,1,'pending',?,?)""",
                (db.new_id("dlv"), pid, "Final delivery package", db.jdump(package), db.now(), db.now()))
        bump_project(pid, status="review")
        emit("log", {"level": "info", "text": "NORA: final package ready for your approval."}, pid)

        # --- deliverable approval gate
        auto = db.kv_get("auto_approve", "0") == "1"
        if not auto:
            emit("approval_required", {"kind": "deliverable", "package": package}, pid)
            try:
                await asyncio.wait_for(run.deliverable_approval.wait(), timeout=1800)
            except asyncio.TimeoutError:
                emit("log", {"level": "warn", "text": "Delivery approval timed out — package kept as pending."}, pid)
                return
        if run.stop.is_set():
            bump_project(pid, status="stopped")
            return

        db.execute("UPDATE deliverables SET status='approved' WHERE project_id=?", (pid,))
        bump_project(pid, status="delivered", progress=100.0)
        set_agent_state("nora", "done", "Delivered ✓", project_id=pid)
        agent_say("nora", "Delivered ✓", pid)
        emit("confetti", {"agent_id": "nora"}, pid)
        emit("delivered", {"package": package}, pid)
        db.log_activity("📦 Package delivered to the Boss", "success", pid)
        emit("log", {"level": "success", "text": "📦 Package delivered — open Preview to review."}, pid)
        # persist final memory
        db.add_memory("project", pid, f"Delivered: {package['summary']}", "decision")

    except ProviderError as e:
        bump_project(pid, status="error")
        emit("log", {"level": "error", "text": f"Project error: {e.friendly()}"}, pid)
        db.log_activity(f"Project error: {e.friendly()}", "error", pid)
    except Exception as e:
        bump_project(pid, status="error")
        emit("log", {"level": "error", "text": f"Project crashed: {e}"}, pid)
        db.log_activity(f"Project crashed: {e}", "error", pid)
        traceback.print_exc()
    finally:
        # gentle idle reset
        for a in agentreg.list_agents():
            if a["status"] not in ("idle", "offline"):
                set_agent_state(a["id"], "idle", "", project_id=pid)
        RUNS.pop(pid, None)


# --------------------------------------------------------------------------
# controls
# --------------------------------------------------------------------------
def pause_run(pid: str) -> bool:
    run = RUNS.get(pid)
    if not run:
        return False
    run.pause.clear()
    emit("control", {"action": "pause"}, pid)
    db.log_activity("Boss paused the project", "warn", pid)
    agent_say("nora", "Paused — awaiting resume", pid)
    return True


def resume_run(pid: str) -> bool:
    run = RUNS.get(pid)
    if not run:
        return False
    run.pause.set()
    emit("control", {"action": "resume"}, pid)
    db.log_activity("Boss resumed the project", "info", pid)
    agent_say("nora", "Resuming work", pid)
    return True


def stop_run(pid: str) -> bool:
    run = RUNS.get(pid)
    if not run:
        # mark project stopped anyway
        bump_project(pid, status="stopped")
        return False
    run.stop.set()
    run.pause.set()  # unblock waiters so they can exit
    for t in run.tasks.values():
        t.cancel()
    emit("control", {"action": "stop"}, pid)
    db.log_activity("Boss stopped the project", "warn", pid)
    return True


def approve_plan(pid: str, approved: bool, comment: str = "") -> bool:
    run = RUNS.get(pid)
    if not run:
        return False
    if approved:
        db.add_message(f"Boss approved the plan. {comment}".strip(), channel="boss", project_id=pid)
        run.approval.set()
        emit("log", {"level": "success", "text": "Plan approved by Boss ✓"}, pid)
        agent_say("nora", "Approved — let's go!", pid)
    else:
        db.add_message(f"Boss rejected the plan: {comment}", channel="boss", project_id=pid)
        emit("log", {"level": "warn", "text": f"Plan rejected: {comment}"}, pid)
        # simple revision: re-plan with feedback appended to brief
        run.approval.clear()
        proj = db.one("SELECT brief FROM projects WHERE id=?", (pid,))
        if proj:
            new_brief = proj["brief"] + f"\n\n[MANAGER NOTE — plan was rejected, fix this:] {comment}"
            db.execute("UPDATE projects SET brief=? WHERE id=?", (new_brief, pid))
    return True


def approve_deliverable(pid: str, approved: bool, comment: str = "") -> bool:
    run = RUNS.get(pid)
    if not run:
        # allow approving stored deliverables even if run finished
        if approved:
            db.execute("UPDATE deliverables SET status='approved' WHERE project_id=?", (pid,))
            bump_project(pid, status="delivered")
            emit("log", {"level": "success", "text": "Deliverable approved ✓"}, pid)
            return True
        return False
    db.add_message(f"Boss {'approved' if approved else 'rejected'} deliverable. {comment}".strip(),
                   channel="boss", project_id=pid)
    if approved:
        run.deliverable_approval.set()
        emit("log", {"level": "success", "text": "Deliverable approved by Boss ✓"}, pid)
    else:
        emit("log", {"level": "warn", "text": f"Deliverable rejected: {comment}"}, pid)
        run.deliverable_approval.set()  # proceed; tasks stay for rework via chat
    return True


def push_boss_reply(pid: str, text: str) -> None:
    run = RUNS.get(pid)
    if run:
        run.boss_replies.put_nowait(text)


# --------------------------------------------------------------------------
# Meeting room — roundtable brainstorm
# --------------------------------------------------------------------------
async def run_meeting(project_id: str, topic: str) -> dict:
    pid = project_id
    participants = [a for a in agentreg.list_agents() if a["id"] != "nora"]
    emit("meeting_start", {"topic": topic, "participants": [p["id"] for p in participants]}, pid)
    agent_say("nora", f"Meeting: {topic}", pid)
    db.log_activity(f"Roundtable meeting: {topic}", "info", pid)

    user = (f"ROLE: Manager facilitating a brainstorm\nTOPIC: {topic}\n"
            f"<<<BRIEF>>>{(db.one('SELECT brief FROM projects WHERE id=?', (pid,)) or {'brief': ''})['brief']}<<<ENDBRIEF>>>\n"
            "Each participant gives ONE short idea. Return JSON {\"ideas\": [{\"agent\": id, \"idea\": str}]} covering: "
            + ", ".join(p["id"] for p in participants))
    try:
        text = await call_llm("nora", agentreg.get_agent("nora")["system_prompt"],  # type: ignore[index]
                              user, pid, marker="meeting")
        ideas = parse_json(text).get("ideas", [])
    except Exception:
        ideas = []

    recorded = []
    for idea in ideas:
        aid = idea.get("agent")
        if not agentreg.get_agent(aid):
            continue
        set_agent_state(aid, "working", "Brainstorming…", project_id=pid)
        agent_say(aid, str(idea.get("idea", ""))[:80], pid)
        recorded.append({"agent": aid, "idea": idea.get("idea", "")})
        await asyncio.sleep(0.6)
        set_agent_state(aid, "idle", "", project_id=pid)

    best = max(recorded, key=lambda x: len(x["idea"]))["idea"] if recorded else ""
    mid = db.new_id("mtg")
    db.execute("INSERT INTO meetings (id, project_id, topic, ideas, best, created_at) VALUES (?,?,?,?,?,?)",
               (mid, pid, topic, db.jdump(recorded), best, db.now()))
    db.add_memory("project", pid, f"Meeting '{topic}' best idea: {best}", "decision")
    emit("meeting_end", {"id": mid, "topic": topic, "ideas": recorded, "best": best}, pid)
    set_agent_state("nora", "idle", "", project_id=pid)
    return {"id": mid, "topic": topic, "ideas": recorded, "best": best}


# --------------------------------------------------------------------------
# Daily stand-up report from the Manager
# --------------------------------------------------------------------------
async def run_standup(project_id: str) -> dict:
    pid = project_id
    logs = [r["text"] for r in db.query(
        "SELECT text FROM activity WHERE project_id=? ORDER BY created_at DESC LIMIT 30", (pid,))]
    tasks = [dict(r) for r in db.query("SELECT title, status, assignee FROM tasks WHERE project_id=?", (pid,))]
    user = (f"ROLE: Manager daily stand-up\nACTIVITY LOG (newest first):\n" + "\n".join(logs) +
            "\nTASKS:\n" + json.dumps(tasks, ensure_ascii=False) +
            '\nReturn JSON {"done": [str], "blockers": [str], "next": [str]}')
    try:
        text = await call_llm("nora", agentreg.get_agent("nora")["system_prompt"],  # type: ignore[index]
                              user, pid, marker="standup")
        data = parse_json(text)
    except Exception:
        data = {"done": [l for l in logs[:5]], "blockers": [], "next": []}
    content = ("STAND-UP — " + time.strftime("%Y-%m-%d %H:%M") + "\n\n"
               + "✅ Done:\n" + "\n".join(f"• {x}" for x in data.get("done", []))
               + "\n\n🚧 Blockers:\n" + ("\n".join(f"• {x}" for x in data.get("blockers", [])) or "• none")
               + "\n\n➡️ Next:\n" + "\n".join(f"• {x}" for x in data.get("next", [])))
    sid = db.new_id("su")
    db.execute("INSERT INTO standups (id, project_id, content, created_at) VALUES (?,?,?,?)",
               (sid, pid, content, db.now()))
    agent_say("nora", "Stand-up ready", pid)
    emit("standup", {"id": sid, "content": content}, pid)
    return {"id": sid, "content": content}
