# FindingFrame — R6 Vertical Slice Build Spec (contract for build agents)

Read `strategy/PRODUCT_BUILD_PLAN.md` §8 (R1–R6) first. This spec is the fixed contract; do not
re-decide architecture. Build the **R6 vertical slice**: one patient → durable extraction run →
review workbench (verbatim evidence, gate-failed facts quarantined) → human-confirmed track linking
→ RECIST worksheet with human target-lesion selection → signed, exported audit packet.

## Repo layout (fixed)
```
pre/findingframe/
  backend/app/{core,db,engine,jobs,services,schemas,api/v1/routers}   # FastAPI (Python 3.12)
  backend/.venv  backend/requirements.txt  backend/.env(.example)
  worker/                # extraction worker (imports backend.app)
  web/                   # Next.js 14 App Router (TS, Tailwind, TanStack Query, @supabase/supabase-js)
  infra/supabase/migrations  infra/scripts  infra/docker
  docs/
```
Backend venv: `pre/findingframe/backend/.venv` (python3.12). Engine at `pre/tmc` (do NOT edit it).

## Database (ALREADY APPLIED to Supabase — schema `ff`, 23 tables)
Migrations `infra/supabase/migrations/0001_init.sql`, `0002_rls.sql` are live. Key tables:
`orgs, profiles, memberships(role admin|reviewer|viewer), patients(subject_code, NO PII),
patient_identifiers(*_enc bytea, DPDP-deletable), reports, report_versions(text,text_sha256,version_no),
extraction_runs(status,manifest_hash,report_manifest,engine_git_sha,model_*,progress_*,checkpoint,locked_by),
frames, tracks(unresolved_link,false_split_candidate,clinical_section), track_events,
link_decisions(APPEND-ONLY,signed), target_lesion_selections(<=5,signed), recist_assessments,
reviews(pins run_id, reviewed_value snapshot, slot-correctness bools, model_output_visible),
review_sessions, signoffs(payload_sha256,prev_signoff_sha256 hash-chain), audit_log(append-only,hash-chain),
annotation_tasks/assignments/records, adjudications, gold_candidates(contamination_model_visible)`.
Append-only tables reject UPDATE/DELETE for `authenticated`. Enums in `ff.*` (assertion, run_status, etc.).

## Connectivity (verified)
- Postgres 17, Supabase project `cuhrmxeqcgkvggdzlrye`, region ap-southeast-1.
- Async DSN in `backend/.env` as `FF_DATABASE_URL` (asyncpg, direct IPv6 host; needs SSL + `server_settings={"search_path":"ff,public"}`).
- **Backend connects as `postgres` (superuser) = the tenant boundary.** RLS is defense-in-depth. Enforce org scoping in the service layer on EVERY query; never trust client-supplied org_id without a membership check.
- Auth: **ES256 JWTs verified via JWKS** (`FF_SUPABASE_JWKS_URL`) — no secret needed. Use `jwt.PyJWKClient`. Audience `authenticated`. `sub` = user id (matches auth.users.id / profiles.id).

## Engine adapter (DONE — use it, don't reimplement)
`app/engine/adapter.py::get_engine()` →
- `manifest_base() -> ExtractionManifest`
- `build_manifest(reports) -> ExtractionManifest` (deterministic `manifest_hash`)
- `extract_report(ReportInput) -> ReportExtraction`
- `process_patient(subject_code, [ReportInput]) -> PatientArtifact` (frames, tracks dict, track_graph, unresolved_link_queue, false_split_candidates, manifest, raw)
Types in `app/engine/types.py`. Frame dict fields mirror `ff.frames` columns (track_key, finding_type,
finding_surface, assertion, anatomy, laterality, temporal_change, measurement, evidence_text,
evidence_span_start/end, clinical_importance, review_only, lesion_key). `evidence_verified` = span located.

## REST API contract (`/api/v1`, all JSON, all require Bearer JWT except /health)
Every mutating call writes an `audit_log` row (actor, action, entity, before/after, request_id, hash-chain).

- `GET /health` (public) → `{status,engine_sha,db:"ok"}`
- `GET /me` → `{user:{id,email,full_name}, orgs:[{id,name,role}]}`
- **Patients**
  - `POST /patients` `{subject_code,cancer_type,identifiers?{mrn,name,dob}}` → creates patient (+ encrypted identifiers via pgcrypto `pgp_sym_encrypt` with `FF_PII_ENCRYPTION_KEY`). Requires org context (member's org).
  - `GET /patients` → list (org-scoped). `GET /patients/{id}` → detail (+ report count, latest run).
  - `DELETE /patients/{id}/identifiers` → DPDP erasure (delete PII row only; clinical artifacts remain).
- **Reports**
  - `POST /patients/{id}/reports` accepts one or a list `[{report_date,note_type,external_note_id,text}]` → creates `reports` + `report_versions` v1 with `text_sha256`. Addendum = new version on same report.
  - `GET /patients/{id}/reports` → list with current version.
- **Extraction runs**
  - `POST /patients/{id}/runs` → build manifest over current report versions; if a `succeeded` run with same `manifest_hash` exists, return it (idempotent); else insert `extraction_runs(status=queued)` and return it. Worker picks it up.
  - `GET /runs/{id}` → run + progress. `GET /patients/{id}/runs` → list.
  - `GET /runs/{id}/events` → SSE progress (optional; polling `GET /runs/{id}` is acceptable for the slice).
- **Digest / review**
  - `GET /runs/{id}/digest` → clinician digest built from persisted `frames`/`tracks`: sections
    (needs_attention/stable/resolved/uncertain/routine_negatives), each track with events (date, evidence_text,
    assertion, measurement, `full_text` of source report), plus `unresolved_link`/`false_split_candidate` flags,
    and a `gate_failed` list (frames with `evidence_verified=false`) that MUST be surfaced for mandatory review.
  - `POST /runs/{id}/reviews` `{track_key, reviewed_value, link_correct,type_correct,progression_correct,
    latest_status_correct,false_merge,false_split,evidence_valid,clinically_significant,
    correction_*?,comment?}` → append `reviews` (model_output_visible=true).
  - `GET /runs/{id}/reviews`.
- **Human-confirmed linking (R1)**
  - `POST /runs/{id}/link-decisions` `{decision(confirm|merge|split|mark_unresolved|reject),primary_track_key,
    related_track_keys?,resulting_track_key?,rationale?}` → append `link_decisions` (signed: sha256 of payload).
  - `GET /runs/{id}/link-decisions`; `GET /runs/{id}/confirmed-tracks` → tracks after applying decisions.
- **RECIST (R1 — only over confirmed tracks)**
  - `POST /runs/{id}/target-lesions` `{baseline_report_version_id,selections:[{confirmed_track_key,organ,baseline_mm}]}`
    validate ≤5 total and ≤2/organ → append `target_lesion_selections` (signed).
  - `GET /runs/{id}/recist` → compute per-timepoint SLD + PD/SD/PR/CR over confirmed target tracks; persist
    `recist_assessments`. Return **422** with a clear message if no confirmed tracks or no target selection exist
    (never render RECIST from unconfirmed linking).
- **Sign-off / audit / export**
  - `POST /patients/{id}/signoff` → build payload {run manifest + review deltas + link decisions + recist inputs},
    hash it, chain from prior signoff → insert `signoffs`.
  - `GET /patients/{id}/audit` → audit log (org-scoped).
  - `GET /runs/{id}/audit-packet` → **the demo centerpiece**: JSON bundle {patient(pseudonymized), manifest,
    frames+verbatim evidence, tracks, human link decisions, target selection, recist, reviews, signoffs}. Also
    offer `?format=csv` (flat facts+evidence) later.
- **Review sessions (time-saved ROI)**: `POST /review-sessions` (start), `PATCH /review-sessions/{id}` (end: active_seconds, tracks_reviewed).

## Worker (`worker/`, separate process, imports `app`)
Loop: `SELECT ... FROM ff.extraction_runs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`,
set status=running/locked_by/started_at → load report versions → `engine.process_patient(...)` →
persist frames/tracks/track_events (map artifact → rows), copy manifest fields, set progress_done/total,
cost/latency → status=succeeded/finished_at. On failure: status=failed + error, attempts++. Per-report
checkpointing in `checkpoint` jsonb (resume, don't restart). **Shared LLM rate limit** (5/min) via a Postgres
counter table or advisory lock — the engine's in-process limiter does NOT survive multiple workers. Retry/backoff
on transient LLM errors from M1 (not later). Everything the worker does → `audit_log`.

## Non-negotiable product/UX rules (Fable R1/R5)
- Every displayed fact shows its **verbatim source sentence**; clicking reveals the full source report.
- **Gate-failed facts (`evidence_verified=false`) are quarantined** and force-routed to review — never silently included. Claim = "100% source-linked; gate-failed facts quarantined for mandatory human review."
- **RECIST renders ONLY over human-confirmed tracks.** Surface `unresolved_link`/`false_split_candidate` first.
- Human-in-the-loop: nothing enters the signed record without clinician sign-off.
- Multi-tenant: org-scope every query; test it.

## Standards
Strong typing (Pydantic v2 DTOs backend, TS types frontend). Structured logging w/ request id. Typed errors,
no raw 500s. Tests per module (pytest; contract test for the engine adapter with a mocked LLM). Async SQLAlchemy 2.0.
