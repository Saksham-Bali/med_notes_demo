# Clinical Intelligence Platform -- Setup & Deployment Guide

## Overview

The Clinical Intelligence Platform is a 10-agent microservices system orchestrated by a central FastAPI orchestrator, with a Next.js frontend. It processes clinical documents (radiology reports, handwritten notes, counselling audio, department notes) and maintains a longitudinal patient record via a Fact Graph.

**Architecture:**

```
Your Laptop (macOS)                          Tyrone Server (Linux, bare-metal)
+---------------------------+                +------------------------------------------+
| Next.js Frontend (:3000)  |   SSH tunnel   | Orchestrator (:8000)                     |
| - Architecture pages      | <-----------> | - Routes requests to agents              |
| - Agent documentation     |   port 8000    | - Preview/Confirm workflow               |
| - Patient explorer        |                |                                          |
| - Workflow UIs            |                | 10 Microservice Agents:                  |
| - Review/approve layer    |                | :5001 OCR Agent                          |
+---------------------------+                | :5002 SOAP Extractor                     |
                                             | :5003 Radiology Extractor                |
                                             | :5004 Voice Transcription                |
                                             | :5005 Counselling Summarizer             |
                                             | :5006 Fact Graph Engine                  |
                                             | :5007 Department Merger                  |
                                             | :5008 Summary Generator                  |
                                             | :5009 QA Agent                           |
                                             | :5010 Translation Layer                  |
                                             +------------------------------------------+
```

---

## 1. Backend on Tyrone

### 1.1 What's Running

All backend services run as **bare-metal Python processes** (no Docker, no conda). Each is a FastAPI app served by uvicorn, running in the background via `nohup`.

| Port | Service | Directory | Module | Purpose |
|------|---------|-----------|--------|---------|
| 5001 | OCR Agent | `ocr-agent/` | `app.main:app` | Azure GPT-4o-mini vision for handwritten note OCR |
| 5002 | SOAP Extractor | `soap-extractor/` | `app.main:app` | Structured clinical note extraction (Subjective/Objective/Assessment/Plan) |
| 5003 | Radiology Extractor | `radiology-extractor/` | `app.main:app` | Hybrid rule+LLM extraction from radiology reports (159 regex patterns + EntityGrounder) |
| 5004 | Voice Transcription | `2nd/` | `main:app` | Sarvam AI speech-to-text for counselling sessions |
| 5005 | Counselling Summarizer | `3rd/counselling-summarizer/` | `main:app` | Extract clinical facts from counselling transcripts |
| 5006 | Fact Graph Engine | `fact-graph-service/` | `app.main:app` | Append-only entity store with RadLex/SNOMED grounding, trajectory tracking |
| 5007 | Department Merger | `4th/department-merger/` | `main:app` | Merge notes from multiple departments with conflict detection |
| 5008 | Summary Generator | `5th/` | `main:app` | Generate NABH-compliant discharge summaries |
| 5009 | QA Agent | `6th/qa-agent/` | `main:app` | Validate summaries for accuracy, completeness, traceability |
| 5010 | Translation Layer | `7th/` | `main:app` | Translate summaries + generate audio/PDF/FHIR artifacts |
| 8000 | Orchestrator | `final/orchestrator/` | `app.main:app` | Central API gateway, workflow coordination, preview/confirm pattern |

### 1.2 How It Was Deployed

The deployment script `deploy_tyrone.sh` does the following:

1. **Creates a Python virtual environment** at `~/projects/pre/.platform_venv` using system Python 3.12
2. **Installs all pip dependencies** (fastapi, uvicorn, httpx, openai, scikit-learn, rapidfuzz, etc.)
3. **Kills any previously running uvicorn processes** on ports 5001-5010 and 8000
4. **Sets environment variables** for Azure OpenAI, Sarvam API, service URLs, and feature flags
5. **Starts all 11 services** using `nohup uvicorn ... &` with logs going to `~/projects/pre/logs/`
6. **Runs health checks** on all services
7. **Seeds 5 patients** into the Fact Graph

### 1.3 Environment Variables (set by deploy script)

```bash
# Azure OpenAI (used by all 10 agents for LLM calls)
AZURE_API_KEY="Fdl4xjJwFM3hONUePvxGyZdzFoGT3MtJbM9hEbVUUqW17cQs1ImNJQQJ99CDACHYHv6XJ3w3AAAAACOGBDbt"
AZURE_ENDPOINT="https://sherpartap1101-5077-resource.cognitiveservices.azure.com/"
AZURE_DEPLOYMENT="gpt-4o-mini"
AZURE_API_VERSION="2025-01-01-preview"

# Sarvam AI (voice transcription + translation)
SARVAM_API_KEY="sk_py5uq3wn_ABmCmnEE8AowmTDhN890kiNt"

# Feature flags (all enabled)
ENABLE_FACT_GRAPH="true"
ENABLE_RADIOLOGY_EXTRACTOR="true"
ENABLE_OCR_AGENT="true"
ENABLE_SOAP_EXTRACTOR="true"

# Inter-service URLs (all localhost since bare-metal)
FACT_GRAPH_URL="http://localhost:5006"
RADIOLOGY_EXTRACTOR_URL="http://localhost:5003"
OCR_AGENT_URL="http://localhost:5001"
SOAP_EXTRACTOR_URL="http://localhost:5002"
VOICE_TRANSCRIPTION_URL="http://localhost:5004"
COUNSELLING_SUMMARIZER_URL="http://localhost:5005"
DEPARTMENT_MERGER_URL="http://localhost:5007"
SUMMARY_GENERATOR_URL="http://localhost:5008"
QA_AGENT_URL="http://localhost:5009"
TRANSLATION_LAYER_URL="http://localhost:5010"

# Fact graph data storage
DATA_DIR="~/projects/pre/data/fact_graph"
```

### 1.4 Seeded Patient Data

5 patients are pre-loaded into the Fact Graph:

| Patient ID | Cancer Type | Entities | Events | Source |
|------------|-------------|----------|--------|--------|
| 10000935 | Gastric | 155 | 304 | Real TMC fact graph (from `tmc/outputs/eval_v14_paired/`) |
| 19540374 | Lung | 67 | 67 | Generated from gold annotations |
| 10016197 | Colon | 27 | 27 | Generated from gold annotations |
| 11392257 | Breast | 56 | 56 | Generated from gold annotations |
| 10511269 | Brain | 54 | 54 | Generated from gold annotations |

The seeding script is at `scripts/seed_patients.py`. Patient 10000935 uses a pre-existing TMC fact graph with full temporal data. The other 4 are generated from gold evaluation annotations at `tmc/outputs/eval_v14_paired/*/gold.json`.

### 1.5 Logs

All service logs are at `~/projects/pre/logs/` on tyrone:

```bash
ssh tyrone 'ls ~/projects/pre/logs/'
# fact-graph.log, ocr-agent.log, soap-extractor.log, radiology-extractor.log,
# voice-transcription.log, counselling-summarizer.log, department-merger.log,
# summary-generator.log, qa-agent.log, translation-layer.log, orchestrator.log
```

To check a specific service's log:
```bash
ssh tyrone 'tail -50 ~/projects/pre/logs/orchestrator.log'
```

---

## 2. Frontend on Your Laptop

### 2.1 Why Separate?

Tyrone doesn't have Node.js installed, so the Next.js frontend runs locally on your laptop. It communicates with the backend via an SSH tunnel.

### 2.2 How the Proxy Works

The frontend has a **server-side API proxy** at `app/api/proxy/[...path]/route.ts`:

```
Browser (client-side JS)
    |
    |  fetch('/api/proxy/api/v1/patients')
    v
Next.js Server (localhost:3000)
    |
    |  fetch('http://localhost:8000/api/v1/patients')  <-- goes through SSH tunnel
    v
Orchestrator on Tyrone (localhost:8000 via tunnel)
    |
    |  httpx.get('http://localhost:5006/api/v1/patients')
    v
Fact Graph Service on Tyrone (localhost:5006)
```

The proxy exists so that:
- Browser JS doesn't need CORS headers
- All API calls go through Next.js server-side, which routes through the SSH tunnel
- The URL `NEXT_PUBLIC_ORCHESTRATOR_URL` defaults to `http://localhost:8000`

### 2.3 Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Architecture Overview | Hero section, how-it-works pipeline diagram, agent grid, tech stack |
| `/agents/[slug]` | Agent Detail | Purpose, I/O schemas, prompting strategy, failure modes for each of the 10 agents |
| `/demo` | Patient Explorer | Select from 5 patients, shows entity counts and body regions from live API |
| `/demo/patient/[id]` | Patient Detail | 3 tabs: Clinical Summary (entities by body region), Event Timeline, Add New Data |
| `/demo/patient/[id]/workflow/radiology` | Radiology Workflow | 4-step: paste report text -> processing -> review extracted entities -> confirm/ingest |
| `/demo/patient/[id]/workflow/note` | Handwritten Note Workflow | Upload image -> OCR + SOAP extraction -> review -> confirm |
| `/demo/patient/[id]/workflow/merge` | Department Merge | Enter multi-department notes -> merge -> resolve conflicts -> confirm |
| `/demo/patient/[id]/workflow/summary` | Discharge Summary | Generate summary -> QA validation -> translation -> download |

---

## 3. Running the Platform

### Step 1: Start the Backend (on Tyrone)

If the backend is already running (services were started previously), verify:

```bash
ssh tyrone 'for p in 5001 5002 5003 5004 5005 5006 5007 5008 5009 5010 8000; do
  status=$(curl -sf http://localhost:$p/health 2>/dev/null || curl -sf http://localhost:$p/healthz 2>/dev/null)
  if [ -n "$status" ]; then echo "OK   :$p"; else echo "FAIL :$p"; fi
done'
```

If services are down, re-deploy:

```bash
ssh tyrone 'bash ~/projects/pre/deploy_tyrone.sh'
```

**Important:** If the fact-graph service (5006) needs to be restarted independently, you must pass `DATA_DIR`:

```bash
ssh tyrone 'cd ~/projects/pre/fact-graph-service && DATA_DIR=~/projects/pre/data/fact_graph nohup ~/projects/pre/.platform_venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5006 > ~/projects/pre/logs/fact-graph.log 2>&1 &'
```

Similarly, voice-transcription (5004) needs `SARVAM_API_KEY` and Azure env vars:

```bash
ssh tyrone 'cd ~/projects/pre/2nd && \
  SARVAM_API_KEY="sk_py5uq3wn_ABmCmnEE8AowmTDhN890kiNt" \
  AZURE_API_KEY="Fdl4xjJwFM3hONUePvxGyZdzFoGT3MtJbM9hEbVUUqW17cQs1ImNJQQJ99CDACHYHv6XJ3w3AAAAACOGBDbt" \
  AZURE_ENDPOINT="https://sherpartap1101-5077-resource.cognitiveservices.azure.com/" \
  AZURE_DEPLOYMENT="gpt-4o-mini" \
  AZURE_API_VERSION="2025-01-01-preview" \
  nohup ~/projects/pre/.platform_venv/bin/uvicorn main:app --host 0.0.0.0 --port 5004 > ~/projects/pre/logs/voice-transcription.log 2>&1 &'
```

### Step 2: SSH Tunnel

Open a terminal and run:

```bash
ssh -L 8000:localhost:8000 tyrone
```

This forwards your laptop's port 8000 to tyrone's port 8000 (the orchestrator). Keep this terminal open.

**To verify the tunnel works:**

```bash
curl http://localhost:8000/healthz
# Should return: {"status":"ok"}

curl http://localhost:8000/api/v1/patients | python3 -m json.tool | head -20
# Should return array of patient objects with entity counts
```

### Step 3: Start the Frontend

In a **second terminal**:

```bash
cd /Users/sher/project/pre/platform-ui
npm install    # only needed first time or after dependency changes
npm run dev
```

### Step 4: Open the UI

Open **http://localhost:3000** in your browser.

- **Home page** (`/`): Architecture overview with all 10 agents described
- Click **"Try the Demo"** or navigate to `/demo` to see the 5 seeded patients
- Click a patient to see their clinical summary, timeline, and available workflows
- Use the **"Add New Data"** tab to run extraction workflows with human-in-the-loop review

---

## 4. How the Workflow Works (Demo Flow)

### Example: Adding a Radiology Report

1. Go to `/demo` and select a patient (e.g., Patient 10000935 - Gastric)
2. Click the **"Add New Data"** tab, then **"Add Radiology Report"**
3. Paste a radiology report text and select modality (CT/MRI/PET)
4. Click **"Extract"** -- this sends the report to the orchestrator's `/api/v1/workflow/radiology-report/preview` endpoint
5. The orchestrator calls the **Radiology Extractor** (port 5003) which uses:
   - 159 regex patterns for rule-based extraction
   - EntityGrounder for RadLex/SNOMED mapping
   - Azure GPT-4o-mini for LLM-assisted extraction
6. The extracted entities are returned for **human review** (NOT ingested yet)
7. For each entity, you can:
   - **Approve** (green check) -- will be ingested
   - **Reject** (red X) -- will be discarded
   - **Edit** -- modify the entity name, certainty, etc. before approving
8. Click **"Confirm & Ingest"** -- sends only approved entities to `/api/v1/workflow/confirm`
9. The orchestrator ingests the approved facts into the **Fact Graph** (port 5006)
10. The patient's clinical summary updates with the new entities

This **preview/confirm pattern** is the same across all workflows (radiology, handwritten note, department merge).

---

## 5. Stopping Everything

### Stop all backend services on Tyrone:

```bash
ssh tyrone "pkill -f 'uvicorn.*:500[0-9]'; pkill -f 'uvicorn.*:8000'; echo done"
```

### Stop the frontend (on your laptop):

Press `Ctrl+C` in the terminal running `npm run dev`.

### Close the SSH tunnel:

Press `Ctrl+C` or `exit` in the terminal running the SSH tunnel.

---

## 6. Re-seeding Patients

If you need to re-seed (e.g., after clearing data):

```bash
# Clear existing data for a specific patient
ssh tyrone 'rm -rf ~/projects/pre/data/fact_graph/10000935'

# Restart fact-graph to clear in-memory cache
ssh tyrone 'kill $(lsof -ti:5006) 2>/dev/null'
ssh tyrone 'cd ~/projects/pre/fact-graph-service && DATA_DIR=~/projects/pre/data/fact_graph nohup ~/projects/pre/.platform_venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5006 > ~/projects/pre/logs/fact-graph.log 2>&1 &'
sleep 4

# Run seed script
ssh tyrone '~/projects/pre/.platform_venv/bin/python ~/projects/pre/scripts/seed_patients.py http://localhost:5006'
```

---

## 7. Docker Compose (Alternative Deployment)

For environments where Docker is available, `docker-compose.yml` at the project root defines all 14 services (postgres, redis, 10 agents, orchestrator, frontend). To use:

```bash
cd /Users/sher/project/pre
cp .env.example .env   # or ensure .env has AZURE_API_KEY and SARVAM_API_KEY
docker-compose up --build -d
```

This runs everything locally including the frontend. The orchestrator is exposed on port 8000, frontend on port 3000.

**Key difference from bare-metal**: In Docker, services use Docker DNS names (e.g., `http://fact-graph:5006`) instead of `localhost`. The frontend uses `ORCHESTRATOR_INTERNAL_URL=http://orchestrator:5000` for server-side calls.

---

## 8. Troubleshooting

### "No patient data found" / "Seed required" on the demo page

This means the frontend can't reach the orchestrator or the fact-graph has no data.

1. Check SSH tunnel is running: `curl http://localhost:8000/healthz`
2. Check patients exist: `curl http://localhost:8000/api/v1/patients`
3. If empty, re-seed (see Section 6)

### Service fails to start on tyrone

Check the log:
```bash
ssh tyrone 'tail -50 ~/projects/pre/logs/<service-name>.log'
```

Common issues:
- **Missing pip packages**: Install with `ssh tyrone '~/projects/pre/.platform_venv/bin/pip install <package>'`
- **Permission denied on `/app/data`**: The `DATA_DIR` env var wasn't set. Use `DATA_DIR=~/projects/pre/data/fact_graph` when starting the fact-graph service.
- **Port already in use**: Kill the old process first with `ssh tyrone 'kill $(lsof -ti:<port>)'`

### Frontend shows 502 errors

The proxy at `/api/proxy/` returns 502 when it can't reach the orchestrator. Check:
1. SSH tunnel is active
2. Orchestrator is running: `ssh tyrone 'curl -sf http://localhost:8000/healthz'`
3. The specific agent is running (check orchestrator logs for upstream errors)

### Orchestrator returns 503 for a workflow

This means the specific agent it tried to call is down or unreachable. Check:
1. Which agent: the error message says which agent failed
2. That agent's health: `ssh tyrone 'curl -sf http://localhost:<port>/health'`
3. That agent's logs: `ssh tyrone 'tail -30 ~/projects/pre/logs/<agent>.log'`

---

## 9. Project Structure

```
/Users/sher/project/pre/
├── final/orchestrator/          # Central orchestrator (port 8000)
│   └── app/
│       ├── main.py              # All API endpoints
│       ├── config.py            # Settings from env vars
│       ├── registry.py          # Agent definitions (URLs, endpoints, timeouts)
│       ├── agent_client.py      # HTTP client with retry logic
│       ├── schemas.py           # Pydantic models
│       ├── storage.py           # Counselling sessions + deferred jobs
│       └── errors.py            # Custom exceptions
├── ocr-agent/                   # Agent 01 (port 5001)
├── soap-extractor/              # Agent 02 (port 5002)
├── radiology-extractor/         # Agent 03 (port 5003)
├── 2nd/                         # Voice Transcription (port 5004)
├── 3rd/counselling-summarizer/  # Agent 05 (port 5005)
├── fact-graph-service/          # Agent 06 (port 5006)
├── 4th/department-merger/       # Agent 07 (port 5007)
├── 5th/                         # Summary Generator (port 5008)
├── 6th/qa-agent/                # Agent 09 (port 5009)
├── 7th/                         # Translation Layer (port 5010)
├── platform-ui/                 # Next.js frontend
│   ├── app/                     # App router pages
│   │   ├── page.tsx             # Architecture overview homepage
│   │   ├── agents/[slug]/       # Agent detail pages
│   │   ├── demo/                # Patient explorer
│   │   │   └── patient/[id]/    # Patient detail + workflows
│   │   └── api/proxy/           # Server-side proxy to orchestrator
│   ├── components/              # Reusable UI components
│   ├── lib/                     # API client, types, agent metadata
│   └── data/patients.json       # Static patient metadata
├── scripts/
│   └── seed_patients.py         # Seed 5 patients into fact graph
├── data/fact_graph/             # Patient data (on tyrone)
├── logs/                        # Service logs (on tyrone)
├── deploy_tyrone.sh             # Bare-metal deployment script
├── docker-compose.yml           # Docker alternative
├── audit.md                     # Agent audit report
├── IMPLEMENTATION_PLAN.md       # Original build plan
└── REBUILD_PLAN.md              # UI rebuild plan
```

---

## 10. Key API Endpoints

All endpoints are on the orchestrator (port 8000).

### Health & Status
- `GET /healthz` -- Simple health check
- `GET /api/v1/health` -- Detailed health of all 10 agents

### Patient Data (read-only, proxied from Fact Graph)
- `GET /api/v1/patients` -- List all patients with entity/event counts
- `GET /api/v1/patient/{id}/state` -- Current entity state for a patient
- `GET /api/v1/patient/{id}/timeline` -- Chronological event timeline
- `GET /api/v1/patient/{id}/entity/{eid}` -- Full history of a single entity

### Extraction Workflows (preview -- extract without ingesting)
- `POST /api/v1/workflow/radiology-report/preview` -- Extract from radiology report text
- `POST /api/v1/workflow/handwritten-note/preview` -- OCR + SOAP from uploaded image (multipart)
- `POST /api/v1/workflow/department-merge/preview` -- Merge multi-department notes

### Confirm (ingest approved facts)
- `POST /api/v1/workflow/confirm` -- Ingest human-reviewed facts into fact graph

### Direct Workflows (extract + ingest in one step, no review)
- `POST /api/v1/workflow/radiology-report` -- Full radiology pipeline
- `POST /api/v1/workflow/handwritten-note` -- Full OCR + SOAP + ingest
- `POST /api/v1/workflow/department-merge` -- Full merge + ingest
- `POST /api/v1/workflow/counselling` -- Full audio transcription + summarization
- `POST /api/v1/workflow/counselling/approve` -- Approve counselling facts
- `POST /api/v1/workflow/generate-summary` -- Generate + QA + translate discharge summary
