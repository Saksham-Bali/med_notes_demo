"""Canonical entity vocabulary for TMC pipeline.

Stabilises entity names across extraction runs by mapping LLM-generated
free-form entity names to a controlled canonical vocabulary.  Without
this, the same clinical finding can appear under 5+ different names
across runs (~55% name divergence), breaking longitudinal entity tracking.

Architecture:
    Tier 1 — Mandatory canonical names (cancer-critical entities):
        LLM output is ALWAYS normalised to the canonical form.
    Tier 2 — Free-form with normalisation rules:
        Names are cleaned (lowercased, underscored, prefix-added) but
        not forced into a vocabulary entry.

Kill-switch:
    Set CANONICAL_MAP = {} to disable all normalisation.  Pipeline output
    must be identical to pre-P2 baseline when the vocabulary is empty.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Tier 1 — mandatory canonical vocabulary
# ---------------------------------------------------------------------------

CANONICAL_CANCER_VOCABULARY: dict[str, list[str]] = {
    # Primary malignancy — keyed by cancer type
    "lung_cancer": [
        "lung carcinoma", "bronchogenic carcinoma", "nsclc", "sclc",
        "lung adenocarcinoma", "pulmonary carcinoma",
    ],
    "breast_cancer": [
        "breast carcinoma", "breast malignancy", "invasive ductal carcinoma",
        "idc", "invasive lobular carcinoma", "ilc",
    ],
    "brain_tumor": [
        "glioblastoma", "gbm", "high-grade glioma", "glioma",
        "brain neoplasm", "astrocytoma", "oligodendroglioma",
    ],
    "colon_cancer": [
        "colorectal carcinoma", "colon carcinoma", "colorectal cancer",
        "rectal cancer", "colon malignancy",
    ],
    "gastric_cancer": [
        "gastric carcinoma", "stomach cancer", "gastric malignancy",
    ],

    # Metastatic disease — the most important longitudinal entities
    "finding_hepatic_metastases": [
        "liver metastases", "hepatic mets", "metastatic disease liver",
        "innumerable hepatic lesions metastatic",
        "metastatic liver disease", "hepatic metastatic disease",
    ],
    "finding_pulmonary_metastases": [
        "lung metastases", "pulmonary mets", "metastatic pulmonary nodules",
        "pulmonary metastatic disease", "metastases to lung",
    ],
    "finding_bone_metastases": [
        "osseous metastases", "bone mets", "skeletal metastases",
        "metastatic bone disease", "lytic osseous lesions",
        "blastic osseous lesions",
    ],
    "finding_brain_metastases": [
        "intracranial metastases", "brain mets", "cerebral metastases",
        "metastatic brain lesions",
    ],
    "finding_lymph_node_metastases": [
        "nodal metastases", "metastatic lymphadenopathy",
        "lymph node involvement metastatic",
    ],
    "finding_adrenal_metastases": [
        "adrenal metastases", "adrenal involvement metastatic",
    ],
    "finding_peritoneal_metastases": [
        "peritoneal carcinomatosis", "peritoneal mets",
        "peritoneal metastatic disease",
    ],

    # Key longitudinal findings — laterality in event attributes, NOT in name
    "finding_pleural_effusion": [
        "pleural fluid", "hydrothorax", "pleural effusion",
    ],
    "finding_pericardial_effusion": [
        "pericardial fluid", "pericardial effusion",
    ],
    "finding_ascites": [
        "free intraperitoneal fluid", "peritoneal fluid", "abdominal ascites",
    ],
    "finding_pulmonary_nodule": [
        "lung nodule", "pulmonary nodule",
    ],
    "finding_lymphadenopathy": [
        "lymph node enlargement", "adenopathy", "enlarged lymph nodes",
        "lymphadenopathy",
    ],
    "finding_bowel_obstruction": [
        "small bowel obstruction", "sbo", "large bowel obstruction", "lbo",
        "bowel obstruction", "intestinal obstruction",
    ],
    "finding_deep_vein_thrombosis": [
        "dvt", "venous thrombosis", "deep venous thrombosis",
    ],
    "finding_pulmonary_embolism": [
        "pe", "pulmonary thrombus", "pulmonary embolism",
    ],
    "finding_hepatomegaly": [
        "enlarged liver", "hepatosplenomegaly", "hepatomegaly",
    ],
    "finding_splenomegaly": [
        "enlarged spleen", "splenomegaly",
    ],
    "finding_pneumothorax": [
        "pneumothorax", "ptx",
    ],
    "finding_hydrocephalus": [
        "hydrocephalus", "ventriculomegaly",
    ],
    "finding_midline_shift": [
        "midline shift", "mass effect with midline shift",
    ],
}


def _build_canonical_map() -> dict[str, str]:
    """Build synonym → canonical mapping from the vocabulary."""
    mapping: dict[str, str] = {}
    for canonical, synonyms in CANONICAL_CANCER_VOCABULARY.items():
        for syn in synonyms:
            mapping[syn.lower()] = canonical
    return mapping


# Kill-switch: set to {} to disable all normalisation.
# Pipeline output must be identical to pre-P2 baseline when empty.
CANONICAL_MAP: dict[str, str] = _build_canonical_map()


def normalize_entity_name(raw_name: str) -> str:
    """Map a raw LLM-generated entity name to the canonical vocabulary.

    Returns the canonical name if a match is found, otherwise returns the
    cleaned raw name (lowercased, underscored, finding_ prefixed).
    """
    if not raw_name or not raw_name.strip():
        return "finding_unspecified"

    # Remove any leading "finding_" prefix for lookup purposes
    lookup = raw_name.lower().strip().replace("_", " ")

    # Exact synonym match (Tier 1)
    if CANONICAL_MAP:
        if lookup in CANONICAL_MAP:
            return CANONICAL_MAP[lookup]

        # Fuzzy fallback: token-overlap match
        lookup_tokens = set(lookup.split())
        best_match: tuple[int, str] | None = None
        for syn, canonical in CANONICAL_MAP.items():
            syn_tokens = set(syn.split())
            if not syn_tokens:
                continue
            overlap = len(lookup_tokens & syn_tokens)
            if overlap >= max(1, len(syn_tokens) // 2):
                if best_match is None or overlap > best_match[0]:
                    best_match = (overlap, canonical)
        if best_match is not None:
            return best_match[1]

    # Tier 2: clean and return as-is
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw_name.lower().strip()).strip("_")
    if not cleaned:
        return "finding_unspecified"

    # Ensure finding_ prefix for non-cancer entities
    if not cleaned.startswith("finding_") and not any(
        cleaned.endswith(suffix)
        for suffix in ("_cancer", "_tumor", "_carcinoma", "_malignancy")
    ):
        cleaned = f"finding_{cleaned}"

    return cleaned


# ---------------------------------------------------------------------------
# Entity types that require anatomical disambiguation in their entity ID.
# Used by P3 cross-anatomy collapse fix.
# ---------------------------------------------------------------------------

ANATOMY_DISAMBIGUATED_ENTITIES: frozenset[str] = frozenset({
    "finding_acute_fracture",
    "finding_fracture",
    "finding_dislocation",
    "finding_degenerative_changes",
    "finding_osteophytes",
    "finding_joint_effusion",
    "finding_soft_tissue_swelling",
    "finding_stress_fracture",
    "finding_periosteal_reaction",
    "finding_bone_marrow_edema",
    "finding_ligament_injury",
    "finding_tendon_abnormality",
})
