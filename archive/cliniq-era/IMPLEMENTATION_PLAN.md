# Clinical Intelligence Platform — Full Implementation Plan

> Written: April 4, 2026  
> Goal: Live demo with all agents connected, fact graph running, UI accessible  
> Azure LLM: `https://sherpartap1101-5077-resource.cognitiveservices.azure.com/`  
> Key: `Fdl4xjJwFM3hONUePvxGyZdzFoGT3MtJbM9hEbVUUqW17cQs1ImNJQQJ99CDACHYHv6XJ3w3AAAAACOGBDbt`  
> Compute: tyrone server for docker / compute-heavy runs (see `machine.md`)

---

## 0. Current State Snapshot

### What exists and works
| Component | Location | Status |
|---|---|---|
| Agent 04 Voice Transcription | `2nd/` | Built, tested, Sarvam AI |
| Agent 05 Counselling Summarizer | `3rd/counselling-summarizer/` | Built, tested |
| Agent 07 Department Merger | `4th/department-merger/` | Built, tested |
| Agent 08 Summary Generator | `5th/` | Built, tested |
| Agent 09 QA Agent | `6th/qa-agent/` | Built, tested |
| Agent 10 Translation Layer | `7th/` | Built, tested, Sarvam AI |
| Orchestrator | `final/orchestrator/` | Built, all 10 slots wired, deferred-job fallback for missing agents |
| Radiology Fact Graph | `tmc/fact_graph/` | Sophisticated JSON/SQLite append-only store, F1=0.871 |
| Radiology Pipeline | `tmc/pipeline/patient_processor.py` | HybridExtractor → EntityGrounder → FactStore |
| TMC Demo API | `tmc/api/server.py` | FastAPI serving existing fact graph outputs |
| OCR + SOAP Prompts | `Med copy/lib/prompts.ts` | Production-quality prompts, Azure OpenAI client already wired |
| docker-compose | `docker-compose.yml` | 6 agents + orchestrator + postgres + redis |

### What is missing (blockers)
| Missing | Impact |
|---|---|
| **Agent 06 Fact Graph Engine** (port 5006) | All workflows branch to deferred jobs — the biggest blocker |
| **Agent 03 Radiology Extractor** (port 5003) | Radiology workflow inoperative |
| **Agent 01 OCR Agent** (port 5001) | Handwritten note workflow inoperative |
| **Agent 02 SOAP Extractor** (port 5002) | Handwritten note + dept-merge workflow incomplete |
| **Azure LLM migration** | All agents currently use OpenRouter (credits exhausted) |
| **Demo UI** | Med copy Next.js app exists but not connected to orchestrator |

---

## 1. Azure LLM Configuration

All Python agents use this endpoint. The `openai` SDK handles Azure natively.

```python
# shared pattern — use in every agent's LLM client
import os
from openai import AzureOpenAI

AZURE_ENDPOINT   = "https://sherpartap1101-5077-resource.cognitiveservices.azure.com/"
AZURE_DEPLOYMENT = "gpt-4o-mini"           # text tasks
AZURE_API_VERSION = "2025-01-01-preview"
AZURE_API_KEY    = os.environ["AZURE_API_KEY"]

client = AzureOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=AZURE_API_KEY,
    api_version=AZURE_API_VERSION,
)
```

Environment variable to add to `.env` and docker-compose:
```
AZURE_API_KEY=Fdl4xjJwFM3hONUePvxGyZdzFoGT3MtJbM9hEbVUUqW17cQs1ImNJQQJ99CDACHYHv6XJ3w3AAAAACOGBDbt
AZURE_ENDPOINT=https://sherpartap1101-5077-resource.cognitiveservices.azure.com/
AZURE_DEPLOYMENT=gpt-4o-mini
AZURE_API_VERSION=2025-01-01-preview
```

---

## 2. Phase 1 — Agent 06: Fact Graph Engine (HIGHEST PRIORITY)

**What it is:** Wrap the existing `tmc/fact_graph/` code in a FastAPI service on port 5006.  
**Why first:** Every orchestrator workflow that involves persistent patient data calls this agent. The deferred-jobs queue will drain the moment it's deployed.  
**Effort:** 1–2 days. The logic already exists — this is only an HTTP wrapper.

### 2.1 Directory structure

```
fact-graph-service/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, all routes
│   ├── models.py        # Pydantic input models (CFS adapter)
│   ├── store.py         # thin wrapper around tmc/fact_graph/
│   └── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    └── test_api.py
```

The `tmc/fact_graph/` directory is copied (or mounted) into this service. The service does NOT import from the tmc venv — it carries its own copy.

### 2.2 API surface (minimum viable)

```
POST   /api/v1/ingest                              Accept CFS facts, write to fact graph
GET    /api/v1/patient/{patient_id}/state          Current entity state for patient
GET    /api/v1/patient/{patient_id}/timeline       Ordered event timeline
GET    /api/v1/patient/{patient_id}/entity/{id}/history  Single entity history
POST   /api/v1/patient/{patient_id}/check-conflicts      Conflict detection
GET    /health
```

### 2.3 CFS → Fact Graph adapter

The orchestrator uses the **Clinical Fact Schema (CFS)** as the universal language. The existing `tmc` fact graph uses its own internal `EntityNode` + `Event` Pydantic models. The adapter converts CFS objects on ingestion:

```python
class ClinicalFact(BaseModel):
    fact_id: str
    patient_id: str
    department: str | None = None
    date: str                   # ISO 8601
    source_type: str            # "radiology" | "soap" | "counselling" | "lab"
    source_report_id: str
    entity_name: str            # canonical name e.g. "pleural_effusion"
    radlex_id: str | None = None
    body_region: str | None = None
    measurement: dict | None = None
    certainty: float = 0.5
    certainty_label: str = "suspected"
    is_negated: bool = False
    temporal_change: str | None = None
    evidence_text: str | None = None

class IngestRequest(BaseModel):
    patient_id: str
    facts: list[ClinicalFact]
```

The store layer calls `fact_store.append_grounded_finding()` for each fact, translating fields.

### 2.4 State / timeline response format

```json
{
  "patient_id": "P001",
  "entity_count": 12,
  "entities": [
    {
      "entity_id": "finding_pleural_effusion",
      "canonical_name": "pleural_effusion",
      "radlex_id": "RID4836",
      "body_region": "chest",
      "first_seen": "2025-01-10",
      "last_seen": "2025-03-22",
      "event_count": 4,
      "trend": "increasing",
      "current_certainty": 0.96,
      "events": [...]
    }
  ]
}
```

### 2.5 Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5006
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5006"]
```

### 2.6 Requirements

```
fastapi>=0.111
uvicorn[standard]
pydantic>=2.0
openai>=1.30       # for Azure LLM if needed
aiosqlite
```

### 2.7 Enabling in orchestrator config

Once deployed, set in `.env`:
```
ENABLE_FACT_GRAPH=true
FACT_GRAPH_URL=http://fact-graph:5006
```

---

## 3. Phase 2 — Agent 03: Radiology Extractor

**What it is:** Wrap the existing `tmc/pipeline/patient_processor.py` extraction stages as a stateless HTTP service on port 5003.  
**Stateless design:** The service receives `(current_report_text, prior_report_text, patient_id, modality, body_region)` and returns CFS facts. All state is in the Fact Graph (Agent 06).

### 3.1 Directory structure

```
radiology-extractor/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI, single POST /api/v1/extract
│   ├── extractor.py     # wraps HybridExtractor + EntityGrounder
│   ├── cfs_adapter.py   # converts tmc findings → CFS
│   └── config.py
├── tmc_core/            # copy of relevant tmc modules:
│   ├── extraction/
│   ├── entity_grounding/
│   ├── fact_graph/schema.py   # for Pydantic models only
│   └── utils/
├── Dockerfile
└── requirements.txt
```

### 3.2 API

```
POST /api/v1/extract
GET  /health
```

**Request:**
```json
{
  "patient_id": "P001",
  "report_text": "...",
  "prior_report_text": "...",  // optional — enables temporal change
  "report_id": "R-20250310",
  "report_date": "2025-03-10",
  "modality": "CT",
  "body_region": "chest",
  "hadm_id": "12345"
}
```

**Response:**
```json
{
  "result": {
    "clinical_facts": [...],   // CFS format, ready for Fact Graph /ingest
    "entity_count": 8,
    "extraction_source": "hybrid",  // "rule" | "llm" | "hybrid"
    "processing_time_ms": 1200
  }
}
```

### 3.3 Extraction pipeline (within the service)

```
report_text + prior_report_text
    ↓
RuleExtractor (Tier 0, no LLM — 159 patterns)
    ↓
PairedFindingExtractor (Tier 1, Azure GPT-4o-mini)
    ↓
EntityGrounder (TF-IDF → Fuzzy → LLM-assisted)
    ↓
EntityNormalizer (Pass 0 token-majority + Pass 1 SequenceMatcher)
    ↓
CFS adapter → list[ClinicalFact]
```

The service does NOT write to any database — it returns facts for the caller to ingest into Agent 06.

### 3.4 LLM calls budget

- Rule extractor: 0 LLM calls
- PairedFindingExtractor: 1 call per report pair (Azure GPT-4o-mini, ~$0.001)
- EntityGrounder Tier 3: 1 call per ungrounded entity (rare, ~5% of entities)
- EntityNormalizer Pass 2: 1 call per ambiguous merge pair (rare)

**Limiting:** Set `MAX_LLM_GROUNDING_CALLS=5` per request to cap cost.

### 3.5 Enabling in orchestrator

```
ENABLE_RADIOLOGY_EXTRACTOR=true
RADIOLOGY_EXTRACTOR_URL=http://radiology-extractor:5003
```

---

## 4. Phase 3 — Agent 01: OCR Agent

**What it is:** Python FastAPI service on port 5001 wrapping the OCR prompt already proven in `Med copy/`.  
**Key insight:** The OCR prompt (`OCR_EXTRACTION_PROMPT`) and Azure vision call already exist in `Med copy/lib/`. Port them to Python.

### 4.1 Directory structure

```
ocr-agent/
├── app/
│   ├── __init__.py
│   ├── main.py       # FastAPI, POST /api/v1/extract
│   ├── ocr.py        # Azure GPT-4o with image input
│   └── config.py
├── Dockerfile
└── requirements.txt
```

### 4.2 API

```
POST /api/v1/extract   (multipart/form-data: image + patient_id + department)
GET  /health
```

**Response:**
```json
{
  "result": {
    "full_text": "...",
    "overall_confidence": 0.87,
    "layout_regions": [...],
    "flags": {
      "needs_human_review": false,
      "has_indic_script": false
    }
  }
}
```

### 4.3 LLM: Azure GPT-4o (vision)

The image is base64-encoded and sent to Azure GPT-4o vision endpoint. Use the `responses` API endpoint as specified:

```
https://sherpartap1101-5077-resource.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview
```

For chat completions (vision):
```
https://sherpartap1101-5077-resource.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2025-01-01-preview
```

OCR prompt is ported directly from `Med copy/lib/prompts.ts → OCR_EXTRACTION_PROMPT`.

### 4.4 Confidence scoring

Heuristic post-processing:
- Count `[ILLEGIBLE]` markers → subtract from confidence
- If >20% illegible → `needs_human_review = true`
- Detect Devanagari/other Indic script → `has_indic_script = true`

---

## 5. Phase 4 — Agent 02: SOAP Extractor

**What it is:** Python FastAPI service on port 5002, two-stage LLM extraction.  
**Existing assets:** `SOAP_FROM_TEXT_ENHANCED_PROMPT` and `SOAP_EXTRACTION_PROMPT` from `Med copy/lib/prompts.ts`. Azure OpenAI integration already implemented in `Med copy/lib/azure-openai.ts` — port to Python.

### 5.1 API

```
POST /api/v1/extract   (JSON: text + patient_id + department + source_confidence)
GET  /health
```

**Request:**
```json
{
  "text": "...",
  "patient_id": "P001",
  "department": "cardiology",
  "source_confidence": 0.87,
  "layout_regions": [...]
}
```

**Response:**
```json
{
  "result": {
    "soap": { "subjective": {...}, "objective": {...}, "assessment": {...}, "plan": {...} },
    "clinical_facts": [...],   // CFS format
    "extraction_confidence": 0.91
  }
}
```

### 5.2 Two-stage extraction

**Stage 1 (Azure GPT-4o-mini):** SOAP structured extraction using `SOAP_FROM_TEXT_ENHANCED_PROMPT`. Returns `soap` JSON.

**Stage 2:** Convert `soap.assessment` + `soap.plan` items into `ClinicalFact` objects (CFS format). Each diagnosis → one fact with `certainty_degree` mapped to `certainty`. This is deterministic, no second LLM call.

### 5.3 Enabling

```
ENABLE_SOAP_EXTRACTOR=true
SOAP_EXTRACTOR_URL=http://soap-extractor:5002
```

---

## 6. Phase 5 — Azure LLM Migration (Existing Agents 05, 07, 08, 09)

Agents 05, 07, 08, 09 currently use OpenRouter (`openai/gpt-5-mini`). Migrate them to Azure.

### 6.1 Change pattern (same in each agent)

**Before (OpenRouter):**
```python
from openai import AsyncOpenAI
client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
response = await client.chat.completions.create(model="openai/gpt-5-mini", ...)
```

**After (Azure):**
```python
from openai import AsyncAzureOpenAI
client = AsyncAzureOpenAI(
    azure_endpoint=os.environ["AZURE_ENDPOINT"],
    api_key=os.environ["AZURE_API_KEY"],
    api_version=os.environ.get("AZURE_API_VERSION", "2025-01-01-preview"),
)
response = await client.chat.completions.create(model=os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini"), ...)
```

### 6.2 Files to update

| Agent | File |
|---|---|
| Agent 05 Counselling Summarizer | `3rd/counselling-summarizer/agents/` LLM calls |
| Agent 07 Department Merger | `4th/department-merger/agents/` LLM calls |
| Agent 08 Summary Generator | `5th/agents/` LLM calls |
| Agent 09 QA Agent | `6th/qa-agent/agents/` LLM calls |

Update `.env` and each agent's `docker-compose` `environment:` block to use `AZURE_API_KEY` instead of `OPENROUTER_API_KEY`.

---

## 7. Phase 6 — Demo UI

### 7.1 Option A (fastest): Extend Med copy Next.js app

`Med copy/` is already a working Next.js app with:
- OCR extraction UI (upload image → extract text)  
- SOAP extraction UI  
- Azure OpenAI client wired  

**Add to it:**
1. A patient dashboard page that calls `GET /api/v1/patient/{id}/state` on the orchestrator
2. A radiology report upload page that calls `POST /api/v1/workflow/radiology-report`
3. A patient timeline visualization component

**Proxy orchestrator calls:** Add `/app/api/orchestrator/[...path]/route.ts` as a passthrough proxy to `http://orchestrator:5000`. This avoids CORS issues.

### 7.2 Option B: Use existing TMC frontend

`tmc/frontend/` has a React frontend already wired to the TMC demo API. It shows entity timelines, RECIST data. 

**Add to it:**
1. Connect to orchestrator instead of the TMC local API
2. Add upload pages for handwritten notes, radiology reports

### 7.3 Recommendation

Use **Option A** (Med copy) for the live demo — it's already polished and has the Azure client. The TMC frontend can remain as the "research view."

### 7.4 Key pages for demo

| Page | Path | What it does |
|---|---|---|
| Upload Handwritten Note | `/upload/note` | Image → OCR → SOAP → Fact Graph |
| Upload Radiology Report | `/upload/radiology` | Report text → Radiology Extractor → Fact Graph |
| Patient Dashboard | `/patient/[id]` | Entity timeline, RECIST data |
| Dept Merge | `/merge` | Multi-dept notes → merge → conflicts UI |
| Generate Summary | `/summary/[id]` | QA + translate workflow |

---

## 8. Phase 7 — docker-compose Full Stack

Update `docker-compose.yml` to include the 4 new agents:

```yaml
# Add to existing docker-compose.yml

  fact-graph:
    build: ./fact-graph-service
    ports:
      - "5006:5006"
    environment:
      - AZURE_API_KEY=${AZURE_API_KEY}
      - AZURE_ENDPOINT=${AZURE_ENDPOINT}
    volumes:
      - fact-graph-data:/app/data
    depends_on:
      - postgres

  radiology-extractor:
    build: ./radiology-extractor
    ports:
      - "5003:5003"
    environment:
      - AZURE_API_KEY=${AZURE_API_KEY}
      - AZURE_ENDPOINT=${AZURE_ENDPOINT}

  ocr-agent:
    build: ./ocr-agent
    ports:
      - "5001:5001"
    environment:
      - AZURE_API_KEY=${AZURE_API_KEY}
      - AZURE_ENDPOINT=${AZURE_ENDPOINT}

  soap-extractor:
    build: ./soap-extractor
    ports:
      - "5002:5002"
    environment:
      - AZURE_API_KEY=${AZURE_API_KEY}
      - AZURE_ENDPOINT=${AZURE_ENDPOINT}

  frontend:
    build: ./Med copy
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_ORCHESTRATOR_URL=http://localhost:8000
      - AZURE_KEY=${AZURE_API_KEY}
    depends_on:
      - orchestrator

volumes:
  fact-graph-data:
```

Update orchestrator env block:
```yaml
      - ENABLE_FACT_GRAPH=true
      - ENABLE_RADIOLOGY_EXTRACTOR=true
      - ENABLE_OCR_AGENT=true
      - ENABLE_SOAP_EXTRACTOR=true
      - FACT_GRAPH_URL=http://fact-graph:5006
      - RADIOLOGY_EXTRACTOR_URL=http://radiology-extractor:5003
      - OCR_AGENT_URL=http://ocr-agent:5001
      - SOAP_EXTRACTOR_URL=http://soap-extractor:5002
      - AZURE_API_KEY=${AZURE_API_KEY}
```

---

## 9. Phase 8 — Tyrone Server Deployment

Per `machine.md` — all heavy runs go on tyrone via tmux.

### 9.1 Deploy sequence

```bash
ssh tyrone
tmux new -s platform-demo

# Check GPU before starting
nvidia-smi

# Clone/sync repo
rsync -avz /Users/sher/project/pre/ tyrone:~/projects/pre/ \
  --exclude='.git' --exclude='venv' --exclude='node_modules' --exclude='__pycache__'

cd ~/projects/pre

# Check resources
nvidia-smi && htop  # confirm GPU idle

# Build and run
docker compose up -d --build

# Verify
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

### 9.2 Port access from local machine

```bash
# SSH tunnel to access tyrone services locally
ssh -L 8000:localhost:8000 -L 3000:localhost:3000 tyrone
```

Then open `http://localhost:3000` locally to access the demo UI through the tunnel.

---

## 10. Testing Plan

### 10.1 Unit tests per agent

Each new agent needs tests in `tests/`:

| Agent | Test file | Tests |
|---|---|---|
| fact-graph-service | `tests/test_api.py` | ingest CFS → query state, timeline, entity history |
| radiology-extractor | `tests/test_extractor.py` | extract from sample report, verify CFS output structure |
| ocr-agent | `tests/test_ocr.py` | mock Azure vision call, test confidence scoring |
| soap-extractor | `tests/test_soap.py` | SOAP extraction from known text, CFS conversion |

### 10.2 Integration test

```bash
# Start full stack
docker compose up -d

# Health check all agents
curl http://localhost:8000/api/v1/health

# E2E: radiology workflow
curl -X POST http://localhost:8000/api/v1/workflow/radiology-report \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "report_text": "CT chest: 2.3cm left lower lobe nodule. Pleural effusion present.",
    "report_date": "2026-04-01",
    "modality": "CT",
    "body_region": "chest"
  }'

# Verify patient state in fact graph
curl http://localhost:8000/api/v1/patient/P001/state

# E2E: dept merge workflow
curl -X POST http://localhost:8000/api/v1/workflow/department-merge \
  -H "Content-Type: application/json" \
  -d '{ "patient_id": "P001", "department_notes": [...] }'
```

### 10.3 TMC research pipeline (keep running)

The `tmc/` pipeline continues to run independently — it is NOT affected by these changes. Its existing `api/server.py` and frontend remain intact. The fact-graph-service is a separate deployment wrapping the same underlying code.

---

## 11. Build Order (Strict Sequence)

```
Step 1:  fact-graph-service/     ← unlocks ALL orchestrator workflows
Step 2:  Azure LLM migration     ← fix agents 05, 07, 08, 09 (credits gone from OpenRouter)  
Step 3:  radiology-extractor/    ← wires the TMC radiology pipeline into the platform
Step 4:  ocr-agent/              ← enables handwritten note workflow
Step 5:  soap-extractor/         ← completes handwritten + dept-merge workflows
Step 6:  UI updates (Med copy)   ← patient dashboard + upload pages
Step 7:  docker-compose update   ← wire all new services
Step 8:  Integration test local  ← verify E2E on macOS
Step 9:  tyrone deploy           ← full stack on GPU server
```

---

## 12. LLM Call Budget

To keep costs minimal per the instruction to limit LLM calls:

| Operation | Calls per request | Strategy |
|---|---|---|
| OCR (Agent 01) | 1 vision call | No way to avoid; necessary |
| SOAP extraction (Agent 02) | 1 text call | Single prompt, structured output |
| Radiology extraction (Agent 03) | 1 paired call + max 5 grounding calls | Rule extractor handles ~60% of entities with 0 LLM calls |
| Fact graph ingest (Agent 06) | 0 | Deterministic |
| Counselling summarizer (Agent 05) | 1 | Already minimized |
| Department merger (Agent 07) | 1 per merge | Already minimized |
| Summary generator (Agent 08) | 1 | Single prompt |
| QA agent (Agent 09) | 1 | Single validation call |
| Translation (Agent 10) | 0 LLM, uses Sarvam API | Not LLM |

**Total for a full discharge summary workflow: ~8–12 LLM calls**

---

## 13. Files to Create

| File | Phase | Notes |
|---|---|---|
| `fact-graph-service/app/main.py` | 1 | FastAPI routes |
| `fact-graph-service/app/models.py` | 1 | CFS Pydantic models |
| `fact-graph-service/app/store.py` | 1 | Wrapper around tmc fact_store |
| `fact-graph-service/Dockerfile` | 1 | |
| `radiology-extractor/app/main.py` | 2 | FastAPI route |
| `radiology-extractor/app/extractor.py` | 2 | HybridExtractor wrapper |
| `radiology-extractor/app/cfs_adapter.py` | 2 | Converts tmc findings → CFS |
| `radiology-extractor/Dockerfile` | 2 | |
| `ocr-agent/app/main.py` | 3 | FastAPI + Azure vision |
| `ocr-agent/app/ocr.py` | 3 | OCR logic ported from Med copy |
| `ocr-agent/Dockerfile` | 3 | |
| `soap-extractor/app/main.py` | 4 | FastAPI + Azure text |
| `soap-extractor/app/soap.py` | 4 | SOAP extraction ported from Med copy |
| `soap-extractor/Dockerfile` | 4 | |
| `docker-compose.yml` (update) | 7 | Add 4 new services |
| `.env` (update) | all | Add AZURE_API_KEY |

## 14. Files to Modify

| File | Phase | Change |
|---|---|---|
| `3rd/counselling-summarizer/` LLM calls | 5 | OpenRouter → Azure |
| `4th/department-merger/` LLM calls | 5 | OpenRouter → Azure |
| `5th/` LLM calls | 5 | OpenRouter → Azure |
| `6th/qa-agent/` LLM calls | 5 | OpenRouter → Azure |
| `final/orchestrator/app/config.py` | 7 | Enable new agents by default |
| `docker-compose.yml` | 7 | Add 4 new services + update env |
| `Med copy/` (or new frontend) | 6 | Add orchestrator proxy + patient UI |

---

## 15. Quick Reference: Key Paths

```
tmc/fact_graph/fact_store.py     Core fact graph logic to wrap
tmc/fact_graph/schema.py         EntityNode, Event Pydantic models
tmc/pipeline/patient_processor.py  Full pipeline orchestration (extraction ref)
tmc/extraction/hybrid_extractor.py Rule + LLM hybrid
tmc/extraction/paired_extractor.py Temporal change extraction
tmc/entity_grounding/entity_grounder.py 4-tier grounding
Med copy/lib/prompts.ts          OCR_EXTRACTION_PROMPT, SOAP prompts
Med copy/lib/azure-openai.ts     Azure client (port to Python)
final/orchestrator/app/config.py Orchestrator feature flags
final/orchestrator/app/main.py   Workflow routes
docker-compose.yml               Service mesh
```
