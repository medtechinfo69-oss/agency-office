-- Additive Supabase foundation. This does NOT replace the Python API yet.
-- Owner-scoped data, no anonymous reads, no service-role key in the browser.
create table public.agency_workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 200),
  created_at timestamptz not null default now()
);

create index agency_workspaces_owner_idx on public.agency_workspaces(owner_id);
alter table public.agency_workspaces enable row level security;
revoke all on public.agency_workspaces from anon, authenticated;
grant select, insert, update, delete on public.agency_workspaces to authenticated;
create policy agency_workspace_owner on public.agency_workspaces
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create table public.agency_projects (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.agency_workspaces(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 200),
  brief text not null default '',
  status text not null default 'planning' check (status in (
    'planning', 'awaiting_approval', 'running', 'review', 'delivered', 'stopped', 'error'
  )),
  progress double precision not null default 0 check (progress between 0 and 100),
  cost_usd double precision not null default 0 check (cost_usd >= 0),
  tokens_in bigint not null default 0 check (tokens_in >= 0),
  tokens_out bigint not null default 0 check (tokens_out >= 0),
  revision_rounds integer not null default 0 check (revision_rounds >= 0),
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index agency_projects_workspace_idx on public.agency_projects(workspace_id);
alter table public.agency_projects enable row level security;
revoke all on public.agency_projects from anon, authenticated;
grant select, insert, update, delete on public.agency_projects to authenticated;
create policy agency_project_owner on public.agency_projects
  for all to authenticated
  using (exists (
    select 1 from public.agency_workspaces w
    where w.id = workspace_id and w.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.agency_workspaces w
    where w.id = workspace_id and w.owner_id = (select auth.uid())
  ));

create function public.agency_touch_project() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
revoke all on function public.agency_touch_project() from public, anon, authenticated;
create trigger agency_project_updated before update on public.agency_projects
  for each row execute function public.agency_touch_project();

-- Private files only. Paths must begin with the authenticated user's UUID.
insert into storage.buckets (id, name, public, file_size_limit)
values ('agency-private', 'agency-private', false, 10485760);
create policy agency_private_files_owner on storage.objects
  for all to authenticated
  using (
    bucket_id = 'agency-private'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id = 'agency-private'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- Public readiness RPC reveals no user data and validates browser connectivity.
create function public.agency_connection_status() returns jsonb
language sql stable security invoker set search_path = '' as $$
  select jsonb_build_object('service', 'agency-office', 'schema_version', 1);
$$;
revoke all on function public.agency_connection_status() from public;
grant execute on function public.agency_connection_status() to anon, authenticated;
