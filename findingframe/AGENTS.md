# FindingFrame — agent conventions

Read `HANDOFF.md` first for product status, then `docs/INDEX.md` for the doc map.
This file is only the working conventions that keep agents from tripping.

## Where to stand

- **Work from `findingframe/` as cwd**, not the repo root. All paths below are
  relative to `findingframe/` unless prefixed with `pre/`.
- `pre/tmc/` is a **separate git repo** (nested checkout, ignored by `pre/`).
  Never edit it from here, never commit it from here. Same for `pre/Med copy/`,
  `pre/dasyante-site/`, `pre/findingframe_deploy_snapshot/`.

## Local vs tyrone compose

- **Local/dev:** `infra/docker-compose.yml` — backend/worker/web, no local
  Postgres (points at hosted Supabase via `backend/.env`).
- **Tyrone deploy:** `infra/docker-compose.tyrone.yml` — adds Caddy (single
  origin, no CORS). On tyrone (`ssh tyrone`, user `deep`) the stack lives at
  `~/findingframe/`. No Caddyfile exists in this repo — the compose file
  bind-mounts one that lives on the tyrone host only.
- Both compose files build with context `findingframe/` and need
  `infra/engine_vendor/` populated first (`infra/scripts/vendor_engine.sh`).

## Secrets

- `backend/.env` + `web/.env.local` carry real secrets and are **gitignored**
  (see `.gitignore`). Copy from the `.example` files, never commit the real ones.
- `pre/findingframe_deploy_snapshot/` carries live secrets — gitignored, never commit.
- Before any commit: `git status --short` and eyeball staged files for secrets.

## Engine seam (`FF_ENGINE_PATH`)

- The **only** code that imports the research engine is `backend/app/engine/`.
- Local dev: `FF_ENGINE_PATH=../../tmc` (in `backend/.env`) → live `pre/tmc/` checkout.
- Containers: `FF_ENGINE_PATH=/app/engine` → the vendored allowlist copy baked
  into the image from `infra/engine_vendor/` (written by
  `infra/scripts/vendor_engine.sh`, pinned in `infra/engine_vendor/VENDOR_SHA`).
  Never import engine modules from outside `backend/app/engine/`.

## What is live / parked / proposed

- **Live:** R6 vertical slice (extract → review → human-confirmed linking →
  RECIST → hash-chained sign-off → audit packet) + incremental runs with
  carry-forward (`GET /runs/{id}/delta`, `POST /runs/{id}/carry-forward`,
  `GET /runs/{id}/recist/progression`) + blinded-IRR tooling (protocol and
  `compute_kappa.py` ready, **pilot not yet executed**).
- **Parked (deliberately not built):** voice/Sarvam, TTS/translation, general
  OCR, department-merge, discharge-summary, multi-tenant onboarding UI, SSO,
  DICOM/EHR, crypto-shredding of free-text PII.
- **Proposed (not built):** `docs/DEMO_INCREMENTAL.md` — pre-build proposal;
  three of its claims are superseded, see `docs/HANDOFF_INCREMENTAL_DEMO.md` §3.
  The Aug 13–14 memory-layer pivot in `pre/strategy/` is strategy, not product.

## ⚠ Migration 0008 is untracked

`infra/supabase/migrations/0008_incremental_runs.sql` exists in the working
tree but is **untracked (`??` in `git status`) with no git history**. A fresh
clone therefore lacks the incremental schema (`parent_run_id`,
`run_kind`, `carried_from_run_id`, …) — DB-backed tests fail with
`column "parent_run_id" does not exist`, which is the missing migration, not a
regression. Do not "fix" it by reverting the ORM. See
`docs/HANDOFF_INCREMENTAL_DEMO.md` NOTE 2026-09-03: §0-vs-tail status
contradiction is **unresolved** — treat the tail (blocked) as authoritative
until verified against the production DB. Do not resolve that contradiction
from repo state alone.

## Seed order (and the TRUNCATE trap)

Run in this order, all from `findingframe/` with the backend venv:

```bash
backend/.venv/bin/python infra/scripts/seed_demo.py          # 1st: org + user + 10000935
backend/.venv/bin/python infra/scripts/seed_money_patient.py # 2nd: DEMO-NSCLC-01
backend/.venv/bin/python infra/scripts/seed_long_patient.py  # 3rd: DEMO-NSCLC-LONG-01
```

- `seed_demo.py` **TRUNCATEs** the demo clinical tables (`RESTART IDENTITY
  CASCADE`) — it wipes the other two patients. Re-running it means re-running
  all three seeds in order.
- `seed_money_patient.py` / `seed_long_patient.py` are additive (no TRUNCATE)
  but require `seed_demo.py` first (org + demo user).
- Never point seeds at a DB with patients you want to keep.
