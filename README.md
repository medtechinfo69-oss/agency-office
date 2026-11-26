# 🏢 AGENCY OFFICE

**Self-growing AI teams in an isometric virtual office.**

You (the Boss) only talk to the **Manager (Nora)**. Write a project brief —
Nora splits it into tasks, assigns the right agents, QA (Rami) reviews every
output, and the final package is delivered to you after you approve it.
You watch everything live in an animated isometric office.

```
You (Boss) → Nora (Manager/Director)
   ├── LINA     Designer       brand identity, visuals, layout, image prompts
   ├── KARIM    Developer      HTML/CSS/JS, landing pages, code, bug fixes
   ├── SAMI     Copywriter     slogans, captions, ad texts, emails
   ├── YARA     SEO            keywords, meta tags, content strategy
   ├── ADAM     Ads Manager    Facebook & Instagram campaigns (A/B/C, budget, KPIs, UTM)
   ├── MONA     Social Media   30-day calendar, captions, hashtags, Reels ideas
   ├── ZED      Image Artist   1:1 / 4:5 / 9:16 creatives in brand colors
   ├── RAMI     QA Reviewer    strict — can REJECT work and send it back
   └── PIXEL    Intern         new hire: earns XP, grows into a full agent
```

## Website builder

The **Site Builder** sidebar entry contains the integrated website workspace, preview, code editor, version history, local model manager and Lovable handoff. It runs from the same `./run.sh` process and uses the same provider credentials, but stores its website projects separately from agency projects. See [SITE_BUILDER.md](SITE_BUILDER.md) for instructions, data locations and important prototype limitations.

## Features

- **Full orchestration**: brief → Manager plan (JSON) → *approval gate* →
  parallel agent work → QA review (max 3 revision rounds, then escalation to
  you) → final check → *delivery approval gate* → package
- **Animated isometric office**: original SVG artwork, agent status indicators, floor selector and camera controls.
- **Multi-provider AI with one-click switching** (OpenAI-compatible):
  OpenRouter, APInex, Groq, Google Gemini and local Ollama presets — pick the
  active one in **Settings → Connections → Providers** (or `ACTIVE_PROVIDER` in `.env`),
  edit model/URL per provider, and the app **auto-fails-over** to the next
  configured provider on billing/auth/rate-limit/network errors.
  Free-model presets included (`:free`, `free/*`, Groq/Gemini free tiers).
  Retries with backoff, timeouts, visible "agent stuck" state. Tokens are
  stored server-side only — never sent to the frontend or written to logs.
- **Automatic model selection**: paste an API key → the app validates it
  live, then fills the **model dropdown** with that provider's *free* models
  and auto-picks the right one; the **image model** is chosen the same way
  (default: keyless `pollinations-free` — free images with no key at all).
  Demo mode is removed: everything runs on real APIs with clear errors.
- **Clean first open**: no seeded demo project — the app starts on an empty
  office and immediately opens **New Project** so your real brief is first.
- **Meta module**: Adam's campaign packages (audience, budget plan, 3 A/B/C
  variants, CTA, UTM, KPIs), Mona's 30-day calendar, Zed's images,
  **Facebook/Instagram post & ad mockups**, compliance checker
  (risky claims, text-heavy images, Meta rejection triggers),
  ZIP export (images + captions.txt + calendar.csv), and **draft/approval-only**
  Meta Graph publishing (nothing publishes until you click Approve).
- **Persistent memory** (SQLite): brand rules, decisions, preferences,
  campaign results — injected into every agent's prompt.
- **Extras**: brand kit (logo/colors/fonts/tone), project templates,
  XP & leveling with Intern promotion, meeting room roundtable, competitor &
  trend scan (with sources), version history + rollback, analytics dashboard
  with AI insights, daily stand-up, EN/FR/AR UI (RTL), auto-schedules,
  prompt library and in-UI agent editor.
- **Live everything**: WebSocket events drive the office, Kanban, activity
  log, progress bar, per-project cost/token counters, pause/resume/stop.

## Project structure

```
agency-office/
├── .env.example          # copy to .env
├── run.sh                # one-command start (backend + frontend)
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py       # FastAPI app, WS, seed data
│   │   ├── config.py     # env settings (secrets stay server-side)
│   │   ├── db.py         # SQLite schema + memory API
│   │   ├── provider.py   # OpenAI-compatible layer + demo provider
│   │   ├── agents.py     # personas, prompts, skills, XP
│   │   ├── orchestration.py  # plan → assign → QA → deliver
│   │   ├── compliance.py # Meta ads compliance checker
│   │   ├── images.py     # Zed: image API or branded SVG fallback
│   │   ├── exporter.py   # ZIP/CSV export + Meta drafts
│   │   ├── trends.py     # competitor & trend scan
│   │   ├── scheduler.py  # recurring jobs
│   │   └── routers/api.py
│   └── tests/
│       ├── test_orchestration.py   # 31 offline tests (incl. providers)
│       └── smoke_ui.py             # headless-browser E2E (needs playwright)
└── frontend/
    ├── vite.config.js    # proxies /api, /ws, /media → :8000
    └── src/
        ├── App.jsx       # state, WebSocket, layout
        ├── api.js, ws.js, i18n.js
        ├── pages/         # Office, Chat, Projects, and other screens
        ├── styles/        # theme tokens and application styles
        └── components/
            ├── Characters.jsx      # original SVG robots
            ├── IsometricOffice.jsx # original SVG office
            ├── Sidebar.jsx, TopBar.jsx, ui.jsx
            ├── AgentPanel.jsx   # click-an-agent detail view
            ├── PreviewScreen.jsx# FB/IG mockups + campaign + calendar
            ├── AnalyticsScreen.jsx
            ├── SettingsScreen.jsx # provider/brand/agents/prompts/schedules
            └── NewProjectModal.jsx
```

## Quick start (one command)

```bash
cd agency-office
./run.sh
```

This creates a virtualenv if needed, installs dependencies, builds the
frontend, waits until both services answer, then prints the URL.

| Service  | URL                              |
|----------|----------------------------------|
| Frontend | http://localhost:5173            |
| Backend  | http://localhost:8000 (API/docs) |

Safe to re-run any time: it frees ports 8000/5173 first (only the
processes listening on them), so a second `./run.sh` just restarts
everything cleanly. Ctrl+C stops both services.

### Manual start

```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev
```

## Configuration (multi-provider ready)

`.env` is preconfigured with **OpenRouter active** plus APInex kept as
failover. Every provider follows the same pattern:

```bash
ACTIVE_PROVIDER=openrouter     # openrouter | apinex | groq | gemini | ollama

# per provider: {KEY}_TOKEN / {KEY}_MODEL / {KEY}_BASE_URL
OPENROUTER_TOKEN=sk-or-...     # your key — backend only, never sent to the browser
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
APINEX_TOKEN=sk-apx...
APINEX_MODEL=free/glm-5.3-flash
GROQ_TOKEN=                    # free tier: console.groq.com/keys
GEMINI_TOKEN=                  # free tier: aistudio.google.com/apikey
OLLAMA_BASE_URL=http://localhost:11434/v1   # local, unlimited, no key

IMAGE_MODEL=pollinations-free   # automatic free images (no key needed)
DEMO_MODE=false                # demo mode removed — real APIs only
```

- **Switch in the UI**: Settings → **Providers** — one click activates a
  provider (stored server-side); keys are password fields that are
  write-only (never returned by the API).
- **Auto model dropdowns**: the moment a key validates (on save, on blur,
  or silently for stored keys) the backend pulls the provider's `/models`
  list, shows only **free models** in the dropdown, and auto-selects the
  model — plus the image model (provider image API when available, else
  `pollinations-free`).
- **Automatic failover**: billing (402), auth (401), rate-limit (429),
  network and server errors walk the chain of configured providers
  (`openrouter → apinex → …`); if everything fails you get a clear,
  actionable error in the activity log (no demo fallback).
- **`.env` vs Settings**: no `.env` editing needed — paste a key in
  **Settings → Connections → Providers**, hit 💾 Save, then ⚡ Activate. Values saved in
  Settings (server-side kv) win over `.env` on every restart; clearing a
  key in Settings stays cleared.

### Local Ollama — unlimited AI, no key, works offline

```bash
# 1) install (starts ollama serve)
curl -fsSL https://ollama.com/install.sh | sh
# 2) pull a model (small + fast; use llama3.2 on bigger machines)
ollama pull qwen2.5:1.5b
```

Then in the app: **Settings → Connections → Providers → Ollama** (base URL defaults to
`http://localhost:11434/v1`) → **💾 Save** (the model dropdown fills from
`/v1/models` automatically) → **⚡ Activate**. Every agent, plan, QA round
and image prompt now runs against your local model. CPU models get a
generous 900 s per-call budget automatically (cloud stays at 120 s), run
with 2 parallel runners, and long outputs (30-day calendar) get a bigger
token cap — so slow local generation never gets cut off mid-answer.
- Any OpenAI-compatible endpoint works — add/adjust presets in
  `backend/app/config.py::PROVIDER_PRESETS`.
- Optional Meta publishing: `META_ACCESS_TOKEN`, `META_PAGE_ID`,
  `META_IG_BUSINESS_ID` — without them, local ZIP export still works and the
  UI shows “local only”.

## Testing

```bash
cd backend
python3 -m pytest tests/ -q        # 31 offline tests (orchestration, QA, compliance, providers…)

# full UI smoke test (backend + frontend running, playwright installed):
python3 tests/smoke_ui.py          # 16 checks: shell, gates, modals, theme/lang, no console errors

# auto-model settings flow (keys never touch the DOM):
python3 tests/verify_auto.py       # 8 checks

# force-check EVERY endpoint with a real API key (LLM-backed ones included):
python3 tests/api_sweep.py         # ~54 checks: providers/models, CRUD, standup, trends,
                                   # meeting, campaign, calendar, insight, images + media,
                                   # meta approval gate, ZIP export, control, chat, frontend
```

The sweep reports PASS/FAIL per endpoint with timings; the only failures it
can hit are external (provider quota/billing) — the app surfaces them as
clear 502s with failover attempted, never crashes.

## Design & performance

- **UI** follows the [agent-office-oss](https://github.com/alexdeg92/agent-office-oss)
  visual language: warm light theme by default (🌙/☀️ toggle for dark),
  left icon sidebar, page header with **En direct** badge + clock, KPI stat
  cards, office canvas in a rounded card, right-side roster with status
  chips. Tokens live in `frontend/src/styles/app.css` (`:root` light +
  `.app.night` dark) transcribed from the reference `design/tokens.json`.
- **No render-blocking assets**: Google Fonts removed — system font stacks
  only, zero external requests. First paint ≈ **40–500 ms** locally.
- **Production build**: `npm run build` (JS ≈ 222 kB / **72 kB gz**, CSS ≈
  32 kB / **6.7 kB gz**) served by `vite preview`; the API adds **gzip**
  (`GZipMiddleware`) for all JSON responses.
- **Parallel boot**: projects + agents load together; WebSocket connects
  while the canvas draws.

## How to use

1. Open the app → **New Project** opens automatically (empty office, no
   demo data) — name it and paste your brief to start a real project.
2. Nora replies with a plan built on real AI (your active provider).
3. **Approve the plan** (approval gate) → agents work in parallel; watch the
   office, Kanban and activity log.
4. QA may reject work (max 3 rounds) — Nora escalates to you if stuck.
5. Approve the **final package** → delivery. Then try **Preview** (FB/IG
   mockups), **Analytics**, **Stand-up**, **Meeting**, **Export ZIP**.
6. Click any agent for their task, conversation, memory, skills and tokens.

## Notes

- The office and characters are original SVG artwork in `frontend/src/components`.
- All numbers/prices in outputs come strictly from your brief — agents are
  prompt-enforced (and QA-checked) to never invent facts.
