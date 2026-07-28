# PROJECT.md — Clinical Intelligence Platform Orchestrator

> **This is the master document.** It describes the central router/orchestrator  
> that connects all 10 agents into a single working product.

---

## 1. System Overview

The platform is a **microservices architecture** where each agent runs as an independent service. The **Orchestrator** is the central brain — it receives requests from the web app frontend, determines which agents need to run, calls them in the correct order, handles errors, and returns results.

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                        │
│  Dashboard  │  Upload  │  Review UI  │  Patient Timeline         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR (FastAPI)                        │
│                        Port: 5000                                │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │ Workflow  │ │ Agent    │ │ Error    │ │ Event Publisher    │  │
│  │ Engine   │ │ Registry │ │ Handler  │ │ (Kafka Producer)   │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
└──────┬────────────┬────────────┬────────────┬───────────────────┘
       │            │            │            │
       ▼            ▼            ▼            ▼
  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐
  │ Agent 01│ │ Agent 02 │ │Agent 03 │ │Agent 04 │  ...etc
  │ OCR     │ │ SOAP     │ │Radiology│ │ Voice   │
  │ :5001   │ │ :5002    │ │ :5003   │ │ :5004   │
  └─────────┘ └──────────┘ └─────────┘ └─────────┘
```

---

## 2. Agent Registry

The orchestrator maintains a registry of all agents and their health status:

```python
AGENT_REGISTRY = {
    "ocr-agent": {
        "url": "http://ocr-agent:5001",
        "health": "/health",
        "endpoints": {
            "extract": "/api/v1/extract",
        },
        "timeout_seconds": 30,
        "retries": 2,
    },
    "soap-extractor": {
        "url": "http://soap-extractor:5002",
        "health": "/health",
        "endpoints": {
            "extract": "/api/v1/extract",
        },
        "timeout_seconds": 30,
        "retries": 2,
    },
    "radiology-extractor": {
        "url": "http://radiology-extractor:5003",
        "health": "/health",
        "endpoints": {
            "extract": "/api/v1/extract",
        },
        "timeout_seconds": 30,
        "retries": 2,
    },
    "voice-transcription": {
        "url": "http://voice-transcription:5004",
        "health": "/health",
        "endpoints": {
            "transcribe": "/api/v1/transcribe",
        },
        "timeout_seconds": 60,  # audio processing takes longer
        "retries": 1,
    },
    "counselling-summarizer": {
        "url": "http://counselling-summarizer:5005",
        "health": "/health",
        "endpoints": {
            "summarize": "/api/v1/summarize",
        },
        "timeout_seconds": 30,
        "retries": 2,
    },
    "fact-graph": {
        "url": "http://fact-graph:5006",
        "health": "/health",
        "endpoints": {
            "ingest": "/api/v1/ingest",
            "patient_state": "/api/v1/patient/{patient_id}/state",
            "patient_timeline": "/api/v1/patient/{patient_id}/timeline",
            "entity_history": "/api/v1/patient/{patient_id}/entity/{radlex_id}/history",
            "check_conflicts": "/api/v1/patient/{patient_id}/check-conflicts",
        },
        "timeout_seconds": 10,
        "retries": 3,
    },
    "department-merger": {
        "url": "http://department-merger:5007",
        "health": "/health",
        "endpoints": {
            "merge": "/api/v1/merge",
        },
        "timeout_seconds": 45,
        "retries": 1,
    },
    "summary-generator": {
        "url": "http://summary-generator:5008",
        "health": "/health",
        "endpoints": {
            "generate": "/api/v1/generate",
        },
        "timeout_seconds": 45,
        "retries": 2,
    },
    "qa-agent": {
        "url": "http://qa-agent:5009",
        "health": "/health",
        "endpoints": {
            "validate": "/api/v1/validate",
        },
        "timeout_seconds": 30,
        "retries": 2,
    },
    "translation-layer": {
        "url": "http://translation-layer:5010",
        "health": "/health",
        "endpoints": {
            "translate": "/api/v1/translate",
        },
        "timeout_seconds": 60,
        "retries": 1,
    },
}
```

---

## 3. Workflow Definitions

The orchestrator supports **5 primary workflows** that the frontend can trigger. Each workflow is a DAG (directed acyclic graph) of agent calls.

### 3.1 Workflow: Handwritten Note Processing

**Trigger:** User uploads a scanned/photographed handwritten note  
**Frontend action:** Upload image via the "Upload Note" page

```
USER UPLOADS IMAGE
        │
        ▼
[1] OCR Agent (5001)
    POST /api/v1/extract
    Input: image file + patient_id + department
    Output: extracted text + layout regions + confidence
        │
        ▼
[2] SOAP Extractor (5002)
    POST /api/v1/extract
    Input: extracted text + layout regions + source_confidence
    Output: SOAP JSON + clinical_facts[] (CFS)
        │
        ▼
[3] Fact Graph (5006)
    POST /api/v1/ingest
    Input: clinical_facts[]
    Output: updated entity count, new entities created
        │
        ▼
[4] Return to Frontend
    - SOAP structured view for display
    - Updated patient timeline
    - Any new entities flagged
```

**Orchestrator code:**

```python
@app.post("/api/v1/workflow/handwritten-note")
async def workflow_handwritten_note(
    image: UploadFile,
    patient_id: str = Form(...),
    department: str = Form(None),
):
    # Step 1: OCR
    ocr_result = await call_agent("ocr-agent", "extract", 
        files={"image": await image.read()},
        data={"patient_id": patient_id, "source_type": "handwritten", "department": department},
    )
    
    if ocr_result["result"]["flags"]["needs_human_review"]:
        # Return early with low-confidence warning
        return WorkflowResult(
            status="needs_review",
            step_completed="ocr",
            data=ocr_result,
            message="OCR confidence is low. Please review extracted text before proceeding.",
        )
    
    # Step 2: SOAP Extraction
    soap_result = await call_agent("soap-extractor", "extract",
        json={
            "text": ocr_result["result"]["full_text"],
            "layout_regions": ocr_result["result"]["layout_regions"],
            "patient_id": patient_id,
            "source_confidence": ocr_result["result"]["overall_confidence"],
            "department": department,
        },
    )
    
    # Step 3: Ingest into Fact Graph
    ingest_result = await call_agent("fact-graph", "ingest",
        json={
            "patient_id": patient_id,
            "facts": soap_result["result"]["clinical_facts"],
        },
    )
    
    # Step 4: Get updated patient state for frontend
    patient_state = await call_agent("fact-graph", "patient_state",
        path_params={"patient_id": patient_id},
    )
    
    return WorkflowResult(
        status="completed",
        steps=[
            {"agent": "ocr-agent", "status": "success"},
            {"agent": "soap-extractor", "status": "success"},
            {"agent": "fact-graph", "status": "success"},
        ],
        data={
            "soap": soap_result["result"]["soap"],
            "clinical_facts": soap_result["result"]["clinical_facts"],
            "patient_state": patient_state,
        },
    )
```

---

### 3.2 Workflow: Radiology Report Processing

**Trigger:** User uploads or pastes a radiology report  
**Frontend action:** Upload via "Add Radiology Report" page

```
USER UPLOADS REPORT TEXT
        │
        ▼
[1] Radiology Extractor (5003)
    POST /api/v1/extract
    Input: report_text + patient_id + modality + body_region
    Output: findings + clinical_facts[] (CFS) with RadLex grounding
        │
        ▼
[2] Fact Graph (5006)
    POST /api/v1/ingest
    Input: clinical_facts[]
    Output: updated entities, merge events, trajectory updates
        │
        ▼
[3] Return to Frontend
    - Structured findings view
    - RECIST measurement updates
    - Entity trajectory visualizations
```

---

### 3.3 Workflow: Voice Counselling Processing

**Trigger:** User uploads audio recording of counselling session  
**Frontend action:** Upload via "Add Counselling Session" page

```
USER UPLOADS AUDIO
        │
        ▼
[1] Voice Transcription (5004)
    POST /api/v1/transcribe
    Input: audio file + patient_id + consent flag + consent timestamp
    Output: English transcript + original language transcript + speaker diarization
        │
        ▼
[2] Counselling Summarizer (5005)
    POST /api/v1/summarize
    Input: English transcript segments
    Output: counselling_facts[] + clinical_facts[] (CFS)
        │
        ▼
[3] Return to Frontend → SELECTIVE INCLUSION UI
    - Display counselling facts as selectable cards
    - Clinician reviews and checks/unchecks facts
    - Clinician clicks "Approve Selected"
        │
        ▼
[4] (On clinician approval) Fact Graph (5006)
    POST /api/v1/ingest
    Input: ONLY the approved clinical_facts[]
    Output: updated entities
```

**Note:** This workflow has a **human-in-the-loop step** between steps 3 and 4. The orchestrator returns after step 3 and waits for the clinician's approval via a separate endpoint.

```python
@app.post("/api/v1/workflow/counselling/approve")
async def approve_counselling_facts(
    patient_id: str,
    approved_fact_ids: list[str],
    session_id: str,
):
    """Called when clinician approves selected counselling facts."""
    # Retrieve the stored counselling facts for this session
    session = await get_counselling_session(session_id)
    
    # Filter to only approved facts
    approved_facts = [f for f in session.clinical_facts if f.id in approved_fact_ids]
    
    # Ingest approved facts into Fact Graph
    await call_agent("fact-graph", "ingest",
        json={"patient_id": patient_id, "facts": approved_facts},
    )
    
    return {"status": "approved", "facts_ingested": len(approved_facts)}
```

---

### 3.4 Workflow: Multi-Department Merge

**Trigger:** User submits notes from multiple departments  
**Frontend action:** Via "Merge Department Notes" page — upload/paste notes from each dept

```
USER SUBMITS MULTI-DEPT NOTES
        │
        ▼
[1] Department Merger (5007)
    POST /api/v1/merge
    Input: department_notes[] (text + department + date per entry)
    (Internally: calls SOAP Extractor for each dept in parallel)
    Output: unified_facts[] + conflicts[]
        │
        ├── No conflicts ──────────────────┐
        │                                   │
        ├── Conflicts found ──┐             │
        │                     ▼             │
        │          Return conflicts to      │
        │          Frontend for clinician    │
        │          review + resolution       │
        │                     │             │
        │          [Clinician resolves]      │
        │                     │             │
        │                     ▼             │
        └─────────────────────┘             │
                                            │
        ▼                                   ▼
[2] Fact Graph (5006)
    POST /api/v1/ingest
    Input: unified_facts[] (with provenance tags)
    Output: updated entities
```

---

### 3.5 Workflow: Generate Discharge Summary

**Trigger:** Clinician requests discharge summary generation  
**Frontend action:** Click "Generate Discharge Summary" on patient page

```
CLINICIAN REQUESTS SUMMARY
        │
        ▼
[1] Summary Generator (5008)
    POST /api/v1/generate
    Input: patient_id + dates + approved_counselling_ids + template
    (Internally: reads from Fact Graph, RECIST data, approved counselling)
    Output: structured discharge summary
        │
        ▼
[2] QA Agent (5009)
    POST /api/v1/validate
    Input: discharge_summary + source_facts
    Output: verdict (PASS/FAIL) + issues[] + audit_trail
        │
        ├── PASS ──────────────────────────┐
        │                                   │
        ├── FAIL ──────┐                    │
        │              ▼                    │
        │    Return issues to Frontend      │
        │    Clinician fixes / regenerates  │
        │              │                    │
        │    [Loop back to Step 1]          │
        │                                   │
        └───────────────────────────────────┘
                                            │
        ▼                                   ▼
[3] Translation Layer (5010)
    POST /api/v1/translate
    Input: approved_summary + target_language + output_options
    Output: English PDF + Translated PDF + Audio MP3 + FHIR JSON
        │
        ▼
[4] Return to Frontend
    - Download links for all output files
    - Summary preview
    - Audit trail reference
```

---

## 4. Real-Time Event System

For the tumor board / joint clinic use case, the orchestrator also runs an **event consumer** that listens for real-time updates.

### 4.1 Event Flow

```
New Clinical Event (lab, note, scan)
        │
        ▼
┌───────────────────┐
│  Kafka / Redis     │  ◄── Event Bus
│  Streams           │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Orchestrator      │  ◄── Event Consumer (background worker)
│  Event Handler     │
└────────┬──────────┘
         │
         ▼
  Route to appropriate workflow:
  - lab_result → Fact Graph ingest (direct)
  - dept_note → SOAP Extract → Fact Graph
  - scan_report → Radiology Extract → Fact Graph
         │
         ▼
┌───────────────────┐
│  Delta Processor   │  ◄── Only re-process changed sections
│  (within orchest.) │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  WebSocket Push    │  ◄── To connected dashboard clients
│  to Frontend       │
└───────────────────┘
```

### 4.2 WebSocket Implementation

```python
from fastapi import WebSocket

connected_clients: dict[str, list[WebSocket]] = {}  # patient_id → websocket list

@app.websocket("/ws/patient/{patient_id}")
async def patient_live_feed(websocket: WebSocket, patient_id: str):
    await websocket.accept()
    if patient_id not in connected_clients:
        connected_clients[patient_id] = []
    connected_clients[patient_id].append(websocket)
    
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        connected_clients[patient_id].remove(websocket)

async def notify_patient_update(patient_id: str, update: dict):
    """Push update to all connected dashboards for this patient."""
    if patient_id in connected_clients:
        for ws in connected_clients[patient_id]:
            await ws.send_json({
                "type": "patient_update",
                "patient_id": patient_id,
                "timestamp": datetime.utcnow().isoformat(),
                "update": update,
            })
```

---

## 5. Error Handling Strategy

```python
async def call_agent(agent_name: str, endpoint: str, **kwargs) -> dict:
    agent = AGENT_REGISTRY[agent_name]
    url = agent["url"] + agent["endpoints"][endpoint]
    
    for attempt in range(agent["retries"] + 1):
        try:
            response = await http_client.request(
                method=kwargs.get("method", "POST"),
                url=url.format(**kwargs.get("path_params", {})),
                timeout=agent["timeout_seconds"],
                **{k: v for k, v in kwargs.items() if k not in ["method", "path_params"]},
            )
            response.raise_for_status()
            return response.json()
        
        except httpx.TimeoutException:
            if attempt < agent["retries"]:
                await asyncio.sleep(2 ** attempt)  # exponential backoff
                continue
            raise AgentTimeoutError(f"{agent_name} timed out after {agent['retries']+1} attempts")
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < agent["retries"]:
                await asyncio.sleep(2 ** attempt)
                continue
            raise AgentError(f"{agent_name} returned {e.response.status_code}: {e.response.text}")
```

---

## 6. Frontend Routes (What the Web App Exposes)

The Next.js frontend communicates with the orchestrator via these routes:

| Frontend Page | Orchestrator Endpoint | Workflow |
|---|---|---|
| Upload Handwritten Note | `POST /api/v1/workflow/handwritten-note` | 3.1 |
| Add Radiology Report | `POST /api/v1/workflow/radiology-report` | 3.2 |
| Add Counselling Session | `POST /api/v1/workflow/counselling` | 3.3 |
| Approve Counselling Facts | `POST /api/v1/workflow/counselling/approve` | 3.3 (step 4) |
| Merge Department Notes | `POST /api/v1/workflow/department-merge` | 3.4 |
| Resolve Conflicts | `POST /api/v1/workflow/department-merge/resolve` | 3.4 (conflict resolution) |
| Generate Discharge Summary | `POST /api/v1/workflow/generate-summary` | 3.5 |
| Download Summary Files | `GET /api/v1/files/{file_id}` | 3.5 (after translation) |
| Patient Dashboard | `GET /api/v1/patient/{patient_id}/state` | Direct Fact Graph read |
| Patient Timeline | `GET /api/v1/patient/{patient_id}/timeline` | Direct Fact Graph read |
| Entity History | `GET /api/v1/patient/{patient_id}/entity/{id}` | Direct Fact Graph read |
| Live Updates (Tumor Board) | `WS /ws/patient/{patient_id}` | Section 4 |
| System Health | `GET /api/v1/health` | Health check all agents |

---

## 7. Docker Compose (Full Stack)

```yaml
version: "3.8"

services:
  # ── INFRASTRUCTURE ──
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: factgraph
      POSTGRES_USER: clinical
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # ── ORCHESTRATOR ──
  orchestrator:
    build: ./orchestrator
    ports:
      - "5000:5000"
    environment:
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://clinical:${DB_PASSWORD}@postgres:5432/factgraph
    depends_on:
      - postgres
      - redis
      - ocr-agent
      - soap-extractor
      - radiology-extractor
      - voice-transcription
      - counselling-summarizer
      - fact-graph
      - department-merger
      - summary-generator
      - qa-agent
      - translation-layer

  # ── AGENTS ──
  ocr-agent:
    build: ./ocr-agent
    ports:
      - "5001:5001"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - SARVAM_API_KEY=${SARVAM_API_KEY}

  soap-extractor:
    build: ./soap-extractor
    ports:
      - "5002:5002"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  radiology-extractor:
    build: ./radiology-extractor
    ports:
      - "5003:5003"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - radlex-data:/data

  voice-transcription:
    build: ./voice-transcription
    ports:
      - "5004:5004"
    environment:
      - SARVAM_API_KEY=${SARVAM_API_KEY}

  counselling-summarizer:
    build: ./counselling-summarizer
    ports:
      - "5005:5005"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  fact-graph:
    build: ./fact-graph
    ports:
      - "5006:5006"
    environment:
      - DATABASE_URL=postgresql://clinical:${DB_PASSWORD}@postgres:5432/factgraph
    depends_on:
      - postgres
    volumes:
      - radlex-data:/data

  department-merger:
    build: ./department-merger
    ports:
      - "5007:5007"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  summary-generator:
    build: ./summary-generator
    ports:
      - "5008:5008"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  qa-agent:
    build: ./qa-agent
    ports:
      - "5009:5009"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  translation-layer:
    build: ./translation-layer
    ports:
      - "5010:5010"
    environment:
      - SARVAM_API_KEY=${SARVAM_API_KEY}

  # ── FRONTEND ──
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://orchestrator:5000
      - NEXT_PUBLIC_WS_URL=ws://orchestrator:5000
    depends_on:
      - orchestrator

volumes:
  pgdata:
  radlex-data:
```

---

## 8. Development Order (Build Sequence)

Build in this order — each phase gives you a demoable product:

### Phase A: Foundation (Weeks 1-3)
1. **Fact Graph Engine** (Agent 06) — the core. Upgrade from log to state machine. Without this, nothing else works properly.
2. **Orchestrator** — basic scaffolding with agent registry and health checks.

### Phase B: Input Pipelines (Weeks 4-7)
3. **OCR Agent** (Agent 01) — add Sarvam Vision route alongside existing Gemini.
4. **SOAP Extractor** (Agent 02) — add CFS output stage. Wire to Fact Graph.
5. **Radiology Extractor** (Agent 03) — refactor with clinical intent + scope control. Wire to Fact Graph.

**Demo checkpoint:** Upload a handwritten note OR a radiology report → see structured extraction → see it in the patient timeline.

### Phase C: Voice + Counselling (Weeks 8-11)
6. **Voice Transcription** (Agent 04) — new, Sarvam integration.
7. **Counselling Summarizer** (Agent 05) — new, Claude-based extraction.
8. **Frontend: Selective Inclusion UI** — checkbox review interface.

**Demo checkpoint:** Upload a counselling audio → see transcript → see extracted facts → approve selected → see them in patient timeline.

### Phase D: Multi-Department + Outputs (Weeks 12-17)
9. **Department Merger** (Agent 07) — new, conflict detection.
10. **Summary Generator** (Agent 08) — new, NABH-compliant output.
11. **QA Agent** (Agent 09) — new, validation gatekeeper.
12. **Translation Layer** (Agent 10) — new, Sarvam translation + TTS.

**Demo checkpoint:** Upload notes from multiple departments + a radiology report + a counselling session → merge → generate discharge summary → get translated PDF + audio.

### Phase E: Real-Time + Polish (Weeks 18-22)
13. **Event Bus** (Kafka/Redis) — real-time event infrastructure.
14. **WebSocket Dashboard** — live updates for tumor boards.
15. **EMR Adapter** — HL7 FHIR integration.

**Final demo:** Full platform with real-time tumor board updates.

---

## 9. Environment Variables (.env master file)

```env
# ── API Keys ──
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
SARVAM_API_KEY=srv-...
OPENAI_API_KEY=sk-...          # for embeddings only

# ── Database ──
DB_PASSWORD=secure-password-here
DATABASE_URL=postgresql://clinical:${DB_PASSWORD}@postgres:5432/factgraph

# ── Infrastructure ──
REDIS_URL=redis://redis:6379
KAFKA_BROKERS=kafka:9092        # if using Kafka instead of Redis

# ── Feature Flags ──
SARVAM_ENABLED=true
REALTIME_UPDATES_ENABLED=false  # enable in Phase E
FHIR_EXPORT_ENABLED=false       # enable when EMR adapter is ready
```

---

## 10. Monitoring & Observability

Every agent logs in structured JSON format:

```json
{
  "timestamp": "2026-03-26T10:30:00Z",
  "agent": "ocr-agent",
  "level": "info",
  "event": "extraction_complete",
  "patient_id": "PAT-12345",
  "processing_time_ms": 2340,
  "engine_used": "gemini_vision",
  "confidence": 0.87
}
```

The orchestrator exposes a unified health endpoint:

```
GET /api/v1/health
```

```json
{
  "orchestrator": "ok",
  "agents": {
    "ocr-agent": {"status": "ok", "latency_ms": 45},
    "soap-extractor": {"status": "ok", "latency_ms": 38},
    "radiology-extractor": {"status": "ok", "latency_ms": 52},
    "voice-transcription": {"status": "ok", "latency_ms": 61},
    "counselling-summarizer": {"status": "ok", "latency_ms": 40},
    "fact-graph": {"status": "ok", "latency_ms": 12},
    "department-merger": {"status": "ok", "latency_ms": 55},
    "summary-generator": {"status": "ok", "latency_ms": 48},
    "qa-agent": {"status": "ok", "latency_ms": 35},
    "translation-layer": {"status": "degraded", "latency_ms": 2100, "note": "Sarvam TTS slow"}
  },
  "database": "ok",
  "event_bus": "ok"
}
```

---

## 11. Repository Structure

```
clinical-intelligence-platform/
├── orchestrator/                # This service — the brain
│   ├── main.py
│   ├── workflows/
│   │   ├── handwritten_note.py
│   │   ├── radiology_report.py
│   │   ├── counselling.py
│   │   ├── department_merge.py
│   │   └── discharge_summary.py
│   ├── agent_client.py          # HTTP client for calling agents
│   ├── agent_registry.py        # Agent definitions + health checks
│   ├── events/
│   │   ├── consumer.py          # Kafka/Redis event consumer
│   │   ├── publisher.py         # Event publisher
│   │   └── handlers.py          # Route events to workflows
│   ├── websocket.py             # WebSocket manager for live dashboard
│   ├── config.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── ocr-agent/                   # Agent 01 (see 01-ocr-agent.md)
├── soap-extractor/              # Agent 02 (see 02-soap-extractor.md)
├── radiology-extractor/         # Agent 03 (see 03-radiology-extractor.md)
├── voice-transcription/         # Agent 04 (see 04-voice-transcription.md)
├── counselling-summarizer/      # Agent 05 (see 05-counselling-summarizer.md)
├── fact-graph/                  # Agent 06 (see 06-fact-graph-engine.md)
├── department-merger/           # Agent 07 (see 07-department-merger.md)
├── summary-generator/           # Agent 08 (see 08-summary-generator.md)
├── qa-agent/                    # Agent 09 (see 09-qa-agent.md)
├── translation-layer/           # Agent 10 (see 10-translation-layer.md)
│
├── frontend/                    # Next.js web application
│   ├── app/
│   │   ├── dashboard/           # Patient dashboard
│   │   ├── upload/              # Upload interfaces
│   │   ├── review/              # Selective inclusion + conflict resolution
│   │   ├── summary/             # Discharge summary preview + download
│   │   └── live/                # Real-time tumor board view
│   ├── components/
│   │   ├── PatientTimeline.tsx
│   │   ├── EntityTrajectory.tsx
│   │   ├── CounsellingReview.tsx
│   │   ├── ConflictResolver.tsx
│   │   └── SummaryPreview.tsx
│   └── lib/
│       ├── api.ts               # HTTP client to orchestrator
│       └── websocket.ts         # WebSocket client for live updates
│
├── shared/                      # Shared schemas used by multiple agents
│   ├── clinical_fact_schema.py  # The CFS definition
│   ├── agent_envelope.py        # Standard agent request/response envelope
│   └── radlex/
│       └── radlex.db            # RadLex ontology database
│
├── docker-compose.yml           # Full stack deployment
├── docker-compose.dev.yml       # Development overrides
├── .env.example                 # Environment variable template
└── README.md
```

---

## 12. Key Architectural Principles

1. **Every agent is independently deployable and testable.** You can run any agent in isolation with `docker run` and hit its API with curl. No agent depends on another agent being alive to start up.

2. **All agents communicate through the Clinical Fact Schema.** No agent-to-agent direct calls except through the orchestrator. The CFS is the universal language.

3. **The Fact Graph is the single source of truth.** All reads and writes go through it. The frontend never reads directly from an agent — it reads from the Fact Graph via the orchestrator.

4. **Conflicts are never auto-resolved.** Any contradiction between departments or data sources is flagged for human review. Patient safety over convenience.

5. **Every claim is traceable.** From the final discharge summary, you can trace any statement back through the Summary Generator → Fact Graph → originating agent → source document/audio. This is the audit trail.

6. **Graceful degradation.** If Sarvam APIs are down, fall back to Google. If an agent is slow, the orchestrator reports degraded status. If QA fails, the summary doesn't release — it goes back for fixing. The system never produces output it can't verify.
