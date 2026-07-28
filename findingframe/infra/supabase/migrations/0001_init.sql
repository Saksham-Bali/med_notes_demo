-- FindingFrame — initial schema (audit-grade, multi-tenant)
-- Postgres 17 / Supabase. Idempotent-ish: guarded by IF NOT EXISTS where practical.
--
-- Design invariants (see strategy/PRODUCT_BUILD_PLAN.md §8):
--   R1  Human-confirmed linking is first-class (link_decisions, target_lesion_selections);
--       RECIST is computed ONLY over human-confirmed tracks.
--   R2  Clinical validation (kappa) is a designed, blinded study, modeled now
--       (annotation_tasks / assignments / adjudications / gold_candidates with contamination flags).
--   R3  Audit-grade = immutable extraction_runs + reproducibility manifest,
--       reviews pin a run and snapshot what was seen, hash-chained sign-off + audit log,
--       PII separated for DPDP erasure, reports versioned for addenda.
--
-- Tenancy: every domain row carries org_id. RLS scopes reads/writes to org membership.
-- Append-only tables have NO update/delete policy AND revoke UPDATE/DELETE from app roles.

begin;

-- Allow forward references from SQL function bodies to tables created later in this file.
set local check_function_bodies = off;

create schema if not exists ff;
comment on schema ff is 'FindingFrame application schema';

create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
do $$ begin
  create type ff.member_role as enum ('admin','reviewer','viewer');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ff.run_status as enum ('queued','running','succeeded','failed','canceled');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ff.assertion as enum ('present','absent','uncertain','not_mentioned');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ff.link_decision_kind as enum ('confirm','merge','split','mark_unresolved','reject');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ff.recist_class as enum ('CR','PR','SD','PD','NE');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ff.agreement_unit as enum ('slot','frame','track');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ff.signoff_scope as enum ('patient','track');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Shared helpers
-- ---------------------------------------------------------------------------
create or replace function ff.set_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

-- Membership / role helpers used by RLS policies. SECURITY DEFINER so the
-- policy can read ff.memberships without recursing through its own RLS.
create or replace function ff.is_org_member(p_org uuid) returns boolean
language sql stable security definer set search_path = ff, public as $$
  select exists (
    select 1 from ff.memberships m
    where m.org_id = p_org and m.user_id = auth.uid()
  );
$$;

create or replace function ff.has_org_role(p_org uuid, p_roles ff.member_role[]) returns boolean
language sql stable security definer set search_path = ff, public as $$
  select exists (
    select 1 from ff.memberships m
    where m.org_id = p_org and m.user_id = auth.uid() and m.role = any(p_roles)
  );
$$;

-- ---------------------------------------------------------------------------
-- Identity & tenancy
-- ---------------------------------------------------------------------------
create table if not exists ff.orgs (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  region      text not null default 'ap-southeast-1',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Mirrors auth.users (Supabase). One row per platform user.
create table if not exists ff.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  full_name   text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists ff.memberships (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references ff.orgs(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        ff.member_role not null default 'reviewer',
  created_at  timestamptz not null default now(),
  unique (org_id, user_id)
);
create index if not exists memberships_user_idx on ff.memberships(user_id);

-- ---------------------------------------------------------------------------
-- Patients — pseudonymized clinical anchor (NO direct identifiers here)
-- ---------------------------------------------------------------------------
create table if not exists ff.patients (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references ff.orgs(id) on delete cascade,
  subject_code  text not null,                 -- pseudonym / external study code, NOT a name
  cancer_type   text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid references auth.users(id),
  unique (org_id, subject_code)
);
create index if not exists patients_org_idx on ff.patients(org_id);

-- PII vault — DPDP erasure = delete this row; clinical artifacts remain pseudonymized.
-- Values are encrypted at rest with pgcrypto (key supplied by the app, never stored in-DB).
create table if not exists ff.patient_identifiers (
  patient_id    uuid primary key references ff.patients(id) on delete cascade,
  org_id        uuid not null references ff.orgs(id) on delete cascade,
  mrn_enc       bytea,     -- pgp_sym_encrypt(mrn, key)
  name_enc      bytea,
  dob_enc       bytea,
  extra_enc     bytea,     -- json blob for any other identifiers
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid references auth.users(id)
);

-- ---------------------------------------------------------------------------
-- Reports — versioned (radiology addenda/amendments are routine)
-- ---------------------------------------------------------------------------
create table if not exists ff.reports (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid not null references ff.orgs(id) on delete cascade,
  patient_id        uuid not null references ff.patients(id) on delete cascade,
  report_date       timestamptz not null,          -- charttime
  note_type         text not null default 'RR',
  external_note_id  text,                           -- MIMIC note_id or hospital accession
  created_at        timestamptz not null default now(),
  created_by        uuid references auth.users(id)
);
create index if not exists reports_patient_idx on ff.reports(patient_id, report_date);

create table if not exists ff.report_versions (
  id             uuid primary key default gen_random_uuid(),
  report_id      uuid not null references ff.reports(id) on delete cascade,
  org_id         uuid not null references ff.orgs(id) on delete cascade,
  version_no     int not null default 1,
  text           text not null,
  text_sha256    text not null,                     -- hex sha256 of text
  is_addendum    boolean not null default false,
  created_at     timestamptz not null default now(),
  created_by     uuid references auth.users(id),
  unique (report_id, version_no)
);
create index if not exists report_versions_report_idx on ff.report_versions(report_id);

-- ---------------------------------------------------------------------------
-- Extraction runs — IMMUTABLE artifacts with a reproducibility manifest
-- ---------------------------------------------------------------------------
create table if not exists ff.extraction_runs (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references ff.orgs(id) on delete cascade,
  patient_id         uuid not null references ff.patients(id) on delete cascade,
  status             ff.run_status not null default 'queued',
  -- reproducibility manifest --------------------------------------------------
  engine_git_sha     text,
  model_provider     text,
  model_id           text,
  prompt_version     text,
  schema_version     text,
  temperature        numeric,
  reasoning_effort   text,
  manifest_hash      text,        -- sha256 over ordered (report_version_id, text_sha256) + params
  report_manifest    jsonb not null default '[]'::jsonb,  -- [{report_id, report_version_id, text_sha256, source_report_id}]
  -- accounting ----------------------------------------------------------------
  cost_usd           numeric,
  latency_ms         bigint,
  error              text,
  -- job / checkpointing (Postgres-backed queue, FOR UPDATE SKIP LOCKED) -------
  attempts           int not null default 0,
  locked_by          text,
  locked_at          timestamptz,
  progress_total     int not null default 0,
  progress_done      int not null default 0,
  checkpoint         jsonb not null default '{}'::jsonb,   -- per-report resume state
  created_at         timestamptz not null default now(),
  created_by         uuid references auth.users(id),
  started_at         timestamptz,
  finished_at        timestamptz
);
create index if not exists runs_patient_idx on ff.extraction_runs(patient_id, created_at desc);
create index if not exists runs_queue_idx on ff.extraction_runs(status, created_at)
  where status in ('queued','running');

-- Frames belong to a run (immutable once the run succeeds)
create table if not exists ff.frames (
  id                   uuid primary key default gen_random_uuid(),
  run_id               uuid not null references ff.extraction_runs(id) on delete cascade,
  org_id               uuid not null references ff.orgs(id) on delete cascade,
  patient_id           uuid not null references ff.patients(id) on delete cascade,
  report_version_id    uuid references ff.report_versions(id) on delete set null,
  source_report_id     text,             -- engine's report_N
  frame_index          int,
  track_key            text not null,    -- finding_type|anatomy|laterality[|lesion_key]
  finding_type         text not null,
  finding_surface      text,
  assertion            ff.assertion not null default 'present',
  anatomy              text,
  laterality           text,
  uncertainty          text,
  temporal_change      text,
  measurement          jsonb,            -- {raw,value,values,unit,normalized_mm,text}
  clinical_importance  text,
  severity             text,
  evidence_text        text not null,
  evidence_span_start  int default -1,
  evidence_span_end    int default -1,
  evidence_verified    boolean not null default false,  -- gate: span located in source
  review_only          boolean not null default false,
  lesion_key           text,
  created_at           timestamptz not null default now()
);
create index if not exists frames_run_idx on ff.frames(run_id);
create index if not exists frames_track_idx on ff.frames(run_id, track_key);

-- Machine-proposed tracks (deterministic linker output for a run)
create table if not exists ff.tracks (
  id                    uuid primary key default gen_random_uuid(),
  run_id                uuid not null references ff.extraction_runs(id) on delete cascade,
  org_id                uuid not null references ff.orgs(id) on delete cascade,
  patient_id            uuid not null references ff.patients(id) on delete cascade,
  track_key             text not null,
  finding_type          text,
  anatomy               text,
  laterality            text,
  latest_status         text,
  progression           text,
  progression_detail    text,
  event_count           int not null default 0,
  measurement_trend     text,
  report_range          text,
  unresolved_link       boolean not null default false,  -- surface these first in review
  false_split_candidate boolean not null default false,
  clinical_section      text,   -- needs_attention/stable/resolved/uncertain/routine_negative
  created_at            timestamptz not null default now(),
  unique (run_id, track_key)
);
create index if not exists tracks_run_idx on ff.tracks(run_id);

create table if not exists ff.track_events (
  id                 uuid primary key default gen_random_uuid(),
  track_id           uuid not null references ff.tracks(id) on delete cascade,
  frame_id           uuid references ff.frames(id) on delete set null,
  org_id             uuid not null references ff.orgs(id) on delete cascade,
  report_version_id  uuid references ff.report_versions(id) on delete set null,
  event_date         timestamptz,
  assertion          ff.assertion,
  evidence_text      text,
  temporal_change    text,
  measurement        jsonb,
  created_at         timestamptz not null default now()
);
create index if not exists track_events_track_idx on ff.track_events(track_id, event_date);

-- ---------------------------------------------------------------------------
-- R1: HUMAN-confirmed linking (the most important table). Append-only, signed.
-- ---------------------------------------------------------------------------
create table if not exists ff.link_decisions (
  id                  uuid primary key default gen_random_uuid(),
  org_id              uuid not null references ff.orgs(id) on delete cascade,
  patient_id          uuid not null references ff.patients(id) on delete cascade,
  run_id              uuid not null references ff.extraction_runs(id) on delete cascade,
  decision            ff.link_decision_kind not null,
  primary_track_key   text not null,
  related_track_keys  jsonb not null default '[]'::jsonb,
  resulting_track_key text,             -- the human-confirmed identity
  rationale           text,
  decided_by          uuid not null references auth.users(id),
  decided_at          timestamptz not null default now(),
  signature_sha256    text
);
create index if not exists link_decisions_run_idx on ff.link_decisions(run_id);

-- R1: RECIST baseline is a human act (<=5 targets, <=2/organ). Append-only, signed.
create table if not exists ff.target_lesion_selections (
  id                        uuid primary key default gen_random_uuid(),
  org_id                    uuid not null references ff.orgs(id) on delete cascade,
  patient_id                uuid not null references ff.patients(id) on delete cascade,
  run_id                    uuid not null references ff.extraction_runs(id) on delete cascade,
  baseline_report_version_id uuid references ff.report_versions(id),
  selections                jsonb not null,  -- [{confirmed_track_key, organ, baseline_mm}]
  selected_by               uuid not null references auth.users(id),
  selected_at               timestamptz not null default now(),
  signature_sha256          text,
  -- RECIST 1.1 caps enforced app-side; a coarse guard here:
  constraint target_cap check (jsonb_array_length(selections) <= 5)
);
create index if not exists target_sel_run_idx on ff.target_lesion_selections(run_id);

-- RECIST assessments — computed ONLY over human-confirmed tracks. Immutable history.
create table if not exists ff.recist_assessments (
  id                       uuid primary key default gen_random_uuid(),
  org_id                   uuid not null references ff.orgs(id) on delete cascade,
  patient_id               uuid not null references ff.patients(id) on delete cascade,
  run_id                   uuid not null references ff.extraction_runs(id) on delete cascade,
  target_selection_id      uuid references ff.target_lesion_selections(id),
  assessment_date          timestamptz not null,
  sld_mm                   numeric,
  baseline_sld_mm          numeric,
  nadir_sld_mm             numeric,
  pct_from_baseline        numeric,
  pct_from_nadir           numeric,
  classification           ff.recist_class,
  new_lesion               boolean not null default false,
  inputs                   jsonb not null default '{}'::jsonb,  -- per-lesion measurements + confirmed tracks
  computed_at              timestamptz not null default now()
);
create index if not exists recist_run_idx on ff.recist_assessments(run_id, assessment_date);

-- ---------------------------------------------------------------------------
-- Reviews — slot-level feedback. Pins a run + snapshots exactly what was seen.
-- Append-only.
-- ---------------------------------------------------------------------------
create table if not exists ff.reviews (
  id                       uuid primary key default gen_random_uuid(),
  org_id                   uuid not null references ff.orgs(id) on delete cascade,
  patient_id               uuid not null references ff.patients(id) on delete cascade,
  run_id                   uuid not null references ff.extraction_runs(id) on delete cascade,
  track_id                 uuid references ff.tracks(id) on delete set null,
  track_key                text not null,
  reviewer_id              uuid not null references auth.users(id),
  reviewed_value           jsonb not null,  -- snapshot of the digest the reviewer saw
  link_correct             boolean,
  type_correct             boolean,
  progression_correct      boolean,
  latest_status_correct    boolean,
  false_merge              boolean,
  false_split              boolean,
  evidence_valid           boolean,
  clinically_significant   boolean,
  correction_finding_type  text,
  correction_anatomy       text,
  correction_laterality    text,
  comment                  text,
  model_output_visible     boolean not null default true,  -- production review = anchored (NOT IRR)
  assignment_id            uuid,           -- set only for blinded IRR annotations
  created_at               timestamptz not null default now()
);
create index if not exists reviews_run_idx on ff.reviews(run_id);
create index if not exists reviews_reviewer_idx on ff.reviews(reviewer_id, created_at);

-- Time-saved instrumentation (the ~1hr -> ~20min ROI number)
create table if not exists ff.review_sessions (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references ff.orgs(id) on delete cascade,
  patient_id       uuid not null references ff.patients(id) on delete cascade,
  run_id           uuid references ff.extraction_runs(id) on delete set null,
  reviewer_id      uuid not null references auth.users(id),
  started_at       timestamptz not null default now(),
  ended_at         timestamptz,
  tracks_reviewed  int not null default 0,
  active_seconds   int not null default 0
);

-- ---------------------------------------------------------------------------
-- R3: Sign-off (hash-chained) + append-only audit log
-- ---------------------------------------------------------------------------
create table if not exists ff.signoffs (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references ff.orgs(id) on delete cascade,
  patient_id         uuid not null references ff.patients(id) on delete cascade,
  run_id             uuid not null references ff.extraction_runs(id) on delete cascade,
  scope              ff.signoff_scope not null default 'patient',
  payload            jsonb not null,       -- run + review deltas + link decisions + recist inputs
  payload_sha256     text not null,
  prev_signoff_sha256 text,                -- hash chain within (org, patient)
  signed_by          uuid not null references auth.users(id),
  signed_at          timestamptz not null default now()
);
create index if not exists signoffs_patient_idx on ff.signoffs(patient_id, signed_at);

create table if not exists ff.audit_log (
  id            bigint generated always as identity primary key,
  org_id        uuid,
  actor_id      uuid,
  action        text not null,
  entity_type   text,
  entity_id     text,
  before        jsonb,
  after         jsonb,
  request_id    text,
  prev_hash     text,
  row_hash      text,
  created_at    timestamptz not null default now()
);
create index if not exists audit_org_idx on ff.audit_log(org_id, created_at desc);

-- ---------------------------------------------------------------------------
-- R2: Clinical validation (blinded IRR / kappa) — modeled now, run via scripts
-- ---------------------------------------------------------------------------
create table if not exists ff.annotation_tasks (
  id                 uuid primary key default gen_random_uuid(),
  org_id             uuid not null references ff.orgs(id) on delete cascade,
  protocol_id        text not null,
  name               text not null,
  unit_of_agreement  ff.agreement_unit not null,
  description        text,
  created_at         timestamptz not null default now(),
  created_by         uuid references auth.users(id)
);

create table if not exists ff.annotation_assignments (
  id                   uuid primary key default gen_random_uuid(),
  task_id              uuid not null references ff.annotation_tasks(id) on delete cascade,
  org_id               uuid not null references ff.orgs(id) on delete cascade,
  annotator_id         uuid not null references auth.users(id),
  run_id               uuid references ff.extraction_runs(id) on delete set null,
  model_output_visible boolean not null default false,   -- blinded by default for IRR
  independence_group   text,
  status               text not null default 'assigned',
  created_at           timestamptz not null default now()
);

create table if not exists ff.annotation_records (
  id            uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references ff.annotation_assignments(id) on delete cascade,
  org_id        uuid not null references ff.orgs(id) on delete cascade,
  item_ref      text not null,     -- frame_id / track_key / slot ref
  labels        jsonb not null,
  created_at    timestamptz not null default now()
);

create table if not exists ff.adjudications (
  id                     uuid primary key default gen_random_uuid(),
  task_id                uuid not null references ff.annotation_tasks(id) on delete cascade,
  org_id                 uuid not null references ff.orgs(id) on delete cascade,
  item_ref               text not null,
  resolves_assignment_ids jsonb not null default '[]'::jsonb,
  consensus              jsonb not null,
  adjudicator_id         uuid not null references auth.users(id),
  created_at             timestamptz not null default now()
);

create table if not exists ff.gold_candidates (
  id                        uuid primary key default gen_random_uuid(),
  org_id                    uuid not null references ff.orgs(id) on delete cascade,
  task_id                   uuid references ff.annotation_tasks(id) on delete set null,
  item_ref                  text not null,
  gold                      jsonb not null,
  contamination_model_visible boolean not null default true,  -- was model output visible when created?
  source                    text not null default 'adjudication', -- adjudication | engineering
  created_at                timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['orgs','profiles','patients','patient_identifiers'] loop
    execute format('drop trigger if exists set_updated_at on ff.%I', t);
    execute format('create trigger set_updated_at before update on ff.%I for each row execute function ff.set_updated_at()', t);
  end loop;
end $$;

commit;
