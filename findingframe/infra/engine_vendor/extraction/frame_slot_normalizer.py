"""Deterministic FindingFrame slot normalization views.

These helpers create comparison/linking views of frame slots. They should not be
used to rewrite the original extracted frame payloads; the raw model output
keeps the detailed anatomy and wording for review.
"""

from __future__ import annotations

import re
from typing import Any

from extraction.finding_type_taxonomy import canonicalize_anatomy


UNKNOWN_ANATOMY = {"", "unknown", "not_stated", "not_applicable", "none", "unspecified", "unspecified_location"}

_PANCREAS_TOKENS = {"pancreas", "pancreatic", "pancreatic_head", "pancreas_head"}
_COLON_TOKENS = {"colon", "colonic", "ascending_colon", "colon_ascending", "cecum"}

_POSTSURGICAL_ANATOMY_FAMILIES = {
    "eye": {
        "eye",
        "eyes",
        "eyes_orbits",
        "orbit",
        "orbits",
        "orbits_lenses",
    },
    "pancreas": {
        "ampulla",
        "ampullary_region",
        "pancreas",
        "pancreaticoduodenal_region",
        "pancreatic_head",
    },
    "bowel": {
        "anastomosis",
        "bowel",
        "ileocolic_anastomosis",
        "ileoanal_anastomosis",
        "jejunostomy",
        "jejunojejunostomy",
        "colon",
        "colonic",
        "rectum",
        "rectal",
        "sigmoid",
        "sigmoid_colon",
    },
    "breast": {
        "breast",
        "breasts",
        "chest_wall",
        "mastectomy",
        "mastectomy_bed",
        "anterior_chest_wall",
    },
    "kidney": {
        "kidney",
        "kidneys",
        "left_kidney",
        "right_kidney",
        "renal",
        "renal_pelvis",
    },
}

_BILIARY_DEVICE_ANATOMY = {
    "bile_duct",
    "biliary_system",
    "biliary_tree",
    "common_bile_duct",
}

_DEEP_VENOUS_ANATOMY = {
    "deep_vein",
    "hepatic_vein",
    "hepatic_veins",
    "inferior_vena_cava",
    "ivc",
    "vein",
    "venous_system",
}

_INTRACRANIAL_DEVICE_ANATOMY = {
    "intracranial",
    "ventricular_catheter",
    "ventricular_system",
    "ventriculostomy",
}

# Central venous / peripheral vein anatomy used for device_or_line normalization.
# Source extractions sometimes emit the specific access site (port, jugular, PICC)
# while the gold collapses these to the broader parent vein family for scoring.
_VENOUS_DEVICE_ANATOMY = {
    "central_venous_catheter",
    "central_venous_system",
    "internal_jugular_vein",
    "external_jugular_vein",
    "superior_vena_cava",
    "inferior_vena_cava",
    "subclavian_vein",
    "femoral_vein",
    "popliteal_vein",
    "saphenous_vein",
    "basilic_vein",
    "cephalic_vein",
    "port_a_cath",
    "picc",
    "picc_line",
    "venous_system",
    "peripheral_vein",
}

# Pelvic-region sub-anatomies for post_surgical_change. The model emits the
# specific surgical bed; gold uses the parent pelvis.
_PELVIC_SURGICAL_BED = {
    "prostate",
    "prostatectomy",
    "prostate_bed",
    "rectal_bed",
    "bladder_bed",
    "uterine_bed",
    "cervical_bed",
    "vaginal_cuff",
    "prostatectomy_bed",
    "urinary_bladder_prostatectomy_bed",
}

_NEW_TERMS = {"new", "newly", "developed", "develop", "developing", "develops", "arisen", "arose"}
_INCREASED_TERMS = {
    "increased",
    "increase",
    "larger",
    "enlarged",
    "enlarging",
    "worse",
    "worsened",
    "progressed",
    "progression",
    "progressive",
    "progress",
    "worsening",
    "growth",
    "grown",
    "grow",
    "worsens",
    "enlarge",
    "enlargement",
    "enlarges",
}
_DECREASED_TERMS = {
    "decreased",
    "decrease",
    "smaller",
    "improved",
    "improving",
    "less",
    "reduced",
    "reduction",
    "regressed",
    "regression",
    "atrophy",
    "atrophic",
    "atrophied",
    "shrink",
    "shrank",
    "shrunk",
    "shrinking",
    "shrinkage",
}
_STABLE_TERMS = {"stable", "unchanged", "persistent", "similar", "still", "again", "previously", "prior", "persistence", "persists"}
_RESOLVED_TERMS = {"resolved", "resolution", "disappeared", "resolving", "resolve"}
_POSTSURGICAL_TERMS = {
    "postoperative",
    "postsurgical",
    "resection",
    "resected",
    "surgical",
    "operative",
}
_HEALED_TERMS = {"healed", "healing", "chronic"}


def normalize_slot_token(value: Any) -> str:
    """Normalize a free-text slot to a stable snake_case token."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _token_set(*values: Any) -> set[str]:
    joined = "_".join(normalize_slot_token(value) for value in values if value is not None)
    return {token for token in joined.split("_") if token}


def normalize_anatomy_for_scoring(
    *,
    finding_type: str,
    anatomy: Any,
    evidence_text: Any = "",
    finding_surface: Any = "",
) -> str:
    """Return anatomy used for metrics, preserving a broad clinical comparison view."""
    finding_type = normalize_slot_token(finding_type)
    raw = normalize_slot_token(anatomy)
    canonical = canonicalize_anatomy(raw or "unknown")
    tokens = _token_set(raw, evidence_text, finding_surface)

    # Metastasis identity is evaluated at the organ-family level. The source
    # frame and linking view retain the more specific compartment/site (for
    # example cerebellum, hepatic segment, lung lobe, or iliac bone). Keeping
    # this mapping finding-type driven also handles an omitted/unknown anatomy
    # without inventing a site beyond what the finding type itself entails.
    metastasis_organ_family = {
        "brain_metastasis": "intracranial",
        "bone_metastasis": "bone",
        "liver_metastasis": "liver",
        "lung_metastasis": "thorax",
        "lymph_node_metastasis": "lymph_node",
    }.get(finding_type)
    if metastasis_organ_family:
        return metastasis_organ_family

    # Hemorrhage organ family: intracranial subregions collapse to intracranial.
    if finding_type == "hemorrhage":
        if raw in {
            "intracranial",
            "brain",
            "cerebrum",
            "cerebral",
            "cerebellum",
            "cerebellar",
            "frontal_lobe",
            "parietal_lobe",
            "temporal_lobe",
            "occipital_lobe",
            "frontal",
            "parietal",
            "temporal",
            "occipital",
            "temporal_region",
            "frontal_region",
            "parietal_region",
            "occipital_region",
            "right_temporal_lobe",
            "left_temporal_lobe",
            "right_frontal_lobe",
            "left_frontal_lobe",
            "right_parietal_lobe",
            "left_parietal_lobe",
            "right_cerebellar",
            "left_cerebellar",
            "right_cerebellum",
            "left_cerebellum",
            "right_lateral_ventricle",
            "left_lateral_ventricle",
            "cerebellar_vermis",
            "putamen",
            "basal_ganglia",
            "brainstem",
            "pons",
            "medulla",
            "thalamus",
            "midbrain",
        } or canonical in {
            "intracranial",
            "brain",
            "cerebellum",
        }:
            return "intracranial"

    # Hydronephrosis: side-specific kidneys collapse to parent kidney.
    if finding_type == "hydronephrosis" and (
        raw in {"right_kidney", "left_kidney", "kidney", "renal_pelvis", "renal_collecting_system"}
        or canonical in {"kidney", "renal_collecting_system"}
    ):
        return "kidney"

    # Organ/subregion families accepted by the prediction-only discovery pass
    # and conservative semantic review. These are scoring views only; detailed
    # raw anatomy remains available to linking and review.
    if finding_type == "bowel_obstruction" and "bowel" in tokens:
        return "bowel"

    if finding_type == "fracture" and any(token.startswith("femur") for token in tokens):
        return "femur"

    if finding_type == "post_surgical_change" and "thoracic_spine" in raw:
        return "spine"

    if finding_type == "device_or_line":
        if raw in {"ureter", "ureters"}:
            return "ureter"
        if raw in {"hip", "left_hip", "right_hip"}:
            return "hip"

    if finding_type == "primary_tumor":
        if any(term in raw for term in ("occipital_lobe", "intracranial", "brain", "cerebellum", "temporoparietal", "pachymeninges", "meningioma", "meninges")):
            return "intracranial"
        if "ureter" in tokens:
            return "ureter"
        if "bladder" in raw or "urinary_bladder" in raw:
            return "bladder"

    if finding_type == "pneumonia_or_infection" and raw.startswith("liver_segment"):
        return "liver"

    if finding_type == "fracture" and (
        raw in {"osseous_structures", "bones", "skeleton"}
        or canonical in {"bone"}
    ):
        return "bone"

    if finding_type == "fracture" and any(
        token in raw for token in ("vertebra", "spine", "spinal")
    ):
        return "spine"

    if finding_type == "primary_tumor":
        if tokens & _PANCREAS_TOKENS or raw in _PANCREAS_TOKENS:
            return "pancreas"
        if tokens & _COLON_TOKENS or raw in _COLON_TOKENS:
            return "colon"
        if raw in _PELVIC_SURGICAL_BED or canonical in _PELVIC_SURGICAL_BED:
            return "pelvis"
        if raw in {"tumor_bed", "surgical_bed"}:
            if "pancrea" in normalize_slot_token(evidence_text):
                return "pancreas"
            if tokens & _COLON_TOKENS:
                return "colon"

    if finding_type == "ascites":
        return "peritoneum"

    if finding_type == "pneumonia_or_infection" and (
        raw in _COLON_TOKENS or tokens & _COLON_TOKENS
    ):
        return "colon"

    if finding_type == "deep_vein_thrombosis":
        if (
            raw in _DEEP_VENOUS_ANATOMY
            or canonical in _DEEP_VENOUS_ANATOMY
            or canonical == "tibia"
            or "vein" in tokens
            or "veins" in tokens
            or "venous" in tokens
            or "smv" in tokens
            or "portal" in tokens
            or "popliteal" in tokens
            or "peroneal" in tokens
            or "tibial" in tokens
            or "jugular" in tokens
            or "iliac" in tokens
            or "femoral" in tokens
            or "saphenous" in tokens
            or "calf" in tokens
            or "lower_extremity" in tokens
            or "upper_extremity" in tokens
        ):
            return "vein"

    if finding_type == "pulmonary_embolism" and raw in {
        "pulmonary_artery",
        "pulmonary_arteries",
        "pulmonary_arterial_tree",
    }:
        return "pulmonary_artery"

    if finding_type == "device_or_line":
        if raw in _BILIARY_DEVICE_ANATOMY or canonical in _BILIARY_DEVICE_ANATOMY:
            return "bile_duct"
        if raw in {"airway", "trachea", "endotracheal_tube"}:
            return "airway"
        if raw in _INTRACRANIAL_DEVICE_ANATOMY:
            return "intracranial"
        if (raw in _VENOUS_DEVICE_ANATOMY or canonical in {"vein", "heart", "right_atrium", "left_atrium"}) and (
            tokens & {"chest", "thorax", "thoracic", "jugular", "subclavian", "svc", "cavoatrial", "atrial", "atrium", "port", "picc", "catheter"}
            or "junction" in tokens
        ):
            return "thorax"
        if raw in _VENOUS_DEVICE_ANATOMY or canonical in _VENOUS_DEVICE_ANATOMY or canonical == "vein":
            return "vein"

    if finding_type == "post_surgical_change":
        for family, members in _POSTSURGICAL_ANATOMY_FAMILIES.items():
            if raw in members or canonical in members:
                return family
        if raw in _PELVIC_SURGICAL_BED or canonical in _PELVIC_SURGICAL_BED:
            return "pelvis"
        if tokens & {
            "anastomosis",
            "anastomotic",
            "ileocolic",
            "ileoanal",
            "jejunojejunostomy",
            "jejunostomy",
        }:
            return "bowel"
        if "periorbital" in raw:
            return "eye"
        if tokens & {"craniotomy", "intracranial", "ventriculostomy"} or any(
            region in raw for region in ("frontal", "temporal_lobe", "temporal_region")
        ):
            return "intracranial"

    if finding_type == "primary_tumor" and raw in {
        "ampulla",
        "ampullary_region",
        "pancreaticoduodenal_region",
    }:
        return "pancreas"

    if finding_type == "primary_tumor" and tokens & {
        "intracranial",
        "meningioma",
    }:
        return "intracranial"

    if finding_type == "hydronephrosis" and (
        canonical in {"kidney", "renal_collecting_system"}
        or raw in {"renal_collecting_systems", "kidney_collecting_systems"}
    ):
        return "kidney"

    return canonical


def normalize_anatomy_for_linking(
    *,
    finding_type: str,
    anatomy: Any,
    assertion: Any = "",
    evidence_text: Any = "",
    finding_surface: Any = "",
) -> str:
    """Return anatomy used for longitudinal linking.

    This is intentionally less aggressive than scoring normalization so that
    clinically distinct nodal and bone regions remain available for review.
    Broad absent statements are allowed to collapse because they represent a
    global negative over a body-region family.
    """
    finding_type = normalize_slot_token(finding_type)
    assertion = normalize_slot_token(assertion)
    raw = normalize_slot_token(anatomy)
    canonical = canonicalize_anatomy(raw or "unknown")

    if assertion == "absent" and finding_type in {
        "lymph_node_metastasis",
        "bone_metastasis",
    }:
        return normalize_anatomy_for_scoring(
            finding_type=finding_type,
            anatomy=anatomy,
            evidence_text=evidence_text,
            finding_surface=finding_surface,
        )

    if finding_type == "primary_tumor":
        return normalize_anatomy_for_scoring(
            finding_type=finding_type,
            anatomy=anatomy,
            evidence_text=evidence_text,
            finding_surface=finding_surface,
        )

    return canonical


def _is_negated_term(text: str, terms: set[str]) -> bool:
    if not terms:
        return False
    terms_pattern = "|".join(re.escape(term) for term in terms)
    pattern = rf"\b(no|without|free|negative|clear|absence|cleared)_(?:[a-z0-9]+_)*({terms_pattern})\b"
    return bool(re.search(pattern, text))


def normalize_temporal_change_for_scoring(
    *,
    temporal_change: Any,
    evidence_text: Any = "",
    finding_surface: Any = "",
    assertion: Any = "",
    finding_type: Any = "",
    source_report_id: Any = "",
    anatomy: Any = "",
) -> str:
    """Return the temporal value supported by frame-local source evidence.

    The scoring view intentionally does not trust an explicit model/gold slot
    when its evidence span lacks the corresponding cue.
    """
    text = normalize_slot_token(evidence_text or "")
    tokens = set(text.split("_"))
    assertion_token = normalize_slot_token(assertion)
    finding_type_token = normalize_slot_token(finding_type)
    anatomy_token = normalize_slot_token(anatomy)

    if tokens & _INCREASED_TERMS and not _is_negated_term(text, _INCREASED_TERMS):
        return "increased"
    if tokens & _DECREASED_TERMS and not _is_negated_term(text, _DECREASED_TERMS):
        return "decreased"
    is_new = (tokens & _NEW_TERMS) or ("interval_new" in text)
    if is_new and not _is_negated_term(text, _NEW_TERMS | {"interval_new", "new"}):
        return "new"
    if tokens & _RESOLVED_TERMS or any(
        phrase in text for phrase in ("no_longer", "no_longer_seen")
    ):
        return "resolved" if assertion_token == "absent" else "stable"
    if any(phrase in text for phrase in ("not_visualized", "not_seen")):
        if _not_visualized_context_matches_finding(
            finding_type=finding_type_token,
            anatomy=anatomy_token,
            text=text,
        ):
            return "resolved" if assertion_token == "absent" else "stable"
        return "not_stated"
    if tokens & _HEALED_TERMS:
        return "resolved" if finding_type_token == "fracture" else "stable"
    if tokens & _STABLE_TERMS or any(
        phrase in text
        for phrase in (
            "no_significant_change",
            "without_significant_change",
            "again_seen",
            "again_identified",
            "again_noted",
            "again_visualized",
            "again_observed",
            "again_detected",
            "previously_seen",
            "previously_noted",
            "previously_identified",
            "previously_visualized",
            "previously_described",
            "previous_ct",
            "previous_study",
            "previous_exam",
            "previous_examination",
            "prior_ct",
            "prior_mri",
            "prior_study",
            "prior_exam",
            "prior_examination",
            "better_evaluated_on_the_previous",
            "redemonstrated",
            "re_demonstrated",
            "interval_stable",
            "interval_stability",
            "stable_appearance",
        )
    ):
        return "stable"
    return "not_stated"


def _not_visualized_context_matches_finding(
    *,
    finding_type: str,
    anatomy: str,
    text: str,
) -> bool:
    """Guard against treating out-of-field nonvisualization as resolution."""
    context_terms_by_type = {
        "brain_metastasis": {"brain", "intracranial", "cerebellar", "cerebral", "head"},
        "liver_metastasis": {"liver", "hepatic", "segment"},
        "lung_metastasis": {"lung", "pulmonary", "chest", "thorax"},
        "bone_metastasis": {"bone", "osseous", "lytic", "rib", "spine", "sternum"},
        "lymph_node_metastasis": {"lymph", "node", "adenopathy", "nodal"},
        "primary_tumor": {"tumor", "mass", "neoplasm", "carcinoma", "adenocarcinoma"},
    }
    tokens = set(text.split("_"))
    context_terms = set(context_terms_by_type.get(finding_type, set()))
    if anatomy:
        context_terms.update(anatomy.split("_"))
    return bool(tokens & context_terms)
