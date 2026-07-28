"""
Single-report FindingFrame extractor.

This is a new path for the FindingFrame pivot. It does not use paired report
context and does not alter the legacy free-form finding extractor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .finding_frame_schema import (
    FINDING_FRAME_SCHEMA_VERSION,
    FindingFrame,
    FindingFrameExtractionOutput,
    check_evidence_quality,
    evidence_mentions_any,
    normalize_evidence_text,
    normalize_slot_text,
)
from .finding_type_taxonomy import (
    canonicalize_cxr_finding_type,
    canonicalize_finding_type,
    cxr_taxonomy_prompt_block,
    echo_taxonomy_prompt_block,
    evidence_terms_for_type,
    is_taxonomy_finding_type,
    taxonomy_prompt_block,
)
from .report_cleaner import clean_report
from utils.llm import create_default_llm_client, parse_json_from_text


logger = logging.getLogger("extraction.finding_frame_extractor")

_PROMPT_VERSION = "finding_frame_prompt_v7_generalization_contract"

_GENERIC_FRACTURE_NEGATIVE_ANATOMIES = {
    "unknown",
    "bone",
    "bones",
    "skull",
    "spine",
    "cervical_spine",
    "thoracic_spine",
    "lumbar_spine",
    "rib",
    "ribs",
    "osseous_structures",
}

_SPECIFIC_FRACTURE_ANATOMY_TERMS = (
    "hip",
    "ankle",
    "foot",
    "hand",
    "wrist",
    "knee",
    "shoulder",
    "femur",
    "tibia",
    "fibula",
    "malleolus",
    "patella",
    "radius",
    "ulna",
    "humerus",
)

_NO_FRACTURE_SENTENCE_RE = re.compile(
    r"[^.\n]*(?:"
    r"\bno acute fracture or dislocation\b|"
    r"\bno signs? (?:for|of) acute fractures? or dislocations?\b|"
    r"\bno additional fracture or dislocation\b"
    r")[^.\n]*\.",
    re.IGNORECASE,
)
_NO_PRIMARY_SENTENCE_RE = re.compile(
    r"[^.\n]*\bno separate primary lesion identified\b[^.\n]*\.",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"[^.\n;]+(?:[.;]|\n|$)", re.MULTILINE)
_NEGATED_RE = re.compile(r"\b(no|without|negative for|free of)\b", re.IGNORECASE)
_ONCOLOGY_CONTEXT_RE = re.compile(
    r"\b(cancer|carcinoma|malignan\w*|metasta\w*|neoplas\w*|tumou?r|oncolog\w*)\b",
    re.IGNORECASE,
)
_PRIMARY_TUMOR_SENTENCE_RE = re.compile(
    r"\b("
    r"(?:mass|nodule|lesion)s?.{0,60}(?:neoplastic|malignan\w*|carcinoma|tumou?r|cancer)|"
    r"(?:neoplastic|malignan\w*|carcinoma|tumou?r|cancer).{0,60}(?:mass|nodule|lesion)s?|"
    r"primary\s+(?:adenocarcinoma|carcinoma|tumou?r)|"
    r"hepatocellular carcinoma|"
    r"squamous cell carcinoma"
    r")\b",
    re.IGNORECASE,
)
_TUMOR_THROMBUS_SENTENCE_RE = re.compile(
    r"\b(?:"
    r"tumou?r (?:thrombus|embol(?:us|i))|"
    r"(?:thrombus|embol(?:us|i)).{0,100}(?:ivc|inferior vena cava|hepatic vein|portal vein|renal vein|right atrium|pulmonary arter)|"
    r"(?:ivc|inferior vena cava|hepatic vein|portal vein|renal vein|right atrium|pulmonary arter).{0,100}(?:thrombus|embol(?:us|i))"
    r")\b",
    re.IGNORECASE,
)
_PULMONARY_VASCULAR_RE = re.compile(
    r"\b(?:pulmonary arter(?:y|ies)|pulmonary system|pulmonary embol|segmental|subsegmental)\b",
    re.IGNORECASE,
)
_DEEP_VENOUS_RE = re.compile(
    r"\b(?:ivc|inferior vena cava|hepatic vein|portal vein|renal vein|deep vein|femoral vein|iliac vein|right atrium)\b",
    re.IGNORECASE,
)
_NEGATED_THROMBUS_RE = re.compile(
    r"\b(?:no|without)\s+(?:visible\s+|evidence of\s+)?(?:tumou?r\s+)?thrombus\b",
    re.IGNORECASE,
)
_LYMPH_NODE_POSITIVE_RE = re.compile(
    r"\b("
    r"(?:metastatic|malignant|pathologic(?:ally)?|bulky|extensive|suspicious|ipsilateral|mediastinal|retroperitoneal|mesenteric|inguinal|axillary|supraclavicular)"
    r".{0,80}(?:lymphadenopathy|adenopathy|lymph nodes?|nodal disease)|"
    r"(?:lymphadenopathy|adenopathy|lymph nodes?|nodal disease).{0,80}"
    r"(?:metastatic|malignant|pathologic(?:ally)?|bulky|extensive|suspicious)"
    r")\b",
    re.IGNORECASE,
)
_LYMPH_NODE_NEGATIVE_RE = re.compile(
    r"\b(?:no|without|negative for)\b.{0,80}"
    r"\b(?:lymphadenopathy|adenopathy|pathologically enlarged lymph nodes?|lymph nodes? enlargement|nodal metastases|nodal disease)\b",
    re.IGNORECASE,
)
_LIVER_METASTASIS_RE = re.compile(
    r"\b(?:liver|hepatic).{0,80}(?:lesions?|masses?|hypodensit\w*).{0,80}"
    r"(?:metasta\w*|suspicious|concerning|suggestive\s+of\s+metasta\w*|compatible\s+with\s+metasta\w*)",
    re.IGNORECASE,
)
_BONE_METASTASIS_POSITIVE_RE = re.compile(
    r"\b("
    r"(?:osseous|bone|bony|skeletal|spine|vertebr\w*|rib|sternal|calvarial|femur|femoral|pelvis|ili\w*|acetabul\w*|sacrum).{0,80}"
    r"(?:metasta\w*|lytic|lucent|sclerotic|destructive|pathologic fracture|concerning|suspicious)|"
    r"metasta\w*.{0,80}(?:osseous|bone|bony|skeletal|spine|vertebr\w*|rib|sternal|calvarial|femur|femoral|pelvis|ili\w*|acetabul\w*|sacrum)|"
    r"(?:lytic|lucent|sclerotic|destructive).{0,80}(?:lesions?|metasta\w*)|"
    r"pathologic fracture"
    r")\b",
    re.IGNORECASE,
)
_BONE_METASTASIS_NEGATIVE_RE = re.compile(
    r"\b(?:no|without|negative for)\b.{0,100}(?:"
    r"(?:osseous|bone|bony|skeletal).{0,80}(?:metasta\w*|lesions?|malignan\w*|destructive)|"
    r"(?:aggressive|concerning|suspicious)?[^.]{0,30}(?:osteo)?lytic[^.]{0,50}(?:sclerotic|lesions?)|"
    r"(?:aggressive|concerning|suspicious)?[^.]{0,30}(?:osteo)?sclerotic[^.]{0,50}(?:lytic|lesions?)"
    r")",
    re.IGNORECASE,
)
_PATHOLOGIC_FRACTURE_RE = re.compile(r"\bpathologic(?:al)? fracture\b", re.IGNORECASE)
_INFECTION_NEGATIVE_RE = re.compile(
    r"\b(?:no|without|negative for)\b.{0,80}"
    r"\b(?:consolidation|infiltrate|infiltrates|pneumonia|diverticulitis|infectious process)\b",
    re.IGNORECASE,
)
_ASCITES_NEGATIVE_RE = re.compile(
    r"\b(?:no|without|negative for)\s+(?:evidence of\s+)?ascites\b",
    re.IGNORECASE,
)
_PNEUMOTHORAX_NEGATIVE_RE = re.compile(
    r"\b(?:no|without|negative for)\s+(?:evidence of\s+)?pneumothorax\b",
    re.IGNORECASE,
)
_HYDRONEPHROSIS_NEGATIVE_RE = re.compile(
    r"\b(?:no|without|negative for)\s+(?:evidence of\s+)?hydronephrosis\b",
    re.IGNORECASE,
)
_BOWEL_OBSTRUCTION_NEGATIVE_RE = re.compile(
    r"\b(?:"
    r"(?:loops? of )?(?:small and large )?bowels?\b.{0,50}\b(?:normal caliber|unremarkable|nondilated|non-dilated)|"
    r"no\b.{0,30}\b(?:dilated|distended)\b.{0,30}\bbowel(?: loops?)?\b"
    r")",
    re.IGNORECASE,
)
_PATENT_DEEP_VEIN_RE = re.compile(
    r"\b(?:portal|splenic|hepatic|renal|iliac|femoral)\b(?:\s+and\s+(?:portal|splenic|hepatic|renal|iliac|femoral))?\s+veins?\s+(?:are|is|remain|remains)\s+patent\b",
    re.IGNORECASE,
)
_NORMAL_HEART_SIZE_RE = re.compile(
    r"\b(?:heart|cardiac silhouette)\s+(?:size\s+)?(?:is\s+)?(?:normal|within normal limits)\b",
    re.IGNORECASE,
)
_BILIARY_STENT_RE = re.compile(
    r"\b(?:biliary|common bile duct|cbd)\s+stent\b|"
    r"\bstent\b.{0,40}\b(?:biliary|common bile duct|cbd)\b",
    re.IGNORECASE,
)
_PANCREATIC_MASS_RE = re.compile(
    r"\b(?:ill[- ]defined\s+)?(?:mass|tumou?r|neoplasm)\b.{0,60}\b(?:pancreas|pancreatic)\b|"
    r"\b(?:pancreas|pancreatic)\b.{0,60}\b(?:mass|tumou?r|neoplasm)\b",
    re.IGNORECASE,
)

_FRACTURE_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("left hip", "left_hip", "left"),
    ("right hip", "right_hip", "right"),
    ("left ankle", "left_ankle", "left"),
    ("right ankle", "right_ankle", "right"),
    ("left foot", "left_foot", "left"),
    ("right foot", "right_foot", "right"),
    ("left hand", "left_hand", "left"),
    ("right hand", "right_hand", "right"),
    ("left wrist", "left_wrist", "left"),
    ("right wrist", "right_wrist", "right"),
    ("left knee", "left_knee", "left"),
    ("right knee", "right_knee", "right"),
    ("left shoulder", "left_shoulder", "left"),
    ("right shoulder", "right_shoulder", "right"),
    ("cervical spine", "cervical_spine", "not_applicable"),
    ("thoracic spine", "thoracic_spine", "not_applicable"),
    ("lumbar spine", "lumbar_spine", "not_applicable"),
    ("pelvis", "pelvis", "not_applicable"),
)


@dataclass
class FindingFrameExtractionResult:
    """Validated frame extraction result."""

    report_metadata: dict[str, Any]
    frames: list[FindingFrame]
    other_important_findings: list[FindingFrame]
    overall_confidence: float
    critical_ambiguities: list[str]
    raw_response: str
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_metadata": self.report_metadata,
            "frames": [frame.model_dump() for frame in self.frames],
            "other_important_findings": [
                frame.model_dump() for frame in self.other_important_findings
            ],
            "overall_confidence": self.overall_confidence,
            "critical_ambiguities": list(self.critical_ambiguities),
            "raw_response": self.raw_response,
            "diagnostics": dict(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FindingFrameExtractionResult":
        return cls(
            report_metadata=dict(data.get("report_metadata") or {}),
            frames=[FindingFrame.model_validate(item) for item in data.get("frames", [])],
            other_important_findings=[
                FindingFrame.model_validate(item)
                for item in data.get("other_important_findings", [])
            ],
            overall_confidence=float(data.get("overall_confidence") or 0.0),
            critical_ambiguities=list(data.get("critical_ambiguities") or []),
            raw_response=str(data.get("raw_response") or ""),
            diagnostics=dict(data.get("diagnostics") or {}),
        )


class FindingFrameExtractionCache:
    """Disk cache keyed by source report text and frame schema version."""

    CACHE_VERSION = f"{FINDING_FRAME_SCHEMA_VERSION}:{_PROMPT_VERSION}"

    def __init__(
        self,
        cache_path: str = "./outputs/cache/finding_frame_extraction_cache.json",
        namespace: str = "",
    ):
        self._path = Path(cache_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._namespace = namespace
        self._data: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def _load(self) -> None:
        if self._data is not None:
            return
        if not self._path.exists():
            self._data = {}
            return
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = loaded if isinstance(loaded, dict) else {}
        except Exception:
            self._data = {}

    def _persist(self) -> None:
        assert self._data is not None
        self._path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _key(
        self, report_text: str, chart_date: str, study_type: str, source_report_id: str
    ) -> str:
        text_hash = hashlib.sha256(report_text.encode("utf-8")).hexdigest()[:16]
        return (
            f"{self.CACHE_VERSION}:{self._namespace}:"
            f"{text_hash}:{chart_date}:{study_type}:{source_report_id}"
        )

    def get(
        self, report_text: str, chart_date: str, study_type: str, source_report_id: str
    ) -> FindingFrameExtractionResult | None:
        with self._lock:
            self._load()
            assert self._data is not None
            entry = self._data.get(
                self._key(report_text, chart_date, study_type, source_report_id)
            )
        if entry is None:
            return None
        try:
            return FindingFrameExtractionResult.from_dict(entry)
        except Exception:
            return None

    def set(
        self,
        report_text: str,
        chart_date: str,
        study_type: str,
        source_report_id: str,
        result: FindingFrameExtractionResult,
    ) -> None:
        with self._lock:
            self._load()
            assert self._data is not None
            self._data[self._key(report_text, chart_date, study_type, source_report_id)] = (
                result.to_dict()
            )
            self._persist()


def _source_report_id(chart_date: str, study_type: str, source_report_id: str | None) -> str:
    if source_report_id:
        return str(source_report_id)
    return f"{chart_date}:{study_type}"


def _extract_list(data: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _coerce_frame_dict(
    item: Any,
    source_report_id: str,
    review_only: bool,
    ambiguities: list[str],
) -> dict[str, Any] | None:
    if isinstance(item, str) and review_only:
        text = item.strip()
        if not text:
            return None
        item = {
            "finding_type": "other_important_finding",
            "finding_surface": text,
            "assertion": "present",
            "evidence_text": text,
            "anatomy": "unknown",
            "laterality": "unknown",
            "uncertainty": "indeterminate",
            "temporal_change": "not_stated",
            "measurement": None,
            "clinical_importance": "review_only",
            "review_only": True,
        }

    if not isinstance(item, dict):
        ambiguities.append("non_object_frame_skipped")
        return None

    frame = dict(item)
    aliases = {
        "entity": "finding_surface",
        "entity_name": "finding_surface",
        "finding": "finding_surface",
        "surface": "finding_surface",
        "text": "finding_surface",
        "evidence": "evidence_text",
        "anatomical_location": "anatomy",
        "site": "anatomy",
        "location": "anatomy",
        "certainty": "uncertainty",
        "change": "temporal_change",
        "temporal_qualifier": "temporal_change",
    }
    for old_key, new_key in aliases.items():
        if old_key in frame and new_key not in frame:
            frame[new_key] = frame.pop(old_key)
        elif old_key in frame:
            frame.pop(old_key)

    if "is_negated" in frame:
        if "assertion" not in frame:
            frame["assertion"] = "absent" if frame["is_negated"] else "present"
        frame.pop("is_negated", None)
        ambiguities.append("coerced_legacy_is_negated_to_assertion")

    if frame.get("source_report_id") and str(frame.get("source_report_id")) != source_report_id:
        ambiguities.append(
            f"source_report_id_overridden:{frame.get('source_report_id')}->{source_report_id}"
        )
    frame["source_report_id"] = source_report_id
    frame.setdefault("anatomy", "unknown")
    frame.setdefault("laterality", "unknown")
    frame.setdefault("uncertainty", "definite")
    frame.setdefault("temporal_change", "not_stated")
    frame.setdefault("assertion", "present")
    frame.setdefault("clinical_importance", "review_only" if review_only else None)
    frame.setdefault("review_only", review_only)

    if review_only and not frame.get("finding_type"):
        frame["finding_type"] = "other_important_finding"
    if frame.get("finding_type"):
        frame["finding_type"] = canonicalize_finding_type(str(frame["finding_type"]))
    return frame


def _normalize_response_data(
    parsed: Any,
    chart_date: str,
    study_type: str,
    source_report_id: str,
) -> dict[str, Any]:
    ambiguities: list[str] = []

    if isinstance(parsed, list):
        parsed = {"frames": parsed}
    if not isinstance(parsed, dict):
        raise ValueError("Frame extraction response is not a JSON object")

    metadata = dict(parsed.get("report_metadata") or {})
    metadata["study_date"] = chart_date
    metadata["study_type"] = study_type
    metadata["source_report_id"] = source_report_id

    raw_frames = _extract_list(parsed, "frames", "finding_frames", "checklist_findings")
    raw_other = _extract_list(parsed, "other_important_findings", "catch_all_findings")

    frames = [
        coerced
        for raw in raw_frames
        if (
            coerced := _coerce_frame_dict(
                raw,
                source_report_id=source_report_id,
                review_only=False,
                ambiguities=ambiguities,
            )
        )
        is not None
    ]
    other = [
        coerced
        for raw in raw_other
        if (
            coerced := _coerce_frame_dict(
                raw,
                source_report_id=source_report_id,
                review_only=True,
                ambiguities=ambiguities,
            )
        )
        is not None
    ]

    if parsed.get("critical_ambiguities"):
        ambiguities.extend(str(item) for item in parsed.get("critical_ambiguities", []))

    return {
        "report_metadata": metadata,
        "frames": frames,
        "other_important_findings": other,
        "overall_confidence": parsed.get("overall_confidence", 0.0),
        "critical_ambiguities": ambiguities,
    }


def _has_frame_type(frames: list[FindingFrame], finding_type: str) -> bool:
    canonical = canonicalize_finding_type(finding_type)
    return any(frame.finding_type == canonical for frame in frames)


def _first_matching_sentence(report_text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(report_text or "")
    if not match:
        return None
    return normalize_evidence_text(match.group(0))


def _iter_sentences(report_text: str) -> list[str]:
    sentences: list[str] = []
    # MIMIC reports contain hard line wraps inside sentences. Rejoin whitespace
    # before sentence splitting so a leading negation remains attached.
    normalized_report = normalize_evidence_text(report_text or "")
    # Protect common comparison abbreviations so ``Vs. prominent veins`` does
    # not cut the evidence span in half at a non-terminal period.
    protected_report = re.sub(r"\b(vs)\.", r"\1<FF_DOT>", normalized_report, flags=re.IGNORECASE)
    for match in _SENTENCE_RE.finditer(protected_report):
        sentence = normalize_evidence_text(match.group(0).replace("<FF_DOT>", "."))
        if len(sentence) >= 8:
            sentences.append(sentence)
    return sentences


def _first_sentence_matching(report_text: str, pattern: re.Pattern[str]) -> str | None:
    for sentence in _iter_sentences(report_text):
        if pattern.search(sentence):
            return sentence
    return None


def _sentences_matching(report_text: str, pattern: re.Pattern[str]) -> list[str]:
    """Return each distinct source sentence matching a deterministic rule."""
    matches: list[str] = []
    seen: set[str] = set()
    for sentence in _iter_sentences(report_text):
        if pattern.search(sentence):
            key = sentence.casefold()
            if key not in seen:
                seen.add(key)
                matches.append(sentence)
    return matches


def _is_stability_negation(evidence: str) -> bool:
    return bool(
        re.search(
            r"\b(?:no|not)\s+(?:statistically\s+)?significant(?:ly)?\s+change",
            evidence,
            re.IGNORECASE,
        )
        or re.search(r"\bnot\s+significantly\s+changed", evidence, re.IGNORECASE)
    )


def _sentence_negates_finding(evidence: str) -> bool:
    """Recognize high-confidence negation while preserving stability phrases."""
    if _is_stability_negation(evidence):
        return False
    return bool(
        _NEGATED_RE.search(evidence)
        or re.search(
            r"\b(?:do|does|did)\s+not\s+(?:meet|demonstrate|show|represent|suggest)\b",
            evidence,
            re.IGNORECASE,
        )
    )


def _infer_oncology_anatomy(evidence: str, default: str = "unknown") -> tuple[str, str]:
    text = evidence.lower()
    if any(term in text for term in ("liver", "hepatic", "hepatocellular")):
        return "liver", "not_applicable"
    if any(term in text for term in ("lung", "pulmonary", "hilar", "lower lobe", "upper lobe", "middle lobe")):
        if "right" in text:
            return "lung", "right"
        if "left" in text:
            return "lung", "left"
        if "bilateral" in text or "both" in text:
            return "lung", "bilateral"
        return "lung", "unknown"
    if any(term in text for term in ("mediastinal", "hilar", "paratracheal", "subcarinal")):
        return "mediastinum", "not_applicable"
    if any(term in text for term in ("retroperitoneal", "mesenteric", "inguinal", "axillary", "supraclavicular", "lymph")):
        return "lymph_node", "not_applicable"
    if any(term in text for term in ("spine", "vertebral", "vertebra", "rib", "sternal", "osseous", "bone", "bony", "skeletal", "calvarial")):
        return "bone", "not_applicable"
    return default, "unknown"


def _infer_bone_metastasis_anatomy(evidence: str) -> tuple[str, str]:
    """Infer conservative bone site/laterality from an explicit source sentence."""
    text = evidence.lower()
    has_right = "right" in text
    has_left = "left" in text
    if "bilateral" in text or "bilaterally" in text or (has_right and has_left):
        laterality = "bilateral"
    elif has_right:
        laterality = "right"
    elif has_left:
        laterality = "left"
    else:
        laterality = "not_applicable"

    if any(term in text for term in ("femur", "femoral")):
        anatomy = "femur"
    elif any(term in text for term in ("ilium", "iliac", "acetabul", "pelvis", "sacrum")):
        anatomy = "pelvis"
    elif re.search(r"\b(?:[ctl]\d{1,2}|vertebr\w*|spine|spinous|lamina|pedicle)\b", text):
        anatomy = "spine"
    elif re.search(r"\bribs?\b", text):
        anatomy = "rib"
    else:
        anatomy = "bone"
    return anatomy, laterality


def _temporal_from_evidence(evidence: str) -> str:
    text = evidence.lower()
    if any(term in text for term in ("new", "newly", "acute", "developed")):
        return "new"
    if any(term in text for term in ("increase", "increased", "larger", "progress", "worsen")):
        return "increased"
    if any(term in text for term in ("decrease", "decreased", "smaller", "improved", "less")):
        return "decreased"
    if any(term in text for term in ("stable", "unchanged", "no significant change", "not significantly changed", "persistent", "old", "healed", "status post", "as on", "as compared")):
        return "stable"
    if "resolved" in text:
        return "resolved"
    return "not_stated"


def _infer_deep_venous_anatomy(evidence: str) -> tuple[str, str]:
    text = evidence.lower()
    if "portal" in text and "vein" in text:
        return "portal_vein", "not_applicable"
    for terms, anatomy in (
        (("hepatic vein",), "hepatic_vein"),
        (("portal vein",), "portal_vein"),
        (("renal vein",), "renal_vein"),
        (("inferior vena cava", "ivc"), "inferior_vena_cava"),
        (("femoral vein",), "femoral_vein"),
        (("iliac vein",), "iliac_vein"),
        (("right atrium",), "right_atrium"),
    ):
        if any(term in text for term in terms):
            return anatomy, "not_applicable"
    return "vein", "not_applicable"


def _infer_pulmonary_embolism_laterality(evidence: str) -> str:
    text = evidence.lower()
    has_right = "right" in text
    has_left = "left" in text
    if has_right and has_left:
        return "bilateral"
    if has_right:
        return "right"
    if has_left:
        return "left"
    if "bilateral" in text or "both" in text:
        return "bilateral"
    return "not_applicable"


def _frame_exists_with_type_and_evidence(
    frames: list[FindingFrame],
    finding_type: str,
    evidence: str,
) -> bool:
    canonical = canonicalize_finding_type(finding_type)
    evidence_norm = normalize_evidence_text(evidence).lower()
    for frame in frames:
        if frame.finding_type != canonical:
            continue
        frame_evidence = normalize_evidence_text(frame.evidence_text).lower()
        if frame_evidence and (
            frame_evidence in evidence_norm or evidence_norm in frame_evidence
        ):
            return True
    return False


def _append_rescue_frame(
    frames: list[FindingFrame],
    ambiguities: list[str],
    *,
    finding_type: str,
    finding_surface: str,
    assertion: str,
    evidence: str | None,
    anatomy: str,
    laterality: str,
    source_report_id: str,
    importance: str = "routine_positive",
    uncertainty: str = "definite",
) -> None:
    if not evidence:
        return
    if _frame_exists_with_type_and_evidence(frames, finding_type, evidence):
        return
    frames.append(
        FindingFrame.model_validate(
            {
                "finding_type": finding_type,
                "finding_surface": finding_surface,
                "assertion": assertion,
                "evidence_text": evidence,
                "anatomy": anatomy,
                "laterality": laterality,
                "uncertainty": uncertainty,
                "temporal_change": _temporal_from_evidence(evidence),
                "measurement": None,
                "clinical_importance": importance,
                "source_report_id": source_report_id,
            }
        )
    )
    ambiguities.append(f"deterministic_rescue:{finding_type}:{source_report_id}")


def rescue_explicit_bone_metastasis_frames(
    report_text: str,
    source_report_id: str,
    frames: list[FindingFrame],
    ambiguities: list[str],
) -> list[FindingFrame]:
    """Add every distinct explicit positive bone-metastasis sentence."""
    rescued = list(frames)
    for evidence in _sentences_matching(report_text, _BONE_METASTASIS_POSITIVE_RE):
        if _sentence_negates_finding(evidence):
            continue
        anatomy, laterality = _infer_bone_metastasis_anatomy(evidence)
        assertion = "uncertain" if re.search(
            r"\b(?:possible|possibly|indeterminate|differential|ddx|versus|vs\.?)\b",
            evidence,
            re.IGNORECASE,
        ) else "present"
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="bone_metastasis",
            finding_surface="osseous lesion suspicious for metastasis",
            assertion=assertion,
            evidence=evidence,
            anatomy=anatomy,
            laterality=laterality,
            source_report_id=source_report_id,
            importance="high",
        )
        if "pathologic fracture" in evidence.lower():
            _append_rescue_frame(
                rescued,
                ambiguities,
                finding_type="fracture",
                finding_surface="pathologic fracture",
                assertion="present",
                evidence=evidence,
                anatomy="bone",
                laterality="not_applicable",
                source_report_id=source_report_id,
                importance="high",
            )
    return rescued


def rescue_oncology_recall_frames(
    report_text: str,
    source_report_id: str,
    frames: list[FindingFrame],
    ambiguities: list[str],
) -> list[FindingFrame]:
    """Add high-precision oncology recall frames from explicit source sentences."""
    rescued = list(frames)
    report_has_oncology_context = bool(_ONCOLOGY_CONTEXT_RE.search(report_text or ""))

    tumor_thrombus_evidence = _first_sentence_matching(
        report_text, _TUMOR_THROMBUS_SENTENCE_RE
    )
    if tumor_thrombus_evidence and not _NEGATED_THROMBUS_RE.search(
        tumor_thrombus_evidence
    ):
        has_deep_venous = bool(_DEEP_VENOUS_RE.search(tumor_thrombus_evidence))
        has_pulmonary = bool(_PULMONARY_VASCULAR_RE.search(tumor_thrombus_evidence))
        if has_deep_venous or not has_pulmonary:
            anatomy, laterality = _infer_deep_venous_anatomy(tumor_thrombus_evidence)
            _append_rescue_frame(
                rescued,
                ambiguities,
                finding_type="deep_vein_thrombosis",
                finding_surface="venous tumor thrombus",
                assertion="present",
                evidence=tumor_thrombus_evidence,
                anatomy=anatomy,
                laterality=laterality,
                source_report_id=source_report_id,
                importance="high",
            )
        if has_pulmonary:
            _append_rescue_frame(
                rescued,
                ambiguities,
                finding_type="pulmonary_embolism",
                finding_surface="pulmonary tumor embolus",
                assertion="present",
                evidence=tumor_thrombus_evidence,
                anatomy="pulmonary_artery",
                laterality=_infer_pulmonary_embolism_laterality(
                    tumor_thrombus_evidence
                ),
                source_report_id=source_report_id,
                importance="high",
            )

    evidence = _first_sentence_matching(report_text, _PRIMARY_TUMOR_SENTENCE_RE)
    if (
        evidence
        and report_has_oncology_context
        and not _sentence_negates_finding(evidence)
        and not re.search(r"\b(?:thrombus|embol(?:us|i))\b", evidence, re.IGNORECASE)
    ):
        anatomy, laterality = _infer_oncology_anatomy(evidence, default="unknown")
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="primary_tumor",
            finding_surface="malignant or neoplastic mass/lesion",
            assertion="present",
            evidence=evidence,
            anatomy=anatomy,
            laterality=laterality,
            source_report_id=source_report_id,
            importance="high",
        )

    evidence = _first_sentence_matching(report_text, _PANCREATIC_MASS_RE)
    has_pancreatic_primary = any(
        frame.finding_type == "primary_tumor"
        and normalize_slot_text(frame.anatomy) == "pancreas"
        for frame in rescued
    )
    if (
        evidence
        and report_has_oncology_context
        and not _NEGATED_RE.search(evidence)
        and not has_pancreatic_primary
    ):
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="primary_tumor",
            finding_surface="pancreatic mass",
            assertion="present",
            evidence=evidence,
            anatomy="pancreas",
            laterality="not_applicable",
            source_report_id=source_report_id,
            importance="high",
        )

    evidence = _first_sentence_matching(report_text, _LYMPH_NODE_POSITIVE_RE)
    if evidence and not _sentence_negates_finding(evidence):
        anatomy, laterality = _infer_oncology_anatomy(evidence, default="lymph_node")
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="lymph_node_metastasis",
            finding_surface="malignant or suspicious lymphadenopathy",
            assertion="present",
            evidence=evidence,
            anatomy=anatomy,
            laterality=laterality,
            source_report_id=source_report_id,
            importance="high",
        )

    evidence = _first_sentence_matching(report_text, _LYMPH_NODE_NEGATIVE_RE)
    _append_rescue_frame(
        rescued,
        ambiguities,
        finding_type="lymph_node_metastasis",
        finding_surface="no malignant lymphadenopathy",
        assertion="absent",
        evidence=evidence,
        anatomy="lymph_node",
        laterality="not_applicable",
        source_report_id=source_report_id,
        importance="routine_negative",
    )

    evidence = _first_sentence_matching(report_text, _LIVER_METASTASIS_RE)
    if evidence:
        assertion = "uncertain" if any(term in evidence.lower() for term in ("suspicious", "concerning", "suggestive", "compatible")) else "present"
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="liver_metastasis",
            finding_surface="hepatic lesions suspicious for metastases",
            assertion=assertion,
            evidence=evidence,
            anatomy="liver",
            laterality="not_applicable",
            source_report_id=source_report_id,
            importance="high",
            uncertainty="possible" if assertion == "uncertain" else "definite",
        )

    # Production rescue remains one high-confidence summary frame per report.
    # The all-sentence variant is exposed separately for granularity audits but
    # is not enabled here because older gold contracts collapse lesion sites.
    evidence = _first_sentence_matching(report_text, _BONE_METASTASIS_POSITIVE_RE)
    if evidence and not _sentence_negates_finding(evidence):
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="bone_metastasis",
            finding_surface="osseous lesion suspicious for metastasis",
            assertion="present",
            evidence=evidence,
            anatomy="bone",
            laterality="not_applicable",
            source_report_id=source_report_id,
            importance="high",
        )

    evidence = _first_sentence_matching(report_text, _PATHOLOGIC_FRACTURE_RE)
    if evidence and not _sentence_negates_finding(evidence):
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="fracture",
            finding_surface="pathologic fracture",
            assertion="present",
            evidence=evidence,
            anatomy="bone",
            laterality="not_applicable",
            source_report_id=source_report_id,
            importance="high",
        )

    evidence = _first_sentence_matching(report_text, _BONE_METASTASIS_NEGATIVE_RE)
    if not (
        evidence
        and re.search(
            r"\bno\b.{0,60}\b(?:change|progression|extension)\b",
            evidence,
            re.IGNORECASE,
        )
    ):
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="bone_metastasis",
            finding_surface="no suspicious osseous lesion",
            assertion="absent",
            evidence=evidence,
            anatomy="bone",
            laterality="not_applicable",
            source_report_id=source_report_id,
            importance="routine_negative",
        )

    evidence = _first_sentence_matching(report_text, _INFECTION_NEGATIVE_RE)
    _append_rescue_frame(
        rescued,
        ambiguities,
        finding_type="pneumonia_or_infection",
        finding_surface="no consolidation or infectious process",
        assertion="absent",
        evidence=evidence,
        anatomy="lung" if evidence and "lung" in evidence.lower() else "unknown",
        laterality="bilateral",
        source_report_id=source_report_id,
        importance="routine_negative",
    )
    return rescued


def _infer_fracture_target(report_text: str, study_type: str) -> tuple[str, str] | None:
    normalized = f"{report_text} {study_type}".lower().replace("_", " ")
    for phrase, anatomy, laterality in _FRACTURE_TARGETS:
        if phrase in normalized:
            return anatomy, laterality
    return None


def rescue_targeted_negative_frames(
    report_text: str,
    source_report_id: str,
    frames: list[FindingFrame],
    ambiguities: list[str],
) -> list[FindingFrame]:
    """Add narrow, directly stated negative frames for recurrent omissions."""
    rescued = list(frames)

    evidence = _first_sentence_matching(report_text, _BOWEL_OBSTRUCTION_NEGATIVE_RE)
    _append_rescue_frame(
        rescued,
        ambiguities,
        finding_type="bowel_obstruction",
        finding_surface="no bowel obstruction",
        assertion="absent",
        evidence=evidence,
        anatomy="bowel",
        laterality="not_applicable",
        source_report_id=source_report_id,
        importance="routine_negative",
    )

    evidence = _first_sentence_matching(report_text, _PATENT_DEEP_VEIN_RE)
    if evidence:
        anatomy, laterality = _infer_deep_venous_anatomy(evidence)
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type="deep_vein_thrombosis",
            finding_surface="patent vein without thrombosis",
            assertion="absent",
            evidence=evidence,
            anatomy=anatomy,
            laterality=laterality,
            source_report_id=source_report_id,
            importance="routine_negative",
        )
    return rescued


def rescue_deterministic_frames(
    report_text: str,
    study_type: str,
    source_report_id: str,
    frames: list[FindingFrame],
    ambiguities: list[str],
) -> list[FindingFrame]:
    """
    Add high-precision frames for patterns the LLM repeatedly omits.

    These rescues are intentionally narrow and evidence-sentence based. They do
    not infer disease from clinical history.
    """
    rescued = list(frames)

    if not _has_frame_type(rescued, "fracture"):
        evidence = _first_matching_sentence(report_text, _NO_FRACTURE_SENTENCE_RE)
        target = _infer_fracture_target(report_text, study_type)
        if evidence and target:
            anatomy, laterality = target
            rescued.append(
                FindingFrame.model_validate(
                    {
                        "finding_type": "fracture",
                        "finding_surface": f"no acute fracture or dislocation of {anatomy.replace('_', ' ')}",
                        "assertion": "absent",
                        "evidence_text": evidence,
                        "anatomy": anatomy,
                        "laterality": laterality,
                        "uncertainty": "definite",
                        "temporal_change": "not_stated",
                        "measurement": None,
                        "clinical_importance": "routine_negative",
                        "source_report_id": source_report_id,
                    }
                )
            )
            ambiguities.append(f"deterministic_rescue:fracture:{source_report_id}")

    if not _has_frame_type(rescued, "primary_tumor"):
        evidence = _first_matching_sentence(report_text, _NO_PRIMARY_SENTENCE_RE)
        if evidence:
            rescued.append(
                FindingFrame.model_validate(
                    {
                        "finding_type": "primary_tumor",
                        "finding_surface": "no separate primary lesion identified",
                        "assertion": "absent",
                        "evidence_text": evidence,
                        "anatomy": "unknown",
                        "laterality": "unknown",
                        "uncertainty": "definite",
                        "temporal_change": "not_stated",
                        "measurement": None,
                        "clinical_importance": "routine_negative",
                        "source_report_id": source_report_id,
                    }
                )
            )
            ambiguities.append(f"deterministic_rescue:primary_tumor:{source_report_id}")

    deterministic_patterns = (
        ("ascites", _ASCITES_NEGATIVE_RE, "no ascites", "absent", "peritoneal_cavity", "not_applicable", "routine_negative"),
        ("pneumothorax", _PNEUMOTHORAX_NEGATIVE_RE, "no pneumothorax", "absent", "pleural_space", "bilateral", "routine_negative"),
        ("hydronephrosis", _HYDRONEPHROSIS_NEGATIVE_RE, "no hydronephrosis", "absent", "kidney", "bilateral", "routine_negative"),
        ("cardiomegaly", _NORMAL_HEART_SIZE_RE, "normal heart size", "absent", "heart", "not_applicable", "routine_negative"),
        ("device_or_line", _BILIARY_STENT_RE, "biliary stent", "present", "biliary_tree", "not_applicable", "routine_positive"),
    )
    for finding_type, pattern, surface, assertion, anatomy, laterality, importance in deterministic_patterns:
        _append_rescue_frame(
            rescued,
            ambiguities,
            finding_type=finding_type,
            finding_surface=surface,
            assertion=assertion,
            evidence=_first_sentence_matching(report_text, pattern),
            anatomy=anatomy,
            laterality=laterality,
            source_report_id=source_report_id,
            importance=importance,
        )

    return rescued


def _normalized_anatomy_matches(a: str, b: str) -> bool:
    return normalize_slot_text(a) == normalize_slot_text(b)


def _catch_all_duplicates_checklist(
    catch_all: FindingFrame,
    checklist_frame: FindingFrame,
) -> bool:
    if catch_all.assertion != checklist_frame.assertion:
        return False
    if not _normalized_anatomy_matches(catch_all.anatomy, checklist_frame.anatomy):
        return False
    terms = evidence_terms_for_type(checklist_frame.finding_type)
    return evidence_mentions_any(catch_all.finding_surface, terms)


def dedupe_catch_all_findings(
    checklist_frames: list[FindingFrame],
    catch_all_frames: list[FindingFrame],
) -> list[FindingFrame]:
    """
    Keep only catch-all findings that do not duplicate checklist frames.

    A catch-all duplicate is skipped when its surface text overlaps a checklist
    finding type or synonym, anatomy matches, and assertion matches.
    """
    deduped: list[FindingFrame] = []
    for catch_all in catch_all_frames:
        duplicate = any(
            _catch_all_duplicates_checklist(catch_all, frame)
            for frame in checklist_frames
        )
        if duplicate:
            continue
        deduped.append(
            catch_all.model_copy(
                update={"review_only": True, "clinical_importance": "review_only"}
            )
        )
    return deduped


def _routine_negative_review_reason(frame: FindingFrame) -> str | None:
    """Return a review-only reason for broad routine negatives."""
    if frame.review_only or frame.assertion != "absent":
        return None
    if frame.clinical_importance in {"critical", "high"}:
        return None

    finding_type = frame.finding_type
    evidence = f"{frame.finding_surface} {frame.evidence_text}"
    anatomy = normalize_slot_text(frame.anatomy)

    if finding_type in {"cardiomegaly", "hydronephrosis"}:
        return f"routine_negative_review_only:{finding_type}"

    if finding_type == "ascites" and not evidence_mentions_any(evidence, ("ascites",)):
        return "routine_negative_review_only:ascites_indirect_free_fluid"

    if finding_type == "fracture":
        has_specific_anatomy = evidence_mentions_any(
            f"{anatomy} {evidence}", _SPECIFIC_FRACTURE_ANATOMY_TERMS
        )
        if anatomy in _GENERIC_FRACTURE_NEGATIVE_ANATOMIES and not has_specific_anatomy:
            return "routine_negative_review_only:generic_fracture"

    return None


_EXPLICIT_INFECTION_EVIDENCE_RE = re.compile(
    r"\b(?:pneumoni\w*|infect\w*|abscess\w*|consolidat\w*|infiltrat\w*|"
    r"diverticulitis|cholecystitis|inflamm\w*|septic|empyema)\b",
    re.IGNORECASE,
)


def _taxonomy_evidence_rejection_reason(frame: FindingFrame) -> str | None:
    """Reject a taxonomy frame when its evidence supports only normality."""
    if (
        frame.finding_type == "pneumonia_or_infection"
        and not _EXPLICIT_INFECTION_EVIDENCE_RE.search(
            f"{frame.finding_surface} {frame.evidence_text}"
        )
    ):
        return "taxonomy_evidence_rejected:infection_concept_not_explicit"
    return None


def apply_frame_policy(
    frames: list[FindingFrame],
    ambiguities: list[str],
) -> list[FindingFrame]:
    """Apply deterministic trust-policy flags after schema/evidence checks."""
    updated: list[FindingFrame] = []
    for frame in frames:
        rejection = _taxonomy_evidence_rejection_reason(frame)
        if rejection:
            ambiguities.append(
                f"{rejection}:{frame.source_report_id}:{frame.finding_type}"
            )
            continue
        reason = _routine_negative_review_reason(frame)
        if reason:
            ambiguities.append(f"{reason}:{frame.source_report_id}:{frame.finding_type}")
            frame = frame.model_copy(
                update={"review_only": True, "clinical_importance": "review_only"}
            )
        updated.append(frame)
    return updated


def _dedupe_cxr_air_fluid_frames(
    frames: list[FindingFrame], ambiguities: list[str]
) -> list[FindingFrame]:
    """Collapse air-fluid-level over-emission for the CXR domain.

    An air-fluid level in the pleural space is a single finding (hydropneumothorax).
    Some models additionally emit a separate pneumothorax and/or pleural_effusion
    frame derived from the SAME evidence sentence + laterality, double-counting it.
    When a hydropneumothorax frame exists, drop pneumothorax / pleural_effusion frames
    that share its normalized evidence span and laterality. Frames with independent
    evidence are kept.
    """
    def _key(frame: FindingFrame) -> tuple[str, str]:
        ev = " ".join(str(frame.evidence_text or "").split()).lower()
        return (ev, str(frame.laterality))

    hydro_keys = {_key(f) for f in frames if f.finding_type == "hydropneumothorax"}
    if not hydro_keys:
        return frames
    kept: list[FindingFrame] = []
    for frame in frames:
        if frame.finding_type in ("pneumothorax", "pleural_effusion") and _key(frame) in hydro_keys:
            ambiguities.append(
                f"cxr_air_fluid_dedup_removed:{frame.finding_type}:{frame.laterality}"
            )
            continue
        kept.append(frame)
    return kept


class FindingFrameExtractor:
    """
    Extract evidence-backed FindingFrame objects from one radiology report.

    The extractor evaluates a fixed taxonomy checklist and optionally returns
    review-only catch-all findings. It never receives prior report text.
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        use_cache: bool = True,
        cache_path: str = "./outputs/cache/finding_frame_extraction_cache.json",
        domain: str = "radiology",
    ):
        self.llm_client = llm_client or create_default_llm_client()
        self.domain = domain
        model = str(getattr(self.llm_client, "model", "unknown"))
        reasoning_effort = os.getenv("OPENROUTER_REASONING_EFFORT", "medium")
        cache_namespace = (
            f"model={model}:reasoning={reasoning_effort}:domain={self.domain}"
        )
        self._cache = (
            FindingFrameExtractionCache(cache_path, namespace=cache_namespace)
            if use_cache
            else None
        )

    def extract(
        self,
        report_text: str,
        chart_date: str,
        study_type: str = "Unknown",
        source_report_id: str | None = None,
    ) -> FindingFrameExtractionResult:
        source_id = _source_report_id(chart_date, study_type, source_report_id)
        cleaned = clean_report(report_text)
        extraction_text = cleaned.extraction_text or report_text
        if cleaned.indication:
            extraction_text = f"Clinical indication: {cleaned.indication}\n\n{extraction_text}"

        if self._cache is not None:
            cached = self._cache.get(extraction_text, chart_date, study_type, source_id)
            if cached is not None:
                logger.debug("finding-frame extraction cache hit for %s", source_id)
                cached.diagnostics = {**cached.diagnostics, "cache_hit": True}
                return cached

        prompt = self._build_prompt(
            extraction_text=extraction_text,
            chart_date=chart_date,
            study_type=study_type,
            source_report_id=source_id,
        )

        parse_retry_used = False
        initial_parse_failure: str | None = None
        try:
            raw_response = self._call_llm(prompt)
            try:
                parsed = parse_json_from_text(raw_response)
            except Exception as parse_exc:
                initial_parse_failure = f"{type(parse_exc).__name__}: {parse_exc}"
                parse_retry_used = True
                retry_prompt = (
                    prompt
                    + "\n\nYour previous answer could not be parsed as one complete JSON "
                    "object. Return exactly one complete JSON object matching the requested "
                    "shape. Do not include markdown, commentary, or trailing text."
                )
                raw_response = self._call_llm(retry_prompt, max_tokens=12000)
                parsed = parse_json_from_text(raw_response)
            normalized = _normalize_response_data(
                parsed,
                chart_date=chart_date,
                study_type=study_type,
                source_report_id=source_id,
            )
            output = FindingFrameExtractionOutput.model_validate(normalized)
        except Exception as exc:
            return FindingFrameExtractionResult(
                report_metadata={
                    "study_date": chart_date,
                    "study_type": study_type,
                    "source_report_id": source_id,
                },
                frames=[],
                other_important_findings=[],
                overall_confidence=0.0,
                critical_ambiguities=[
                    f"FindingFrame extraction failed: {type(exc).__name__}: {exc}"
                ],
                raw_response=locals().get("raw_response", ""),
                diagnostics={
                    "cache_hit": False,
                    "failure_type": type(exc).__name__,
                    "prompt_version": _PROMPT_VERSION,
                    "schema_version": FINDING_FRAME_SCHEMA_VERSION,
                    "domain": self.domain,
                    "parse_retry_used": parse_retry_used,
                    "initial_parse_failure": initial_parse_failure,
                    "failure_raw_response_chars": len(locals().get("raw_response", "") or ""),
                    "failure_raw_response_snippet": (
                        (locals().get("raw_response", "") or "")[:500]
                    ),
                },
            )

        ambiguities = list(output.critical_ambiguities)
        raw_frame_count = len(output.frames)
        raw_catch_all_count = len(output.other_important_findings)
        checklist_frames = self._taxonomy_frames_only(output.frames, ambiguities)
        llm_taxonomy_frame_count = len(checklist_frames)
        # Oncology-specific deterministic rescues must not run for other domains
        # (echo, cxr) — they would inject oncology findings as false positives.
        if self.domain not in ("echo", "cxr"):
            rescue_text = cleaned.extraction_text or report_text
            checklist_frames = rescue_deterministic_frames(
                report_text=rescue_text,
                study_type=study_type,
                source_report_id=source_id,
                frames=checklist_frames,
                ambiguities=ambiguities,
            )
            checklist_frames = rescue_oncology_recall_frames(
                report_text=rescue_text,
                source_report_id=source_id,
                frames=checklist_frames,
                ambiguities=ambiguities,
            )
        taxonomy_frame_count = len(checklist_frames)
        deterministic_rescue_count = taxonomy_frame_count - llm_taxonomy_frame_count
        checklist_frames = self._attach_evidence_checks(
            checklist_frames,
            report_text=report_text,
            ambiguities=ambiguities,
            require_taxonomy_concept=True,
        )
        checklist_frames = apply_frame_policy(checklist_frames, ambiguities)
        if self.domain == "cxr":
            checklist_frames = _dedupe_cxr_air_fluid_frames(checklist_frames, ambiguities)
        other_frames = dedupe_catch_all_findings(
            checklist_frames,
            output.other_important_findings,
        )
        deduped_catch_all_count = len(other_frames)
        other_frames = self._attach_evidence_checks(
            other_frames,
            report_text=report_text,
            ambiguities=ambiguities,
            require_taxonomy_concept=False,
        )

        result = FindingFrameExtractionResult(
            report_metadata=output.report_metadata,
            frames=checklist_frames,
            other_important_findings=other_frames,
            overall_confidence=output.overall_confidence,
            critical_ambiguities=ambiguities,
            raw_response=raw_response,
            diagnostics={
                "cache_hit": False,
                "prompt_version": _PROMPT_VERSION,
                "schema_version": FINDING_FRAME_SCHEMA_VERSION,
                "domain": self.domain,
                "raw_frame_count": raw_frame_count,
                "taxonomy_frame_count": taxonomy_frame_count,
                "llm_taxonomy_frame_count": llm_taxonomy_frame_count,
                "deterministic_rescue_count": deterministic_rescue_count,
                "non_taxonomy_frame_count": raw_frame_count - llm_taxonomy_frame_count,
                "raw_catch_all_count": raw_catch_all_count,
                "deduped_catch_all_count": deduped_catch_all_count,
                "catch_all_duplicate_count": raw_catch_all_count - deduped_catch_all_count,
                "critical_ambiguity_count": len(ambiguities),
                "raw_response_chars": len(raw_response or ""),
                "parse_retry_used": parse_retry_used,
                "initial_parse_failure": initial_parse_failure,
            },
        )
        if self._cache is not None:
            self._cache.set(extraction_text, chart_date, study_type, source_id, result)
        return result

    def _taxonomy_frames_only(
        self, frames: list[FindingFrame], ambiguities: list[str]
    ) -> list[FindingFrame]:
        taxonomy_frames: list[FindingFrame] = []
        for frame in frames:
            canonical_type = (
                canonicalize_cxr_finding_type(frame.finding_type)
                if self.domain == "cxr"
                else canonicalize_finding_type(frame.finding_type)
            )
            if is_taxonomy_finding_type(canonical_type):
                taxonomy_frames.append(
                    frame.model_copy(update={"finding_type": canonical_type})
                )
                continue
            ambiguities.append(f"non_taxonomy_frame_moved_to_review:{frame.finding_type}")
        return taxonomy_frames

    def _attach_evidence_checks(
        self,
        frames: list[FindingFrame],
        report_text: str,
        ambiguities: list[str],
        require_taxonomy_concept: bool,
    ) -> list[FindingFrame]:
        checked_frames: list[FindingFrame] = []
        for frame in frames:
            concept_terms = (
                evidence_terms_for_type(frame.finding_type)
                if require_taxonomy_concept
                else ()
            )
            check = check_evidence_quality(frame, report_text, concept_terms)
            if check.source_verifiable:
                frame = frame.model_copy(
                    update={
                        "evidence_span_start": check.span_start,
                        "evidence_span_end": check.span_end,
                    }
                )
            if check.issues:
                ambiguities.append(
                    "evidence_quality:"
                    f"{frame.source_report_id}:{frame.finding_type}:"
                    f"{','.join(check.issues)}"
                )
            checked_frames.append(frame)
        return checked_frames

    def _build_prompt(
        self,
        extraction_text: str,
        chart_date: str,
        study_type: str,
        source_report_id: str,
    ) -> str:
        if self.domain == "echo":
            return self._build_echo_prompt(
                extraction_text=extraction_text,
                chart_date=chart_date,
                study_type=study_type,
                source_report_id=source_report_id,
            )
        if self.domain == "cxr":
            return self._build_cxr_prompt(
                extraction_text=extraction_text,
                chart_date=chart_date,
                study_type=study_type,
                source_report_id=source_report_id,
            )
        return self._build_radiology_prompt(
            extraction_text=extraction_text,
            chart_date=chart_date,
            study_type=study_type,
            source_report_id=source_report_id,
        )

    def _build_radiology_prompt(
        self,
        extraction_text: str,
        chart_date: str,
        study_type: str,
        source_report_id: str,
    ) -> str:
        return f"""You are extracting evidence-backed FindingFrame JSON from ONE radiology report.

No previous report text is available. Do not infer findings from prior-report,
comparison, history, or indication context unless the finding is stated in this
source report's findings/impression text.

Evaluate each taxonomy class below as a checklist. Return frames only for
classes that are explicitly mentioned as present, absent, or uncertain. Negation
must be encoded only in the assertion slot. Do not create negated entities.

High-priority extraction rules:
- Use source_report_id exactly as "{source_report_id}" in every frame.
- If an impression states combined sites such as "hepatic and pulmonary
  metastases", create separate liver_metastasis and lung_metastasis frames
  supported by the same evidence sentence.
- Oncology recall: suspicious/neoplastic/malignant masses, nodules, lesions,
  carcinoma, or tumor thrombus should be mapped to the appropriate taxonomy
  frame even when the exact taxonomy name is not repeated. Examples:
  right-lower-lobe mass or likely neoplastic lung nodule -> primary_tumor;
  hepatic lesions suspicious/concerning/suggestive of metastases ->
  liver_metastasis; lucent/lytic/pathologic osseous lesions concerning for
  metastasis -> bone_metastasis.
- Tumor-thrombus routing: venous tumor thrombus in the IVC, portal/hepatic/renal
  veins, or with contiguous right-atrial extension -> deep_vein_thrombosis;
  tumor embolus in pulmonary arteries -> pulmonary_embolism; emit both when one
  statement explicitly spans both vascular beds. Do not emit primary_tumor for
  tumor thrombus alone unless a primary/local tumor is separately stated.
  Vascular encasement or invasion without explicit intraluminal thrombus is not
  deep_vein_thrombosis.
- Nodal disease recall: adenopathy, lymphadenopathy, pathologically enlarged
  lymph nodes, nodal disease, or explicit no-lymphadenopathy statements should
  map to lymph_node_metastasis when the report context is oncologic or staging
  related. Use assertion="absent" for explicit negatives.
- Pathologic fracture recall: when a report states a pathologic fracture or a
  metastatic/lytic bone lesion with fracture, create both fracture and
  bone_metastasis frames if both facts are stated.
- Infection recall: no consolidation, no infiltrate, no pneumonia, no
  diverticulitis, and no infectious process can support absent
  pneumonia_or_infection. Generic normality such as "lungs are clear" or
  "within normal limits" alone is not sufficient evidence for this class.
- Explicit negative-surrogate recall: normal or nondilated small/large bowel
  caliber supports bowel_obstruction with assertion="absent"; no suspicious
  pulmonary nodules or masses supports lung_metastasis absent; homogeneous
  liver without focal lesions or masses supports liver_metastasis absent in an
  oncologic/staging report. Do not infer these negatives from unrelated organ
  normality.
- For targeted musculoskeletal radiographs, extract explicit "no acute fracture
  or dislocation" statements as fracture frames and set anatomy from the study
  target when stated in the report or study type.
- Broad routine negative findings may be retained but should use
  clinical_importance="routine_negative"; downstream policy may route them to
  review_only if they are not clinically salient.

Context and laterality:
- Use the examination header and study description as clinical context. When a
  finding's laterality is not explicitly repeated in the finding sentence,
  infer it from the study context (e.g., a report describing a unilateral
  right-knee exam implies right-sided findings unless stated otherwise). Do not
  guess — only infer when the study clearly targets a single side or region.
- For findings in paired/bilateral anatomic structures (lungs, pleural spaces,
  kidneys), use laterality="bilateral" rather than "not_applicable" when the
  report describes both sides or a standard bilateral exam.

Temporal change:
- When a report states the finding is "new", "acute", "newly developed", or
  describes it for the first time without reference to prior studies, use
  temporal_change="new".
- When a report describes a finding as "healing", "healed", "stable",
  "unchanged", "improving", "improved", "resolved", "status post", or
  explicitly compares to a prior study showing no significant change, use
  temporal_change="stable" (or "resolved" if fully resolved).
- When a report uses terms like "worsened", "increased in size", "progressed",
  use temporal_change="increased".
- When a report uses terms like "decreased", "smaller", "improved", use
  temporal_change="decreased".
- Use temporal_change="not_stated" only when the report provides no temporal
  signal at all (no comparison, no change word, no prior reference).

Evidence requirements:
- evidence_text must be a readable source sentence or source span copied from this report.
- evidence_text must support the finding_type and assertion.
- evidence_text must not be copied from any prior-report context.

Taxonomy:
{taxonomy_prompt_block()}

Return JSON only with this shape:
{{
  "report_metadata": {{
    "study_date": "{chart_date}",
    "study_type": "{study_type}",
    "source_report_id": "{source_report_id}"
  }},
  "frames": [
    {{
      "finding_type": "pleural_effusion",
      "finding_surface": "no pleural effusion",
      "assertion": "absent",
      "evidence_text": "There is no pleural effusion or pneumothorax.",
      "anatomy": "pleural_space",
      "laterality": "bilateral",
      "uncertainty": "definite",
      "temporal_change": "not_stated",
      "measurement": null,
      "clinical_importance": "routine_negative",
      "source_report_id": "{source_report_id}"
    }}
  ],
  "other_important_findings": [],
  "overall_confidence": 0.0,
  "critical_ambiguities": []
}}

Allowed assertion values: present, absent, uncertain, not_mentioned.
Allowed laterality values: left, right, bilateral, midline, unknown, not_applicable.
Use not_applicable for findings where laterality does not clinically apply.
Allowed uncertainty values: definite, probable, possible, indeterminate.
Allowed temporal_change values: new, increased, decreased, stable, resolved, not_stated, other.
Allowed clinical_importance values: critical, high, routine_positive, routine_negative, incidental, review_only.

REPORT TEXT:
{extraction_text}
"""

    def _build_echo_prompt(
        self,
        extraction_text: str,
        chart_date: str,
        study_type: str,
        source_report_id: str,
    ) -> str:
        return f"""You are extracting evidence-backed FindingFrame JSON from ONE echocardiogram report.

No previous report text is available. Do not infer findings from prior-report,
comparison, history, or indication context unless the finding is stated in this
source report's findings/conclusion text.

Evaluate each echo taxonomy class below as a checklist. Return frames only for
classes that are explicitly mentioned as present, absent, or uncertain. Negation
must be encoded only in the assertion slot. Do not create negated entities.

High-priority extraction rules:
- Use source_report_id exactly as "{source_report_id}" in every frame.
- Measurement values are critical in echo reports. Extract LVEF percentages,
  chamber dimensions (mm or cm), valve gradients (mmHg), and areas (cm2)
  into the measurement field using the raw text and parsed numeric values.
- For valve disease severity, use the severity field (mild, moderate, severe).
  If the report explicitly grades severity, include it.
- For qualitative wall motion assessments (hypokinesis, akinesis, dyskinesis),
  extract the specific segment or region as the anatomy slot.
- For chamber sizes with explicit dimensions, include the measurement.
- If TR velocity and RVSP are both stated, include both in measurement text.
- Normal/normal, trace/physiologic regurgitation should use assertion=absent
  for valve stenosis/regurgitation types and assertion=present for normal
  function types.
- Use anatomy to specify the precise cardiac structure (e.g., left_ventricle,
  mitral_valve, aortic_valve, ivc, pericardial_space).

Evidence requirements:
- evidence_text must be a readable source sentence or source span copied from this report.
- evidence_text must support the finding_type and assertion.
- evidence_text must not be copied from any prior-report context.

Taxonomy:
{echo_taxonomy_prompt_block()}

Return JSON only with this shape:
{{
  "report_metadata": {{
    "study_date": "{chart_date}",
    "study_type": "{study_type}",
    "source_report_id": "{source_report_id}"
  }},
  "frames": [
    {{
      "finding_type": "lv_systolic_function",
      "finding_surface": "left ventricular systolic function is normal with estimated EF 60-65%",
      "assertion": "present",
      "evidence_text": "Left ventricular systolic function is normal. Estimated ejection fraction is 60-65%.",
      "anatomy": "left_ventricle",
      "laterality": "not_applicable",
      "uncertainty": "definite",
      "temporal_change": "not_stated",
      "measurement": {{ "raw": "60-65%", "value": 62.5, "unit": "%" }},
      "severity": "not_applicable",
      "clinical_importance": "routine_positive",
      "source_report_id": "{source_report_id}"
    }}
  ],
  "other_important_findings": [],
  "overall_confidence": 0.0,
  "critical_ambiguities": []
}}

Allowed assertion values: present, absent, uncertain, not_mentioned.
Allowed laterality values: left, right, bilateral, midline, unknown, not_applicable.
Use not_applicable for cardiac structures where laterality does not apply.
Allowed uncertainty values: definite, probable, possible, indeterminate.
Allowed temporal_change values: new, increased, decreased, stable, resolved, not_stated, other.
Allowed clinical_importance values: critical, high, routine_positive, routine_negative, incidental, review_only.
Allowed severity values (for valve disease grading): mild, moderate, severe, not_applicable.

REPORT TEXT:
{extraction_text}
"""

    def _build_cxr_prompt(
        self,
        extraction_text: str,
        chart_date: str,
        study_type: str,
        source_report_id: str,
    ) -> str:
        return f"""You are extracting evidence-backed FindingFrame JSON from ONE chest radiograph (CXR) report.

Extract findings that are stated in THIS report's findings/impression text. Do not
invent findings from the indication/history alone. Chest radiographs routinely
compare to a prior study; unlike other report types, you SHOULD use that
in-report comparison language to set the temporal_change of a finding described in
this report (see Temporal change below). Negation must be encoded only in the
assertion slot. Do not create negated entities.

Evaluate each CXR taxonomy class below as a checklist. Return frames only for
classes explicitly mentioned as present, absent, or uncertain.

High-priority extraction rules:
- Use source_report_id exactly as "{source_report_id}" in every frame.
- Severity, not measurement: chest radiograph reports rarely give numeric sizes.
  Set measurement=null unless an explicit size is stated (e.g. a nodule "8 mm").
  Capture graded severity words (small/mild, moderate, large/severe) in the
  severity field instead.
- Laterality is first-class. Set laterality from the described side or lung zone
  (e.g. "right lower lobe" -> right; "left costophrenic angle" -> left). Use
  "bilateral" when both sides/lungs are described, and "not_applicable" only for
  midline/unpaired structures (mediastinum, trachea, devices) where side does not
  apply.
- Anatomy granularity: set anatomy to the specific lung zone/lobe when stated
  (e.g. "upper lung zone"/"lower lobe"/"mid lung zone"), NOT just "lung", so
  distinct lobes are tracked as separate findings. Put the SIDE in laterality, not
  in anatomy. For enlarged_cardiac_silhouette use anatomy="cardiac_silhouette".
- bone_lesion requires an explicit focal osseous lesion (lytic, sclerotic, or
  blastic). A generic "no acute osseous abnormality" / "no acute osseous findings"
  is NOT sufficient to emit bone_lesion(absent) — omit the frame in that case.
- Negative recall (important): CXR reports state many explicit negatives; emit
  them as assertion="absent" frames. Examples: "no pneumothorax" -> pneumothorax
  absent; "no pleural effusion" -> pleural_effusion absent; "no focal
  consolidation" -> consolidation absent; "no pulmonary edema" -> pulmonary_edema
  absent; "no evidence of pneumonia" -> pneumonia absent; "normal heart size" ->
  enlarged_cardiac_silhouette absent. A bare "lungs are clear"/"within normal
  limits" alone is NOT sufficient evidence for a specific class.
- Devices/tubes/lines are findings: extract endotracheal_tube, enteric_tube,
  chest_tube, central_venous_line (IJ/subclavian/PICC/port/Swan-Ganz), and
  cardiac_device (pacer/ICD/sternal wires/CABG/valve). Use anatomy for position
  when stated (e.g. tip relative to carina, SVC, stomach).
- Map to the closest taxonomy class. If a stated finding does not fit any class,
  place it in other_important_findings (do not force it into a taxonomy frame).

Temporal change (extract from in-report comparison-to-prior language):
- "new", "newly appeared", "developing", "not previously seen" -> "new".
- "increased", "worsened", "larger", "progressed", "interval increase",
  "more pronounced" -> "increased".
- "decreased", "improved", "smaller", "interval decrease", "reduced",
  "less pronounced" -> "decreased".
- "unchanged", "stable", "no significant change", "persistent" -> "stable".
- "resolved", "cleared", "no longer seen" -> "resolved".
- Use "not_stated" only when the report gives no comparison or change word for
  that finding.

Evidence requirements:
- evidence_text must be a readable source sentence or span copied from THIS report.
- evidence_text must support the finding_type and assertion.

Taxonomy:
{cxr_taxonomy_prompt_block()}

Return JSON only with this shape:
{{
  "report_metadata": {{
    "study_date": "{chart_date}",
    "study_type": "{study_type}",
    "source_report_id": "{source_report_id}"
  }},
  "frames": [
    {{
      "finding_type": "pleural_effusion",
      "finding_surface": "small left pleural effusion, increased from prior",
      "assertion": "present",
      "evidence_text": "There is a small left pleural effusion, increased compared to the prior study.",
      "anatomy": "pleura",
      "laterality": "left",
      "uncertainty": "definite",
      "temporal_change": "increased",
      "measurement": null,
      "severity": "mild",
      "clinical_importance": "routine_positive",
      "source_report_id": "{source_report_id}"
    }},
    {{
      "finding_type": "pneumothorax",
      "finding_surface": "no pneumothorax",
      "assertion": "absent",
      "evidence_text": "No pneumothorax.",
      "anatomy": "pleura",
      "laterality": "bilateral",
      "uncertainty": "definite",
      "temporal_change": "not_stated",
      "measurement": null,
      "severity": "not_applicable",
      "clinical_importance": "routine_negative",
      "source_report_id": "{source_report_id}"
    }}
  ],
  "other_important_findings": [],
  "overall_confidence": 0.0,
  "critical_ambiguities": []
}}

Allowed assertion values: present, absent, uncertain, not_mentioned.
Allowed laterality values: left, right, bilateral, midline, unknown, not_applicable.
Allowed uncertainty values: definite, probable, possible, indeterminate.
Allowed temporal_change values: new, increased, decreased, stable, resolved, not_stated, other.
Allowed clinical_importance values: critical, high, routine_positive, routine_negative, incidental, review_only.
Allowed severity values: mild, moderate, severe, not_applicable.

REPORT TEXT:
{extraction_text}
"""

    def _call_llm(self, prompt: str, max_tokens: int = 8000) -> str:
        schema = FindingFrameExtractionOutput.model_json_schema()
        try:
            return self.llm_client.chat(
                prompt,
                max_tokens=max_tokens,
                temperature=0.0,
                json_schema=schema,
            )
        except TypeError:
            return self.llm_client.chat(
                prompt,
                max_tokens=max_tokens,
                temperature=0.0,
            )
