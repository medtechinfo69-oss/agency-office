"""Tests for orchestration logic: JSON parsing, plan validation, QA gates,
compliance checker, deliverable versioning, and the demo provider.

These tests run fully offline (demo provider).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import compliance, db  # noqa: E402
from app.orchestration import parse_json, MAX_REVISIONS, RunControl, _save_deliverable  # noqa: E402
from app.provider import DemoProvider, ProviderError  # noqa: E402
from app import agents as agentreg  # noqa: E402


# --------------------------------------------------------------- JSON parsing
def test_parse_json_plain():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_prose():
    assert parse_json('Here you go:\n{"tasks": [1,2]}\nHope that helps') == {"tasks": [1, 2]}


def test_parse_json_invalid_raises():
    with pytest.raises(ValueError):
        parse_json("no json here at all")


# --------------------------------------------------------------- demo provider
@pytest.mark.asyncio
async def test_demo_provider_plan_is_structured():
    p = DemoProvider()
    res = await p.chat([
        {"role": "system", "content": "[TASK:plan]\nROLE: Manager (Nora)\n<<<BRIEF>>>launch an insurance campaign<<<ENDBRIEF>>>"},
        {"role": "user", "content": "plan"},
    ], json_mode=True)
    plan = json.loads(res.text)
    assert "tasks" in plan and len(plan["tasks"]) >= 5
    for t in plan["tasks"]:
        assert {"id", "title", "description", "assignee", "depends", "acceptance"} <= set(t)


@pytest.mark.asyncio
async def test_demo_provider_never_invents_prices():
    """Demo outputs may only echo facts present in the brief."""
    p = DemoProvider()
    brief = "We sell insurance. No prices given at all."
    res = await p.chat([
        {"role": "system", "content": f"[TASK:plan]\n<<<BRIEF>>>{brief}<<<ENDBRIEF>>>"},
        {"role": "user", "content": "x"},
    ], json_mode=True)
    plan = json.loads(res.text)
    blob = json.dumps(plan)
    # no currency amounts may appear
    import re
    assert not re.search(r"[$€]\s?\d|\d+\s?(?:TND|USD|EUR)", blob)


@pytest.mark.asyncio
async def test_demo_provider_qa_rejects_placeholders():
    p = DemoProvider()
    res = await p.chat([
        {"role": "system", "content": "[TASK:qa]\nROLE: QA"},
        {"role": "user", "content": 'OUTPUT: {"summary": "TODO finish this"}'},
    ], json_mode=True)
    qa = json.loads(res.text)
    assert qa["approved"] is False
    assert qa["issues"]


# --------------------------------------------------------------- QA / revisions
def test_max_revisions_constant():
    assert MAX_REVISIONS == 3


# --------------------------------------------------------------- deliverables
def test_save_deliverable_and_versioning(tmp_path, monkeypatch):
    # isolate DB
    os.environ["DB_PATH"] = str(tmp_path / "t.db")
    from app.config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    import app.db as dbmod
    dbmod._conn = None
    dbmod.get_conn()
    agentreg.seed_agents()

    pid = db.new_id("prj")
    db.execute(
        "INSERT INTO projects (id, name, brief, status, created_at, updated_at) VALUES (?,?,?,'running',?,?)",
        (pid, "T", "brief", db.now(), db.now()))
    task = {"title": "Slogans", "description": "d", "acceptance": ["a"]}
    tid = db.new_id("task")
    db.execute(
        "INSERT INTO tasks (id, project_id, title, description, assignee, status, created_at, updated_at) "
        "VALUES (?,?,?,?,'sami','progress',?,?)",
        (tid, pid, "Slogans", "d", db.now(), db.now()))

    d1 = _save_deliverable(pid, tid, task, {"summary": "v1"})
    row = db.one("SELECT version FROM deliverables WHERE id=?", (d1["id"],))
    assert row["version"] == 1

    d2 = _save_deliverable(pid, tid, task, {"summary": "v2"})
    assert d2["id"] == d1["id"]
    row = db.one("SELECT version FROM deliverables WHERE id=?", (d1["id"],))
    assert row["version"] == 2

    versions = db.query("SELECT version FROM deliverable_versions WHERE deliverable_id=? ORDER BY version",
                        (d1["id"],))
    assert [v["version"] for v in versions] == [1, 2]


# --------------------------------------------------------------- RunControl
def test_runcontrol_defaults():
    r = RunControl(project_id="x")
    assert r.pause.is_set()          # running
    assert not r.stop.is_set()
    assert not r.approval.is_set()
    assert not r.approved_plan


# --------------------------------------------------------------- compliance
def test_compliance_flags_guaranteed():
    issues = compliance.check_text("Get guaranteed savings today!")
    assert any(i["severity"] == "high" for i in issues)


def test_compliance_headline_length():
    issues = compliance.check_text("x" * 60, context="headline")
    assert any("truncates" in i["message"] for i in issues)


def test_compliance_clean_text_passes():
    issues = compliance.check_text(
        "Protect what matters. Get a free quote in minutes.")
    assert not any(i["severity"] == "high" for i in issues)


def test_compliance_text_heavy_image():
    issues = compliance.check_image_spec({"note": "55% text overlay on the creative"})
    assert any(i["severity"] == "high" for i in issues)


def test_compliance_campaign_report():
    campaign = {
        "variants": [
            {"label": "A", "headline": "GUARANTEED best insurance in town",
             "primary_text": "We are #1 and 100% risk-free, act now!",
             "cta": "Get Quote", "image_brief": "70% text overlay"},
            {"label": "B", "headline": "Coverage that fits your life",
             "primary_text": "Compare plans side by side in minutes.",
             "cta": "Learn More", "image_brief": "minimal text"},
        ],
        "budget_plan": {"daily": "$50"},
        "claims": [],
    }
    rep = compliance.check_campaign(campaign)
    assert rep["passed"] is False
    assert rep["counts"]["high"] >= 2
    assert any(i["where"].startswith("Variant A") for i in rep["issues"])


# --------------------------------------------------------------- agent registry
def test_all_agents_seeded_with_prompts():
    for a in agentreg.AGENTS:
        assert a["prompt"].strip()
        assert "STRICT RULES" in a["prompt"]
        assert a["skills"]


def test_agent_ids_unique():
    ids = [a["id"] for a in agentreg.AGENTS]
    assert len(ids) == len(set(ids))
    assert {"nora", "rami", "pixel"} <= set(ids)


# --------------------------------------------------------------- XP / leveling
def test_xp_levels_and_intern_promotion(tmp_path, monkeypatch):
    os.environ["DB_PATH"] = str(tmp_path / "xp.db")
    from app.config import settings
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "xp.db"))
    import app.db as dbmod
    dbmod._conn = None
    dbmod.get_conn()
    agentreg.seed_agents()

    info = agentreg.add_xp("pixel", 100)   # 40 + 100 = 140 → level 2
    assert info["level"] == 2
    info = agentreg.add_xp("pixel", 200)   # 340 → level 4 ≥ 3 → promoted
    assert info["promoted"] is True
    a = agentreg.get_agent("pixel")
    assert "promoted" in a["role"]


# --------------------------------------------------------------- provider errors
def test_provider_error_kinds():
    e = ProviderError("rate_limit", "429")
    assert "Rate limited" in e.friendly()
    e2 = ProviderError("auth", "401")
    assert "API_TOKEN" in e2.friendly()
