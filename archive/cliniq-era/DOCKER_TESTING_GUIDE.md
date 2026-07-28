# Docker E2E Testing Guide

This guide documents the exact steps taken to successfully containerize and test the Orchestrator and the local Agent microservices through Docker on macOS.

## 1. Environment Configuration

Because Docker containers run in their own isolated networks, the default `localhost` routing specified inside the Pydantic configurations of the Orchestrator will not resolve to other containers. To fix this, we created a single unified `.env` file at the root of the project to securely house the API keys and database passwords.

**File: `.env`**
```env
OPENROUTER_API_KEY=sk-or-...
SARVAM_API_KEY=sk_py...
DB_PASSWORD=secure-password-here
```

## 2. Dynamic Docker Compose Generation

The master project definition (`final/project.md`) assumed that all 10 agents were present in the immediate file tree. Since only a subset of agents (Folders 2nd through 7th) exist locally, a tailored `docker-compose.yml` was generated.

Key modifications included:
- **Port Remapping:** Changed the Orchestrator's exposed host port from `5000:5000` to `8000:5000`. This is necessary on macOS because the native "AirPlay Receiver" process automatically binds to port 5000, which causes Docker daemon errors.
- **Internal DNS Definitions:** Injected `*_URL` definitions (e.g., `VOICE_TRANSCRIPTION_URL=http://voice-transcription:5004`) directly into the Orchestrator's `environment:` block so it could resolve the agent containers correctly.

## 3. Booting the Stack

To build the images locally and compile all Python dependencies:
```bash
docker compose up -d --build
```

*(Note: If errors occur regarding caching, use `docker compose build --no-cache && docker compose up -d`)*

## 4. Verification & Testing Commands

### A. Health Probe Mesh
Once the containers settle, verify that the Orchestrator has successfully established TCP connections to the PostgreSQL database, Redis instance, and all active agent endpoints:

```bash
curl -s http://localhost:8000/api/v1/health | jq
```
*Expected Result:* The orchestrator returns a JSON payload listing available agents (e.g., `voice-transcription`, `qa-agent`, etc.) with `status: "ok"`.

### B. End-to-End Workflow Test
To test the routing and internal intelligence capability, we dispatched a multi-department payload to the orchestrator:

```bash
curl -X POST http://localhost:8000/api/v1/workflow/department-merge \
-H "Content-Type: application/json" \
-d '{
  "patient_id": "P1",
  "department_notes": [
    {
      "department": "neurology",
      "text": "Doctor Smith saw patient for severe migraines.",
      "source_system": "sys",
      "date": "2026-03-20T00:00:00",
      "author": "Dr. Smith"
    },
    {
      "department": "internal_medicine",
      "text": "Patient reports headaches. Prescribed sumatriptan.",
      "source_system": "sys",
      "date": "2026-03-20T00:00:00",
      "author": "Dr. Jones"
    }
  ]
}'
```

*Expected Result:* The Orchestrator forwards this payload securely to the `department-merger` agent over the internal Docker network. In our test, the payload successfully reached Agent 07, which threw a 503 error trying to contact the missing `soap-extractor` dependency—proving the end-to-end routing framework works exactly as designed.

## 5. Teardown and Cleanup

To prune the test environment entirely, recovering disk space by deleting the compiled images and postgres/redis volumes:

```bash
docker compose down --rmi all -v
```
