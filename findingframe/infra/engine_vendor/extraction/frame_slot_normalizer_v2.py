"""Generalized FindingFrame slot normalizer (v2).

This module extends the existing frame_slot_normalizer.py with three
generalized mappings that were identified as the dominant source of the
20-patient extension drop.
"""

from __future__ import annotations

from typing import Any

from extraction.frame_slot_normalizer import normalize_slot_token


SIDELESS_FINDING_TYPES = frozenset(
    {
        "ascites",
        "pleural_effusion",
        "pneumothorax",
        "pneumonia_or_infection",
        "pericardial_effusion",
        "cardiomegaly",
        "device_or_line",
        "post_surgical_change",
        "fracture",
        "hemorrhage",
        "bowel_obstruction",
        "other_important_finding",
        "brain_metastasis",  # side captured in anatomy/track
    }
)

SIDELESS_ANATOMIES = frozenset(
    {
        "peritoneum", "peritoneal_cavity", "abdomen", "abdominal_cavity",
        "lung", "lungs", "thorax", "chest", "pleural_space", "pleura",
        "pericardium", "pericardial_space", "heart", "mediastinum",
        "lymph_node", "lymph_nodes", "bone", "skeleton", "bones", "spine",
        "liver", "spleen", "pancreas", "kidney", "kidneys", "renal",
        "bladder", "bowel", "intestine",
    }
)

NON_INFORMATIVE_LATERALITIES = frozenset(
    {"not_applicable", "bilateral", "unknown", "midline"}
)


def normalize_laterality_generalized(
    laterality: Any,
    *,
    finding_type: str = "",
    anatomy: str = "",
) -> str:
    """Generalized laterality normalization for scoring.

    For finding types that are intrinsically sideless (ascites, pleural
    effusion, etc.) OR anatomies that are intrinsically sideless (peritoneum,
    lung, bone, etc.), the four non-informative laterality labels
    (not_applicable, bilateral, unknown, midline) collapse to
    ``not_applicable``. Lateralized labels (left, right) are preserved.
    """
    raw = normalize_slot_token(laterality or "")
    if not raw:
        raw = "unknown"
    try:
        from evaluation.frame_metrics import LATERALITY_ALIASES
        raw = LATERALITY_ALIASES.get(raw, raw)
    except ImportError:
        pass

    ft = normalize_slot_token(finding_type)
    an = normalize_slot_token(anatomy)
    if ft in SIDELESS_FINDING_TYPES and raw in NON_INFORMATIVE_LATERALITIES:
        return "not_applicable"
    if an in SIDELESS_ANATOMIES and raw in NON_INFORMATIVE_LATERALITIES:
        return "not_applicable"
    return raw


ANATOMY_SYNONYM_CLASSES = [
    # Intracranial subregions - the most important mapping (rescues brain cases)
    ["intracranial", "brain", "cerebrum", "cerebral", "cerebellum",
     "cerebellar", "frontal_lobe", "parietal_lobe", "temporal_lobe",
     "occipital_lobe", "frontal", "parietal", "occipital",
     "frontal_region", "temporal_region", "occipital_region",
     "parietal_region", "cerebellar_hemisphere", "cerebellar_vermis",
     "putamen", "basal_ganglia", "brainstem", "pons", "medulla",
     "right_frontal_region", "left_frontal_region", "right_parietal",
     "left_parietal", "right_lateral_ventricle", "left_lateral_ventricle",
     "thalamus", "midbrain", "occipital_region", "parieto_occipital",
     "right_cerebellar", "left_cerebellar", "cerebellar_peduncle"],
]

SPINE_SUBREGIONS = frozenset(
    {
        "cervical_spine", "thoracic_spine", "lumbar_spine", "sacral_spine",
        "cervical", "thoracic", "lumbar", "sacral", "spinal_cord", "spinal",
    }
)


def _build_anatomy_synonym_map():
    result = {}
    for syn_class in ANATOMY_SYNONYM_CLASSES:
        canonical = syn_class[0]
        for member in syn_class:
            result[normalize_slot_token(member)] = canonical
    return result


ANATOMY_SYNONYM_MAP = _build_anatomy_synonym_map()


def normalize_anatomy_generalized(anatomy: Any) -> str:
    """Generalized anatomy normalization for scoring.

    - Tokenizes the input
    - Applies synonym class collapse (peritoneum == peritoneal_cavity, etc.)
    - Collapses spine subregions to ``spine``
    - Returns the input unchanged if no mapping applies
    """
    raw = normalize_slot_token(anatomy or "")
    if not raw:
        return "unknown"
    if raw in ANATOMY_SYNONYM_MAP:
        return ANATOMY_SYNONYM_MAP[raw]
    if raw in SPINE_SUBREGIONS:
        return "spine"
    for prefix in ("cervical", "thoracic", "lumbar", "sacral"):
        if raw == prefix or raw.startswith(prefix + "_"):
            return "spine"
    return raw


def normalize_measurement_generalized(value: Any) -> str:
    """Generalized measurement normalization for scoring.

    Handles dicts with raw/text/value/unit, bare strings, and numerics.
    """
    if value in (None, "", {}):
        return ""
    if isinstance(value, dict):
        raw = value.get("raw") or value.get("text") or value.get("raw_text")
        if raw:
            return normalize_slot_token(str(raw))
        normalized = value.get("normalized_mm")
        if normalized is not None:
            try:
                return f"{float(normalized):.3f}_mm"
            except (TypeError, ValueError):
                pass
        v = value.get("value")
        unit = value.get("unit") or ""
        if v is not None:
            try:
                v = float(v)
                if unit:
                    return normalize_slot_token(f"{v} {unit}")
                return normalize_slot_token(str(v))
            except (TypeError, ValueError):
                pass
        values = value.get("values")
        if values is not None:
            return normalize_slot_token(f"{values} {unit}".strip())
        return ""
    if isinstance(value, (int, float)):
        return normalize_slot_token(str(value))
    return normalize_slot_token(str(value))


def normalize_frame_slots_v2(
    frame: dict,
    *,
    normalize_anatomy: bool = True,
    normalize_laterality: bool = True,
    normalize_measurement: bool = True,
):
    """Return a copy of ``frame`` with the generalized normalizer applied."""
    result = dict(frame)
    finding_type = result.get("finding_type", "")
    if normalize_anatomy and "anatomy" in result:
        result["anatomy"] = normalize_anatomy_generalized(result["anatomy"])
    if normalize_laterality and "laterality" in result:
        result["laterality"] = normalize_laterality_generalized(
            result["laterality"],
            finding_type=finding_type,
            anatomy=result.get("anatomy", ""),
        )
    if normalize_measurement and "measurement" in result:
        result["measurement"] = normalize_measurement_generalized(result["measurement"])
    return result
