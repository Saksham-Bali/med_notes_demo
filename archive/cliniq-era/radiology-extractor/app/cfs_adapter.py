"""
CFS Adapter: converts grounded tmc finding dicts → ClinicalFact dicts.

A ClinicalFact is the canonical output format of the radiology-extractor
service (and the lingua franca of the clinical intelligence platform).
"""

from __future__ import annotations

import re
import uuid
from typing import Any


def _extract_measurement(finding: dict) -> dict | None:
    """
    Build a normalised measurement dict from a grounded finding.

    Tries the following sources in priority order:
    1. finding["measurement_normalized"] (produced by FindingExtractor)
    2. finding["measurement"]["value"] / finding["measurement"]["unit"]
    3. A numeric value extracted from finding["evidence_text"]
    """
    # Source 1: pre-normalised measurement dict from FindingExtractor
    norm = finding.get("measurement_normalized")
    if isinstance(norm, dict) and norm.get("current_value") is not None:
        value = norm.get("current_value")
        unit = norm.get("current_unit", "mm")
        mm = norm.get("current_mm")
        if value is not None:
            return {
                "value": value,
                "unit": unit,
                "normalized_mm": mm if mm is not None else _to_mm(value, unit),
            }

    # Source 2: raw measurement dict from rule extractor
    raw_meas = finding.get("measurement")
    if isinstance(raw_meas, dict):
        value = raw_meas.get("value")
        unit = raw_meas.get("unit", "mm")
        mm = raw_meas.get("normalized_mm")
        if value is not None:
            return {
                "value": float(value),
                "unit": unit,
                "normalized_mm": mm if mm is not None else _to_mm(value, unit),
            }

    # Source 3: parse from evidence_text
    evidence = str(finding.get("evidence_text") or finding.get("evidence_surface") or "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm)\b", evidence, re.IGNORECASE)
    if m:
        value = float(m.group(1))
        unit = m.group(2).lower()
        return {
            "value": value,
            "unit": unit,
            "normalized_mm": _to_mm(value, unit),
        }

    return None


def _to_mm(value: Any, unit: str) -> float:
    """Convert a measurement value + unit to millimetres."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    unit = (unit or "mm").lower()
    if unit == "cm":
        return round(v * 10.0, 2)
    if unit == "in":
        return round(v * 25.4, 2)
    return round(v, 2)


def _certainty_score(finding: dict) -> float:
    """
    Derive a numeric certainty score [0, 1] from the finding dict.

    Maps qualitative labels to canonical scores used downstream.
    """
    # Prefer explicit numeric score from LLM extractor
    score = finding.get("certainty_score") or finding.get("confidence_score")
    if score is not None:
        try:
            return max(0.0, min(1.0, float(score)))
        except (TypeError, ValueError):
            pass

    # Map qualitative certainty labels
    label = str(
        finding.get("certainty") or finding.get("certainty_label") or ""
    ).lower().strip()
    _LABEL_MAP: dict[str, float] = {
        "confirmed": 0.96,
        "definite": 0.96,
        "high": 0.90,
        "probable": 0.80,
        "likely": 0.80,
        "possible": 0.65,
        "suspected": 0.65,
        "indeterminate": 0.50,
        "equivocal": 0.50,
        "low": 0.40,
        "unknown": 0.50,
    }
    return _LABEL_MAP.get(label, 0.50)


def _certainty_label(finding: dict) -> str:
    """Derive a canonical certainty label string."""
    explicit = str(
        finding.get("certainty_label") or finding.get("certainty") or ""
    ).lower().strip()
    if explicit in ("confirmed", "definite", "definitive"):
        return "confirmed"
    if explicit in ("probable", "likely", "high"):
        return "probable"
    if explicit in ("possible", "suspected"):
        return "suspected"
    if explicit in ("indeterminate", "equivocal", "uncertain", "unknown"):
        return "indeterminate"
    # Derive from score
    score = _certainty_score(finding)
    if score >= 0.90:
        return "confirmed"
    if score >= 0.70:
        return "probable"
    if score >= 0.50:
        return "suspected"
    return "indeterminate"


def grounded_finding_to_cfs(
    finding: dict,
    patient_id: str,
    report_id: str,
    report_date: str,
    modality: str,
    hadm_id: str,
) -> dict:
    """
    Convert a single grounded finding dict to a ClinicalFact dict.

    Args:
        finding: Grounded finding dict as returned by RadiologyExtractor.extract().
        patient_id: Patient identifier.
        report_id: Source report identifier.
        report_date: ISO-8601 date string.
        modality: Imaging modality string (CT, MRI, …).
        hadm_id: Hospital admission ID (may be empty string).

    Returns:
        A ClinicalFact dict compatible with the clinical intelligence platform.
    """
    # Entity name: prefer canonical name from grounder, fall back to extraction label
    entity_name = (
        finding.get("canonical_name")
        or finding.get("entity")
        or finding.get("entity_name")
        or finding.get("finding_type")
        or "unknown"
    )

    # Evidence text: the verbatim span from the report
    evidence_text = str(
        finding.get("evidence_text")
        or finding.get("evidence_surface")
        or finding.get("negation_language")
        or ""
    )

    # Temporal change: normalise to uppercase canonical form
    temporal_raw = finding.get("temporal_change") or finding.get("change_status")
    temporal_change: str | None = None
    if temporal_raw:
        t = str(temporal_raw).upper().strip()
        if t in ("NEW", "UNCHANGED", "STABLE", "IMPROVED", "WORSENED", "RESOLVED",
                 "INCREASED", "DECREASED"):
            temporal_change = t

    return {
        "fact_id": str(uuid.uuid4()),
        "patient_id": patient_id,
        "entity_name": entity_name,
        "radlex_id": finding.get("radlex_id"),
        "snomed_id": finding.get("snomed_id"),
        "body_region": (
            finding.get("body_region")
            or finding.get("anatomical_location")
        ),
        "certainty": _certainty_score(finding),
        "certainty_label": _certainty_label(finding),
        "is_negated": bool(finding.get("is_negated", False)),
        "temporal_change": temporal_change,
        "evidence_text": evidence_text,
        "measurement": _extract_measurement(finding),
        "modality": modality,
        "source_type": "radiology",
        "source_report_id": report_id,
        "date": report_date,
        "hadm_id": hadm_id,
    }
