# Supabase connection — stage 1, not a backend cutover

## Project and deployed settings

- Project: `caqtysblmkkevzhradun`, https://caqtysblmkkevzhradun.supabase.co
- Existing Vercel project: `agency-office`; frontend https://agency-office-indol.vercel.app/
- Vercel production/preview public variables: `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
- Public credentials are kept in deployment configuration, not hardcoded in source. Never add a secret/service-role key, database password or AI provider key to a `VITE_` variable.

The supplied key was entered with Markdown-escaped underscores; the deployment value uses ordinary underscores. The client accepts only the `sb_publishable_` key format. Health was verified through the connected management API. Browser connectivity/key acceptance is a separate check, not implied by management API health.

## What has been implemented

- Official `@supabase/supabase-js` client, lazy initialization, public-config validation, in-memory-only auth state. No Supabase login flow is enabled yet, no session tokens are written to localStorage, and URL fragments are not treated as login credentials.
- Additive migration `supabase/migrations/202611260001_agency_foundation.sql` applied to the selected existing project.
- `agency_workspaces`: owner-scoped workspace records, linked to Supabase Auth users.
- `agency_projects`: initial cloud project model, linked to a workspace. Existing SQLite rows are **not** imported automatically; the new UUID IDs and timestamps need an explicit migration mapping.
- RLS and explicit grants: only authenticated owners can operate on their workspace/project rows. Anonymous roles cannot read them. Ownership cannot be reassigned to another user through the client.
- Private `agency-private` storage bucket (10 MB per file). Storage object paths begin with `<auth-user-uuid>/`; policies limit reads/writes/deletes to that user's folder. No public bucket or global authenticated-user access is enabled.
- A public, constant readiness RPC, `agency_connection_status()`, returns only service name and schema version. It reveals no account data and grants no data access.
- On the existing backend-unavailable screen, a read-only Supabase connection check reports whether that RPC is reachable. It explicitly says that the API migration is pending. It does **not** unlock the app or suppress the existing backend failure.

## Verification

- Live Supabase Auth, REST, database and Storage services reported healthy.
- Live SQL isolation test (`supabase/tests/owner_isolation.sql`): owner can create/read a workspace and project; another user cannot read/edit those rows or insert data for the owner; an owner cannot transfer ownership through the client; anonymous project reads/workspace inserts are denied; the readiness RPC works as anon. Test users/rows are created inside a transaction and rolled back.
- Frontend configuration/readiness unit tests reject partial config, unsafe origins, secret keys and unexpected schema responses. All 8 Node tests (including existing hosting/handoff tests) pass; they do not make external requests.
- Mocked browser tests pass for Supabase readiness/public-key header, rejected key, no auth bypass/private API reads and no stored credentials. Existing hosted owner sign-in/logout/backend-down/retry regression tests also pass. The frontend production build passes; the SDK is lazy-loaded only for the diagnostic.
- Browser acceptance of the supplied publishable key and the new diagnostic must still be checked on the deployment. Management health and SQL role tests do not substitute for an end-to-end login test.

## What is NOT migrated yet

The live Office still calls the existing Python `/api` endpoints and direct Railway WebSocket. The current Vercel rewrites are deliberately unchanged. Setting a Supabase URL does not make Supabase serve those Python routes.

Remaining work before safely cutting over:

1. Implement Supabase sign-in, account ownership, session refresh/expiry and logout, with tested isolation. Supabase users are separate from the dashboard's GitHub login and from the existing single-owner `ACCESS_PASSWORD`.
2. Port project CRUD and wire it to the cloud model; map/import any existing office data explicitly.
3. Migrate agents, tasks, messages, deliverables/version history, brand kits, templates, schedules, meetings, analytics, provider settings and both Site Builder data and APIs.
4. Keep AI/provider credentials server-side with authorization checks. Do not place them in broadly readable JSON columns or public browser variables.
5. Replace the in-process event bus with authenticated live updates; redesign long AI runs into resumable, bounded jobs that respect free serverless limits. Do not mark a job complete just because it was enqueued.
6. Migrate uploaded/generated files to private Storage, using signed URLs where needed; adapt exports and HTML previews safely.
7. Test all existing workflows and errors on a preview deployment, including long generations, tenant isolation and storage, before changing production routing.

No promise of unlimited/always-on AI generation is made. Free-plan quotas, pauses and external model costs still apply. No paid Supabase resources or branching have been requested.
