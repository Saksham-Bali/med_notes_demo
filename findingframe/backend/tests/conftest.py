"""Test bootstrap: make both the backend (``app``) and the sibling ``worker`` package
importable, and ensure unit tests never require a live LLM key or DB."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FINDINGFRAME_DIR = BACKEND_DIR.parent

for p in (str(BACKEND_DIR), str(FINDINGFRAME_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Keep the engine offline in unit tests (no accidental network / key requirement).
os.environ.setdefault("FF_OPENROUTER_API_KEY", "")
os.environ.setdefault("FF_OPENAI_API_KEY", "")
