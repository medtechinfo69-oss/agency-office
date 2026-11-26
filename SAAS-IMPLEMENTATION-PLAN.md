# Centrally managed SaaS implementation plan

## Existing architecture review (before code changes)

The current FastAPI application uses a shared SQLite/PostgreSQL database, global settings, owner/managed sessions, resource-based legacy roles, server-side provider credentials, and both local and request-driven orchestration. Legacy SQL is not tenant-scoped; event broadcasts, media, Builder tables, mutable provider settings and legacy administration assume a single workspace. Simply adding `tenant_id` to a few tables or hiding navigation would not make it safe.

Connections discovery currently mixes Ollama native `/api/tags` with OpenAI-compatible `/v1` endpoints, requires an unnecessary JSON body in one route, and lacks a native Anthropic adapter. Discovery will be checked and corrected with contract tests. No real provider secret will be requested in chat.

## Security and compatibility decision

Introduce an additive, explicitly scoped SaaS API and schema. Existing data and legacy APIs remain available to the existing platform owner; they are NOT silently reassigned or copied to demo agencies. Tenant identities are denied access to the entire legacy API/media/websocket surface, except their own explicitly allowlisted account/security routes. New tenant data always has `tenant_id`; every query includes its server-derived tenant. Caller-supplied tenant IDs never choose scope. Platform operations require the immutable existing owner identity, with administrator 2FA setup gating. No automatic creation of another platform owner.

This deliberate containment avoids shipping an unsafe partial SQL rewrite. Legacy Builder/media/orchestration require dedicated tenant ports before tenants can use them. Unsupported tenant capabilities must be clearly disclosed rather than passing unscoped calls through.

## Work sequence

1. Add portable SaaS tables, immutable platform-owner membership and tenant memberships; manual plans/licenses; transactional quota/limit admission; tenant-bound audit with IP.
2. Enforce auth tenant scope, protected-request license/read-only policy, owner MFA enrollment gate, tenant API allowlist and impersonation scope/session audit.
3. Implement manual agency creation/invitation, lifecycle/recovery/export, plans/license overrides, catalog/recruitment, projects/team, support/notifications and own usage APIs.
4. Implement centralized `/api/ai` gateway using server credentials only; model allowlists, license checks, idempotency, atomic reserved quotas, usage records and bounded fallback. Route real manager planning/delegation/review through this gateway; persist work and agent communication rather than animate fake activity.
5. Add platform sidebar and matching component-based platform/tenant screens; tenant-only Connections (authorized models, no key controls), plan/usage, recruitment, project execution and onboarding.
6. Correct provider discovery and Anthropic protocol; cover connection contracts, cross-tenant URL/body attacks, legacy denial, expiry, limits, key secrecy, fallback and concurrency.
7. Run tests/build and produce evidence-backed QA report; clearly state missing integrations/manual configuration. Do not claim production readiness without isolation tests and operational validation. No payment SDK, billing gateway or automatic subscription logic.

## Deployment/data precautions

All schema changes additive. Preserve existing signing/encryption keys and environment. Demo agencies must be explicitly seeded, never populated with real agency data or fake usage. Invitations use the existing hashed single-use flow; email delivery needs server SMTP configuration and is not asserted without delivery evidence. Custom DNS/TLS, domain verification and external durable workers require infrastructure configuration, not a fake toggle.
