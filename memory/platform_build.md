---
name: Platform Build State
description: What microservices exist, their ports, locations, test status, and what's still pending
type: project
---

# Clinical Intelligence Platform — Build State (April 2026)

## Fully built and tested services

| Service | Port | Location | Tests |
|---|---|---|---|
| fact-graph-service (Agent 06) | 5006 | `fact-graph-service/` | 12/12 pass |
| ocr-agent (Agent 01) | 5001 | `ocr-agent/` | 19/19 pass |
| soap-extractor (Agent 02) | 5002 | `soap-extractor/` | 25/25 pass |
| radiology-extractor (Agent 03) | 5003 | `radiology-extractor/` | 24/24 pass |
| voice-transcription (Agent 04) | 5004 | `2nd/` | pre-existing |
| counselling-summarizer (Agent 05) | 5005 | `3rd/counselling-summarizer/` | pre-existing |
| department-merger (Agent 07) | 5007 | `4th/department-merger/` | pre-existing |
| summary-generator (Agent 08) | 5008 | `5th/` | pre-existing |
| qa-agent (Agent 09) | 5009 | `6th/qa-agent/` | pre-existing |
| translation-layer (Agent 10) | 5010 | `7th/` | pre-existing |
| orchestrator | 8000 (host) | `final/orchestrator/` | 3/3 pass |

## Frontend UI
- `platform-ui/` — Next.js 14 app, dark clinical theme ("ClinIQ")
- Pages: Dashboard (health panel + patient search), Upload Note, Upload Radiology, Merge Departments, Patient Dashboard, Generate Summary
- Proxies all API calls through `/api/proxy/[...path]` to avoid CORS

## Radiology research pipeline (separate from platform)
- `tmc/` — standalone pipeline, F1=0.871 on best patient, 0.592 mean
- Has its own frontend at `tmc/frontend/`
- TMC pipeline code is copied into `radiology-extractor/tmc_core/` for platform use

## LLM migration
- All agents (05, 07, 08, 09, 01, 02, 03, 06) now use Azure OpenAI
- Old agents 05/07/08/09 were migrated from OpenRouter
- Key change: `OpenAI(base_url=openrouter)` → `AzureOpenAI(azure_endpoint=...)`

## docker-compose
- `docker-compose.yml` at project root
- All 12 services + postgres + redis + frontend
- Orchestrator host port 8000 (avoids macOS AirPlay conflict with 5000)
- `fact-graph-data` volume for persistence

## To start the full stack
```bash
cd /Users/sher/project/pre
docker compose up -d --build
# UI at http://localhost:3000
# Orchestrator at http://localhost:8000
```

## For tyrone deployment
```bash
ssh tyrone
tmux new -s platform-demo
rsync -avz /Users/sher/project/pre/ tyrone:~/projects/pre/ --exclude='.git' --exclude='venv' --exclude='node_modules' --exclude='__pycache__'
cd ~/projects/pre
nvidia-smi  # check GPU idle before starting
docker compose up -d --build
# SSH tunnel: ssh -L 8000:localhost:8000 -L 3000:localhost:3000 tyrone
```

**Why:** Radiology-extractor (tmc_core) is CPU/memory heavy for ML models. Tyrone has 100+ cores, 120GB RAM.
**How to apply:** Always deploy to tyrone for production runs; local for dev/test only.
