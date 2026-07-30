# FindingFrame — Production Build Plan

**Version:** 2026-07-17 · **Companion docs:** `PRODUCT_AND_MARKET.md`, `PITCH.md`, `MARKET_RESEARCH.md`
**Scope decision:** This plan builds the product defined by `strategy/` (FindingFrame / IndigoEdge), **not** the old `pre/` "ClinIQ" 10-agent platform. It productionizes the TMC research engine (now cloned at `pre/tmc/`) behind an authenticated, multi-tenant, audit-grade platform.

---

## 0. What the product is (one paragraph)

An authenticated, multi-tenant web platform where oncology data abstractors and radiologists turn a cancer patient's longitudinal radiology reports into an **auditable, evidence-anchored finding record with deterministic RECIST 1.1 progression**. The AI extracts structured "frames" (finding_type · anatomy · laterality · measurement · temporal_change · assertion + a mandatory verbatim source sentence); deterministic code links them into longitudinal tracks; a clinician reviews and signs off on every track; corrections flow into a feedback/evaluation pipeline that doubles as the clinical-validation engine. **Reviewer accelerator, human-in-the-loop, provenance-complete.**

---

## 1. Understanding of the current system (verified)

### 1.1 The engine (`pre/tmc/`) — the crown jewel, reused as-is
- **Extract one report:** `FindingFrameExtractor(domain="radiology").extract(report_text, chart_date, study_type, source_report_id) -> FindingFrameExtractionResult` (`extraction/finding_frame_extractor.py`). LLM call requests temperature 0 via `OpenRouterLLMClient`, which sets it with no per-model guard (unlike the direct-OpenAI client, which skips the parameter for models that reject it); whether OpenRouter's `openai/gpt-5.5` honours, ignores, or rejects the value is unverified. JSON-schema-constrained; checklist over 20 oncology finding types + catch-all; deterministic regex "rescue" passes; evidence gate annotates (does **not** drop) each frame with a verifiable span.
- **Process a patient (multi-report):** `FindingFramePatientProcessor.process_patient(subject_id, reports_df)` (`pipeline/finding_frame_processor.py`) → `FrameArtifact` JSON: frames, `frame_events`, `tracks`, `track_graph` (4 edge types), `unresolved_link_queue`, `false_split_candidates`, telemetry, verifier report. `reports_df` cols: `subject_id, charttime, note_id, note_type, text`. **Pure JSON, deterministic, no DB, no LLM beyond extraction.**
- **Linking:** `fact_graph/frame_linker.py` — deterministic composite key `track_key = finding_type|anatomy|laterality[|lesion_key]`. Decisions: new_track / exact_key / compatible_merge / unresolved_link.
- **RECIST / response (frame-native, deterministic):** `oncology_response/frame_response.build_response_review(tracks, subject_id)`. (Legacy `recist/recist_engine.py` operates on the *legacy* entity fact-graph shape, not frames — not on the product path.)
- **Config:** `config/config.yaml` (`provider: openrouter`, `model: openai/gpt-5.5`) + `config/.env`. Providers: openrouter | openai (model-agnostic). Global rate limit 5 calls/min. **Cost ~$0.014/report, ~37s/report.**
- **Entity grounding (RadLex/SNOMED)** is legacy-path only; the frame path doesn't require it. Optional/secondary for the product.

### 1.2 Existing product surface (reuse the *contract*, rebuild the *delivery*)
- **FastAPI `api/server.py`** has the right endpoint shapes: `/api/frame/tracks`, `/api/frame/digest/{sid}` (precomputed digest, no LLM at request time), `/api/frame/track-annotations` (POST/GET/latest/status), `/api/frame/track-adjudications`, `/api/frame/response/{sid}`. Digest schema = `digest_v1`. Persistence = SQLite `outputs/reviews.db` (`track_reviews`).
- **Reusable clinician-review interaction model** (validated design): sections by clinical status (Needs Attention / Stable / Resolved-Improved / Uncertain / Routine Negatives) · per-track evidence table with verbatim `full_text` · **slot-level correctness checkboxes** (`link_correct`, `type_correct`, `progression_correct`, `latest_status_correct`, `false_merge`, `false_split`, `evidence_valid`, `clinically_significant`) · batch-verify negatives · confidence capture · keyboard nav.
- **Debt to fix:** no auth, wide-open CORS, **two divergent frontends** (vanilla `track_review.html` vs a React/Vite SPA that bypasses the API and persists to jsonbin/localStorage), demo-only GC/quick-`10000935` heuristics, precomputed-packet fragility (`sys.path` import at request time).

### 1.3 Honest constraints (must shape the product)
- **Track-linking F1 = 0.382** (strict Jaccard≥0.5, all 30 patients); dominant failure = *false splits* from anatomy-granularity variation. → product is a **reviewer accelerator, not autonomous**; UI must foreground `unresolved_link` / `false_split_candidates`.
- **No clinician κ exists yet.** All gold is *engineering-curated*. The product's review + feedback loop **is** the path to clinician validation (Phase C) and the startup's fundability unlock — one system serves both.
- **Integrity guardrails:** never present engineering-curated gold as clinician-validated; **never surface the simulated-IRR data as real**; latest-status accuracy (~0.90) is strong, identity is the weak axis.

---

## 2. Architectural invariants (non-negotiable — preserve from TMC)

1. **Hybrid split:** LLMs do language understanding only; **identity, linking, normalization, verification are deterministic.**
2. **Composite-key linking** — no fuzzy LLM entity matching.
3. **Evidence anchoring / 0% hallucination by construction** — every fact carries a gate-checked verbatim source sentence; the UI must show it and flag unverifiable spans.
4. **Model-agnosticism** — backend selectable; no vendor lock-in (also serves DPDP / on-prem).
5. **Assertion is a slot** ("no effusion" = same track, `assertion=absent`).
6. **Reproducibility** — SHA-256 report manifests, versioned prompts/gold, extraction caches.
7. **Human-in-the-loop by design** — nothing enters the signed record without clinician sign-off.
8. **Gold governance** — corrections are provenance-tagged; promotion to gold requires adjudication, never auto-merge of low-agreement slots.

**The engine (`pre/tmc/`) stays research-intact.** The product depends on it as a versioned engine; product-specific code lives in the new product tree. Engine improvements happen upstream in `pre/tmc` and are pulled in deliberately.

---

## 3. Scope: KEEP / PARK / KILL (from strategy §6, applied to the build)

- **KEEP (build now):** FindingFrame extractor · deterministic frame Fact Graph + track linker · RECIST/response engine · QA gatekeeper · clinician-review UI — wrapped in auth, multi-tenancy, jobs, audit, feedback/eval, analytics.
- **PARK (design seams, don't build):** patient-facing views · department-merge · discharge-summary generation.
- **KILL (do not build):** voice-counselling transcription · TTS + multilingual translation · general handwriting OCR.
- **Sarvam:** kept only as an *optional input adapter* for non-English report **text** (translate → extract), not the voice product. Behind a feature flag; not on the critical path.

> Reconciliation with the `/goal` feature list: every *production* concern in the goal (auth, user management, streaming, task/job management, auditability, feedback, evaluation, logging, analytics, error handling, settings, config, clean API, reusable components, testing) is **in scope** — applied to the FindingFrame product. The off-strategy *domains* (voice/OCR/translation/dept-merge/discharge) are parked/killed per the strategy the user confirmed as the source of truth.

---

## 4. Target architecture

**Monorepo:** `pre/findingframe/`

```
pre/findingframe/
├── backend/        FastAPI: auth, REST API, job orchestration, audit, feedback/eval, SSE streaming
│   ├── app/
│   │   ├── api/            versioned routers (/api/v1/...)
│   │   ├── core/           config, security (Supabase JWT), logging, errors
│   │   ├── db/             SQLAlchemy async models + repositories (Supabase Postgres)
│   │   ├── engine/         thin adapter over pre/tmc FindingFrame engine
│   │   ├── jobs/           extraction job runner (async; splittable to a queue+worker)
│   │   ├── services/       patient/report/review/recist/feedback/audit services
│   │   └── schemas/        Pydantic API DTOs (distinct from engine schemas)
│   └── tests/
├── worker/         (M4+) dedicated extraction worker consuming a queue (Redis/pg)
├── web/            Next.js 14 (App Router, TS, Tailwind, TanStack Query, Supabase Auth)
│   ├── app/               dashboard, patients, review workbench, analytics, settings, auth
│   ├── components/        reusable UI (TrackCard, EvidenceTable, ReviewForm, ...)
│   └── lib/               api client, supabase client, types (generated from backend)
├── infra/          docker-compose, Supabase SQL migrations, deploy scripts
└── docs/           ADRs, API reference, runbook
```

**Engine dependency:** backend installs `pre/tmc` as an editable local package (`pip install -e ../tmc`) or path-mounts it; the `engine/` adapter is the *only* place that imports engine internals, exposing `extract_report()` and `process_patient(reports) -> FrameArtifact`. This isolates the product from engine churn and keeps the engine research-intact.

**Persistence — Supabase Postgres** (replaces per-patient JSON + `reviews.db` for multi-tenant production):
- `orgs`, `profiles` (role: admin/reviewer/viewer), `memberships`
- `patients`, `reports` (source_text + source_hash + uploaded_by)
- `extraction_jobs` (status, model_backend, manifest_hash, cost, latency, error)
- `frames`, `tracks`, `track_events`, `track_graph_edges`, `recist_assessments`
- `reviews` (the slot-level feedback), `adjudications`, `gold_candidates`
- `audit_log` (append-only, immutable — actor/action/entity/before/after/ts)
- **Row-Level Security** for org scoping (multi-tenant + DPDP localization story)
- Secrets (DB password, keys) live in gitignored `.env`; **never committed**, never echoed.

**Async & streaming:** extraction is 37s/report and rate-limited (5/min) → jobs run in the background; the UI subscribes to **SSE** (or Supabase Realtime) for per-report progress. Task management = the `extraction_jobs` table + a status stream.

---

## 5. Milestones (each gated by a Fable review)

- **M0 — Foundation:** monorepo scaffold; Supabase schema + RLS migrations; Supabase Auth (login, org, roles); backend skeleton with config/logging/error middleware; `engine/` adapter that extracts one report end-to-end; CI (lint, typecheck, tests). *Exit:* authenticated user can POST one report and get frames back.
- **M1 — Ingestion & extraction jobs:** report upload (single + batch paste), async extraction job → `process_patient`, persist frames/tracks/graph/RECIST to Postgres, SSE progress. *Exit:* upload a patient's reports, watch it process, see the track digest.
- **M2 — Review workbench + audit:** unified Next.js clinician-review UI (the `digest_v1` interaction model), slot-level correctness + corrections, approve/sign-off → signed record, immutable audit log. *Exit:* a clinician reviews and signs a patient; every action is auditable and traceable to source.
- **M3 — Longitudinal record + RECIST view:** patient timeline, track detail with evidence, RECIST/response panel, digest export. *Exit:* provenance-complete longitudinal record view.
- **M4 — Feedback / evaluation pipeline:** review aggregation, disagreement worklist, κ computation, review→gold candidates, dedicated worker + queue. *Exit:* two reviewers → adjudication worklist → gold candidate (the Phase-C/validation loop).
- **M5 — Production hardening:** structured logging + tracing, robust error handling/retries/circuit-breaker on LLM calls, settings & config-management UI (model backend selection), analytics dashboard (throughput min/patient, agreement, RECIST distribution), test coverage, deployment (docker-compose + Supabase + web on Vercel or Tyrone). *Exit:* deployable, observable, tested.

---

## 6. Cross-cutting engineering standards
Modularity (deep modules, thin adapters) · strong typing (Pydantic DTOs backend, generated TS types frontend) · observability (structured logs, request IDs, job telemetry mirrored from engine) · auditability (append-only log, provenance on every fact) · testing (unit for services, contract tests for the engine adapter, e2e for the review flow) · error handling (typed errors, no raw 500s, retry/backoff on LLM) · security (RLS, JWT, least privilege, secrets in env).

---

## 7. Open decisions to confirm (with Fable, then user)
1. **Frontend:** fresh Next.js 14 product app (recommended) vs adapting `pre/tmc/frontend` React+Vite. → Recommend fresh Next.js for auth/SSR/streaming + a clean product surface; port the proven review UX.
2. **Engine execution:** in-process background tasks (M1) → split to dedicated worker + Redis/pg queue (M4). → Recommend this staged path.
3. **Deployment target:** Vercel (web) + container host for backend/worker, or all-on-Tyrone. → Decide at M5.
4. **RECIST in product:** use frame-native `frame_response` (deterministic, on the frame path) as primary; legacy `recist_engine` only if the legacy fact-graph shape is populated. → Recommend frame-native.

---

## 8. Revisions after Fable review (2026-07-17) — these override §4–§6 where they conflict

Fable (external reviewer) flagged three **strategic** defects and several sequencing fixes. All accepted:

### R1 — Invert the product around *human-confirmed linking* (don't render RECIST from a 0.382 strict-Jaccard linker)
A false split fabricates a "new lesion," and in RECIST 1.1 a new lesion = **unconditional PD** — the most consequential wrong answer in oncology. So:
- **New table `link_decisions`** (human confirms/merges/splits track identity per report-pair; signed, versioned) — the most important table in the system.
- **RECIST computed *only* over human-confirmed tracks;** the RECIST panel refuses to render otherwise. This turns the weakest metric into the audit-grade differentiator ("clinician-confirmed lesion identity").
- Foreground the engine's existing `unresolved_link_queue` / `false_split_candidates` as the primary review surface.
- In parallel (not gating): RadLex/SNOMED hierarchy-aware anatomy compatibility in the composite key (e.g. "right upper lobe" ⊂ "right lung") to cut false splits — a bounded engine-side task in `pre/tmc`.
- **New table `target_lesion_selections`** — RECIST 1.1 requires a *human* baseline act (≤5 targets, ≤2/organ); deterministic code cannot do it.

### R2 — Clinical validation (κ) is a *designed, blinded study*, not review exhaust — model it now
- Production review (one reviewer, model output visible → anchoring bias) is **statistically not IRR**. Distinguish in the schema from day one: `annotation_tasks` (protocol id, unit of agreement: slot/frame/track), `assignments` (annotator, `model_output_visible: bool`, independence group), `adjudications` (link to resolved assignments), and **contamination flags on `gold_candidates`** (was model output visible when this gold was created?).
- **Run a small blinded clinician IRR pilot (20–30 reports, 2 radiologists) in parallel with M1** — "zero clinician-validated numbers" is the real critical path for pharma/CRO/NCG, not SSE.
- **Vendor `pre/tmc` as a dependency via an explicit allowlist** that strips `evaluation/`, `data/`, `outputs/`, `paper*/` (removes the fabricated simulated-IRR file), pinned by git SHA, **verified in CI**. "Must never surface" needs a mechanism, not a hope.

### R3 — Audit-grade = immutable versioned extraction runs + reproducibility manifest (not mutable rows + side log)
- **`extraction_runs`** are immutable artifacts, each with a **manifest**: engine git SHA, model id + provider version, prompt/schema hash, temperature, input-report-text hash. Re-extraction = new run, never an update. Frames belong to a run.
- **Reviews pin `run_id` and snapshot the exact value the reviewer saw** (not FK-only).
- **Sign-off = server-side hash** of the signed payload (run + review deltas + link decisions + RECIST inputs), who/when/what-version; **hash-chained** where feasible.
- **Append-only enforced in Postgres** (REVOKE UPDATE/DELETE for the app role or triggers) — not by convention.
- **DPDP erasure vs append-only** resolved at **M0**: PII (patient identifiers) in a deletable/crypto-shreddable store; clinical artifacts pseudonymized. Shapes every table.
- **`reports` must be versioned** (radiology addenda/amendments are routine).

### R4 — Engine boundary & sequencing corrections
- **Postgres-backed job queue** (`FOR UPDATE SKIP LOCKED`) + worker as a **separate process** (same image, different entrypoint) **from M1**. Jobs are rows; survive restarts. **Per-report checkpointing** (resume at 401/500, not restart). FastAPI `BackgroundTasks` is disqualified (5/min → 300 reports/hr ceiling; a 10k-report backfill is 33+ hrs; dies on deploy).
- **Shared rate limiter**: the engine's in-process 5/min limiter won't survive 2 workers → shared token bucket (PG advisory lock / counter table). **Verify in the adapter week one.** Higher provider rate limits = a real workstream, not a config value.
- SSE is optional polish; **polling is fine for the demo.**
- **Move earlier:** LLM retry/circuit-breaker → **M1**; model-backend selection (config-file, part of the manifest) → **M1**; **the exported audit packet** (data + verbatim evidence + who-reviewed-what + manifest, CSV/PDF) is the **demo centerpiece**, defined with the design partner early. Tests + hardening are **per-milestone, not M5.**
- **RLS caveat:** if the backend uses the Supabase **service-role key, RLS is bypassed (theater).** Either pass user JWTs through, or make the backend the explicit tenant boundary and **test that in CI**. Decide explicitly.
- **Data residency at M0:** Supabase `ap-south-1`; scrutinize web function regions and zero-retention DPAs for any US LLM API on Indian patient text (a hospital-local model is a real differentiator).
- **Time-saved instrumentation from M2 day one** (per-session review timestamps + a measured manual-abstraction baseline) — else the "~1hr→~20min" ROI is fabricated.

### R5 — Reframe the headline claim (and make it true)
- Drop "0% hallucination by construction." The gate **annotates, does not drop** — unverified facts flow through, and a verbatim sentence doesn't guarantee entailment. **New claim: "100% source-linked; gate-failed facts quarantined for mandatory human review"** — and **enforce the quarantine in the product** so the (stronger-because-true) claim holds by construction.
- **Incident check:** verify no real patient data sits in a live third-party jsonbin (legacy SPA persistence) — remediate if so.

### R6 — Smallest fundable slice (build this first)
Single org, one design partner: **upload one patient's longitudinal reports → durable extraction run → review workbench where every fact shows its verbatim source sentence and gate-failed facts are force-routed to review → human confirms track links → confirmed-track timeline → RECIST worksheet with human target-lesion selection → signed, exported audit packet with reproducibility manifest.** (≈ minimal-M0 + minimal-M1 + M2 + slim-M3.)
**Defer:** M4 as product (run the IRR pilot with scripts + a protocol doc), analytics dashboards, SSE (poll), batch-upload UI, org-onboarding UI, model-backend UI.

---

## 9. Immediate next steps
1. ✅ Understanding (deliverable 1) and plan (deliverable 2) complete; ✅ first Fable review complete and incorporated.
2. Confirm scope/slice priority with the user (see the decision prompts).
3. Lock M0 scope; spawn parallel sub-agents (Database/Schema, Backend, Auth, Frontend, Infra) for the R6 vertical slice.
