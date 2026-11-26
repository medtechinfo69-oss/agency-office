#!/usr/bin/env bash
# AGENCY OFFICE — one-command local start (backend + frontend).
# Safe to re-run: frees ports 8000/5173 first, creates venv on first run.
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo "🏢 AGENCY OFFICE starting…"

# ---- free our ports (only the processes listening on them) ----
free_port() {
  python3 - "$1" 2>/dev/null <<'PY' || true
import os, signal, sys
port = int(sys.argv[1]); hx = f"{port:04X}"; inodes = set()
for f in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        for ln in open(f).read().splitlines()[1:]:
            p = ln.split()
            if p[1].rsplit(":", 1)[-1] == hx and p[3] == "0A":
                inodes.add(p[9])
    except OSError:
        pass
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            t = os.readlink(f"/proc/{pid}/fd/{fd}")
            if t.startswith("socket:[") and t[8:-1] in inodes:
                os.kill(int(pid), signal.SIGTERM)
                break
    except (OSError, PermissionError, ProcessLookupError):
        pass
PY
}
free_port 8000
free_port 5173
sleep 1

# ---- backend python: project venv, else system python3 ----
PY="python3"
if [ -x backend/.venv/bin/python ]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  echo "→ creating Python venv (first run)"
  if python3 -m venv backend/.venv && backend/.venv/bin/pip install -q -r backend/requirements.txt; then
    PY="$ROOT/backend/.venv/bin/python"
  else
    echo "→ venv failed — falling back to system python3"
    rm -rf backend/.venv
    PY="python3"
  fi
fi
if ! "$PY" -c "import fastapi, uvicorn, httpx, dotenv" 2>/dev/null; then
  echo "→ installing backend deps into system python3"
  python3 -m pip install -q -r backend/requirements.txt || true
fi

# ---- frontend deps ----
if [ ! -d frontend/node_modules ]; then
  echo "→ installing npm packages (first run)"
  (cd frontend && npm install --no-audit --no-fund)
fi

# ---- env ----
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "→ created .env from .env.example (add API keys in Settings, no .env editing needed)"
fi

cleanup() {
  [ "${CLEANED:-0}" = 1 ] && return
  CLEANED=1
  echo ""
  echo "⏹ stopping…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---- run both ----
echo "→ backend  http://localhost:8000  (API docs at /docs)"
(cd backend && "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000) &

echo "→ frontend http://localhost:5173 (fast production build)"
(cd frontend && npm run build && npm run preview -- --host 0.0.0.0 --port 5173) &

# ---- wait for both, then print the URL ----
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 \
     && curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
echo ""
echo "✅ AGENCY OFFICE is up — open in your browser:"
echo "   🖥  http://localhost:5173"
echo "   🔌  http://localhost:8000  (API · /docs)"
echo "   ⏹  Ctrl+C stops everything"
echo ""

wait
