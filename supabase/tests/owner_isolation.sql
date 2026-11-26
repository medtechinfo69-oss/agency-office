-- Run as the database administrator; all test users and rows are rolled back.
begin;
select set_config('agency.test_owner', gen_random_uuid()::text, true);
select set_config('agency.test_other', gen_random_uuid()::text, true);
insert into auth.users (id) values
  (current_setting('agency.test_owner')::uuid),
  (current_setting('agency.test_other')::uuid);

set local role authenticated;
select set_config('request.jwt.claim.sub', current_setting('agency.test_owner'), true);
select set_config('request.jwt.claims', json_build_object('sub', current_setting('agency.test_owner'), 'role', 'authenticated')::text, true);
insert into public.agency_workspaces (name) values ('Isolation test workspace');
insert into public.agency_projects (workspace_id, name)
select id, 'Isolation test project' from public.agency_workspaces
where owner_id = auth.uid();
do $$ begin
  if (select count(*) from public.agency_workspaces) <> 1 then
    raise exception 'Owner cannot read their workspace';
  end if;
  if (select count(*) from public.agency_projects) <> 1 then
    raise exception 'Owner cannot read their project';
  end if;
  begin
    update public.agency_workspaces set owner_id = current_setting('agency.test_other')::uuid;
    raise exception 'Workspace ownership transfer escaped RLS';
  exception when insufficient_privilege then null;
  end;
end $$;

select set_config('request.jwt.claim.sub', current_setting('agency.test_other'), true);
select set_config('request.jwt.claims', json_build_object('sub', current_setting('agency.test_other'), 'role', 'authenticated')::text, true);
do $$ begin
  if exists (select 1 from public.agency_workspaces) or exists (select 1 from public.agency_projects) then
    raise exception 'Another user can read owner data';
  end if;
  update public.agency_projects set name = 'Unauthorized';
  if found then raise exception 'Another user can edit owner data'; end if;
  begin
    insert into public.agency_workspaces (owner_id, name)
    values (current_setting('agency.test_owner')::uuid, 'Unauthorized');
    raise exception 'Another user can create owner data';
  exception when insufficient_privilege then null;
  end;
end $$;

set local role anon;
do $$ begin
  if public.agency_connection_status()->>'service' <> 'agency-office' then
    raise exception 'Public connection check failed';
  end if;
  begin
    perform id from public.agency_projects;
    raise exception 'Anonymous project reads are allowed';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.agency_workspaces (name) values ('Anonymous');
    raise exception 'Anonymous workspace inserts are allowed';
  exception when insufficient_privilege then null;
  end;
end $$;
rollback;
