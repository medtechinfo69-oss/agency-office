# AGENCY OFFICE — SaaS implementation and QA

Date: 2026-11-26. Branch: `arena/38052b10-agency-office`.

## Release assessment

**Implemented foundation, not the complete production-ready specification.** This additive release preserves the existing single-workspace owner data and design while introducing isolated agency workspaces. No payment gateway, subscriptions, payment collection, or tenant billing integration was added. Operational and feature gaps below are intentional disclosures, not completed controls.

Architecture and the pre-code plan are in `SAAS-IMPLEMENTATION-PLAN.md`. Production deployment evidence is recorded separately in `deliverables/SAAS-DEPLOYMENT.md` after deployment; a local passing build is not production evidence.

## Required feature matrix

| Feature | Status | Notes |
|---|---|---|
| Multi-tenancy | Implemented, additive | Agency, membership, manual plan/license, catalog, agents, projects/tasks/messages, usage/attempts, audit, support, notifications and tenant Builder tables. Existing global tables remain owner-only, not silently reassigned to agencies. |
| Tenant isolation | Implemented/tested for new surfaces | Scope derived from authenticated membership, not body/header IDs; explicit SQL tenant predicates. Entire legacy API/media/events/websocket surface denied to tenants. Application isolation, **not PostgreSQL RLS**. Unassigned legacy managed users are contained until Boss assigns membership; assignment invalidates old sessions. |
| Boss Admin | Implemented/partial UX | Sole existing owner is platform owner. Eight Platform pages, compulsory authenticator enrollment in production, scoped account/security controls, audited impersonation and red banner. Basic operational tables/editors reuse existing design; not the full chart dashboard. |
| Agency management | Implemented/partial | Create/wizard, edit, suspend/reactivate, manual limits/license, soft-delete/recover within 30 days, owner-reset invitation, JSON export, impersonation, explicit empty demo seeding. Invitations are single-use secure-copy tokens, **not delivered email**. Export excludes generated image bytes. No automatic 30-day purge. |
| Plans and licenses | Implemented/partial | Starter/Professional/Enterprise/Custom policies, random license keys, starts/expiry/grace/status/overrides and manual renewal. Expired workspaces read-only; suspended agencies denied. Model/features/resource/request/token checks server-side. Scheduled 14/7/1-day email reminders absent. Defaults need Boss review; plan names alone do not configure premium models/branding. |
| AI providers | Implemented/partial/manual configuration | Existing central provider management, discovery/testing and credentials reused; native Anthropic transport added. Tenant authorized-model view has no key editing/global costs. Gateway bounded fallback and free-first/quality-first ordering; pricing editor. Real external-provider smoke tests not performed. Per-role routing UI and comprehensive health charts incomplete. |
| API key security | Implemented/tested | Existing server encryption/env retained. Tenant Connections and usage omit credentials/global costs; tests assert ciphertext at rest and no key in tenant response. Preserve existing session/encryption secrets on deploy. No DNS pinning; existing outbound host checks are not a complete DNS-rebinding defense. BYOK not implemented. |
| AI agent catalog | Implemented/partial | Twelve central templates, active/publish eligibility/version/model/prompt/skills editing and update notices. Tool permissions, strictness and fully version-pinned historical template snapshots incomplete. |
| Agent recruitment | Implemented/partial | Plan-filtered locked marketplace, limits, custom name/instructions, pause/resume/duplicate/remove with retained task/message/usage history. Actual tokens/completed tasks/current task/activity. No polished org chart; granular brand voice/tone editor uses instructions/context instead. |
| Manager delegation | Implemented core / partial | AI-generated persisted specialist plan, request-driven execution, sibling-output/context sharing, Manager review/final output and retained errors. Manual specialist retry has reason audit and fresh idempotency key. No fabricated activity. **No durable autonomous worker, automatic stale-reservation recovery, or full QA/correction loop.** Root-plan/review recovery is incomplete. |
| AI usage tracking | Implemented/partial | Tenant requests/tokens/quota and event rows; Boss tenant/agent/provider/model aggregates and CSV with optional configured cost. Idempotency and transactional quota reservations, separate fallback attempts. Missing prices remain unknown, not fake zero. Failed attempts conservatively estimated. Native Excel, image-specific accounting/costs, alerts and trend charts incomplete. Existing owner-only legacy inference has not all migrated to `/api/ai`; tenant inference has. |
| Onboarding | Partial | Agency identity/logo/accent/context and onboarding state, separate recruitment and project screens. Not the complete guided logo→voice→recruit→project→Manager first-login wizard. |
| White-label | Partial | Plan-gated PNG logo and accessible accent in tenant workspace. Verified subdomains/custom-domain DNS/TLS, hide-branding parity and full white-label coverage not implemented. |
| Responsive UI | Tested, bounded evidence | 114 WCAG axe/layout page/viewport scans across tenant11 + Platform8 pages, three widths (1440/768/390), light/dark. Mobile nav inert/Escape, stale-response navigation fix, Builder splitter accessibility. These scans are not proof every control and modal was exercised. |
| Security tests | Passing, not independent audit | Cross-tenant ID/body/header tampering, platform/legacy denial, license expiry, quotas/idempotency/concurrency, image isolation, recruitment limits/history, MFA gate/disable denial, CSRF, scoped Builder, fallback, impersonation audit, unassigned-user containment. No external penetration test or production load test. |

## Connections failure correction

- `/api/models` accepts an omitted JSON body for discovery instead of returning 422.
- Provider `/v1` normalization prevents duplicate version segments for OpenAI-compatible endpoints.
- Native Anthropic uses its own headers/protocol, not an OpenAI-shaped request.
- Unavailable/disconnected discovery returns complete stable provider metadata rather than inconsistent objects.
- Tenant Connections uses `/api/saas/connections` and only returns verified models authorized by the plan. Tenant browser never calls global credential-management endpoints.
- Three mocked contracts pass. Browser acceptance exercised a real HTTP request through the UI/proxy to a **synthetic local provider**. The user's exact upstream account/credential failure has not been reproduced with live credentials; external model access still needs a Boss-side provider Test and plan assignment.

## Validation evidence

Commands run against disposable local data, never production test data:

- `backend/.venv/bin/python -m pytest -q backend/tests`: **96 passed, 4 skipped**. The four skips require PostgreSQL.
- `TEST_POSTGRES_URL='postgresql://postgres:postgres@/postgres?host=/tmp/agency-pg' backend/.venv/bin/python -m pytest -q backend/tests/test_postgres.py`: **8 passed**, including schema conversion, persistence, auth/security SQL and four-connection advisory-lock admission. This is **not** the entire HTTP suite rerun on PostgreSQL.
- `npm --prefix frontend test`: **12 passed**.
- `npm --prefix frontend run lint`: passed, zero warnings.
- `npm --prefix frontend run build`: passed.
- `NODE_PATH=/tmp/agency-browser/node_modules LD_LIBRARY_PATH=/tmp/al2023/lib node frontend/tests/saas-platform.cjs`: passed, **114 axe/layout scans**. Boss MFA enrollment was exercised on the earlier fresh-database run; subsequent runs use disposable recovery codes. Invitation/login, agency wizard/demos, tenant sidebar/API denial, Connections omitted-body discovery, recruitment, populated Builder fixture, usage, impersonation banner/audit exercised. Provider generation is a fixture, not proof of output quality/live upstream access.
- `git diff --check`: passed.

The expanded browser suite found missing `aria-valuenow` on two Builder resize separators; corrected with synchronized pointer/keyboard values. Earlier runs found an auth-read/sign-in rate-limit collision, stale tenant navigation responses, and legacy project-modal interference with Platform; all corrected before passing acceptance.

## Operator handover and launch blockers

1. Keep all existing Vercel project/environment settings, signing secret, encryption derivation and Supabase connection unchanged. Schema initialization is additive; no existing tenant/owner data is reset or migrated into demos.
2. Sign in using the **existing owner login**. Production requires Account authenticator enrollment and saving recovery codes before Platform management. No owner password is included in source/deliverables.
3. Boss configures/tests central providers and explicitly assigns verified `provider/model` identifiers, premium permission, enabled features and quotas in plans/licenses. Empty default model allowlists intentionally deny inference. Configure trusted prices if cost reporting is desired; review provider agreements and external spending independently of app quotas.
4. The Agencies **Create demo agencies** action creates empty Starter, Professional and Enterprise demos at reserved `example.invalid` addresses, idempotently. Disposable acceptance DB has all three. Production creation must be explicitly verified; demo addresses cannot receive invitations. Change to a real owner before use and generate a fresh secure invitation.
5. Share invitations privately; email/SMTP templates/delivery and reminders are not yet implemented. Do not paste invitation tokens or recovery codes into public reports.
6. Assign legacy managed users to the intended agency using the Boss-only assignment endpoint; do not grant global legacy access to bypass containment. Legacy global API keys are not tenant memberships.
7. Tenant Builder supports scoped project CRUD/files/versions/restore/QA/ZIP/chat generation using existing UI and gateway. **Reference attachments disabled**, buffered generation rather than live token streaming, no port of legacy media/workflows/websocket collaboration. Do not expose global Builder routes as a workaround.
8. Manager advances are bounded request-driven operations, not a serverless background daemon. A durable queue/worker, crash reconciliation and full correction/retry workflow are required before selling unattended agency automation.
9. Provision/verify domains and transport/email/monitoring separately. There is no claim of completed domain routing, email delivery, quota fault recovery, backup restoration drill, HA/load testing or SLA.
10. Complete remaining UX/integration features and independent security review before representing the entire requested SaaS as production-ready. No payment integration is needed or planned.

## Arena endpoint hotfix — subsequent release

The shipped Arena preset incorrectly used `https://platform.arena.ai/v1` (dashboard), which caused `/models` HTTP 404. Official documentation at https://platform.arena.ai/docs/api specifies `https://api.arena.ai/v1` for OpenAI-compatible calls. Corrected the preset, environment/provider matching, saved-setting reads, discovery and inference. Only exact known first-party root/version aliases are normalized; custom gateways remain untouched. Stored keys and database settings are not rewritten. Connections now explains the endpoint and Arena errors distinguish API access denial from endpoint failure without echoing upstream bodies/secrets.

Hotfix validation: **8 provider contract tests pass** (including five new Arena regressions); **101 backend tests pass, 4 PostgreSQL-dependent skips**; frontend lint/build pass; diff-check passes. Previous 114 browser scans and 8 disposable PostgreSQL tests describe the SaaS predecessor, not a new hotfix browser/PostgreSQL run. Live Arena credentials/inference remain untested; after deploying, reload Connections and run Test connection to fetch the key's actual available models.
