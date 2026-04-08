"""
Schema migration helpers for fact graph payloads.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 2


def migrate_graph_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Best-effort migration to current schema version.
    """
    if not isinstance(payload, dict):
        return payload
    version = int(payload.get("schema_version", 0) or 0)
    if version <= 0:
        payload["schema_version"] = SCHEMA_VERSION
        payload.setdefault("entities", {})
        payload.setdefault("metadata", {})
        return payload

    # v1 → v2: add negation + body_region fields
    if version < 2:
        entities = payload.get("entities", {})
        if isinstance(entities, dict):
            for entity in entities.values():
                if not isinstance(entity, dict):
                    continue
                entity.setdefault("body_region", None)
                events = entity.get("events", [])
                if isinstance(events, list):
                    for event in events:
                        if isinstance(event, dict):
                            event.setdefault("is_negated", False)
                            event.setdefault("negation_language", None)
        payload["schema_version"] = 2

    if version < SCHEMA_VERSION:
        payload["schema_version"] = SCHEMA_VERSION
    return payload
