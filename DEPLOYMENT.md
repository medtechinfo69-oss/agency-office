# Deploy Agency Office: Vercel frontend + persistent Python backend

## Current status

**Supabase migration started:** the selected free-project connection, protected initial tables and private storage are prepared. See [SUPABASE_MIGRATION.md](SUPABASE_MIGRATION.md) for what is implemented and the remaining API/auth/jobs migration. The Python API has **not** been replaced.

- Vercel project **agency-office** has been created in **medtechinfo69-oss' projects** and linked to `medtechinfo69-oss/agency-office`.
- Saved Vercel settings: Vite, root `frontend`, install `npm ci`, build `npm run build`, output `dist`.
- Frontend production alias: https://agency-office-indol.vercel.app/.
- The owner supplied Railway backend origin: `https://agency-office-production-c80c7cdd.up.railway.app`. Its availability, credentials and persistent volume have not yet been verified.
- `frontend/vercel.json` now routes API/media to that Railway origin; Vercel's production/preview `VITE_WS_URL` is configured for its direct `/ws` endpoint. A new deployment is required to apply changes.
- No paid service or disk has been purchased by the agent. The optional Render blueprint below is **paid** and is not the selected deployment route.
- All work in this session uses branch `arena/38052b10-agency-office`. Do not deploy the old `main` commit expecting the redesign or hosting changes.

Vercel project settings: https://vercel.com/medtechinfo69-oss-projects/agency-office

## Why two hosts?

The frontend is a static React/Vite app. The Python service owns two SQLite databases, generated media, exports, scheduled jobs, in-process events, WebSockets and streamed generation. It needs a long-running process with writable persistent storage. Moving that service unchanged into disposable functions would lose functionality and/or data.

HTTP and media requests use the **frontend's own origin** and Vercel external rewrites. Authentication cookies are therefore same-origin, not third-party cookies. WebSockets connect **directly to the backend over WSS**, using a short-lived, WS-only signed ticket obtained through an authenticated same-origin request. They do not rely on Vercel accepting a WebSocket upgrade.

## Selected backend: Railway (owner dashboard setup)

Use the existing Railway service at the origin above. Deploy branch `arena/38052b10-agency-office` with repository root as the build directory and the root `Dockerfile`; leave the start command unset so the image entrypoint runs. Do not deploy only the `frontend` directory to Railway.

In Railway → service → Variables, set:

```text
APP_ENV=production
ALLOWED_ORIGINS=https://agency-office-indol.vercel.app,https://agency-office-medtechinfo69-oss-projects.vercel.app
DATA_DIR=/data
DB_PATH=/data/agency.db
DEMO_MODE=false
```

Also create private `ACCESS_PASSWORD` (unique random 16+ characters) and `SESSION_SECRET` (independent random 32+ characters) values directly in Railway. Never put them in Git, chat or Vercel `VITE_` variables. Missing/short secrets intentionally prevent production startup. Add provider credentials only in Railway or authenticated application settings.

Attach the plan's persistent volume at `/data` before storing real projects. Without a volume, SQLite databases and uploads are ephemeral even when deployment succeeds. Configure public networking to target the running app's `PORT` (the image defaults to `10000`); a mismatched target port can produce an unavailable service despite a successful build. Set the healthcheck path to `/healthz` and keep one replica.

Apply/redeploy after setting variables. Open the Railway origin plus `/healthz` and `/api/auth/session`. The health endpoint should return HTTP 200; the session endpoint should return JSON with authentication required, not an HTML frontend or Railway error page. Do not disable production access checks to resolve a startup failure.

Railway's Free plan has a small monthly usage allowance and sleeps when idle. Usage exhaustion can stop the service, and scheduled/background jobs cannot run while it is asleep or stopped. A live browser WebSocket can consume additional runtime. Confirm Free-plan eligibility and limits in the Railway dashboard; do not approve a paid upgrade. These limits mean this is a light-use deployment, not guaranteed always-on hosting.

## Alternative only — provision Render (paid, not selected)

The supplied `render.yaml` is an optional Render Blueprint. It requests a **paid Starter web service and a 1 GB persistent disk**. Review the current prices shown in Render before approving it. Nothing is provisioned merely by committing this file.

1. Open https://dashboard.render.com and choose **New → Blueprint**.
2. Connect `medtechinfo69-oss/agency-office` and select branch **arena/38052b10-agency-office**. The blueprint is at repository root: `render.yaml`.
3. Review the service, region and disk charges, then approve only if acceptable.
4. Render generates `ACCESS_PASSWORD` and `SESSION_SECRET` in the backend's environment. Keep both private. The workspace owner will use `ACCESS_PASSWORD` on the sign-in screen. Do not paste passwords, signing secrets or provider tokens into chat.
5. Wait for the service to pass **GET /healthz**, then copy its public **HTTPS base URL** from Render's service dashboard.
6. Send only that public URL back to the agent. It is not a secret.

The template intentionally starts `ALLOWED_ORIGINS` empty. Production browser sign-in/writes are blocked until the exact frontend origin is configured in Step 3. The backend is not exposed as an unauthenticated admin API while this is being set up.

If using a different persistent Docker host/VPS, use the same Dockerfile and environment settings below instead. The app expects **one instance and one Uvicorn worker**. SQLite, the event bus and the scheduler are not configured for horizontal scaling.

### Backend environment

| Variable | Value / purpose |
| --- | --- |
| `APP_ENV` | `production` — enables hosted access checks and secure cookies |
| `ACCESS_PASSWORD` | Unique random password, at least 16 characters; generated by the blueprint |
| `SESSION_SECRET` | Independent random secret, at least 32 characters; generated by the blueprint |
| `ALLOWED_ORIGINS` | Exact frontend HTTPS origin(s), comma-separated, without paths; filled after the Vercel deployment URL is known |
| `DATA_DIR` | `/data` |
| `DB_PATH` | `/data/agency.db` |
| `PORT` | Supplied by the host; defaults to `10000` in the image |
| `ACTIVE_PROVIDER` | `openrouter`, or another provider you configure |
| `DEMO_MODE` | `false` — real provider errors are surfaced, not silently simulated |
| `IMAGE_MODEL` | `pollinations-free`, or another supported selection |

Provider tokens belong **only on the backend** (for example `OPENROUTER_TOKEN`) or in the signed-in Settings UI, which persists them server-side. Never use `VITE_` for a password, signing secret or provider key. Render cannot access Ollama running on a laptop via `localhost`; use a cloud provider or a separately secured reachable model server.

The `/data` mount retains:

- `/data/agency.db` — projects, agents, provider settings and schedules;
- `/data/siteforge.db` — Site Builder data;
- `/data/media/` — uploaded/generated media;
- `/data/exports/` — exports.

The container entrypoint fixes ownership of the mount, drops privileges, and starts one worker. The image does not copy local databases or `.env` files. New hosting starts with a fresh office; migrating existing data/backups is a separate explicit task. Back up both SQLite databases and media with a consistent SQLite backup/snapshot procedure; do not copy only a live `.db` file while ignoring its WAL.

## Step 2 — configure and deploy Vercel (agent can complete after receiving the backend URL)

From the repository root:

```sh
node frontend/scripts/configure-hosting.mjs https://YOUR-BACKEND-HOST
```

Replace the example with the actual backend HTTPS origin from the hosting dashboard. The helper rejects localhost, temporary Arena preview addresses, HTTP URLs and embedded credentials. It writes `frontend/vercel.json` with concrete same-origin rewrites for `/api/*` and `/media/*`. Vercel reads this configuration before the build, so it must be generated **before committing/deploying**, not inside a build script.

In the existing **agency-office** Vercel project, set the public build variable:

```text
VITE_WS_URL=wss://YOUR-BACKEND-HOST/ws
```

The helper prints the exact value. Apply it to the environments being deployed (preview and/or production). Rebuild after changing it because Vite embeds public variables at build time.

Commit and push the generated routing configuration on **the current session branch**, then deploy that exact branch/commit to the existing Vercel project. No other Vercel project should be overwritten and no push to `main` is needed. No credentials are included in the generated configuration.

Do not route `/ws` through Vercel. Do not point Vercel at the temporary Arena API/preview port. Do not rely on Vite's dev-only `localhost:8000` proxy in production.

## Step 3 — allow the deployed frontend and verify

1. Copy the exact HTTPS frontend origin returned by Vercel after deployment.
2. In Render, set `ALLOWED_ORIGINS` to that origin. Include the stable production alias too if it differs. Use exact origins, not `*`, paths or trailing slashes. Changing origins requires restarting/redeploying the backend so its startup configuration is refreshed.
3. Open the frontend, sign in using the backend's `ACCESS_PASSWORD`, and confirm:
   - the Office loads and the Live indicator connects over direct WSS;
   - signed-out `/api/settings`, `/media/*`, exports and documentation are rejected;
   - project creation, plan approval, chat and task updates work with the chosen provider;
   - provider keys are not returned to the browser;
   - Site Builder generates, streams, saves and exports;
   - uploads/previews load via the frontend `/media/*` path;
   - logout returns to sign-in;
   - restarting the backend retains projects and both databases.
4. If Vercel deployment protection is enabled, visitors must also satisfy that protection. It does not replace the backend's owner password.

## Hosted access model and limitations

This is a **single-owner gate**, not a multi-tenant authentication/authorization service. Existing illustrative users/roles and the local permission planning matrix are still not enforced as individual roles.

- HttpOnly, Secure, SameSite=Lax session cookies last 12 hours; neither the owner password nor a long-lived auth token is stored in browser localStorage/sessionStorage.
- Login attempts are rate-limited in the single backend process; rotating either `ACCESS_PASSWORD` or `SESSION_SECRET` invalidates existing signed sessions/tickets. Password rotation is the way to invalidate all sessions. Logout removes the current browser cookie, not every previously issued session.
- WebSocket tickets expire after 30 seconds and are sent as subprotocols, not URL parameters. An already-open authenticated connection lasts until it disconnects; there is no distributed session-revocation service.
- The public `/healthz` returns only liveness, not provider configuration or credentials.
- Production startup fails without sufficiently long credentials. Local development remains unauthenticated unless explicitly configured with `ACCESS_PASSWORD` and `SESSION_SECRET`; do not expose local mode as a public backend.
- Scheduled definitions persist, but a process restart can interrupt an in-flight generation. The current orchestration is not a durable distributed job queue.
- Vercel and the backend host impose request/stream/proxy limits. Slow generations and very large uploads/exports need live verification against the selected plans. Very long streaming requests may require a future direct authenticated streaming endpoint instead of an external rewrite. Backend background work itself runs on the persistent server.

## Verification completed locally

- Frontend production build passes.
- Backend: **47 tests pass**, including production fail-closed configuration, protected routes/media/docs, correct/incorrect password, cookie flags, origin restrictions, login throttling, token tampering/expiry, WebSocket ticket authorization and backward-compatible local mode.
- Node tests: **5 pass** (hosting configuration plus existing handoff tests).
- Browser tests cover all 11 pages at four sizes, light/dark accessibility checks, and hosted sign-in/error/logout/retry flows using isolated fixtures.
- Docker is not installed in this sandbox, so the container has **not** been built here. No claim is made that Render provisioning, Vercel proxy cookies, live WSS or live generation has been verified on public hosting yet.

Tests:

```sh
cd backend && .venv/bin/python -m pytest -q
cd ..
npm run build --prefix frontend
node --test frontend/scripts/configure-hosting.test.mjs frontend/src/sitebuilder/handoff.test.mjs
# With the optional Playwright test tools installed:
node frontend/tests/hosted-auth.cjs
UI_AXE=1 node frontend/tests/ui-review.cjs
```

## Vercel + Supabase (request-driven cloud mode)

The current frontend rewrites `/api/*` and `/media/*` to
`https://backend-five-gamma-46.vercel.app`. Deploy `backend/` as FastAPI,
`frontend/` as Vite. Set frontend `VITE_EVENT_TRANSPORT=poll`; do not use a
Railway WebSocket URL. Both projects must deploy the same reviewed commit.

Backend environment (never commit values):
- `DATABASE_URL`: Supabase transaction-pooler connection string, using the
  restricted `agency_backend.<project-ref>` login, port 6543, database postgres,
  TLS verification enabled. Psycopg prepared statements are disabled.
- `APP_ENV=production`, `DEMO_MODE=false`, `ACCESS_PASSWORD` (16+ characters),
  `SESSION_SECRET` (32+ characters), `ALLOWED_ORIGINS` (exact frontend HTTPS URLs).

The backend initializes its tables in private `agency_office` and
`agency_sitebuilder` schemas. These are **single-owner** schemas, not the earlier
public RLS foundation. Grant the restricted backend role USAGE/CREATE on only
these two schemas. Browser clients never receive the database connection string.
The publishable Supabase browser key cannot replace DATABASE_URL.

Office state, provider settings, approvals, events, Site Builder files/versions,
and generated small media persist in Postgres. Media are private bytea records
(maximum 10 MB per file), not public Storage objects. `/tmp` is scratch space only;
export ZIPs are rebuilt from persistent data. Watch the Free database quota.
Existing local SQLite data is **not automatically migrated**.

### Important differences from a persistent worker

Vercel does not host the app's WebSocket or perpetual scheduler. The browser polls
events and advances one bounded planning/task step per request. **Keep the app
open to advance jobs.** Plan and delivery approvals survive page refreshes.
Interrupted or failed tasks require explicit Resume/guidance before retrying;
provider calls are not guaranteed exactly once. Stop/pause prevents future steps,
not an already-running external provider request. Enabling schedules returns 409;
unattended daily work needs an external durable worker. The local/Docker runner
retains its original scheduler and WebSocket implementation.

Configure a cloud AI provider key in Settings before real generation. Ollama on
your laptop cannot serve a Vercel function. No paid provider subscription, hosting
upgrade, or card registration is performed by this code. Free hosting/provider
quotas and time limits still apply. Long individual tasks can exceed Vercel's
request budget; they block for explicit retry rather than silently finishing in
background. Site Builder streams run within a single Vercel request.

### Regression checks

`cd backend && .venv/bin/python -m pytest -q` covers auth, provider behavior,
checkpoint approvals/dependencies/leases/retry/control, and adapter SQL handling.
For disposable local Postgres only, set `TEST_POSTGRES_URL` and run
`tests/test_postgres.py` to verify schema initialization, persistence, binary data,
Unicode/bound parameters, and Site Builder. Never point that test at production.
