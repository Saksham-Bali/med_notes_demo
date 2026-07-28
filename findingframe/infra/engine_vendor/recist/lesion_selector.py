"""
Target lesion selection utilities for RECIST 1.1.
"""

from __future__ import annotations

import re
from typing import Any


def _organ_from_entity(entity_id: str, entity: dict[str, Any]) -> str:
    site = str(entity.get("anatomical_site", "")).lower()
    canonical = str(entity.get("canonical_name", entity_id)).lower()
    text = f"{site} {canonical}"
    if "liver" in text or "hepatic" in text:
        return "liver"
    if "lung" in text or "lobe" in text or "pulmonary" in text:
        return "lung"
    if "adrenal" in text:
        return "adrenal"
    if "node" in text or "lymph" in text:
        return "lymph_node"
    if "brain" in text or "cerebr" in text:
        return "brain"
    if "bone" in text or "osseous" in text:
        return "bone"
    if site:
        return re.sub(r"[^a-z0-9]+", "_", site).strip("_") or "other"
    return "other"


def _max_numeric_measurement_mm(entity: dict[str, Any]) -> float:
    events = entity.get("events", [])
    if not isinstance(events, list):
        return 0.0
    max_mm = 0.0
    for event in events:
        if not isinstance(event, dict):
            continue
        measurement = event.get("measurement", {})
        if not isinstance(measurement, dict):
            continue
        if bool(measurement.get("is_qualitative", False)):
            continue
        mm = measurement.get("normalized_mm")
        if mm is None:
            continue
        try:
            mm_val = float(mm)
        except Exception:
            continue
        max_mm = max(max_mm, mm_val)
    return max_mm


def select_target_lesions(
    fact_graph: dict[str, Any],
    max_total: int = 5,
    max_per_organ: int = 2,
    measurable_threshold_mm: float = 10.0,
) -> list[str]:
    """
    Select measurable target lesions:
    - up to 5 total
    - up to 2 per organ
    """
    entities = fact_graph.get("entities", {}) if isinstance(fact_graph, dict) else {}
    if not isinstance(entities, dict):
        return []

    candidates: list[tuple[str, str, float]] = []
    for entity_id, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        size_mm = _max_numeric_measurement_mm(entity)
        if size_mm < measurable_threshold_mm:
            continue
        organ = _organ_from_entity(entity_id, entity)
        candidates.append((entity_id, organ, size_mm))

    candidates.sort(key=lambda item: item[2], reverse=True)
    selected: list[str] = []
    per_organ: dict[str, int] = {}
    for entity_id, organ, _ in candidates:
        if len(selected) >= max_total:
            break
        if per_organ.get(organ, 0) >= max_per_organ:
            continue
        selected.append(entity_id)
        per_organ[organ] = per_organ.get(organ, 0) + 1
    return selected
