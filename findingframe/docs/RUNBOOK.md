# FindingFrame — R6 Vertical Slice Runbook

Everything below assumes `pre/findingframe/` as the working root (sibling of `pre/tmc/`, the
engine repo — do not edit `tmc/`). Backend venv: `backend/.venv` (Python 3.12).

## 0. One-time setup already done for you

- Supabase Postgres 17, project `cuhrmxeqcgkvggdzlrye`, region **ap-southeast-1**.
- `backend/.env` holds real secrets (`FF_DATABASE_URL`, `FF_SUPABASE_*`, `FF_PII_ENCRYPTION_KEY`,
  `FF_OPENROUTER_API_KEY`). Never commit it (already gitignored).
- `web/.env.local` holds the browser-side Supabase URL/anon key + `NEXT_PUBLIC_API_URL`.
  It currently defaults `NEXT_PUBLIC_API_MODE=mock` (runs the UI against an in-memory demo
  dataset, no backend needed). **Set it to `live` in `web/.env.local` to walk the real demo**
  below against the seeded backend/DB.

## 1. Apply migrations

```bash
infra/scripts/migrate.sh
```

Reads `FF_DATABASE_URL` out of `backend/.env`, applies every file in
`infra/supabase/migrations/` in lexical order (`0001_init.sql`, `0002_rls.sql`,
`0003_integrity.sql`, …) via `psql`. Safe to re-run — every migration is written
idempotently (`IF NOT EXISTS` / guarded `DO $$ ... EXCEPTION WHEN duplicate_object$$` /
`DROP ... IF EXISTS` before `CREATE`). Verified: three consecutive runs, zero errors.

Override the psql binary or env file if needed:
```bash
PSQL_BIN=/opt/homebrew/opt/postgresql@15/bin/psql FF_ENV_FILE=/path/to/other.env infra/scripts/migrate.sh
```

> Migration `0003_integrity.sql` hardens the schema: append-only tables (`frames`, `tracks`,
> `track_events`, `reviews`, `link_decisions`, `target_lesion_selections`,
> `recist_assessments`, `signoffs`, `audit_log`, …) now reject UPDATE/DELETE via triggers
> that fire for **every** role, including the superuser backend DSN — not just RLS. Patient
> deletion is `ON DELETE RESTRICT` while any clinical artifact exists. Hash chains
> (`audit_log.row_hash`, `signoffs.row_sha256`) are computed by DB triggers, not the app.

## 2. Seed the demo

```bash
backend/.venv/bin/python infra/scripts/seed_demo.py
```

Idempotent — re-running it is the standard way to reset the demo patient to a clean state.
It:

1. Creates (or reuses) org **"Tata Memorial (Demo)"**.
2. Creates (or reuses) a **confirmed** auth user — `demo@findingframe.dev` / `demo1234` —
   directly via SQL (`auth.users` + `auth.identities`, so GoTrue password login works),
   plus `ff.profiles` + `ff.memberships(role=admin)` in the demo org.
3. Resets and re-ingests patient **10000935** as a **completed** extraction run, sourced from
   `tmc/evaluation/track_annotations/full_review_packet_10000935.json` (tracks/events) and
   `tmc/outputs/paired_v1/subject_10000935_raw_reports.md` (source report text) — **no LLM
   call, no API key needed**. 37 reports, 1 extraction run (`status=succeeded`), 55 tracks,
   97 frames, 97 track_events.
   - Because append-only triggers now block `DELETE` (see §1), the reset step
     `TRUNCATE`s the demo-owned clinical tables (`patients`, `reports`, `report_versions`,
     `extraction_runs`, `tracks`, `frames`, `track_events`, `reviews`, `link_decisions`,
     `target_lesion_selections`, `recist_assessments`, `signoffs`) rather than deleting rows.
     This assumes the DB is dedicated to this demo — don't point it at a DB with other
     patients you want to keep.
4. Verifies the demo user can obtain an `access_token` from GoTrue's password grant.

Expected tail of output:
```
  ff.reports (patient 10000935): 37
  ff.extraction_runs (patient 10000935): 1
  ff.tracks (patient 10000935): 55
  ff.frames (patient 10000935): 97
  ff.report_versions (patient 10000935): 37
  ff.track_events (patient 10000935): 97

Verifying password login for demo@findingframe.dev ...
  OK: got access_token (len=808), token_type=bearer, expires_in=3600
```

Demo credentials: **demo@findingframe.dev / demo1234**.

### Vendoring the engine (R2 hardening — optional for local dev, required for Docker)

```bash
infra/scripts/vendor_engine.sh            # copy the allowlisted engine into infra/engine_vendor/
infra/scripts/vendor_engine.sh --dry-run  # print the plan only
```

Copies only what the frame path actually needs (verified by static import-graph analysis,
not just the directory names): `extraction/`, `pipeline/`, `fact_graph/`, `oncology_response/`,
`utils/`, `config/`, `telemetry/`, `clinical_dimensions/`, plus `entity_grounding/`,
`gc_system/`, `recist/` (transitively required — see the script's header comment for why),
and optionally `data/Radlex.xls`. Excludes `evaluation/`, `data/external_datasets/`,
`outputs/`, `paper*/`, `scratch/`, `research/`, `tests/`, `api/`, `frontend/`,
`model_comparison/`, `new_plan/`, `scripts/` — no simulated/fabricated IRR material ships.
Pins `infra/engine_vendor/VENDOR_SHA` to the tmc commit vendored. The script self-verifies
(no `*irr*`/`*simulate*` files, no excluded dirs, and a live `import extraction` /
`import pipeline` smoke test against the vendored copy).

Local dev (running backend/worker directly, not via Docker) does **not** need this —
`backend/.env`'s `FF_ENGINE_PATH=../../tmc` already points at the real engine.

## 3. Start the backend

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Check `curl http://localhost:8000/health` → `{"status":"ok","engine_sha":"...","db":"ok"}`.

## 4. Start the worker

```bash
backend/.venv/bin/python -m worker.main   # from the findingframe/ repo root
```

Polls `ff.extraction_runs` for `status='queued'` rows (`FOR UPDATE SKIP LOCKED`). Nothing
to do against the seeded demo patient (its run is already `succeeded`) — this is what
processes any **new** run you kick off from the UI (e.g. re-extracting a fresh patient with
a live OpenRouter key).

## 5. Start the web app

```bash
cd web
npm install   # first time only
npm run dev   # http://localhost:3000
```

Make sure `web/.env.local` has `NEXT_PUBLIC_API_MODE=live` (see §0) so it talks to the real
backend instead of the built-in mock dataset.

## 6. Walk the demo

1. Open `http://localhost:3000/login`, sign in as **demo@findingframe.dev / demo1234**.
2. Dashboard → patient **10000935** (gastric).
3. Patient page → the seeded run (`status: succeeded`, 55 tracks, 97 frames) → **Review**.
   - Every fact shows its verbatim `evidence_text`; click through to the full source report.
   - Gate-failed facts (`evidence_verified=false` — spans the packet couldn't verify, ~11 of
     97 frames) are quarantined and force-routed for review, never silently included.
4. Confirm links (`/runs/{id}/review` → link confirmation UI → `POST .../link-decisions`).
   RECIST is gated on this: it only ever computes over human-confirmed tracks.
5. `/runs/{id}/recist` → select ≤5 target lesions (≤2/organ) from the confirmed tracks →
   RECIST worksheet (SLD, % from baseline/nadir, CR/PR/SD/PD).
6. `/patients/{id}/signoff` → sign off (hash-chained; `GET /patients/{id}/audit` shows the
   append-only, hash-chained audit log) → `GET /runs/{id}/audit-packet` for the exportable,
   pseudonymized audit-grade bundle (the demo centerpiece).

## Docker Compose

No local Postgres — everything still points at the hosted Supabase project via
`backend/.env`. Build context for every service is the `findingframe/` repo root.

```bash
# 1. Vendor the engine first — Dockerfiles COPY infra/engine_vendor/, not tmc/ directly.
infra/scripts/vendor_engine.sh

# 2. web's NEXT_PUBLIC_* vars are baked in at Next.js build time; --env-file supplies them
#    for docker-compose variable substitution (does NOT modify web/.env.local).
cd infra
docker compose --env-file ../web/.env.local -f docker-compose.yml up --build
```

- `backend` → `http://localhost:8000` (healthcheck: `GET /health`)
- `web` → `http://localhost:3000` (healthcheck: `GET /`)
- `worker` has no HTTP surface; its healthcheck just asserts the process/imports are alive.
- `FF_ENGINE_PATH` is overridden to `/app/engine` for `backend`/`worker` (the vendored copy
  baked into the image), overriding whatever dev-relative path is in `backend/.env`.
- Migrations and seeding are **not** run automatically by compose — run
  `infra/scripts/migrate.sh` and `seed_demo.py` against the same Supabase project first
  (from your host, with the venv — they don't need to run inside a container).

## ap-southeast-1 and DPDP

The Supabase project lives in **ap-southeast-1** (Singapore) — the nearest AWS region to
India with a Supabase presence, keeping patient data in-region for India's DPDP Act. Two
things to know:

- **Patients carry no direct identifiers.** `ff.patients` only ever stores a pseudonymous
  `subject_code` (e.g. `10000935` — a MIMIC subject id in this demo, a hospital study code
  in production) + `cancer_type`. Anything identifying (MRN, name, DOB) lives only in
  `ff.patient_identifiers`, encrypted at rest with `pgcrypto` (`FF_PII_ENCRYPTION_KEY`,
  never stored in the DB). `DELETE /patients/{id}/identifiers` performs DPDP erasure by
  deleting *only* that row — the pseudonymized clinical record (frames, tracks, reviews,
  signoffs) survives, since it was never PII to begin with.
- **Direct-DSN caveat for Docker:** `backend/.env`'s `FF_DATABASE_URL` uses Supabase's direct
  IPv6 host (`db.<ref>.supabase.co`). Some Docker network configurations don't route IPv6 by
  default. If `backend`/`worker` containers can't reach the DB, switch to Supabase's IPv4
  session pooler DSN (`aws-0-ap-southeast-1.pooler.supabase.com:5432`, user
  `postgres.<ref>`) in `backend/.env` — this doesn't change the region, only the connection
  path.
