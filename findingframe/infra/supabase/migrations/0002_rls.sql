-- FindingFrame — RLS policies + append-only enforcement
-- Roles (Supabase): authenticated (user JWT, RLS enforced), service_role (bypasses RLS; used by the worker/backend admin ops).
-- Strategy: users act as `authenticated`; RLS scopes every row to their org membership.
-- Append-only tables: INSERT+SELECT policies only, and UPDATE/DELETE revoked from `authenticated`.

begin;

grant usage on schema ff to authenticated, service_role;
grant all on all tables in schema ff to service_role;
grant all on all sequences in schema ff to service_role;
alter default privileges in schema ff grant all on tables to service_role;
alter default privileges in schema ff grant all on sequences to service_role;

-- Base grants for authenticated (RLS then restricts rows). We grant broadly and let
-- policies + targeted REVOKEs (below) decide what actually applies.
grant select, insert, update, delete on all tables in schema ff to authenticated;

-- Enable RLS on every table in ff
do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = 'ff' loop
    execute format('alter table ff.%I enable row level security', r.tablename);
    execute format('alter table ff.%I force row level security', r.tablename);
  end loop;
end $$;

-- Generic org-scoped SELECT + INSERT policies for every table that has an org_id column
do $$
declare r record;
begin
  for r in
    select c.relname as tbl
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid and a.attname = 'org_id'
    where n.nspname = 'ff' and c.relkind = 'r'
  loop
    execute format($f$
      drop policy if exists org_select on ff.%1$I;
      create policy org_select on ff.%1$I for select to authenticated
        using (ff.is_org_member(org_id));
      drop policy if exists org_insert on ff.%1$I;
      create policy org_insert on ff.%1$I for insert to authenticated
        with check (ff.is_org_member(org_id));
    $f$, r.tbl);
  end loop;
end $$;

-- Mutable-by-user tables get an UPDATE policy (admins/authors). Everything else stays
-- effectively append-only for `authenticated`.
do $$
declare t text;
begin
  foreach t in array array[
    'patients','patient_identifiers','reports','review_sessions',
    'annotation_tasks','annotation_assignments'
  ] loop
    execute format($f$
      drop policy if exists org_update on ff.%1$I;
      create policy org_update on ff.%1$I for update to authenticated
        using (ff.is_org_member(org_id)) with check (ff.is_org_member(org_id));
    $f$, t);
  end loop;
end $$;

-- Append-only tables: revoke UPDATE/DELETE from authenticated (defense in depth;
-- there are also no update/delete policies, so RLS already blocks them).
do $$
declare t text;
begin
  foreach t in array array[
    'report_versions','frames','tracks','track_events',
    'link_decisions','target_lesion_selections','recist_assessments',
    'reviews','signoffs','audit_log','annotation_records','adjudications','gold_candidates',
    'extraction_runs'   -- end users never mutate runs; only the worker (service_role) does
  ] loop
    execute format('revoke update, delete on ff.%I from authenticated', t);
  end loop;
end $$;

-- audit_log: readable by org members, never mutable by users (writes come from service_role)
revoke insert on ff.audit_log from authenticated;

-- ---------------------------------------------------------------------------
-- Special-case tables (no org_id, or org_id-independent visibility)
-- ---------------------------------------------------------------------------

-- orgs: a user sees orgs they belong to
alter table ff.orgs enable row level security;
alter table ff.orgs force row level security;
drop policy if exists orgs_select on ff.orgs;
create policy orgs_select on ff.orgs for select to authenticated
  using (ff.is_org_member(id));
drop policy if exists orgs_update on ff.orgs;
create policy orgs_update on ff.orgs for update to authenticated
  using (ff.has_org_role(id, array['admin']::ff.member_role[]))
  with check (ff.has_org_role(id, array['admin']::ff.member_role[]));
-- org creation goes through the backend (service_role) to also create the admin membership.
revoke insert, delete on ff.orgs from authenticated;

-- profiles: self only
alter table ff.profiles enable row level security;
alter table ff.profiles force row level security;
drop policy if exists profiles_self on ff.profiles;
create policy profiles_self on ff.profiles for select to authenticated using (id = auth.uid());
drop policy if exists profiles_self_upd on ff.profiles;
create policy profiles_self_upd on ff.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
drop policy if exists profiles_self_ins on ff.profiles;
create policy profiles_self_ins on ff.profiles for insert to authenticated with check (id = auth.uid());

-- memberships: a user sees their own; org admins see all in their org.
alter table ff.memberships enable row level security;
alter table ff.memberships force row level security;
drop policy if exists memberships_read on ff.memberships;
create policy memberships_read on ff.memberships for select to authenticated
  using (user_id = auth.uid() or ff.has_org_role(org_id, array['admin']::ff.member_role[]));
-- membership writes go through the backend (service_role).
revoke insert, update, delete on ff.memberships from authenticated;

commit;
