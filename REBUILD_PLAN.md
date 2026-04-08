# Platform Rebuild Plan — Demo-Ready Clinical Intelligence Platform

> April 4, 2026 — Complete rewrite of UI, backend preview/review flow, patient seeding, and agent audit

---

## 0. The Gap Between What Exists and What's Needed

**What we have:** 12 Docker services (10 agents + orchestrator + frontend), all tests passing, Azure LLM wired, `docker-compose.yml` ready. The `platform-ui` Next.js app has basic CRUD pages.

**What's missing for a real demo:**

1. **No patient data seeded.** The fact-graph-service starts empty. The 5 TMC patients' fact graphs (155 entities for patient 10000935 alone) need to be loaded at startup.

2. **No review layer.** Current orchestrator workflows auto-ingest into fact graph. The user spec requires: extract → **human reviews each entity** → approve/reject → only then ingest. This is the counselling pattern generalized to ALL workflows.

3. **The UI is a generic CRUD app**, not a demo-grade product. Needs: architecture overview homepage, individual agent documentation pages, patient-centric demo flow with before/after.

4. **No transparency into agent processing.** Users should see intermediate outputs, not just final results.

5. **Agent prompts/configs not audited.** Need to assess quality and document.

---

## 1. Architecture Changes

### 1A. Backend: Preview/Confirm Split (Orchestrator)

Add "preview" variants of every workflow that **extract without ingesting**, returning facts for review.

**New orchestrator endpoints:**

| Endpoint | Method | What it does |
|---|---|---|
| `/api/v1/workflow/radiology-report/preview` | POST | Runs radiology-extractor only, returns extracted facts. Does NOT ingest. |
| `/api/v1/workflow/handwritten-note/preview` | POST | Runs OCR → SOAP extraction only. Returns SOAP + facts. Does NOT ingest. |
| `/api/v1/workflow/department-merge/preview` | POST | Runs dept merger only. Returns unified facts + conflicts. Does NOT ingest. |
| `/api/v1/workflow/confirm` | POST | Takes `patient_id` + list of approved `ClinicalFact` objects → ingests into fact graph. |

The existing endpoints remain unchanged (for programmatic use). The UI uses preview → confirm.

**Changes to `final/orchestrator/app/main.py`:** Add 4 new route handlers.  
**Changes to `final/orchestrator/app/schemas.py`:** Add `PreviewConfirmRequest` model.

### 1B. Backend: Patient Data Seeding (Fact Graph Service)

Add a `POST /api/v1/patient/{patient_id}/import` endpoint to fact-graph-service that accepts a raw TMC FactGraph JSON and loads it directly.

At demo startup, a seed script loads the best available fact graph for each of 5 patients:

| Patient | Cancer Type | Source File | Entities |
|---|---|---|---|
| 10000935 | Gastric | `tmc/outputs/eval_v14_paired/subject_10000935_fact_graph.json` | 155 |
| 19540374 | Lung | need to generate or use available outputs | TBD |
| 10016197 | Colon | need to generate or use available outputs | TBD |
| 11392257 | Breast | need to generate or use available outputs | TBD |
| 10511269 | Brain | need to generate or use available outputs | TBD |

For patients without local fact graph JSONs, we generate synthetic but realistic seed data from the gold standard annotations.

Also add: `GET /api/v1/patients` — lists all patients with summary stats (entity count, last updated, cancer type). Needed for the patient selector.

### 1C. Backend: GC Summary Rendering

Add `GET /api/v1/patient/{patient_id}/gc-summary` to fact-graph-service that renders a markdown clinical summary from the current fact graph state (port the `tmc/gc_system/gc_updater.py` render logic, or return the raw entity timeline in a structured format the UI can render).

---

## 2. UI Rebuild — Page-by-Page Spec

### 2A. Homepage (`/`) — Architecture & Documentation

**NOT a dashboard.** This is a presentation page explaining the entire system.

**Sections:**

1. **Hero** — "Clinical Intelligence Platform" title, one-line description, animated architecture diagram showing data flowing through agents.

2. **How It Works** — 4-step visual: (1) Data Input → (2) AI Processing → (3) Human Review → (4) Patient Record Updated. Each step is a card with an icon and 2-3 sentences.

3. **Architecture Diagram** — Interactive SVG/HTML rendering of:
   ```
   Frontend → Orchestrator → [10 Agent Cards] → Fact Graph → Output
   ```
   Each agent is a clickable card linking to its detail page.

4. **Agent Grid** — 10 cards (2 rows of 5), each showing: Agent name, port, one-line purpose, status badge (active/pending). Click → goes to `/agents/{slug}`.

5. **Technology Stack** — Small section: FastAPI, Next.js, Azure OpenAI, Docker, SQLite, RadLex.

6. **"Try the Demo"** button → links to `/demo`.

### 2B. Agent Detail Pages (`/agents/[slug]`)

One page per agent (10 total). Each page:

| Section | Content |
|---|---|
| Header | Agent number, name, port, status |
| Purpose | 3-5 sentences on what it does and why |
| Position in Pipeline | Visual showing where this agent sits in each workflow |
| Input Schema | JSON example of what it receives |
| Output Schema | JSON example of what it produces |
| Prompting Strategy | Description: zero-shot/few-shot, structured output enforcement, guardrails |
| Example | Real input → real output (from test data) |
| Failure Modes | What can go wrong, how the system handles it |
| Source Location | File path in repo |

Agent slugs: `ocr`, `soap`, `radiology`, `voice`, `counselling`, `fact-graph`, `department-merger`, `summary-generator`, `qa`, `translation`

### 2C. Demo Page (`/demo`) — Patient Selector

**Step 1: Choose Patient**

Show 5 patient cards in a grid:

| Card Content |
|---|
| Patient ID (anonymized display) |
| Cancer type badge (Gastric, Lung, Colon, Breast, Brain) |
| Number of known entities |
| Number of radiology reports processed |
| Date range of records |
| "View Patient →" button |

Data comes from `GET /api/v1/patients` (fact-graph-service) and a static metadata file for cancer type / display names.

### 2D. Patient Detail Page (`/demo/patient/[id]`)

**3-tab layout:**

**Tab 1: Clinical Summary** — Rendered fact graph as a clinical document:
- Entity groups by body region (head_neck, chest, abdomen_pelvis, etc.)
- Each entity: name, RadLex badge, certainty bar, trend arrow, first/last seen
- Event timeline: vertical timeline of all events, color-coded by source

**Tab 2: Fact Graph Explorer** — Entity list with expandable cards:
- Click entity → shows all events, measurements, certainty trajectory
- Filter by: body region, entity type, status, date range

**Tab 3: Add New Data** — Grid of 5 input method cards:

| Card | Action |
|---|---|
| Upload Radiology Report | Text input → preview → review → confirm |
| Upload Handwritten Note | Image upload → OCR preview → SOAP preview → review → confirm |
| Voice Counselling | Audio upload → transcript → facts → review → confirm |
| Merge Department Notes | Multi-dept input → merge → conflict resolution → review → confirm |
| Generate Discharge Summary | Triggers summary → QA → translation pipeline |

Each card links to the input page for that workflow, pre-filled with the patient ID.

### 2E. Workflow Pages (`/demo/patient/[id]/workflow/[type]`)

All workflow pages follow the same 4-step pattern:

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  INPUT   │ →  │  PROCESSING  │ →  │    REVIEW    │ →  │  RESULT  │
│  Form    │    │  Agent Steps │    │  Entity Cards │    │  Updated │
│          │    │  (live)      │    │  ✓/✗ each    │    │  Graph   │
└──────────┘    └──────────────┘    └──────────────┘    └──────────┘
```

**Step 1: Input** — The form (specific per workflow type).

**Step 2: Processing** — Show a live stepper of agent calls:
- Each agent gets a card: name, status (queued → running → done), processing time
- Show intermediate outputs as they arrive (OCR text, SOAP JSON, extracted findings)

**Step 3: Review** — The critical step:
- Each extracted `ClinicalFact` is shown as a review card:
  - Entity name (large, bold)
  - Certainty bar (0-1 with color)
  - Evidence text (quoted from source)
  - RadLex ID badge (or "ungrounded" warning)
  - Body region tag
  - Negation indicator
  - Temporal change badge (NEW / STABLE / WORSENED / etc.)
  - **Toggle: Approve ✓ / Reject ✗** (default: all approved)
  - **Edit button** — expands to let user modify entity name, certainty, etc.
- Summary bar at bottom: "X of Y facts approved"
- "Submit Approved Facts" button

**Step 4: Result** — After confirmation:
- Show what changed in the fact graph (diff view)
- New entities highlighted in green
- Updated entities highlighted in blue
- Link back to patient detail page

### 2F. Discharge Summary Page (`/demo/patient/[id]/workflow/summary`)

Special workflow:
1. Form: dates, physician, language, template, toggles
2. Processing: Summary Generator → QA Agent → Translation
3. QA Results panel: PASS/FAIL with issue list
4. If PASS: Summary text + download links (PDF, audio, FHIR)
5. If FAIL: Issues shown, "Fix & Regenerate" button

---

## 3. Data Seeding Strategy

### 3A. Patient 10000935 (Gastric)
- Full fact graph exists at `tmc/outputs/eval_v14_paired/subject_10000935_fact_graph.json` (155 entities, schema v2)
- GC summary exists at `tmc/outputs/patient_gcs/subject_10000935_full_gc_4_reports.md`
- Gold annotations exist at `tmc/evaluation/manual_annotations/gold_10000935.json`

### 3B. Patients 19540374, 10016197, 11392257, 10511269
- No local fact graph JSONs found (were on tyrone server)
- **Strategy:** Generate seed data from gold annotation files + synthetic events
- Gold files exist at `tmc/evaluation/manual_annotations/gold_{id}.json`
- Convert each gold entity → EntityNode with synthetic events (use gold's entity_type, radlex_id, body_region)

### 3C. Seed Script
Create `scripts/seed_patients.py` that:
1. Reads available fact graph JSONs from `tmc/outputs/`
2. For patients without fact graphs, generates from gold annotations
3. POSTs each to `fact-graph-service /api/v1/patient/{id}/import`

### 3D. Patient Metadata File
Create `platform-ui/data/patients.json`:
```json
[
  {"id": "10000935", "display_name": "Patient A", "cancer_type": "Gastric", "reports_count": 4},
  {"id": "19540374", "display_name": "Patient B", "cancer_type": "Lung", "reports_count": 8},
  {"id": "10016197", "display_name": "Patient C", "cancer_type": "Colon", "reports_count": 5},
  {"id": "11392257", "display_name": "Patient D", "cancer_type": "Breast", "reports_count": 6},
  {"id": "10511269", "display_name": "Patient E", "cancer_type": "Brain", "reports_count": 7}
]
```

---

## 4. Agent Audit Plan

For each agent, audit:
1. **Prompt quality** — Is it task-specialized? Does it use few-shot examples? Is output structured?
2. **Output schema** — Is JSON enforced via Pydantic/schema, or parsed with regex?
3. **Guardrails** — Hallucination checks? Confidence scoring? Negation handling?
4. **Error handling** — What happens on LLM timeout, malformed output, empty input?

Document all findings in `audit.md`.

### Agents to audit:
1. OCR Agent (`ocr-agent/app/ocr.py`) — prompt ported from Med copy
2. SOAP Extractor (`soap-extractor/app/soap.py`) — prompt ported from Med copy
3. Radiology Extractor (`radiology-extractor/`) — uses tmc's battle-tested pipeline
4. Voice Transcription (`2nd/`) — Sarvam API wrapper, minimal prompt
5. Counselling Summarizer (`3rd/counselling-summarizer/`) — LLM extraction prompt
6. Fact Graph Engine (`fact-graph-service/`) — no LLM, deterministic
7. Department Merger (`4th/department-merger/`) — parallel extraction + conflict analysis
8. Summary Generator (`5th/`) — discharge summary composition
9. QA Agent (`6th/qa-agent/`) — validation checks
10. Translation Layer (`7th/`) — Sarvam API wrapper

---

## 5. Execution Order

```
Phase 1: Backend additions (preview/confirm, seeding, patient list)
  ├── 1a. fact-graph-service: /import, /patients, /gc-summary endpoints
  ├── 1b. orchestrator: preview endpoints for all workflows
  ├── 1c. orchestrator: /confirm endpoint
  └── 1d. seed data generation for 5 patients

Phase 2: UI complete rewrite
  ├── 2a. Homepage — architecture visualization
  ├── 2b. Agent detail pages (10 pages)
  ├── 2c. Demo patient selector
  ├── 2d. Patient detail page (3 tabs)
  ├── 2e. Workflow pages with review layer
  └── 2f. Discharge summary page

Phase 3: Agent audit + improvements
  ├── 3a. Read every agent's prompt and config
  ├── 3b. Research SOTA prompt engineering (Firecrawl)
  ├── 3c. Write audit.md
  └── 3d. Implement improvements where meaningful

Phase 4: Integration testing
  ├── 4a. docker compose up --build
  ├── 4b. Seed patients
  ├── 4c. Test each workflow E2E
  └── 4d. Fix issues
```

---

## 6. Files to Create/Modify

### New files:
| File | Phase |
|---|---|
| `fact-graph-service/app/main.py` (add import + patients + gc-summary routes) | 1a |
| `final/orchestrator/app/main.py` (add preview + confirm routes) | 1b |
| `final/orchestrator/app/schemas.py` (add PreviewConfirmRequest) | 1b |
| `scripts/seed_patients.py` | 1d |
| `scripts/generate_seed_data.py` | 1d |
| `platform-ui/data/patients.json` | 1d |
| `platform-ui/data/agents.json` | 2b |
| `platform-ui/app/` (complete rewrite — ~15 page files + ~10 components) | 2 |
| `audit.md` | 3 |

### Modified files:
| File | Change |
|---|---|
| `fact-graph-service/app/store.py` | Add import_graph(), list_patients(), get_gc_summary() |
| `fact-graph-service/app/models.py` | Add ImportRequest, PatientSummary models |
| `docker-compose.yml` | Mount seed data volume |
