# FindingFrame — Handoff

**Date:** 2026-07-18 · **Status:** deployed, verified, demo-ready
**Live (screen-share only):** https://deep.taile0f78b.ts.net · login `demo@findingframe.dev` / `demo1234`

> Screen-share only until patient `10000935`'s MIMIC report text is swapped for synthetic —
> the PhysioNet DUA does not cover handing raw MIMIC text to non-credentialed people via a
> circulating link. A live demo you drive is fine.

---

## 1. What this is

FindingFrame turns a cancer patient's radiology reports into an **auditable, evidence-anchored
longitudinal record with deterministic RECIST 1.1 progression**. An LLM extracts structured
"frames" (finding_type · anatomy · laterality · measurement · temporal_change · assertion), each
tied to a **verbatim source sentence**; deterministic code links them into longitudinal tracks; a
clinician confirms lesion identity and signs off; every fact traces to its source under a
tamper-evident audit trail. It is a **reviewer accelerator with a human gate**, not an autonomous
reader.

It is the productization of the FindingFrame research engine (kept research-intact at `pre/tmc/`),
following the strategy in `pre/strategy/` (pivot from the old "ClinIQ" multi-agent demo to a focused,
audit-grade oncology abstraction + RECIST platform; India-first validation, pharma/CRO revenue).

The **one demo moment**: patient `DEMO-NSCLC-01` — a shrinking liver metastasis is described two ways
across reports, so naive linking splits it and calls a false **new lesion → Progressive Disease**;
one human track-merge recomputes RECIST over the confirmed target → **Partial Response (−38.9%)**.
Same data, opposite treatment-decision, fully attributed and signed.

---

## 2. What was built

Everything lives in `pre/findingframe/` (monorepo). The research engine at `pre/tmc/` is its own
git repo (currently at commit `5edaa99`, remote `med-notes.git`), clean — it is not a fresh, untouched clone.

- **Backend** (`backend/`, FastAPI, Python 3.12): 11 routers, 16 services, 24+ endpoints. Async
  SQLAlchemy over Supabase Postgres. Supabase ES256 JWT auth (verified via public JWKS). Every
  mutation writes an append-only, hash-chained audit row. **69 tests pass.**
- **Worker** (`worker/`): a Postgres-backed job queue (`FOR UPDATE SKIP LOCKED`), separate process,
  shared LLM rate-limiter, runs the engine and persists frames/tracks.
- **Engine adapter** (`backend/app/engine/`): the only code that imports the research engine — a thin
  seam so engine churn never leaks into the product.
- **Web** (`web/`, Next.js 14 App Router, TypeScript, Tailwind, TanStack Query): 13 routes —
  auth, dashboard, patient/reports, review workbench, link-confirmation, RECIST worksheet,
  sign-off + audit packet, analytics, settings, IRR pilot.
- **Database** (`infra/supabase/migrations/`): 7 migrations, 24 tables in schema `ff`, RLS +
  append-only triggers + DB-computed hash chains + a least-privilege `ff_app` role.
- **Infra** (`infra/`): Dockerfiles + `docker-compose.tyrone.yml` + Caddy reverse proxy; under
  `infra/scripts/` — seed scripts (`seed_demo.py`, `seed_money_patient.py`, `seed_irr_demo.py`),
  the independent `verify_chain.py`, and `compute_kappa.py`.
- **Docs** (`docs/`): `BUILD_SPEC.md`, `RUNBOOK.md`, `DEMO_MONEY_PATIENT.md`, `IRR_PROTOCOL.md`.

### Feature checklist (from the product goal)
Auth ✓ · user/org model ✓ · report ingestion (versioned) ✓ · async extraction + task/job
management ✓ · human-confirmed linking ✓ · RECIST 1.1 ✓ · QA/evidence gate ✓ · clinician review UI ✓
· feedback collection ✓ · evaluation pipeline (blinded IRR + Cohen's κ) ✓ · auditability
(hash-chained, independently verifiable) ✓ · analytics ✓ · settings/config ✓ · structured logging +
typed errors ✓ · production API + clean components + tests ✓ · deployment (Docker on Tyrone, public
URL) ✓.
Parked per strategy (deliberately not built): voice/Sarvam, TTS/translation, general OCR,
department-merge, discharge-summary, multi-tenant onboarding UI, SSO, DICOM/EHR.

---

## 3. Architecture

```
Browser ── HTTPS (Tailscale Funnel) ── Caddy :8080 ──┬── web  :3000  (Next.js, same-origin /api)
                                                     └── backend :8000 (FastAPI)  ──► Supabase Postgres (schema ff, IPv4 session pooler)
                                                          │                            (auth: Supabase ES256 JWT via JWKS)
                                                          ├── engine adapter ──► FindingFrame engine via FF_ENGINE_PATH (local dev: pre/tmc checkout; containers: infra/engine_vendor/ copy)
                                                          └── worker (PG job queue) ──► OpenRouter LLM (DeepSeek-V4-Pro default)
```
Single origin (Caddy) → no CORS. Backend connects as the least-privilege `ff_app` role (not
superuser). Model-agnostic: the LLM backend is a config value recorded in each run's manifest.

**Stack:** Supabase (Postgres 17 + Auth) · FastAPI · Next.js 14 · Docker/Caddy on Tyrone (112-core,
Tailscale) · OpenRouter (DeepSeek-V4-Pro for cost; GPT-5.5 available).

---

## 4. Audit-grade guarantees (the differentiator, enforced in the DB)

- **Immutable extraction runs + reproducibility manifest** (engine git SHA, model id, prompt/schema
  versions, temperature, input-report hashes, manifest hash). Re-extraction = a new run, never an edit.
- **Append-only** on all signed/clinical tables — enforced by Postgres triggers, enforced for all application roles, plus `ff_app` has no UPDATE/DELETE/TRUNCATE grant on them.
- **Hash-chained sign-off + audit log**, computed in the database, genesis-defined and race-safe;
  **independently re-verifiable** by `verify_chain.py` (walks the chain, recomputes every hash,
  exits 0/1 — with a negative control proving tampering is caught).
- **RECIST is computed only over human-confirmed tracks** — a false split can never fabricate a
  progression call.
- **Gate-failed facts are quarantined** for mandatory human review, never silently included.
  Honest claim: *"100% source-linked; gate-failed facts quarantined"* (not "0% hallucination").
- **DPDP posture:** PII separated into a deletable vault (`patient_identifiers`); clinical artifacts
  pseudonymized. Crypto-shredding of free-text is a documented future step.

---

## 5. What is verified (evidence, not assertion)

Confirmed live against the public URL and/or the DB:
- `/health` → `db:ok`, engine SHA `5edaa99…` (vendored copy at `infra/engine_vendor/VENDOR_SHA`; verified 2026-07-18 against the then-deployed `e04d3c6`, not re-verified since).
- Login (real Supabase ES256 token) → 2-patient roster with report counts (10000935 → 37, DEMO-NSCLC-01 → 4).
- Full write path: link-confirm → review → target-lesion → **RECIST contrast (naive PD → confirmed PR, discrepancy=true)** → hash-chained sign-off → audit packet (JSON/CSV/PDF).
- `verify_chain.py` → OVERALL PASS (signoffs + audit chains recompute).
- IRR: blinded 2-reader task with real per-slot Cohen's κ (finding_type 0.85, anatomy 0.93,
  laterality 0.74, assertion 0.79, temporal_change −0.09, full-frame 0.44) — **synthetic demo data, labeled as such**.
- Analytics: 3 runs, ~170 frames, 8% gate-failed rate.
- Tests: backend `pytest` 69 passed / 1 skipped; web `tsc` + `next build` green.
- Engine runs live on DeepSeek-V4-Pro (~$0.014/report) and GPT-5.5.

---

## 6. Data / demo patients

| Patient | Source | Reports | Use |
|---|---|---|---|
| `10000935` | **Real, MIMIC-IV-derived** | 37 | Depth/volume for driven diligence Q&A. Screen-share only (DUA). |
| `DEMO-NSCLC-01` | **Synthetic** (hand-authored, labeled) | 4 | The PD→PR money moment. Safe to show anyone. |

RECIST needs numeric measurements; the adapter normalizes them (mm/cm) on the way out of the engine.

---

## 7. Deploy & operate

- **Public URL:** `https://deep.taile0f78b.ts.net` (Tailscale Funnel, stable). Backup: a cloudflared
  quick tunnel (ephemeral).
- **On Tyrone** (`ssh tyrone`, user `deep`): stack at `~/findingframe/`, compose
  `infra/docker-compose.tyrone.yml`; Caddy reverse-proxy config lives on the tyrone host only (no Caddyfile in this repo — compose bind-mounts it).
- Restart app: `ssh tyrone 'cd ~/findingframe && docker compose --env-file web/.env.local -f infra/docker-compose.tyrone.yml restart'`
- Web-only rebuild: `docker compose … build web && docker compose … up -d --no-deps web`
- Funnel toggle: `tailscale funnel --bg 8080` / `tailscale funnel --https=443 off`
- Local dev: see `docs/RUNBOOK.md`. Secrets live only in `backend/.env` + `web/.env.local` (gitignored);
  a secrets-carrying deploy snapshot is at `pre/findingframe_deploy_snapshot/` (not committed).

---

## 8. Design reviews

Six **Fable** (external-reviewer) passes shaped the build and were incorporated: the plan (R1–R6),
the DB schema, the working slice, the milestone, and the closing review. Notable corrections that
became architecture: human-confirmed linking as the workflow (not automated linking); κ as a
blinded designed study, not review exhaust; audit-grade = immutable runs + manifest + hash chains,
enforced in the DB; least-privilege `ff_app` role; RECIST 1.1 nodal short-axis + CR fixes; and the
reframed "100% source-linked" claim.

---

## 9. Known gaps / deferred (honest)

- The κ shown is **synthetic** (banner-labeled). A real 2-reader clinician study has not run.
- Track-linking F1 upstream is 0.382 (strict Jaccard≥0.5, all 30 patients) — *why* human confirmation is the product; no clinician κ yet.
- MIMIC text on the public URL → screen-share only until sanitized (user's decision).
- Single org; no SSO, CI/CD, DICOM/EHR, crypto-shredding — deferred by design.
- Throughput capped at ~5 LLM calls/min (fine for pilots; not a 10k-report backfill).
- Backup/DR: Supabase PITR exists; a rehearsed restore + re-verify drill is not yet documented.
- `LIVE-DEMO-01` test patient was removed; roster is clean.

---

## 10. Demo script (5 min: doubt → discipline → payoff → proof)

1. **Analytics** — lead with the **8% gate-failed rate**: "we quarantine what we can't verify."
2. **DEMO-NSCLC-01** → a report → composite-key tracks (one line on determinism).
3. **Review workbench** — open the quarantine queue first, correct a slot, confirm one track merge.
4. **RECIST contrast** — naive **PD** vs confirmed **PR**; the treatment-decision-level discrepancy.
5. **Sign off → run `verify_chain.py` live** (independent audit) → download the **PDF audit packet**.
6. **IRR page** (synthetic banner) — per-slot κ; temporal_change < chance is *why* the human gate exists.
Keep `10000935` (37 real reports) in reserve for the diligence Q&A.

---

## 11. Recommended next steps (stop building, start converting)

Per the closing review, the platform is past the point where features raise value — evidence does:
1. **Run a real 2-reader clinician κ mini-study** (~30 reports) — the apparatus is built and deployed;
   it is now a people problem (one Tata/NCG contact). Real κ = the seed slide + NCG LOI opener.
2. **Produce one retrospective concordance number** — "X% of automated reads flip RECIST category
   after confirmed tracking" — the pharma/CRO wedge.
3. **Use the PDF audit packet as the leave-behind** after every meeting.

---

## 12. Repo map

```
pre/
├── strategy/            PITCH · MARKET_RESEARCH · PRODUCT_AND_MARKET · PRODUCT_BUILD_PLAN
├── tmc/                 FindingFrame research engine (re-cloned, untouched)
└── findingframe/        THE PRODUCT
    ├── backend/         FastAPI app (app/{api,core,db,engine,jobs,services,schemas}) + tests
    ├── worker/          extraction worker (PG job queue)
    ├── web/             Next.js 14 app
    ├── infra/           migrations · docker · seed/verify/kappa scripts · engine_vendor (Caddyfile: tyrone host only, not in repo)
    ├── docs/            BUILD_SPEC · RUNBOOK · DEMO_MONEY_PATIENT · IRR_PROTOCOL
    ├── README.md        product overview + quickstart
    └── HANDOFF.md       this file
```
