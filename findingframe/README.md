# FindingFrame

**Audit-grade oncology radiology abstraction + longitudinal RECIST — human-in-the-loop, provenance-complete.**

FindingFrame turns a cancer patient's radiology reports into an auditable, evidence-anchored
longitudinal record with deterministic RECIST 1.1 progression. An LLM extracts structured
"frames" (finding_type · anatomy · laterality · measurement · temporal_change · assertion) —
each anchored to a **verbatim source sentence**; deterministic code links them into longitudinal
tracks; a clinician reviews and signs off on every track; and every fact traces to its source
under a tamper-evident audit trail. It is a **reviewer accelerator**, not an autonomous system.

> Product strategy lives in `../strategy/` (PITCH, PRODUCT_AND_MARKET, PRODUCT_BUILD_PLAN).
> This is the productization of the FindingFrame research engine at `../tmc/` (kept research-intact).

## Why it's different
- **100% source-linked; gate-failed facts quarantined for mandatory human review.** No fact enters
  the signed record without a verifiable source span or an explicit human decision.
- **Deterministic composite-key linking + RECIST 1.1.** Same reports in → same tracks and
  progression out, reproducibly.
- **Human-confirmed linking is the workflow.** Automated track-linking is deliberately treated as a
  proposal: the clinician confirms/merges/splits lesion identity, and **RECIST is computed only over
  human-confirmed tracks** (a false split would otherwise fabricate a "new lesion" = false PD).
- **Audit-grade, enforced in the database.** Immutable extraction runs with a reproducibility
  manifest, append-only tables (trigger-enforced for all application roles), DB-computed
  hash-chained sign-off + audit log, independently re-verifiable with `verify_chain.py`.
- **Model-agnostic** (OpenRouter/OpenAI; DeepSeek-V4-Pro, GPT-5.5, …) and **multi-tenant** with
  per-org isolation.

## Architecture
```
web/  (Next.js 14)  ──JWT──>  backend/ (FastAPI)  ──asyncpg (ff_app)──>  Supabase Postgres (schema ff)
                                   │
                                   ├── engine/  thin adapter ──> ../tmc  (FindingFrame engine, untouched)
                                   └── worker/  PG job queue (FOR UPDATE SKIP LOCKED) ──> extraction
```
- **Auth:** Supabase Auth, ES256 JWTs verified via public JWKS.
- **DB:** `infra/supabase/migrations/0001..0008` — schema, RLS, integrity hardening, digest-searchpath fix, least-privilege `ff_app` role, rate limiting, run-grant fix, incremental runs + carry-forward. (⚠ 0008 is untracked in git — see `AGENTS.md`; a fresh clone lacks the incremental schema.)
- **Engine boundary:** `backend/app/engine/adapter.py` is the only code that imports the research engine.

## Quickstart (local)
```bash
# 0) DB: apply migrations (idempotent) to your Supabase project
bash infra/scripts/migrate.sh

# 1) Backend
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill FF_DATABASE_URL (ff_app), FF_SUPABASE_*, FF_OPENROUTER_API_KEY
.venv/bin/uvicorn app.main:app --port 8000        # http://localhost:8000/health

# 2) Worker (separate process, same venv)
cd .. && backend/.venv/bin/python -m worker.main

# 3) Seed the demo (org + confirmed user + patient 10000935 + money patient), no LLM key needed
backend/.venv/bin/python infra/scripts/seed_demo.py
backend/.venv/bin/python infra/scripts/seed_money_patient.py

# 4) Web
cd web && npm install && cp .env.local.example .env.local   # set NEXT_PUBLIC_API_MODE=live
npm run dev                                                  # http://localhost:3000
```
Demo login: **demo@findingframe.dev / demo1234**. See `docs/RUNBOOK.md` for the full walkthrough
and `docs/DEMO_MONEY_PATIENT.md` for the flagship "naive PD → human-confirmed PR" demo.

## The demo that matters
Patient `DEMO-NSCLC-01`: one shrinking liver metastasis is described two ways across reports, so the
deterministic linker **splits** it into two tracks. Naive linking reads the second as a *new lesion*
→ **Progressive Disease** (an erroneous treatment-discontinuation call). The reviewer merges the
tracks in the link-confirmation UI; RECIST recomputes over the confirmed target → **Partial Response
(−38.9%)**. Same data, correct answer, fully attributed and signed. That is the product.

## Verify the audit trail yourself
```bash
backend/.venv/bin/python infra/scripts/verify_chain.py   # recomputes signoff + audit hash chains -> PASS/FAIL
```

## Docs
- `docs/BUILD_SPEC.md` — the API + worker contract and data model.
- `docs/RUNBOOK.md` — run/seed/deploy steps.
- `docs/DEMO_MONEY_PATIENT.md` — the flagship demo script.
- `docs/HANDOFF_INCREMENTAL_DEMO.md` — the incremental-run / carry-forward demo handoff (⚠ status NOTE 2026-09-03).
- `docs/DEMO_INCREMENTAL.md` — pre-build proposal, partly superseded (see the handoff above §3).
- `docs/IRR_PROTOCOL.md` — the blinded clinician-validation (Cohen's κ) protocol.
- `docs/INDEX.md` — one-line status for each doc above.

## Status
R6 vertical slice: complete and verified end-to-end (extraction → review → human-confirmed linking →
RECIST → hash-chained sign-off → exported audit packet). Deferred to next phases: blinded IRR pilot
execution, crypto-shredding of free-text PII (DPDP), analytics dashboards, SSE, containerized deploy
verification.
