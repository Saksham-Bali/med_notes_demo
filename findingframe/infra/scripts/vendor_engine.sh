#!/usr/bin/env bash
# FindingFrame — R2 hardening: vendor an allowlisted, stripped copy of the tmc engine
# to infra/engine_vendor/, pinned to a source git SHA.
#
# Rationale / allowlist derivation
# ---------------------------------
# The engine adapter (backend/app/engine/adapter.py) only calls into:
#   extraction.finding_frame_extractor.FindingFrameExtractor
#   extraction.finding_frame_extractor._PROMPT_VERSION
#   extraction.finding_frame_schema.SCHEMA_VERSION
#   pipeline.finding_frame_processor.FindingFramePatientProcessor
# The build spec's original allowlist for this was:
#   extraction/, pipeline/, fact_graph/, oncology_response/, utils/, config/,
#   telemetry/, clinical_dimensions/, data/Radlex.xls (optional)
#
# Static import-graph analysis (grep across the whole tree) found that allowlist is
# NOT sufficient to make `import extraction` / `import pipeline` succeed on its own:
# package __init__.py files eagerly import submodules that reach outside it at
# *import time*, even though the adapter never calls those submodules directly:
#   extraction/__init__.py   -> extraction.entity_normalizer  -> entity_grounding
#   fact_graph/__init__.py   -> fact_graph.fact_store         -> entity_grounding
#   pipeline/__init__.py     -> pipeline.patient_processor    -> entity_grounding, gc_system
#   gc_system/progression_analyzer.py                          -> recist
# So this script additionally vendors entity_grounding/, gc_system/, and recist/ — all
# three are transitively load-bearing, not optional. Without them the vendored copy
# would fail with ModuleNotFoundError the moment `import extraction` runs.
#
# Two extraction/ modules (frame_slot_normalizer_v2.py, temporal_change_module.py) import
# from evaluation.frame_metrics, but nothing in the actual call path imports THEM (verified:
# no other file in the allowlist imports either module), and the one unguarded reference
# (frame_slot_normalizer_v2.py) is wrapped in try/except ImportError — so they degrade
# harmlessly as unused dead code once evaluation/ is excluded. evaluation/ is excluded
# in full: it holds the IRR/annotation/simulation material this vendor step exists to keep
# out of the shipped product.
#
# EXCLUDED (never copied): evaluation/, data/external_datasets/, outputs/, paper*/,
# scratch/, research/, tests/, api/, frontend/, gc_system/gc_template.md docs, model_comparison/,
# new_plan/, scripts/, .git/, __pycache__/, *.pyc, .eval_snapshot/, and any .env/.env.* file
# (config/.env carries tmc's own real secrets, e.g. its OPENROUTER_API_KEY — never vendor
# those into a Docker image; the backend injects its own credentials at runtime instead).
#
# Usage:
#   infra/scripts/vendor_engine.sh              # vendor into infra/engine_vendor/
#   infra/scripts/vendor_engine.sh --dry-run     # print the plan only, copy nothing
#   infra/scripts/vendor_engine.sh --verify-only  # re-check an existing vendor dir
#   infra/scripts/vendor_engine.sh --allow-untraceable
#       # skip the provenance guard below (dirty tree / unreachable-from-main) for a
#       # deliberate, documented exception. Record WHY in the commit that updates
#       # VENDOR_SHA -- this flag exists for real exceptions, not to silence the check.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FF_ROOT="$(cd "$INFRA_DIR/.." && pwd)"
PRE_DIR="$(cd "$FF_ROOT/.." && pwd)"
ENGINE_SRC="${FF_ENGINE_SRC:-$PRE_DIR/tmc}"
VENDOR_DIR="${FF_VENDOR_DIR:-$INFRA_DIR/engine_vendor}"

DRY_RUN=false
VERIFY_ONLY=false
ALLOW_UNTRACEABLE=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --verify-only) VERIFY_ONLY=true ;;
    --allow-untraceable) ALLOW_UNTRACEABLE=true ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

if [[ ! -d "$ENGINE_SRC" ]]; then
  echo "ERROR: engine source not found at $ENGINE_SRC" >&2
  exit 1
fi

# Directories copied whole (minus __pycache__ / *.pyc), see rationale above.
INCLUDE_DIRS=(
  extraction
  pipeline
  fact_graph
  oncology_response
  utils
  config
  telemetry
  clinical_dimensions
  entity_grounding
  gc_system
  recist
)

# Single optional data file (RadLex ontology xls used by entity_grounding/radlex_loader.py).
OPTIONAL_FILES=(
  "data/Radlex.xls"
)

RSYNC_EXCLUDES=(
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='.DS_Store'
  # config/ carries tmc's own real secrets (config/.env, e.g. its OPENROUTER_API_KEY) —
  # never vendor them into a Docker image. The adapter injects the FindingFrame backend's
  # own credentials via os.environ before touching engine code (see app/engine/adapter.py),
  # so the engine never needs its own .env at runtime here; config.yaml (no secrets) still
  # copies fine.
  --exclude='.env'
  --exclude='.env.*'
)

# ---------------------------------------------------------------------------
# Provenance guard: refuse to vendor (or claim clean via --dry-run/--verify-only)
# a source tree we could not trace back to a commit on the main line. This is the
# fix for the exact failure that shipped e04d3c6: it sat on an abandoned branch
# ("Frames") after a history rewrite and was never an ancestor of origin/main, so
# nobody could resolve its provenance from the main line at all
# (PRE_UPDATE_PLAN_2026-07-30.md §1.3). Runs in every mode (not just a real vendor)
# so `--dry-run`/`--verify-only` actually tell you whether the CURRENT checkout at
# $ENGINE_SRC would pass, per the same plan's requirement to verify this guard
# without re-vendoring.
# ---------------------------------------------------------------------------
if [[ "$ALLOW_UNTRACEABLE" == true ]]; then
  echo "WARNING: --allow-untraceable set -- skipping the source-tree provenance guard." >&2
  echo "  Record why in the commit that updates VENDOR_SHA." >&2
else
  if ! git -C "$ENGINE_SRC" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: $ENGINE_SRC is not a git checkout -- cannot verify provenance." >&2
    echo "  Fix: vendor from a real git checkout of the engine repo, or pass" >&2
    echo "  --allow-untraceable for a deliberate, documented exception." >&2
    exit 1
  fi

  # (a) no uncommitted changes inside what actually gets vendored. Checked as tracked
  # + untracked (mirrors backend/app/engine/adapter.py::_resolve_git_sha's definition
  # of "dirty" -- one definition across the system), but scoped to INCLUDE_DIRS /
  # OPTIONAL_FILES only: an untracked scratch note in e.g. paper/ or research/ never
  # ships and must not block vendoring something that IS clean.
  dirty="$(git -C "$ENGINE_SRC" status --porcelain -- \
      "${INCLUDE_DIRS[@]}" "${OPTIONAL_FILES[@]}" 2>/dev/null || true)"
  if [[ -n "$dirty" ]]; then
    echo "ERROR: $ENGINE_SRC has uncommitted changes inside the vendored paths:" >&2
    echo "$dirty" >&2
    echo "  Fix: commit or stash these changes so the vendored copy traces to a real" >&2
    echo "  commit, then re-run. Use --allow-untraceable only for a deliberate," >&2
    echo "  documented exception." >&2
    exit 1
  fi
  echo "OK: no uncommitted changes in vendored paths"

  # (b) the resolved SHA must be reachable from the SOURCE repo's own origin/main --
  # NOT the product (pre) repo's; a tmc SHA does not resolve inside pre. Best-effort
  # fetch first (freshest signal); a fetch failure (offline, no credentials) is a
  # connectivity problem, not a provenance one, so we fall back to whatever
  # origin/main ref is already known locally rather than hard-failing on it.
  # GIT_TERMINAL_PROMPT=0 stops git from blocking on an interactive credential prompt.
  SRC_SHA="$(git -C "$ENGINE_SRC" rev-parse HEAD)"
  if ! GIT_TERMINAL_PROMPT=0 git -C "$ENGINE_SRC" fetch origin main --quiet 2>/dev/null; then
    echo "WARN: could not fetch $ENGINE_SRC's origin/main (offline?) -- checking" >&2
    echo "  reachability against the last-known local origin/main ref instead." >&2
  fi
  if ! git -C "$ENGINE_SRC" rev-parse --verify -q origin/main >/dev/null; then
    echo "ERROR: $ENGINE_SRC has no origin/main ref to check reachability against." >&2
    echo "  Fix: add/fetch a remote named 'origin' with a 'main' branch, or pass" >&2
    echo "  --allow-untraceable to skip this check for a deliberate exception." >&2
    exit 1
  fi
  if ! git -C "$ENGINE_SRC" merge-base --is-ancestor "$SRC_SHA" origin/main; then
    echo "ERROR: $SRC_SHA is not an ancestor of $ENGINE_SRC's origin/main." >&2
    echo "  This is the exact failure mode that shipped e04d3c6: a commit that sits on" >&2
    echo "  an abandoned branch after a history rewrite and cannot be traced from the" >&2
    echo "  main line. Fix: get this commit onto origin/main (merge/rebase it there)" >&2
    echo "  first, or pass --allow-untraceable for a deliberate, documented exception." >&2
    exit 1
  fi
  echo "OK: $SRC_SHA is an ancestor of origin/main"
fi
echo

echo "FindingFrame engine vendor"
echo "  source: $ENGINE_SRC"
echo "  target: $VENDOR_DIR"
echo

if [[ "$VERIFY_ONLY" != true ]]; then
  echo "Plan: vendor these top-level dirs from tmc:"
  for d in "${INCLUDE_DIRS[@]}"; do
    if [[ -d "$ENGINE_SRC/$d" ]]; then
      n=$(find "$ENGINE_SRC/$d" -name '*.py' | wc -l | tr -d ' ')
      echo "  - $d/  ($n .py files)"
    else
      echo "  - $d/  (MISSING in source — skipped)"
    fi
  done
  for f in "${OPTIONAL_FILES[@]}"; do
    if [[ -f "$ENGINE_SRC/$f" ]]; then
      sz=$(du -h "$ENGINE_SRC/$f" | cut -f1)
      echo "  - $f  (optional, $sz)"
    else
      echo "  - $f  (optional, not present — skipped)"
    fi
  done
  echo
  echo "Explicitly excluded (never touched): evaluation/, data/external_datasets/, outputs/,"
  echo "  paper*/, scratch/, research/, tests/, api/, frontend/, model_comparison/, new_plan/,"
  echo "  scripts/, .git/, .eval_snapshot/"
  echo
fi

if [[ "$DRY_RUN" == true ]]; then
  echo "(--dry-run: no files copied)"
  exit 0
fi

if [[ "$VERIFY_ONLY" != true ]]; then
  echo "Resetting $VENDOR_DIR ..."
  rm -rf "$VENDOR_DIR"
  mkdir -p "$VENDOR_DIR"

  for d in "${INCLUDE_DIRS[@]}"; do
    if [[ -d "$ENGINE_SRC/$d" ]]; then
      mkdir -p "$VENDOR_DIR/$d"
      rsync -a "${RSYNC_EXCLUDES[@]}" "$ENGINE_SRC/$d/" "$VENDOR_DIR/$d/"
      echo "  vendored $d/"
    fi
  done

  for f in "${OPTIONAL_FILES[@]}"; do
    if [[ -f "$ENGINE_SRC/$f" ]]; then
      mkdir -p "$VENDOR_DIR/$(dirname "$f")"
      cp "$ENGINE_SRC/$f" "$VENDOR_DIR/$f"
      echo "  vendored $f (optional)"
    fi
  done

  # __init__.py for the top-level "data" package if we copied anything into data/
  if [[ -d "$VENDOR_DIR/data" && ! -f "$VENDOR_DIR/data/__init__.py" ]]; then
    : > "$VENDOR_DIR/data/__init__.py"
  fi

  # Pin the source git SHA.
  VENDOR_SHA="$(git -C "$ENGINE_SRC" rev-parse HEAD 2>/dev/null || echo "unknown")"
  {
    echo "$VENDOR_SHA"
  } > "$VENDOR_DIR/VENDOR_SHA"
  echo
  echo "Pinned VENDOR_SHA: $VENDOR_SHA"
fi

# ---------------------------------------------------------------------------
# Verification: no simulated/fabricated IRR material, no excluded dirs, importable.
# ---------------------------------------------------------------------------
echo
echo "=== Verification ==="

bad_irr="$(find "$VENDOR_DIR" -iname '*irr*' -o -iname '*simulate*' 2>/dev/null || true)"
if [[ -n "$bad_irr" ]]; then
  echo "FAIL: found *irr*/*simulate* file(s) in vendored copy:" >&2
  echo "$bad_irr" >&2
  exit 1
fi
echo "OK: no *irr*/*simulate* files present"

bad_env="$(find "$VENDOR_DIR" -name '.env' -o -name '.env.*' 2>/dev/null || true)"
if [[ -n "$bad_env" ]]; then
  echo "FAIL: found .env file(s) (real secrets risk) in vendored copy:" >&2
  echo "$bad_env" >&2
  exit 1
fi
echo "OK: no .env files present"

for excluded in evaluation outputs paper paper_jamia_archive scratch research tests \
                api frontend model_comparison new_plan scripts; do
  if [[ -e "$VENDOR_DIR/$excluded" ]]; then
    echo "FAIL: excluded path leaked into vendor: $excluded" >&2
    exit 1
  fi
done
echo "OK: no excluded top-level dirs present"

n_files="$(find "$VENDOR_DIR" -type f | wc -l | tr -d ' ')"
n_py="$(find "$VENDOR_DIR" -name '*.py' | wc -l | tr -d ' ')"
size="$(du -sh "$VENDOR_DIR" 2>/dev/null | cut -f1)"
echo "Vendor dir: $n_files files ($n_py .py), $size total"

if [[ -f "$VENDOR_DIR/VENDOR_SHA" ]]; then
  echo "VENDOR_SHA: $(cat "$VENDOR_DIR/VENDOR_SHA")"
fi

# Smoke test: does the vendored copy actually import (matches what adapter._prepare() does)?
PYBIN="${PYTHON_BIN:-$FF_ROOT/backend/.venv/bin/python}"
if [[ -x "$PYBIN" ]]; then
  echo
  echo "Import smoke test via $PYBIN ..."
  "$PYBIN" - "$VENDOR_DIR" <<'PY'
import sys
vendor_dir = sys.argv[1]
sys.path.insert(0, vendor_dir)
import extraction.finding_frame_extractor as e   # noqa: F401
import extraction.finding_frame_schema as s       # noqa: F401
import pipeline.finding_frame_processor as p      # noqa: F401
print(f"  OK: extraction/pipeline import cleanly from vendored copy")
print(f"  prompt_version={e._PROMPT_VERSION!r} schema_version={s.SCHEMA_VERSION!r}")
PY
else
  echo "(skipping import smoke test: $PYBIN not found/executable)"
fi

# The smoke test imports from VENDOR_DIR, so CPython writes __pycache__/*.pyc back into
# it -- after rsync already excluded exactly those paths. Dockerfile.backend/.worker COPY
# this directory wholesale, so left alone the image ships host bytecode (built here on
# macOS, loaded in a Linux container, where the magic number never matches and it is dead
# weight), and the vendored tree stops being byte-reproducible from a given VENDOR_SHA --
# which is the one property it exists to provide. Clean up after ourselves.
find "$VENDOR_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$VENDOR_DIR" -name '*.pyc' -delete 2>/dev/null || true

echo
echo "Vendor complete."
