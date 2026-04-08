#!/usr/bin/env bash
# =============================================================================
# run_eval.sh — Voice Pipeline Evaluation Runner (Tyrone)
# =============================================================================
# Installs eval-only dependencies into the platform venv, then runs
# eval_voice_pipeline.py with the same env vars the platform uses.
#
# Usage (from repo root on Tyrone):
#   bash scripts/run_eval.sh            # Phase 1, full dataset
#   bash scripts/run_eval.sh 2          # Phase 1+2 (LLM correction delta)
#   bash scripts/run_eval.sh 1 100      # Phase 1, first 100 samples
#   bash scripts/run_eval.sh 2 100 conversation  # Phase 2, conversations only
#
# Arguments:
#   $1  phase      (1 or 2, default: 1)
#   $2  max-samples (integer, default: all 3620)
#   $3  context    (conversation | narrated | demonstration | all, default: all)
# =============================================================================

set -euo pipefail

PHASE="${1:-1}"
MAX_SAMPLES="${2:-}"
CONTEXT="${3:-}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.platform_venv"

echo "=================================================="
echo " Voice Pipeline Evaluation"
echo " Phase: $PHASE"
echo " Max samples: ${MAX_SAMPLES:-all 3620}"
echo " Context: ${CONTEXT:-all}"
echo "=================================================="

# ------------------------------------------------------------------------------
# 1. Sanity checks
# ------------------------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
    echo "ERROR: Platform venv not found at $VENV_DIR"
    echo "       Run deploy_tyrone.sh first."
    exit 1
fi

if [[ -z "${SARVAM_API_KEY:-}" ]]; then
    # Try to source from deploy_tyrone.sh env block
    echo "SARVAM_API_KEY not set — sourcing from deploy_tyrone.sh..."
    # shellcheck disable=SC1090
    eval "$(grep '^export ' "$PROJECT_DIR/deploy_tyrone.sh")"
fi

if [[ -z "${SARVAM_API_KEY:-}" ]]; then
    echo "ERROR: SARVAM_API_KEY is required. Set it or run deploy_tyrone.sh first."
    exit 1
fi

if [[ "$PHASE" == "2" ]] && [[ -z "${AZURE_API_KEY:-}" ]]; then
    echo "ERROR: Phase 2 requires AZURE_API_KEY. Set it or run deploy_tyrone.sh first."
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. Install eval-only dependencies (idempotent)
# ------------------------------------------------------------------------------
echo ""
echo "=== Installing eval dependencies ==="
"$VENV_DIR/bin/pip" install -q --upgrade \
    "jiwer>=3.0" \
    "datasets>=2.20" \
    "huggingface_hub>=0.24" \
    "soundfile>=0.12" \
    2>&1 | tail -3
echo "  Done."

# ------------------------------------------------------------------------------
# 3. Build python args
# ------------------------------------------------------------------------------
PYTHON_ARGS="--phase $PHASE"

if [[ -n "$MAX_SAMPLES" && "$MAX_SAMPLES" != "0" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --max-samples $MAX_SAMPLES"
fi

if [[ -n "$CONTEXT" && "$CONTEXT" != "all" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --context $CONTEXT"
fi

# ------------------------------------------------------------------------------
# 4. Estimate compute before starting
# ------------------------------------------------------------------------------
SAMPLE_COUNT="${MAX_SAMPLES:-3620}"
SARVAM_TIME=$(echo "$SAMPLE_COUNT * 1.1 / 60" | bc -l | xargs printf "%.0f")
TOTAL_TIME="$SARVAM_TIME"

if [[ "$PHASE" == "2" ]]; then
    LLM_TIME=$(echo "$SAMPLE_COUNT * 1.5 / 60" | bc -l | xargs printf "%.0f")
    TOTAL_TIME=$(echo "$SARVAM_TIME + $LLM_TIME" | bc)
    # Token estimates: ~170 input + 150 output per call on gpt-4o-mini
    INPUT_TOKENS=$(echo "$SAMPLE_COUNT * 170 / 1000000" | bc -l | xargs printf "%.2f")
    OUTPUT_TOKENS=$(echo "$SAMPLE_COUNT * 150 / 1000000" | bc -l | xargs printf "%.2f")
    INPUT_COST=$(echo "$SAMPLE_COUNT * 170 * 0.15 / 1000000" | bc -l | xargs printf "%.2f")
    OUTPUT_COST=$(echo "$SAMPLE_COUNT * 150 * 0.60 / 1000000" | bc -l | xargs printf "%.2f")
    TOTAL_COST=$(echo "$INPUT_COST + $OUTPUT_COST" | bc -l | xargs printf "%.2f")
    echo ""
    echo "=== Compute estimate ==="
    echo "  Sarvam calls   : $SAMPLE_COUNT @ 1.1s throttle → ~${SARVAM_TIME}m"
    echo "  Azure LLM calls: $SAMPLE_COUNT @ 1.5s avg       → ~${LLM_TIME}m"
    echo "  Total wall time: ~${TOTAL_TIME}m"
    echo "  Azure tokens   : ~${INPUT_TOKENS}M input + ${OUTPUT_TOKENS}M output"
    echo "  Azure cost     : ~\$${INPUT_COST} input + \$${OUTPUT_COST} output = ~\$${TOTAL_COST}"
    echo "  Sarvam cost    : credit-based (check dashboard.sarvam.ai/billing)"
else
    echo ""
    echo "=== Compute estimate ==="
    echo "  Sarvam calls   : $SAMPLE_COUNT @ 1.1s throttle → ~${SARVAM_TIME}m"
    echo "  Azure LLM calls: none (Phase 1 only)"
    echo "  Total wall time: ~${SARVAM_TIME}m"
    echo "  Azure cost     : \$0"
    echo "  Sarvam cost    : credit-based (check dashboard.sarvam.ai/billing)"
fi

echo ""
echo "Results will be saved to: $PROJECT_DIR/eval_results/"
echo ""
echo "Starting in 5 seconds (Ctrl-C to cancel)..."
sleep 5

# ------------------------------------------------------------------------------
# 5. Run
# ------------------------------------------------------------------------------
cd "$PROJECT_DIR"
"$VENV_DIR/bin/python" scripts/eval_voice_pipeline.py $PYTHON_ARGS
