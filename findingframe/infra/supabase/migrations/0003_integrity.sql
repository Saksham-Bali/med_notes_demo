-- FindingFrame — audit-grade integrity hardening (Fable schema review, 2026-07-17)
-- Applied while the DB is still empty. Fixes the three load-bearing defects:
--   (1) immutability must survive the writer (superuser backend bypasses RLS/REVOKE)
--       -> BEFORE UPDATE/DELETE triggers on append-only tables (fire for ALL roles);
--          seeds/migrations bypass via `SET session_replication_role = replica`.
--   (2) cascade-delete must not erase signed history -> ON DELETE RESTRICT.
--   (3) hash chains must be real -> DB-computed, genesis-defined, race-safe, tamper-evident.
-- Deferred to M2 (documented in BUILD_SPEC): non-superuser ff_app DSN switch + RLS-as-tenant-boundary;
--   crypto-shredding of free-text PII (demo uses de-identified MIMIC, so no live PII).

begin;
set local check_function_bodies = off;

-- ---------------------------------------------------------------------------
-- (1) Append-only enforcement for EVERY role (including the superuser backend).
--     Standard triggers do not fire when session_replication_role='replica',
--     which is how the seed/reset (superuser) performs maintenance.
-- ---------------------------------------------------------------------------
create or replace function ff.forbid_mutation() returns trigger
language plpgsql as $$
begin
  raise exception 'ff.% is append-only (% blocked)', tg_table_name, tg_op
    using errcode = 'raise_exception';
end $$;

do $$
declare t text;
begin
  foreach t in array array[
    'report_versions','frames','tracks','track_events',
    'link_decisions','target_lesion_selections','recist_assessments',
    'reviews','signoffs','audit_log','annotation_records','adjudications','gold_candidates'
  ] loop
    execute format('drop trigger if exists append_only on ff.%I', t);
    execute format(
      'create trigger append_only before update or delete on ff.%I
         for each row execute function ff.forbid_mutation()', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- (2) Stop cascading immutable/signed history away. Patient deletion must be
--     blocked while clinical artifacts exist (erasure targets patient_identifiers).
-- ---------------------------------------------------------------------------
do $$
declare
  rec record;
  -- Only tables that actually carry patient_id. Their children (track_events via tracks,
  -- report_versions via reports) are protected transitively once these RESTRICT, and we
  -- also RESTRICT reports + extraction_runs so the cascade path can't erase them.
  restrict_tables text[] := array[
    'frames','tracks','reports','extraction_runs',
    'link_decisions','target_lesion_selections','recist_assessments',
    'reviews','signoffs'
  ];
  t text;
begin
  foreach t in array restrict_tables loop
    for rec in
      select conname from pg_constraint
      where conrelid = ('ff.'||t)::regclass and contype='f'
        and confrelid = 'ff.patients'::regclass
    loop
      execute format('alter table ff.%I drop constraint %I', t, rec.conname);
    end loop;
    execute format(
      'alter table ff.%I add constraint %I foreign key (patient_id)
         references ff.patients(id) on delete restrict', t, t||'_patient_fk');
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- (3a) extraction_runs: freeze the reproducibility manifest once succeeded, and
--      require the manifest to be complete on success. Job-lifecycle columns stay mutable.
-- ---------------------------------------------------------------------------
create or replace function ff.guard_extraction_run_update() returns trigger
language plpgsql as $$
begin
  if old.status = 'succeeded' then
    if new.engine_git_sha is distinct from old.engine_git_sha
       or new.model_provider is distinct from old.model_provider
       or new.model_id is distinct from old.model_id
       or new.prompt_version is distinct from old.prompt_version
       or new.schema_version is distinct from old.schema_version
       or new.temperature is distinct from old.temperature
       or new.manifest_hash is distinct from old.manifest_hash
       or new.report_manifest is distinct from old.report_manifest then
      raise exception 'extraction_runs manifest is frozen after success';
    end if;
  end if;
  if new.status = 'succeeded' then
    if new.manifest_hash is null or new.engine_git_sha is null or new.model_id is null then
      raise exception 'succeeded run requires manifest_hash, engine_git_sha, model_id';
    end if;
  end if;
  return new;
end $$;

drop trigger if exists guard_run_update on ff.extraction_runs;
create trigger guard_run_update before update on ff.extraction_runs
  for each row execute function ff.guard_extraction_run_update();

-- ---------------------------------------------------------------------------
-- (3b) Hash chains, computed IN the database (survive a buggy backend).
--      Preimage covers the whole meaningful row, not just a payload hash.
-- ---------------------------------------------------------------------------
alter table ff.signoffs add column if not exists row_sha256 text;

-- signoffs: chain per (org_id, patient_id)
create or replace function ff.chain_signoff() returns trigger
language plpgsql as $$
declare head text;
begin
  perform pg_advisory_xact_lock(hashtext('signoff:'||new.org_id::text||':'||new.patient_id::text));
  select row_sha256 into head from ff.signoffs
    where org_id = new.org_id and patient_id = new.patient_id
    order by signed_at desc, id desc limit 1;
  new.prev_signoff_sha256 := head;  -- null for genesis
  new.payload_sha256 := encode(digest(
      convert_to(coalesce(new.payload::text,''),'UTF8'),'sha256'),'hex');
  new.row_sha256 := encode(digest(convert_to(
      coalesce(head,'GENESIS') || '|' || new.payload_sha256 || '|' ||
      coalesce(new.run_id::text,'') || '|' || new.scope::text || '|' ||
      new.signed_by::text || '|' || coalesce(new.signed_at::text, now()::text),
      'UTF8'),'sha256'),'hex');
  return new;
end $$;

drop trigger if exists chain_signoff on ff.signoffs;
create trigger chain_signoff before insert on ff.signoffs
  for each row execute function ff.chain_signoff();

-- race-safety: one child per head, one genesis per patient
create unique index if not exists signoffs_chain_uidx
  on ff.signoffs (patient_id, prev_signoff_sha256);
create unique index if not exists signoffs_genesis_uidx
  on ff.signoffs (patient_id) where prev_signoff_sha256 is null;

-- audit_log: chain per org_id
alter table ff.audit_log alter column org_id set not null;
create or replace function ff.chain_audit() returns trigger
language plpgsql as $$
declare head text;
begin
  perform pg_advisory_xact_lock(hashtext('audit:'||new.org_id::text));
  select row_hash into head from ff.audit_log
    where org_id = new.org_id order by id desc limit 1;
  new.prev_hash := head;
  new.row_hash := encode(digest(convert_to(
      coalesce(head,'GENESIS') || '|' || new.action || '|' ||
      coalesce(new.entity_type,'') || '|' || coalesce(new.entity_id,'') || '|' ||
      coalesce(new.actor_id::text,'system') || '|' ||
      coalesce(new.before::text,'') || '|' || coalesce(new.after::text,'') || '|' ||
      coalesce(new.created_at::text, now()::text),'UTF8'),'sha256'),'hex');
  return new;
end $$;

drop trigger if exists chain_audit on ff.audit_log;
create trigger chain_audit before insert on ff.audit_log
  for each row execute function ff.chain_audit();

-- ---------------------------------------------------------------------------
-- (4) Referential integrity + invariants Fable flagged
-- ---------------------------------------------------------------------------
-- link_decisions.primary_track_key must reference a real track for the run
do $$ begin
  alter table ff.link_decisions
    add constraint link_primary_track_fk
    foreign key (run_id, primary_track_key)
    references ff.tracks(run_id, track_key) on delete restrict;
exception when duplicate_object then null; end $$;

-- reviews.assignment_id provenance (R2 blinded-vs-contaminated)
do $$ begin
  alter table ff.reviews
    add constraint reviews_assignment_fk
    foreign key (assignment_id) references ff.annotation_assignments(id) on delete set null;
exception when duplicate_object then null; end $$;

-- RECIST must be derived from a human target selection (R1 made structural)
alter table ff.recist_assessments alter column target_selection_id set not null;
-- and idempotent so a re-compute doesn't duplicate immutable history
create unique index if not exists recist_idem_uidx
  on ff.recist_assessments (run_id, target_selection_id, assessment_date);

-- frames: no duplicate on crash-resume
create unique index if not exists frames_dedupe_uidx
  on ff.frames (run_id, source_report_id, frame_index);

-- audit_log hash columns are now authoritative -> not null
alter table ff.audit_log alter column row_hash set not null;

-- ---------------------------------------------------------------------------
-- (5) RLS: for the direct frontend->Supabase path, enforce role + actor binding
--     (defense-in-depth; the backend still scopes by org in the service layer).
--     Viewers may read but not perform clinical actions; actors can't spoof identity.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['link_decisions','target_lesion_selections','reviews','signoffs'] loop
    execute format('drop policy if exists org_insert on ff.%I', t);
    execute format($p$
      create policy org_insert on ff.%1$I for insert to authenticated
        with check (ff.has_org_role(org_id, array['admin','reviewer']::ff.member_role[]))
    $p$, t);
  end loop;
end $$;

-- actor binding on the direct path
drop policy if exists org_insert on ff.link_decisions;
create policy org_insert on ff.link_decisions for insert to authenticated
  with check (ff.has_org_role(org_id, array['admin','reviewer']::ff.member_role[])
              and decided_by = auth.uid());
drop policy if exists org_insert on ff.reviews;
create policy org_insert on ff.reviews for insert to authenticated
  with check (ff.has_org_role(org_id, array['admin','reviewer']::ff.member_role[])
              and reviewer_id = auth.uid());
drop policy if exists org_insert on ff.signoffs;
create policy org_insert on ff.signoffs for insert to authenticated
  with check (ff.has_org_role(org_id, array['admin','reviewer']::ff.member_role[])
              and signed_by = auth.uid());
drop policy if exists org_insert on ff.target_lesion_selections;
create policy org_insert on ff.target_lesion_selections for insert to authenticated
  with check (ff.has_org_role(org_id, array['admin','reviewer']::ff.member_role[])
              and selected_by = auth.uid());

-- ---------------------------------------------------------------------------
-- (6) Housekeeping
-- ---------------------------------------------------------------------------
drop extension if exists "uuid-ossp";  -- unused; gen_random_uuid() is core/pgcrypto in PG17

commit;
