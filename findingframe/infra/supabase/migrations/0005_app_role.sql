-- FindingFrame — least-privilege application role (Fable milestone review, move #3).
-- The backend previously connected as the `postgres` SUPERUSER, which bypasses RLS,
-- ignores REVOKE, and can DROP/DISABLE the append-only triggers or TRUNCATE around them.
-- `ff_app` is nosuperuser: append-only triggers, column-scoped grants, and object
-- ownership all now genuinely apply to the backend connection.
--   - nosuperuser  -> triggers + REVOKE + grants are enforced against it
--   - bypassrls    -> tenant scoping stays app-level (unchanged); moving RLS to a
--                     per-request GUC tenant boundary is the remaining M2 step (documented)
--   - not table owner -> cannot DROP/ALTER/DISABLE TRIGGER, cannot TRUNCATE (no grant)
-- Password is set out-of-band (never committed); see infra/scripts (ALTER ROLE ... PASSWORD).

begin;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'ff_app') then
    create role ff_app login nosuperuser bypassrls nocreatedb nocreaterole noreplication;
  else
    alter role ff_app login nosuperuser bypassrls nocreatedb nocreaterole noreplication;
  end if;
end $$;

grant connect on database postgres to ff_app;
grant usage on schema ff, extensions to ff_app;

-- Default: read + append only. No blanket UPDATE/DELETE.
grant select, insert on all tables in schema ff to ff_app;
grant usage, select on all sequences in schema ff to ff_app;
alter default privileges in schema ff grant select, insert on tables to ff_app;
alter default privileges in schema ff grant usage, select on sequences to ff_app;

-- extraction_runs: job-lifecycle columns only (manifest columns stay frozen — also enforced by trigger).
grant update (status, attempts, locked_by, locked_at, progress_total, progress_done,
              checkpoint, started_at, finished_at, cost_usd, latency_ms, error)
  on ff.extraction_runs to ff_app;

-- DPDP erasure targets the PII vault only.
grant update, delete on ff.patient_identifiers to ff_app;

-- Mutable-by-app domain tables (append-only tables are intentionally excluded).
grant update on ff.orgs, ff.profiles, ff.patients, ff.reports, ff.review_sessions,
                ff.annotation_tasks, ff.annotation_assignments to ff_app;

commit;

-- Follow-up: the worker's shared LLM token-bucket needs UPDATE on its coordination table.
grant select, insert, update on ff.llm_rate_limit to ff_app;
