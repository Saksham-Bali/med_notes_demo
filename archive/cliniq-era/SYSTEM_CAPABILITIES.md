# ClinIQ — System Capabilities & Current State

> Honest, detailed assessment of what we have, what works, and what we can demo.  
> May 2026 (Updated 16 May — migrated from dead Azure OpenAI to OpenRouter)

---

## 1. What This System Is

ClinIQ ("Review First") is a **clinical intelligence platform** that ingests unstructured clinical data (radiology reports, handwritten notes, counselling audio, multi-department notes), extracts structured facts using AI agents, lets clinicians review and approve each fact, and maintains a longitudinal patient record. It is a **10-agent microservices architecture** coordinated by a central orchestrator, with a Next.js frontend.

**We built this from scratch over approximately 4 weeks (late March – early April 2026).**

---

## 2. Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                         YOUR LAPTOP                             │
│  ┌───────────────────────┐         SSH Tunnel (port 8000)       │
│  │  Next.js Frontend     │ ════════════════════════════════════ │
│  │  localhost:3000       │                                      │
│  └───────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────┘
                                 ║
                                 ║
┌─────────────────────────────────────────────────────────────────┐
│                      TYRONE SERVER (bare-metal)                │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Orchestrator (:8000)                    │  │
│  │          Central API gateway, workflow coordinator        │  │
│  └──────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────┘  │
│         │      │      │      │      │      │      │      │      │
│   ┌─────┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐    │
│   │ 01  │ │02 │ │03 │ │04 │ │05 │ │06 │ │07 │ │08 │ │09 │ 10 │  │
│   │OCR  │ │SOAP│ │Rad│ │Voice│ │Coun│ │Fact│ │Dept│ │Sum│ │QA │Tr│  │
│   │:5001│ │:5002│:5003│:5004│:5005│:5006│:5007│:5008│:5009│:5010│   │
│   └─────┘ └───┘ └───┘ └───┘ └───┘ └───┘ └───┘ └───┘ └───┘ └──┘  │
│                                                                 │
│  LLM: OpenRouter (openai/gpt-4o-mini)   STT/TTS: Sarvam AI    │
│  Storage: SQLite file per patient   No Docker, no Conda       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. The 10 Agents — What Each One Actually Does

| # | Agent | Port | Provider | What It Does | Status |
|---|-------|------|----------|-------------|--------|
| 01 | **OCR Agent** | 5001 | OpenRouter `openai/gpt-4o-mini` | Converts handwritten/scanned medical docs to machine-readable text. Returns confidence score based on `[ILLEGIBLE]` token count. | Working. Prompt is adequate but not battle-tested. |
| 02 | **SOAP Extractor** | 5002 | OpenRouter `openai/gpt-4o-mini` | Two-stage: LLM extracts Subjective/Objective/Assessment/Plan JSON from OCR text, then deterministically emits ClinicalFact objects. Has a 271-line prompt with 3 few-shot examples. | Working. Best prompt engineering in the platform. |
| 03 | **Radiology Extractor** | 5003 | OpenRouter `openai/gpt-4o-mini` | Hybrid extraction: 159 regex patterns (spaCy + NegEx for negation) + LLM for complex findings. 3-tier entity grounding: TF-IDF → Fuzzy → LLM-assisted to RadLex/SNOMED. Handles single-report and paired temporal reports. | Working. Most sophisticated agent. Ported from the TMC research pipeline. |
| 04 | **Voice Transcription** | 5004 | Sarvam AI `saaras:v3` | Converts clinical counselling audio to English text. Supports 20+ Indian languages, speaker diarization, consent validation. Google STT as fallback. | Working. Tested on EkaCare medical ASR dataset (WER 25.92% → 23.72% with LLM correction). |
| 05 | **Counselling Summarizer** | 5005 | OpenRouter `openai/gpt-4o-mini` | 4-stage pipeline: segment analysis (filters small talk) → LLM fact extraction (Pydantic-validated) → guardrail validation (evidence grounding, hallucination check) → ClinicalFact emission. | Working. Strongest anti-hallucination guardrails. |
| 06 | **Fact Graph Engine** | 5006 | None (deterministic) | Append-only entity store with RadLex/SNOMED grounding, temporal trajectory tracking, conflict detection. File-per-patient SQLite. | Working. Stores real data for Patient 10000935 (155 entities, 304 events). |
| 07 | **Department Merger** | 5007 | OpenRouter `openai/gpt-4o-mini` | 4-stage: parallel SOAP extraction per department → entity alignment (RadLex-first) → conflict detection (staging/medication = critical) → LLM conflict analysis with deterministic fallback. | Working. E2E tested via Docker. |
| 08 | **Summary Generator** | 5008 | OpenRouter `openai/gpt-4o-mini` | Generates NABH-compliant discharge summaries from fact graph state + RECIST data. Uses OpenAI structured output API via OpenRouter. 120s timeout for large patients. | Working. Ported from Azure Responses API to standard `chat.completions.create(response_format={"type":"json_object"})`. |
| 09 | **QA Agent** | 5009 | OpenRouter `openai/gpt-4o-mini` | 5-category gatekeeper: completeness, consistency, confidence, traceability (claim-to-fact linking), NABH compliance. Returns PASS/FAIL with issue list. | Working. Has a known P0 issue: traceability JSON parse fallback treats failures as "all claims supported." |
| 10 | **Translation Layer** | 5010 | Sarvam AI | Translates approved summaries to Indian languages, generates TTS audio, PDF output, and FHIR R4 bundles. | Working. No quality verification (back-translation) — a gap. |

---

## 4. What Actually Runs

### 4.1 Backend (Tyrone server)

All 11 services (10 agents + orchestrator) run as **bare-metal Python processes** on Tyrone:

```bash
# Deploy everything
ssh tyrone 'bash ~/projects/pre/deploy_tyrone.sh'
```

- Each service runs via `nohup uvicorn ... &` from a project-local venv
- Logs go to `~/projects/pre/logs/`
- All services use the SAME OpenRouter key (`OPENROUTER_API_KEY`) and model (`openai/gpt-4o-mini`)
- 5 patients are seeded into the Fact Graph on deploy
- Health checks run automatically and report pass/fail counts

**Currently deployed and runnable**: Yes — services were migrated from Azure → OpenRouter, deployed, tested individually, and then shut down on request. All 11 services verified healthy at ports 5001–5010 + 8000. Redeploy with `deploy_tyrone.sh`.

**Migrated from Azure OpenAI (dead) → OpenRouter (16 May 2026)**: All 8 LLM-dependent agents were migrated. A `gpt-5-mini` reasoning model was tried first but returned `content: null` on all calls — switched to `gpt-4o-mini` which works correctly. The summary-generator (Agent 08) was ported from Azure Responses API (`responses.parse()`) to standard `chat.completions.create(response_format={"type":"json_object"})`.

### 4.2 Frontend (your laptop)

```bash
cd platform-ui && npm install && npm run dev
# Then open localhost:3000
```

Requires an SSH tunnel to Tyrone:
```bash
ssh -L 8000:localhost:8000 tyrone
```

The browser client calls `/api/proxy/...` which the Next.js server proxies through the SSH tunnel to the Tyrone orchestrator — no CORS issues.

---

## 5. UI Capabilities — Page by Page

### 5.1 Homepage (`/`)
- **Hero** with "Minimal surface. Maximal clinical traceability." tagline
- **4 Principles cards**: Quiet Intake, Structured Judgment, Human Authority, Living Memory
- **Architecture diagram**: SVG showing Next.js → Orchestrator → 10 agents
- **Agent grid**: 10 clickable cards linking to detail pages
- **Tech stack chips**: FastAPI, Next.js, Azure, Sarvam, SQLite, RadLex
- **"Open Demo" button** links to patient explorer

**What we can show**: Full page works. Agent grid is populated from `lib/agents-data.ts` (static data). Architecture diagram is an SVG illustration (not live status).

### 5.2 Agent Detail Pages (`/agents/[slug]`) — 10 pages
Each shows:
- Agent number, name, port, status badge
- Purpose (3-5 sentences)
- Pipeline position diagram
- Input/Output JSON schemas
- Prompting strategy description
- Example input → output (from test data)
- Failure modes list
- Source file location in repo
- Previous/Next navigation

**What we can show**: All 10 agent pages render from `lib/agents-data.ts`. This is static documentation, not live introspection of the running agents.

### 5.3 Demo Patient Explorer (`/demo`)
- **5 patient cards** in a grid
- Each shows: anonymized name (Patient A-E), cancer type badge, patient ID, entity count (live from Fact Graph API), report count, date range
- **Live stats card** at top: total patients, total entities
- Falls back to a "Seed Required" message if Fact Graph is unreachable

**What we can show**: This page calls `GET /api/v1/patients` (live API via proxy → orchestrator → fact-graph). If Tyrone is up and seeded, it shows real entity counts. If Tyrone is down, the cards still show static metadata from `data/patients.json`.

### 5.4 Patient Detail (`/demo/patient/[id]`)
**3-tab layout:**
- **Clinical Summary tab**: Renders a prose narrative of the patient's condition by body region, with significance tiering (clinically significant / incidental / uncertain / excluded). For Patient 10000935, shows ~29 key entities out of 155 total.
- **Timeline tab**: Chronological events grouped by date and imaging report. Patient 10000935 has 304 events across 8 date groups.
- **Workflows tab**: 5 cards linking to individual workflow pages: Radiology Report, Handwritten Note, Counselling Session, Department Merge, Discharge Summary.

**What we can show**: Patient 10000935 has the richest data (real TMC pipeline output). The other 4 patients have synthetic data (converted from gold annotations). The clinical summary and timeline both call the live Fact Graph API.

### 5.5 Workflow Pages (5)

All workflow pages follow a **4-step UI pattern**: Input → Processing → Review → Result.

| Workflow | What the User Does | What Actually Runs |
|----------|-------------------|--------------------|
| **Radiology** (`/workflow/radiology`) | Pastes a report, clicks Process | Orchestrator → Radiology Extractor → returns facts for review |
| **Handwritten Note** (`/workflow/note`) | Uploads an image, clicks Process | Orchestrator → OCR Agent → SOAP Extractor → returns OCR text + SOAP structure + facts for review |
| **Counselling** (`/workflow/counselling`) | Uploads audio, picks language | Orchestrator → Voice Transcription (+Sarvam) → Counselling Summarizer → returns bullet points + facts, **human must approve before ingestion** |
| **Department Merge** (`/workflow/merge`) | Enters notes from 2+ departments | Orchestrator → Department Merger → returns conflicts + merged facts |
| **Discharge Summary** (`/workflow/summary`) | Configures options, clicks Generate | Orchestrator → Summary Generator → QA Agent → (if PASS) Translation Layer → returns summary, QA report, PDF/audio downloads |

**Review layer**: Each workflow has a **Review step** where the user sees each extracted `ClinicalFact` as a card with:
- Entity name, certainty bar (0-1 with color), evidence text (quoted from source)
- RadLex ID badge, body region tag, negation indicator, temporal change badge
- **Approve ✓ / Reject ✗ toggle** (default: all approved)
- **Edit button** to modify entity name, certainty, body region
- Summary bar: "X of Y facts approved"
- "Submit Approved Facts" button → calls `POST /api/v1/workflow/confirm` → ingests into Fact Graph

**What we can show**: The complete 4-step flow renders correctly. Whether it *functions end-to-end* depends on:
- Tyrone being up with all services running
- Valid API keys being active
- Real input data being provided

We have verified E2E routing through the orchestrator to the department-merger agent (Docker test). The counselling workflow has a human-in-the-loop breakpoint that was deliberately designed — facts are returned for approval and NOT auto-ingested. Individual agent endpoints were tested with mocked payloads (100% pass).

---

## 6. Data — What's Real vs Generated

| Patient | Cancer | Entities | Events | Data Source |
|---------|--------|----------|--------|-------------|
| 10000935 (Patient A) | Gastric | 155 | 304 | **Real** — from TMC pipeline on MIMIC-IV radiology reports |
| 19540374 (Patient B) | Lung | 67 | 67 | **Synthetic** — generated from gold annotation file |
| 10016197 (Patient C) | Colon | 27 | 27 | **Synthetic** — generated from gold annotation file |
| 11392257 (Patient D) | Breast | 56 | 56 | **Synthetic** — generated from gold annotation file |
| 10511269 (Patient E) | Brain | 54 | 54 | **Synthetic** — generated from gold annotation file |

Patient 10000935 is the showcase case. It has:
- A real fact graph from the TMC research pipeline (F1 score: 0.871)
- Full temporal data across 4+ radiology reports
- Event timeline with date grouping
- Body region information
- The clinical summary prose is generated from this real data

The other 4 patients have structurally valid but simplified entity graphs converted from gold evaluation annotations.

---

## 7. What We Can Actually Demo (Honest Assessment)

### What works end-to-end
- **Navigating the full UI** — all pages render, client-side routing works
- **Browsing agent documentation** — all 10 agent detail pages
- **Patient explorer** — live entity counts from Fact Graph (when Tyrone is up)
- **Patient clinical summary** — for all 5 patients, richest for Patient A
- **Patient timeline** — for Patient 10000935 with real temporal data
- **Workflow UI pages** — all 5 workflows render with their 4-step pattern
- **Server health check** — live status indicator in the nav bar

### What works with Tyrone running
- **Radiology extraction** — paste a real CT/MRI report, get structured facts back
- **Handwritten note OCR + SOAP** — upload a medical note image
- **Department merge** — enter notes from multiple departments, see conflicts
- **Discharge summary generation** — get a NABH-compliant summary with QA report
- **Fact Graph ingestion** — approved facts are written to persistent storage

### What we have NOT fully tested E2E
- **Counselling workflow with real audio** — requires a `.wav` file of a doctor-patient conversation in an Indian language
- **Full end-to-end with real clinical data** — we tested individual agents with mocked payloads and verified Docker service mesh routing, but haven't run a complete real-world scenario through all 5 workflows
- **Translation quality** — Sarvam translation API is wired but we haven't verified the output quality for all 10 supported languages
- **Multi-user concurrent access** — the system is single-user by design (no auth layer)
- **Performance under load** — no load testing done

### What we added in the migration
- **Showcase page** (`/showcase`): Standalone entity-tracking demo showing RUL mass 3.2cm → 3.8cm progression across 3 radiology reports from `sample_report.md`
- **All 8 LLM agents migrated** from Azure OpenAI to OpenRouter (`openai/gpt-4o-mini`) with consistent env vars
- **gpt-5-mini reasoning model bug documented**: model returns `content: null`, breaking all agents — switch to `gpt-4o-mini` fixed it
- **`xlrd` installed on Tyrone** — was missing, caused all `radlex_id: null` in entity grounding
- **UI bugs fixed**: nav active-link invisible (global CSS remap), toggle switches, status dots, hover states

### What is known to have gaps
- **No retry/circuit-breaker on LLM calls** — a transient OpenRouter failure returns a raw 500
- **No structured output mode** on most agents (only Agent 08 uses it) — regex-based JSON parsing is fragile
- **QA Agent P0 bug**: Traceability check fallback treats LLM parse failures as "all claims supported"
- **No auth/authentication** — the platform has no login or user management
- **OCR Agent**: Confidence heuristic is naive ([ILLEGIBLE] token count), no max file size validation
- **Translation Layer**: No back-translation quality check, FHIR bundles are minimal
- **Fact Graph**: File-per-patient storage won't scale past ~100K patients; PostgreSQL migration was planned but not done

---

## 8. How to Run It (Quick Reference)

### Prerequisites
- SSH access to Tyrone server
- Node.js 18+ on laptop
- OpenRouter API key (configured in `deploy_tyrone.sh` as `OPENROUTER_API_KEY`)
- Sarvam AI key (configured in `deploy_tyrone.sh`)

### Start Backend (on Tyrone)
```bash
ssh tyrone 'bash ~/projects/pre/deploy_tyrone.sh'
# Output shows: 11 services started, health checks, patient seeding
```

### Start Frontend (on laptop)
```bash
# Terminal 1: SSH tunnel
ssh -L 8000:localhost:8000 tyrone

# Terminal 2: Next.js
cd platform-ui
npm install
npm run dev
# Open http://localhost:3000
```

### Verify
```bash
# Health check all services
ssh tyrone 'curl -s http://localhost:8000/api/v1/health | python3 -m json.tool'

# List patients
curl http://localhost:8000/api/v1/patients | python3 -m json.tool

# Check specific patient state
curl http://localhost:8000/api/v1/patient/10000935/state | python3 -m json.tool | head -30
```

### Demo files
- `sample_report.md` — 3 radiology reports for paste-into-workflow testing
- `/showcase` page — standalone entity-tracking demo (no backend needed)

### Stop
```bash
ssh tyrone 'pkill -f uvicorn'
```

---

## 9. Key Files & Where to Find Things

| What | Where |
|------|-------|
| Deployment script | `deploy_tyrone.sh` |
| Docker compose | `docker-compose.yml` |
| Orchestrator | `final/orchestrator/app/main.py` (795 lines) |
| Agent 01 (OCR) | `ocr-agent/app/ocr.py` |
| Agent 02 (SOAP) | `soap-extractor/app/soap.py` (460 lines) |
| Agent 03 (Radiology) | `radiology-extractor/app/extractor.py` |
| Agent 04 (Voice) | `2nd/main.py` |
| Agent 05 (Counselling) | `3rd/counselling-summarizer/main.py` |
| Agent 06 (Fact Graph) | `fact-graph-service/app/main.py` |
| Agent 07 (Merger) | `4th/department-merger/main.py` |
| Agent 08 (Summary) | `5th/main.py` |
| Agent 09 (QA) | `6th/qa-agent/main.py` |
| Agent 10 (Translation) | `7th/main.py` |
| Frontend pages | `platform-ui/app/` |
| Frontend components | `platform-ui/components/` |
| API client | `platform-ui/lib/api.ts` |
| Agent metadata (static) | `platform-ui/lib/agents-data.ts` (662 lines) |
| Patient metadata | `platform-ui/data/patients.json` |
| Design system | `platform-ui/app/globals.css` |
| Prompt repository (reference) | `Med copy/lib/prompts.ts` (941 lines) |
| TMC research pipeline | `tmc/` (extraction, fact_graph, evaluation, entity_grounding) |
| Agent audit report | `audit.md` |
| Implementation plan | `IMPLEMENTATION_PLAN.md` |
| Rebuild plan | `REBUILD_PLAN.md` |
| Voice eval results | `eval_results/eval_phase2_results.md` |
| Seed script | `scripts/seed_patients.py` |
| Tyrone operating rules | `machine.md` |
| Sample demo reports | `sample_report.md` |
| Showcase page | `platform-ui/app/showcase/page.tsx` |

---

## 10. Summary Numbers

| Metric | Value |
|--------|-------|
| Total microservices | 11 (10 agents + orchestrator) |
| Total Python/TS source files | ~1,800+ |
| Total lines of code | ~422,000 |
| UI pages | 18 (home + 10 agent pages + 1 demo index + 1 patient detail + 5 workflow pages + 1 showcase) |
| UI components | 11 |
| Seeded patients | 5 |
| Total entities across all patients | ~359 |
| Patient 10000935 entities | 155 (real) |
| Workflow pipelines | 5 |
| Supported Indian languages (voice) | 20+ |
| Supported Indian languages (translation) | 10 |
| LLM provider | **OpenRouter** `openai/gpt-4o-mini` (migrated from dead Azure OpenAI, 16 May 2026) |
| STT/TTS provider | Sarvam AI |
| Eval WER (voice pipeline) | 23.72% (with LLM correction) |
| Eval Entity Recall (voice) | 62.69% |
| TMC Entity F1 score | 0.871 |
| Docker compose services | 14 |
| Known P0 bugs | 3 (no retry logic, QA traceability fallback, radiology silent failure) |
| RadLex grounding | Working (xlrd + 3-tier TF-IDF/Fuzzy/LLM) |
| Hybrid extraction (radiology) | 14 rule + 7 LLM = 17 merged facts (4 dupes removed) |
| Processing time (CT chest) | ~11s per report |
