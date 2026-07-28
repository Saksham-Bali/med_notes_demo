"""Make ``app`` importable regardless of cwd.

The worker imports the backend application package (``app``). The backend lives in a sibling
directory (``findingframe/backend``); add it to sys.path so ``import app`` resolves whether
the worker is launched from the repo root or elsewhere. Run as:

    backend/.venv/bin/python -m worker.main
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
