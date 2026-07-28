#!/bin/bash
set -e

# ==============================================================================
# DEPLOYMENT SCRIPT FOR TYRONE (BARE-METAL, NO DOCKER, NO CONDA)
# Uses system Python 3.12 + project-local venv
# Backend runs on tyrone, frontend runs locally on your laptop
# ==============================================================================

PROJECT_DIR="$HOME/projects/pre"
LOG_DIR="$PROJECT_DIR/logs"
VENV_DIR="$PROJECT_DIR/.platform_venv"

mkdir -p "$LOG_DIR" "$PROJECT_DIR/data/fact_graph"
cd "$PROJECT_DIR" || { echo "ERROR: $PROJECT_DIR not found"; exit 1; }

# ==============================================================================
# 1. RESOURCE CHECK
# ==============================================================================
echo "=== Checking resources ==="
nvidia-smi 2>/dev/null || echo "(No GPU — OK for this deployment)"

# ==============================================================================
# 2. PYTHON VENV (project-local)
# ==============================================================================
if [ ! -d "$VENV_DIR" ]; then
    echo "=== Creating virtual environment ==="
    python3 -m venv "$VENV_DIR"
fi

echo "=== Installing dependencies ==="
"$VENV_DIR/bin/pip" install -q --upgrade pip 2>&1 | tail -1
"$VENV_DIR/bin/pip" install -q \
    fastapi "uvicorn[standard]" httpx openai pydantic pydantic-settings \
    python-multipart mutagen jinja2 scikit-learn pandas openpyxl \
    rapidfuzz python-Levenshtein aiosqlite python-dotenv 2>&1 | tail -3
echo "  Done."

# ==============================================================================
# 3. KILL PREVIOUS PROCESSES
# ==============================================================================
echo "=== Stopping previous platform processes ==="
pkill -f "uvicorn.*:500[0-9]" 2>/dev/null || true
pkill -f "uvicorn.*:8000" 2>/dev/null || true
sleep 2

# ==============================================================================
# 4. ENVIRONMENT VARIABLES
# ==============================================================================
export OPENROUTER_API_KEY="sk-or-..."
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export LLM_MODEL="openai/gpt-4o-mini"
export SARVAM_API_KEY="sk_py5uq3wn_ABmCmnEE8AowmTDhN890kiNt"
export ENABLE_FACT_GRAPH="true"
export ENABLE_RADIOLOGY_EXTRACTOR="true"
export ENABLE_OCR_AGENT="true"
export ENABLE_SOAP_EXTRACTOR="true"
export ENABLE_VOICE_TRANSCRIPTION="true"
export ENABLE_COUNSELLING_SUMMARIZER="true"
export ENABLE_DEPARTMENT_MERGER="true"
export ENABLE_SUMMARY_GENERATOR="true"
export ENABLE_QA_AGENT="true"
export ENABLE_TRANSLATION_LAYER="true"
export FACT_GRAPH_URL="http://localhost:5006"
export RADIOLOGY_EXTRACTOR_URL="http://localhost:5003"
export OCR_AGENT_URL="http://localhost:5001"
export SOAP_EXTRACTOR_URL="http://localhost:5002"
export VOICE_TRANSCRIPTION_URL="http://localhost:5004"
export COUNSELLING_SUMMARIZER_URL="http://localhost:5005"
export DEPARTMENT_MERGER_URL="http://localhost:5007"
export SUMMARY_GENERATOR_URL="http://localhost:5008"
export QA_AGENT_URL="http://localhost:5009"
export TRANSLATION_LAYER_URL="http://localhost:5010"
export DATA_DIR="$PROJECT_DIR/data/fact_graph"
export FACT_GRAPH_BASE_URL="http://localhost:5006"

PY="$VENV_DIR/bin/python"
UVI="$VENV_DIR/bin/uvicorn"

# ==============================================================================
# 5. START SERVICES
# ==============================================================================
echo ""
echo "=== Starting 11 backend services ==="

start_service() {
    local name=$1
    local dir=$2
    local module=$3
    local port=$4
    local logfile="$LOG_DIR/$name.log"

    echo "  [$port] $name..."
    cd "$PROJECT_DIR/$dir"
    nohup "$UVI" "$module" --host 0.0.0.0 --port "$port" > "$logfile" 2>&1 &
    cd "$PROJECT_DIR"
}

start_service "fact-graph"             "fact-graph-service"          "app.main:app" 5006
start_service "ocr-agent"              "ocr-agent"                   "app.main:app" 5001
start_service "soap-extractor"         "soap-extractor"              "app.main:app" 5002
start_service "radiology-extractor"    "radiology-extractor"         "app.main:app" 5003
start_service "voice-transcription"    "2nd"                         "main:app"     5004
start_service "counselling-summarizer" "3rd/counselling-summarizer"  "main:app"     5005
start_service "department-merger"      "4th/department-merger"       "main:app"     5007
start_service "summary-generator"      "5th"                         "main:app"     5008
start_service "qa-agent"               "6th/qa-agent"                "main:app"     5009
start_service "translation-layer"      "7th"                         "main:app"     5010
start_service "orchestrator"           "final/orchestrator"          "app.main:app" 8000

# ==============================================================================
# 6. WAIT AND VERIFY
# ==============================================================================
echo ""
echo "=== Waiting 10 seconds for services to start ==="
sleep 10

echo ""
echo "=== Health Checks ==="
PASS=0
FAIL=0

check() {
    local name=$1 port=$2 path=${3:-/health}
    if curl -sf "http://localhost:$port$path" > /dev/null 2>&1; then
        echo "  OK   $name (:$port)"
        PASS=$((PASS+1))
    else
        echo "  FAIL $name (:$port) — check $LOG_DIR/$name.log"
        FAIL=$((FAIL+1))
    fi
}

check "fact-graph"             5006
check "ocr-agent"              5001
check "soap-extractor"         5002
check "radiology-extractor"    5003
check "voice-transcription"    5004
check "counselling-summarizer" 5005
check "department-merger"      5007
check "summary-generator"      5008
check "qa-agent"               5009
check "translation-layer"      5010
check "orchestrator"           8000 /healthz

echo ""
echo "  $PASS passed, $FAIL failed"

# ==============================================================================
# 7. SEED PATIENTS
# ==============================================================================
if [ "$FAIL" -lt 2 ]; then
    echo ""
    echo "=== Seeding 5 patients into Fact Graph ==="
    "$PY" "$PROJECT_DIR/scripts/seed_patients.py" http://localhost:5006 2>&1
fi

# ==============================================================================
# 8. DONE
# ==============================================================================
echo ""
echo "=============================================================================="
echo "BACKEND DEPLOYMENT COMPLETE"
echo ""
echo "  Orchestrator API: http://localhost:8000"
echo "  Health check:     curl http://localhost:8000/api/v1/health"
echo "  Patient list:     curl http://localhost:8000/api/v1/patients"
echo ""
echo "  FROM YOUR LAPTOP:"
echo "    1. SSH tunnel:  ssh -L 8000:localhost:8000 tyrone"
echo "    2. Start UI:    cd platform-ui && npm install && npm run dev"
echo "    3. Open:        http://localhost:3000"
echo ""
echo "  TO STOP:  pkill -f 'uvicorn.*:500[0-9]'; pkill -f 'uvicorn.*:8000'"
echo "  LOGS:     ls $LOG_DIR/"
echo "=============================================================================="
