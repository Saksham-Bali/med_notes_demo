"""Small hashing helpers used by the audit hash-chain, signed link decisions,
target-lesion selections, and sign-off payloads."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, ``default=str`` so UUIDs /
    datetimes serialize stably. The exact same bytes hash the same everywhere."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def chain_hash(prev_hash: str | None, payload: Any) -> str:
    """row_hash = sha256(prev_hash + canonical(payload))."""
    return sha256_hex((prev_hash or "") + canonical_json(payload))
