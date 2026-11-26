"""SQLite persistence: schema, connection helpers, per-project/per-agent memory.

The DB is deliberately simple (stdlib sqlite3) so the app runs 100% locally
with zero external services. A single connection guarded by a lock is enough
for this workload.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterable, Optional

from .config import settings

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  brief TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planning',   -- planning|awaiting_approval|running|review|delivered|stopped|error
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  revision_rounds INTEGER NOT NULL DEFAULT 0,
  meta TEXT NOT NULL DEFAULT '{}'            -- JSON: template, language, flags
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  personality TEXT NOT NULL DEFAULT '',
  system_prompt TEXT NOT NULL DEFAULT '',
  skills TEXT NOT NULL DEFAULT '[]',         -- JSON list
  color TEXT NOT NULL DEFAULT '#2dd4bf',
  status TEXT NOT NULL DEFAULT 'idle',        -- idle|thinking|working|delegating|reviewing|error|done|offline
  message TEXT NOT NULL DEFAULT '',           -- current speech-bubble text
  xp INTEGER NOT NULL DEFAULT 0,
  level INTEGER NOT NULL DEFAULT 1,
  strictness INTEGER NOT NULL DEFAULT 3,      -- 1..5
  avatar TEXT NOT NULL DEFAULT '{}',          -- JSON appearance
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  custom INTEGER NOT NULL DEFAULT 0,
  current_task TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  assignee TEXT NOT NULL,                     -- agent id
  status TEXT NOT NULL DEFAULT 'todo',        -- todo|progress|review|done|rejected|blocked
  depends TEXT NOT NULL DEFAULT '[]',         -- JSON list of task ids
  acceptance TEXT NOT NULL DEFAULT '[]',      -- JSON checklist
  output TEXT,                                -- JSON output of last attempt
  qa_notes TEXT NOT NULL DEFAULT '[]',        -- JSON list of QA rounds
  revision INTEGER NOT NULL DEFAULT 0,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  channel TEXT NOT NULL DEFAULT 'boss',       -- boss|agent|system
  agent_id TEXT,                              -- sender agent id (null = boss/system)
  to_agent TEXT,
  text TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT,
  level TEXT NOT NULL DEFAULT 'info',         -- info|success|warn|error
  text TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS memory (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,                        -- project|agent
  scope_id TEXT NOT NULL,                     -- project id or agent id
  kind TEXT NOT NULL DEFAULT 'note',          -- decision|preference|brand|result|note
  content TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS deliverables (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  task_id TEXT,
  kind TEXT NOT NULL,                         -- plan|copy|design|code|seo|campaign|calendar|images|package
  title TEXT NOT NULL,
  data TEXT NOT NULL,                         -- JSON
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',       -- draft|pending|approved|rejected
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS deliverable_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deliverable_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  data TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS brand_kit (
  project_id TEXT PRIMARY KEY,
  logo_path TEXT,
  colors TEXT NOT NULL DEFAULT '[]',          -- JSON list
  fonts TEXT NOT NULL DEFAULT '[]',
  tone TEXT NOT NULL DEFAULT '',
  rules TEXT NOT NULL DEFAULT '[]',           -- JSON list of do/don't
  extra TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings_kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents_prompts (   -- prompt library
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  content TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,                         -- weekly_posts|monthly_report|custom
  project_id TEXT,
  interval_hours REAL NOT NULL DEFAULT 168,
  enabled INTEGER NOT NULL DEFAULT 0,
  last_run REAL,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  campaign TEXT NOT NULL,
  metrics TEXT NOT NULL DEFAULT '{}',         -- JSON reach/clicks/spend/...
  notes TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meetings (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  ideas TEXT NOT NULL DEFAULT '[]',           -- JSON [{agent, idea}]
  best TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS standups (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  brief TEXT NOT NULL DEFAULT '',
  meta TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS meta_drafts (       -- Meta publishing: approval-gated
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload TEXT NOT NULL,                      -- JSON post/ad payload
  status TEXT NOT NULL DEFAULT 'draft',       -- draft|approved|published|failed
  external_id TEXT,
  error TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(settings.db_file, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


def query(sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _lock:
        return list(get_conn().execute(sql, tuple(args)).fetchall())


def one(sql: str, args: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    with _lock:
        return get_conn().execute(sql, tuple(args)).fetchone()


def execute(sql: str, args: Iterable[Any] = ()) -> None:
    with _lock:
        get_conn().execute(sql, tuple(args))
        get_conn().commit()


def executescript(script: str) -> None:
    with _lock:
        get_conn().executescript(script)
        get_conn().commit()


def new_id(prefix: str = "") -> str:
    return (prefix + "_" if prefix else "") + uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


def jdump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def jload(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


# ---------------------------------------------------------------- memory API

def add_memory(scope: str, scope_id: str, content: str, kind: str = "note") -> None:
    execute(
        "INSERT INTO memory (id, scope, scope_id, kind, content, created_at) VALUES (?,?,?,?,?,?)",
        (new_id("mem"), scope, scope_id, kind, content, now()),
    )


def get_memory(scope: str, scope_id: str, limit: int = 50) -> list[dict]:
    rows = query(
        "SELECT * FROM memory WHERE scope=? AND scope_id=? ORDER BY created_at DESC LIMIT ?",
        (scope, scope_id, limit),
    )
    return [dict(r) for r in rows]


def log_activity(text: str, level: str = "info", project_id: Optional[str] = None) -> None:
    execute(
        "INSERT INTO activity (project_id, level, text, created_at) VALUES (?,?,?,?)",
        (project_id, level, text, now()),
    )


def add_message(text: str, channel: str = "system", project_id: Optional[str] = None,
                agent_id: Optional[str] = None, to_agent: Optional[str] = None) -> dict:
    mid = new_id("msg")
    execute(
        "INSERT INTO messages (id, project_id, channel, agent_id, to_agent, text, created_at) VALUES (?,?,?,?,?,?,?)",
        (mid, project_id, channel, agent_id, to_agent, text, now()),
    )
    return {
        "id": mid, "project_id": project_id, "channel": channel,
        "agent_id": agent_id, "to_agent": to_agent, "text": text, "created_at": now(),
    }


def kv_get(key: str, default: Optional[str] = None) -> Optional[str]:
    row = one("SELECT value FROM settings_kv WHERE key=?", (key,))
    return row["value"] if row else default


def kv_set(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings_kv (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
