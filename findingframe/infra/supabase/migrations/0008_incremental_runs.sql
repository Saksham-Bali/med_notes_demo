-- 0008 — Incremental runs and carry-forward of human decisions.
--
-- Problem this solves (PRE_UPDATE_PLAN_2026-07-30.md P0-4): adding one report to a
-- patient forces a brand-new run over the whole history, and because every human
-- artifact is keyed to run_id — link_decisions carries a composite FK
-- (run_id, primary_track_key) -> tracks(run_id, track_key) — a reviewer's confirmed
-- linking, target selection and sign-off silently stop applying. In an eleven-report
-- series that means redoing ten reports of clinical work to record one new scan.
--
-- The seam that makes the fix possible is that human decisions reference STABLE
-- STRINGS (track_key = finding_type|anatomy|laterality, and confirmed_track_key), not
-- row identity. So a decision can be replayed onto the next run by key. What this
-- migration adds is the provenance to say that a replayed decision IS a replay — a
-- carried decision is a different act from a fresh one, and the record must say which.
--
-- Nothing here weakens reproducibility. An incremental run still stores the FULL
-- report_manifest for every report in the patient's history, so it remains
-- independently reproducible from its manifest alone. extraction_provenance records
-- which reports were served from the content-addressed extraction cache and which were
-- freshly read by the model — without it, "only one report was read" is an
-- unverifiable stage claim.
--
-- Idempotent: safe to re-run.

begin;

-- ---------------------------------------------------------------------------
-- Run lineage
-- ---------------------------------------------------------------------------
alter table ff.extraction_runs
  add column if not exists parent_run_id uuid references ff.extraction_runs(id) on delete restrict;

alter table ff.extraction_runs
  add column if not exists run_kind text not null default 'full';

-- Per-report record of how each report's frames were obtained on THIS run:
--   {"cache_served": [{report_version_id, source_report_id, text_sha256}, ...],
--    "freshly_extracted": [...], "llm_calls": <int>}
alter table ff.extraction_runs
  add column if not exists extraction_provenance jsonb not null default '{}'::jsonb;

alter table ff.extraction_runs drop constraint if exists extraction_runs_run_kind_chk;
alter table ff.extraction_runs
  add constraint extraction_runs_run_kind_chk check (run_kind in ('full', 'incremental'));

-- An incremental run must name the run it extends; a full run must not.
alter table ff.extraction_runs drop constraint if exists extraction_runs_parent_chk;
alter table ff.extraction_runs
  add constraint extraction_runs_parent_chk check (
    (run_kind = 'incremental' and parent_run_id is not null)
    or (run_kind = 'full' and parent_run_id is null)
  );

create index if not exists runs_parent_idx on ff.extraction_runs(parent_run_id);

-- ---------------------------------------------------------------------------
-- Carry-forward provenance on the human artifacts
-- ---------------------------------------------------------------------------
-- A carried row preserves the ORIGINAL decided_by / decided_at: the clinical act
-- happened once, at that time, by that person. These columns record where it came
-- from so a carried decision can never be mistaken for a fresh one.
alter table ff.link_decisions
  add column if not exists carried_from_run_id uuid references ff.extraction_runs(id);
alter table ff.link_decisions
  add column if not exists carried_from_decision_id uuid references ff.link_decisions(id);

alter table ff.target_lesion_selections
  add column if not exists carried_from_run_id uuid references ff.extraction_runs(id);
alter table ff.target_lesion_selections
  add column if not exists carried_from_selection_id uuid
    references ff.target_lesion_selections(id);

-- ---------------------------------------------------------------------------
-- Acknowledgement of new evidence on an already-confirmed track
-- ---------------------------------------------------------------------------
-- When report N+1 adds a measurement to a lesion whose identity is already confirmed,
-- the identity attestation stands — that is what a longitudinal track is for. But the
-- clinician must still see the new evidence, and seeing it must be recorded. Rather
-- than invent a new signed artifact, this reuses ff.reviews, whose own header comment
-- reads "Pins a run + snapshots exactly what was seen": reviewed_value already stores
-- the snapshot the reviewer had in front of them. review_kind distinguishes a full
-- slot-correctness review from an acknowledgement of added evidence.
alter table ff.reviews
  add column if not exists review_kind text not null default 'review';

alter table ff.reviews drop constraint if exists reviews_kind_chk;
alter table ff.reviews
  add constraint reviews_kind_chk check (review_kind in ('review', 'acknowledgement'));

-- ---------------------------------------------------------------------------
-- Freeze extraction_provenance after success, like the rest of the manifest
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
       or new.report_manifest is distinct from old.report_manifest
       or new.extraction_provenance is distinct from old.extraction_provenance
       or new.parent_run_id is distinct from old.parent_run_id
       or new.run_kind is distinct from old.run_kind then
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
-- Grants
-- ---------------------------------------------------------------------------
-- The worker writes extraction_provenance on the running->succeeded transition, so it
-- needs column UPDATE privilege. Immutability after success is enforced by the trigger
-- above, not by withholding the grant — the same argument 0007 makes for the manifest
-- columns. parent_run_id / run_kind are set at INSERT and are covered by the existing
-- table-level INSERT grant.
grant update (extraction_provenance) on ff.extraction_runs to ff_app;

commit;
