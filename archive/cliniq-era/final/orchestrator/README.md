# Clinical Intelligence Platform Orchestrator

This is the first build slice of the master orchestrator described in [`final/project.md`](/Users/sher/project/pre/final/project.md).

What is implemented now:

- Agent registry with per-service health checks
- Retry-aware HTTP client for downstream agent calls
- Counselling workflow orchestration:
  - voice transcription
  - counselling summarization
  - clinician approval handoff
- Department merge orchestration
- QA + translation orchestration for a supplied draft discharge summary
- File-backed deferred jobs for Fact Graph ingest until that service exists
- File-backed counselling session storage for clinician approval flow

What is intentionally deferred:

- Fact Graph integration beyond deferred-job queuing
- Summary Generator-driven discharge summary creation
- OCR, SOAP, and radiology workflows beyond scaffold status
- Real-time event bus and WebSocket live updates

Run locally:

```bash
cd final/orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 5000
```

Useful environment flags:

```bash
ENABLE_FACT_GRAPH=false
ENABLE_SUMMARY_GENERATOR=false
ENABLE_VOICE_TRANSCRIPTION=true
ENABLE_COUNSELLING_SUMMARIZER=true
ENABLE_DEPARTMENT_MERGER=true
ENABLE_QA_AGENT=true
ENABLE_TRANSLATION_LAYER=true
```
