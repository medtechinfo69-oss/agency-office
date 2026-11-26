# Agency Office — control-panel redesign and audit

Date: 26 November 2026. Branch: `arena/38052b10-agency-office`.

## Summary

Expanded the existing administration console into a responsive control panel with a full-width three-panel Builder, shared model selection, real server-backed administration, encrypted stored provider credentials, persistent personal preferences, and account security. Existing workspace pages and business routes remain available. No production environment variable, user, role, connection or project was intentionally reset or deleted. All destructive acceptance checks ran against disposable local databases, never production.

## Problems found and corrected

- Separate Builder provider configuration could diverge from the workspace model. Unified discovery, selection, benchmarks and Builder candidate routing through the server model hub.
- Provider credentials in database settings lacked authenticated at-rest encryption. Added Fernet encryption with compare-and-swap migration; server `CREDENTIAL_ENCRYPTION_KEY`, falling back to the existing stable `SESSION_SECRET`. Never rotate either key without a migration/backup plan.
- Provider edits could send an existing token to a changed endpoint. Endpoint validation and explicit credential handling now prevent that path; SSRF regression tests cover hosted private addresses. DNS rebinding/pinning is not implemented.
- Request protection was inconsistent. Added shared DB-backed rate buckets, a 2 MB request ceiling, JSON structural bounds, endpoint validation and safer 422 responses that omit submitted passwords/keys/images. These are shared guards, not a claim that every legacy field has a complete domain-specific schema.
- A delegated role administrator could copy/edit a role beyond their own authority. Both routes now reject escalation. Owner remains immutable; system role names/deletion are locked, while system policies remain editable.
- Builder stream interruption could look successful. Require a terminal completion event, restore prior files on failure, bound provider attempts/serverless time, parse HTML structure and allow one model repair before rejecting invalid output. Static checks do not certify arbitrary generated JavaScript.
- Preview interpolation could corrupt JavaScript containing dollar replacement sequences. Function replacements now preserve source exactly; the legacy Builder uses the same preview helper.
- Inspector cards could shrink unpredictably. Fixed flex sizing and full-width workspace expansion.
- New avatar controls overflowed at 390 px. Wrapped identity actions; repeated the complete 80-scan layout/accessibility sweep successfully.
- Personal sound settings could be overwritten during startup. Server preference initialization now takes precedence over workspace defaults.

## Verification evidence

- Frontend ESLint: zero warnings/errors.
- Frontend Node tests: **12 passed**.
- Production Vite build: **passed**, 4.38 seconds in the last measured build.
- Backend default suite: **79 passed, 3 skipped**; the three skips require an explicit disposable PostgreSQL URL.
- Separate disposable PostgreSQL suite: **7 passed**.
- One existing Starlette/httpx test-client deprecation warning remains.
- Browser layout/axe sweep: **80 scans** = 10 pages × 1440/1024/768/390 px × dark/light. **Zero axe WCAG A/AA findings, zero document overflow, zero page exceptions**. Nine legacy routes additionally received desktop render/overflow smoke checks.
- `control-panel.cjs`: passed actual backend catalog/benchmark/selection, model propagation into Builder, 240→64 px sidebar expansion (workspace gains 176 px), bounded user menu, shortcuts, command search, streamed generation, iframe button JavaScript, preview sizes/reload, version compare/restore, editor undo/redo, copy, ZIP, publish/export dialog, static checks, invitations, role matrix, instance save/purge, audit copy and authenticator setup.
- `control-security.cjs`: passed TOTP enable/recovery login/disable, other-session revocation, avatar PNG crop/save, language persistence across reload, sound preference persistence, appearance controls/reset, three-step agent creation/configuration/logs, typed sign-out-all and return to sign-in.
- Seven provider Test UI handlers used **explicit browser response fixtures**. Text generation/benchmark used the real local backend with a **synthetic OpenAI-compatible upstream**. The default-image test used the real image proxy with a **synthetic SD-compatible upstream**. None of these establish live provider credentials, image quality, quota or availability.
- Browser tests exercise representative critical controls and normal states; they are not proof that every hover, modal combination, failure path, operating system or assistive technology was manually tested.

## Page-by-page QA

Statuses apply to the named element and the evidence in Notes, not every possible feature on that page.

| Page | Element | Status (OK/Fixed) | Notes |
|---|---|---|---|
| Global | Sidebar collapse and workspace grid | Fixed | Browser measured 240→64 px rail and +176 px content; responsive scans pass. |
| Global | Breadcrumb, command search, shortcuts | OK | Navigation/search and shortcuts dialog exercised in browser. |
| Global | User menu | Fixed | Bounded right-anchored dropdown; account/appearance/sign-out actions retained. |
| Global | Light/dark, focus and reduced motion | OK | Axe scans in both themes, four widths; tests use reduced motion. Not a manual screen-reader certification. |
| Global | Active model propagation | Fixed | Actual persisted selection immediately appears in Builder; agents inherit global selection. |
| Diagnostics | KPI/health table and refresh age | Fixed | Real DB/API/provider state; in-session trend samples labelled honestly; no invented historical SLA. |
| Diagnostics | Log filters, pause, copy and download | Fixed | Time/agent/level/search, autoscroll and export implemented; audit copy exercised. Every filter combination not exhaustively tested. |
| Agents / Runtimes | Wizard, configuration and timeline | Fixed | Browser creates, configures and inspects an agent; logs query matches message schema. |
| Agents / Runtimes | Model/runtime state | OK | Shared discovered catalog; no invented GPU residency, usage or autonomous-process status. |
| Connections | Discovery/test/connect/default selection | Fixed | Local discovery/benchmark persisted through real backend; seven UI Test handlers fixture-tested. |
| Connections | Credentials and endpoint safety | Fixed | Server encryption/masking, reveal-once flow, delete/rotate controls; validation/exfiltration tests. Live credential rotation not executed. |
| Connections | Default image routing | Fixed | Browser renders PNG returned through `/api/image` and SD-compatible synthetic upstream. |
| Builder | Chat/preview/code, streaming and files | Fixed | Actual streamed fixture, iframe JavaScript, sizing, reload, edits and undo/redo pass. |
| Builder | Versions, ZIP, export and static QA | Fixed | Compare/restore/copy/download/export exercised; HTML structure and safe-preview unit tests. |
| Access | Scoped tokens and permission enforcement | Fixed | Backend tests cover roles, API keys and privilege-escalation denial. Tokens are returned only at creation. |
| Access | Timeout/IP policy and audit | Fixed | Stored policy and lockout validation tested; request-driven audit retention. Email delivery not claimed. |
| Instance | Dirty save and data-safe maintenance | Fixed | Browser save and typed log purge on disposable data; production data untouched by tests. |
| Instance | Restart/update controls | OK | Unsupported Vercel operations explain limits; no fake restart/update success. |
| Appearance | Theme/accent/font/density/motion/reset | Fixed | Browser applies custom accent, font and sidebar spacing, toggles animation, resets. |
| Account | Profile/avatar/language/notifications/sound | Fixed | Real PNG crop/save, language reload and preference API isolation tests; mobile overflow corrected. |
| Account | Password/security/sessions | Fixed | Password meter; TOTP QR/recovery, revoke-other and typed revoke-all browser tests; backend one-use/replay tests. |
| Users | Invite, regenerate, role and delete | Fixed | Browser CRUD on disposable member; hashed single-use invitations, no automatic email promise. |
| Users | Last-admin/owner safeguards | OK | Server guard regression tests; owner recovery access preserved. |
| Roles | CRUD matrix, review and system locks | Fixed | Browser custom-role review/save/delete; delegated copy/edit escalation regression tests. |
| Legacy workspace | Existing route rendering | OK | Nine desktop smoke routes; not an exhaustive legacy workflow acceptance pass. |

## Reproducing browser tests

Use isolated local data and never point these destructive scripts at production. Scripts reject a non-localhost UI URL. Install Playwright and `@axe-core/playwright` in a test tools directory and provide a Chromium binary. The current sandbox uses `/tmp/agency-browser/node_modules` and `/tmp/chromium` (security script uses that path). Launch `frontend/tests/synthetic-provider.py` on 8012, backend on 8011 with `DEMO_MODE=true` and the test password documented in the scripts, and Vite on 5175 with `/api` proxied to 8011. Run `control-panel.cjs`, `control-security.cjs`, then `control-layout.cjs`. Use a fresh disposable DB if an interrupted run leaves a test invitation, role or TOTP setup behind. These scripts are intentionally not part of the ordinary production build.

## Remaining limitations / acceptance boundaries

- Live Ollama Cloud, OpenRouter, Arena, HF and Pollinations inference is **not verified** in this run. Provider service terms/quotas and valid server credentials apply. No keys belong in client bundles. Hosted localhost Ollama is not the user's laptop: use an approved reachable endpoint.
- Model health is periodically refreshed; cached healthy-model fallback and bounded Builder fallback are implemented. `/api/chat` does not retry a failed individual request across providers.
- Image integrations include Pollinations, HF and SD-compatible local API. ComfyUI workflow execution is **not implemented**.
- Per-agent executable tool ACLs and individual model overrides are **not implemented**; skill descriptions are instructions, agents inherit the global model.
- No unattended scheduler on Vercel. Runtime usage, billing, email invitations, deployment restart and self-update are not fabricated; unsupported features explain their limit.
- Personal language changes translated workspace labels; administration copy is still English. Avatar cropping is centered with zoom, not a draggable crop editor.
- Builder validates static structure and isolates its preview; it does not execute a secure server-side browser repair loop for arbitrary generated JavaScript. Google Fonts are allowed; other external dependencies/network behaviors are restricted.
- This is single-workspace role-based access, **not multitenant tenant isolation**. General request guards do not replace a professional penetration test, comprehensive DNS pinning or exhaustive route-specific semantic validation.
- Production migrations are additive (`CREATE ... IF NOT EXISTS`, insert-if-missing and credential compare-and-swap encryption). Existing `SESSION_SECRET` and all environment variables must remain stable. Older sessions may require signing in again because sessions are now individually tracked.

Deployment records are documented in the final delivery note once both production deployments are confirmed ready. Protected production workflows are not destructively tested.
