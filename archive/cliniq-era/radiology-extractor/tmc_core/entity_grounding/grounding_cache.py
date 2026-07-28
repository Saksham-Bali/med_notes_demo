"""
Disk-backed cache for entity grounding decisions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CACHE_MISS_SENTINEL = "__GROUNDING_FAILED__"
CACHE_VERSION = "v15"


def _key(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    normalized = re.sub(r"\s+", " ", text).strip()
    return f"{CACHE_VERSION}:{normalized}"


class GroundingCache:
    def __init__(self, cache_path: str = "./outputs/cache/grounding_cache.json"):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Any] | None = None

    def _load(self) -> None:
        if self._cache is not None:
            return
        if not self.cache_path.exists():
            self._cache = {}
            return
        try:
            self._cache = json.loads(
                self.cache_path.read_text(encoding="utf-8", errors="ignore")
            )
            if not isinstance(self._cache, dict):
                self._cache = {}
        except Exception:
            self._cache = {}

    def _persist(self) -> None:
        assert self._cache is not None
        self.cache_path.write_text(
            json.dumps(self._cache, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, surface_form: str) -> dict[str, Any] | str | None:
        self._load()
        assert self._cache is not None
        return self._cache.get(_key(surface_form))

    def set(self, surface_form: str, payload: dict[str, Any]) -> None:
        self._load()
        assert self._cache is not None
        self._cache[_key(surface_form)] = payload
        self._persist()

    def set_miss(self, surface_form: str) -> None:
        self._load()
        assert self._cache is not None
        self._cache[_key(surface_form)] = CACHE_MISS_SENTINEL
        self._persist()
