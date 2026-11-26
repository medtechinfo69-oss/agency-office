"""Auto-scheduling: recurring content jobs (weekly posts, monthly reports…).

A lightweight asyncio loop checks `schedules` every minute and launches due
jobs in the background (reusing the orchestration pipeline for project jobs).
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from . import db
from .events import bus

_tick_task: Optional[asyncio.Task] = None


def seed_defaults(project_id: str) -> None:
    if db.one("SELECT id FROM schedules LIMIT 1"):
        return
    now = db.now()
    db.execute(
        "INSERT INTO schedules (id, name, kind, project_id, interval_hours, enabled, payload, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (db.new_id("sch"), "Weekly social posts", "weekly_posts", project_id, 168.0, 0,
         json.dumps({"template": "weekly"}), now))
    db.execute(
        "INSERT INTO schedules (id, name, kind, project_id, interval_hours, enabled, payload, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (db.new_id("sch"), "Monthly performance report", "monthly_report", project_id, 720.0, 0,
         json.dumps({}), now))


async def tick() -> None:
    rows = db.query("SELECT * FROM schedules WHERE enabled=1")
    for r in rows:
        last = r["last_run"] or 0
        due = (time.time() - last) >= r["interval_hours"] * 3600
        if not due:
            continue
        db.execute("UPDATE schedules SET last_run=? WHERE id=?", (time.time(), r["id"]))
        _launch(r)


def _launch(row) -> None:
    kind = row["kind"]
    pid = row["project_id"]
    name = row["name"]
    db.log_activity(f"Scheduled job fired: {name}", "info", pid)
    bus.publish_sync("log", {"level": "info", "text": f"⏰ Scheduled job: {name}"}, pid)
    if kind == "weekly_posts":
        # generate a fresh batch of post ideas via the manager pipeline
        from . import orchestration as orch
        brief = (db.one("SELECT brief FROM projects WHERE id=?", (pid,) or [None]) or {"brief": ""})["brief"] \
            if pid else ""
        if not pid:
            return
        db.execute(
            "INSERT INTO messages (id, project_id, channel, text, created_at) VALUES (?,?,?,?,?)",
            (db.new_id("msg"), pid, "system",
             f"⏰ Auto-schedule: {name} — please prepare next week's posts.", time.time()))
        bus.publish_sync("log", {"level": "info",
                                 "text": f"⏰ {name}: Nora is preparing the next batch…"}, pid)
        asyncio.get_running_loop().create_task(_run_manager_job(pid, name))
    elif kind == "monthly_report":
        asyncio.get_running_loop().create_task(_run_manager_job(pid, name))


async def _run_manager_job(pid: str, name: str) -> None:
    from . import orchestration as orch
    from . import agents as agentreg
    try:
        proj = db.one("SELECT brief FROM projects WHERE id=?", (pid,))
        user = (f"SCHEDULED JOB: {name}\nBRIEF: {proj['brief'] if proj else ''}\n"
                "Prepare the next batch of content tasks as a short plan "
                '(JSON {"summary": str, "tasks": [...]}) with assignees.')
        text = await orch.call_llm("nora", agentreg.get_agent("nora")["system_prompt"],  # type: ignore[index]
                                   user, pid, marker="plan")
        plan = orch.parse_json(text)
        db.add_memory("project", pid, f"Scheduled '{name}': {plan.get('summary','')}", "note")
        bus.publish_sync("schedule_done", {"name": name, "summary": plan.get("summary", "")}, pid)
        bus.publish_sync("log", {"level": "success", "text": f"✅ {name} completed"}, pid)
    except Exception as e:
        bus.publish_sync("log", {"level": "error", "text": f"⏰ {name} failed: {e}"}, pid)


async def start() -> None:
    global _tick_task
    if _tick_task is None:
        async def loop() -> None:
            while True:
                await asyncio.sleep(60)
                try:
                    await tick()
                except Exception:
                    pass
        _tick_task = asyncio.create_task(loop())


async def stop() -> None:
    global _tick_task
    if _tick_task:
        _tick_task.cancel()
        _tick_task = None
