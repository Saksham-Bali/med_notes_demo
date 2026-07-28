"""
Schema and evidence checks for evidence-anchored FindingFrame extraction.

FindingFrame is the new single-report representation. Negation is represented
only through the ``assertion`` slot; there are no negated entities.

SCHEMA VERSION: 1.0.0 (frozen 2026-06-16)
    This schema version is LOCKED for the current paper submission.
    Do NOT add, remove, or rename slots without incrementing the version
    and auditing all existing gold files and pipeline artifacts.
    The annotation manual (docs/ANNOTATION_GUIDELINES.md) is bound to
    this schema version. Any schema change requires a corresponding
    annotation manual update.

    Versioning policy:
    - MAJOR: slot added/removed/renamed (gold files need regeneration)
    - MINOR: validator rules tightened or loosened
    - PATCH: documentation, typing, non-functional changes
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---- Schema Version ----
SCHEMA_VERSION = "1.0.0"
SCHEMA_VERSION_DATE = "2026-06-16"
# Legacy constant kept for backward compatibility with cache keys.
FINDING_FRAME_SCHEMA_VERSION = "finding_frame_v1"

ASSERTIONS = ("present", "absent", "uncertain", "not_mentioned")
LATERALITIES = (
    "left",
    "right",
    "bilateral",
    "midline",
    "none",
    "unknown",
    "not_applicable",
)
UNCERTAINTIES = ("definite", "probable", "possible", "indeterminate")
TEMPORAL_CHANGES = (
    "new",
    "increased",
    "decreased",
    "stable",
    "resolved",
    "not_stated",
    "other",
)
CLINICAL_IMPORTANCE = (
    "critical",
    "high",
    "routine_positive",
    "routine_negative",
    "incidental",
    "review_only",
)

Assertion = Literal["present", "absent", "uncertain", "not_mentioned"]
Laterality = Literal[
    "left", "right", "bilateral", "midline", "none", "unknown", "not_applicable"
]
Uncertainty = Literal["definite", "probable", "possible", "indeterminate"]
TemporalChange = Literal[
    "new", "increased", "decreased", "stable", "resolved", "not_stated", "other"
]
ClinicalImportance = Literal[
    "critical",
    "high",
    "routine_positive",
    "routine_negative",
    "incidental",
    "review_only",
]

Severity = Literal["mild", "moderate", "severe", "not_applicable"]

FINDING_FRAME_SCHEMA_VERSION = "finding_frame_v1"

_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_NEGATION_RE = re.compile(
    r"\b(?:no|without|absence of|negative for|not seen|not identified|"
    r"not detected|free of|resolved|resolution of|no evidence of)\b",
    re.IGNORECASE,
)
_UNCERTAIN_RE = re.compile(
    r"\b(?:possible|possibly|probable|probably|suggests?|suggestive|borderline|"
    r"cannot exclude|may represent|questionable|indeterminate)\b",
    re.IGNORECASE,
)

_NORMAL_HEART_SUPPORT_TERMS: tuple[str, ...] = (
    "heart size normal",
    "normal heart size",
    "cardiac silhouette normal",
    "normal cardiac silhouette",
    "cardiomediastinal silhouette normal",
    "normal cardiomediastinal silhouette",
    "heart size within normal limits",
    "cardiomediastinal silhouette is within normal limits",
    "cardiomediastinal silhouette within normal limits",
    "cardiac silhouette within normal limits",
)

_ABSENT_ASSERTION_SUPPORT_TERMS_BY_TYPE: dict[str, tuple[str, ...]] = {
    # oncology canonical
    "cardiomegaly": _NORMAL_HEART_SUPPORT_TERMS,
    # CXR canonical (domain="cxr") — same phrasing supports an absent frame
    "enlarged_cardiac_silhouette": _NORMAL_HEART_SUPPORT_TERMS,
}


def normalize_slot_text(value: Any) -> str:
    """Normalize a free text slot to lower snake case."""
    text = "" if value is None else str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def normalize_evidence_text(value: Any) -> str:
    """Normalize LLM evidence while preserving source wording."""
    text = "" if value is None else str(value)
    return _SPACE_RE.sub(" ", text).strip()


def _coerce_choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    normalized = normalize_slot_text(value)
    aliases = {
        "positive": "present",
        "seen": "present",
        "negative": "absent",
        "negated": "absent",
        "not_present": "absent",
        "not_seen": "absent",
        "not_identified": "absent",
        "not_mentioned": "not_mentioned",
        "not_stated": "not_stated",
        "unchanged": "stable",
        "improved": "decreased",
        "decreasing": "decreased",
        "worsened": "increased",
        "worsening": "increased",
        "routine": "routine_positive",
        "important": "high",
        "unclear": "indeterminate",
        "none": "not_applicable",
        "not_applicable": "not_applicable",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in allowed else default


class FrameMeasurement(BaseModel):
    """Optional structured measurement attached to a frame."""

    raw: str | None = None
    value: float | None = None
    values: list[float] = Field(default_factory=list)
    unit: str | None = None
    normalized_mm: float | None = None
    text: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def coerce_measurement(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return {"raw": value, "text": value}
        return value

    @field_validator("raw", "unit", "text", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("values", mode="before")
    @classmethod
    def coerce_values(cls, value: Any) -> list[float]:
        if value is None or value == "":
            return []
        if isinstance(value, (int, float)):
            return [float(value)]
        if isinstance(value, list):
            coerced: list[float] = []
            for item in value:
                try:
                    coerced.append(float(item))
                except (TypeError, ValueError):
                    continue
            return coerced
        return []


class FindingFrame(BaseModel):
    """One evidence-backed assertion about a finding in one source report."""

    finding_type: str = Field(min_length=1)
    finding_surface: str = Field(min_length=1)
    assertion: Assertion
    evidence_text: str = Field(min_length=1)
    anatomy: str = Field(min_length=1)
    laterality: Laterality = "unknown"
    uncertainty: Uncertainty = "definite"
    temporal_change: TemporalChange = "not_stated"
    measurement: FrameMeasurement | None = None
    clinical_importance: ClinicalImportance = "routine_positive"
    severity: Severity | None = None
    source_report_id: str = Field(min_length=1)
    evidence_span_start: int = -1
    evidence_span_end: int = -1
    lesion_key: str | None = None
    review_only: bool = False

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    @field_validator("finding_type", "anatomy", "lesion_key", mode="before")
    @classmethod
    def normalize_identifier_slots(cls, value: Any) -> str | None:
        if value is None:
            return None
        return normalize_slot_text(value)

    @field_validator("finding_surface", "source_report_id", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> str:
        return normalize_evidence_text(value)

    @field_validator("evidence_text", mode="before")
    @classmethod
    def strip_evidence(cls, value: Any) -> str:
        return normalize_evidence_text(value)

    @field_validator("assertion", mode="before")
    @classmethod
    def normalize_assertion(cls, value: Any) -> str:
        return _coerce_choice(value, ASSERTIONS, "uncertain")

    @field_validator("laterality", mode="before")
    @classmethod
    def normalize_laterality(cls, value: Any) -> str:
        return _coerce_choice(value, LATERALITIES, "unknown")

    @field_validator("uncertainty", mode="before")
    @classmethod
    def normalize_uncertainty(cls, value: Any) -> str:
        return _coerce_choice(value, UNCERTAINTIES, "indeterminate")

    @field_validator("temporal_change", mode="before")
    @classmethod
    def normalize_temporal_change(cls, value: Any) -> str:
        return _coerce_choice(value, TEMPORAL_CHANGES, "not_stated")

    @field_validator("clinical_importance", mode="before")
    @classmethod
    def normalize_clinical_importance(cls, value: Any) -> str:
        if value is None:
            return "routine_positive"
        return _coerce_choice(value, CLINICAL_IMPORTANCE, "routine_positive")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        normalized = normalize_slot_text(value)
        severities = ("mild", "moderate", "severe", "not_applicable")
        return normalized if normalized in severities else None

    @field_validator("measurement", mode="before")
    @classmethod
    def normalize_measurement(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return {"raw": value, "text": value}
        return value

    @model_validator(mode="after")
    def validate_span_order(self) -> "FindingFrame":
        if self.evidence_span_start < 0 or self.evidence_span_end < 0:
            return self
        if self.evidence_span_end <= self.evidence_span_start:
            raise ValueError("evidence_span_end must be greater than evidence_span_start")
        return self

    def track_key(self) -> str:
        """Deterministic longitudinal track key for this frame."""
        parts = [self.finding_type, self.anatomy, self.laterality]
        if self.lesion_key:
            parts.append(self.lesion_key)
        return "|".join(parts)


class FindingFrameExtractionOutput(BaseModel):
    """Top-level JSON contract expected from the frame extractor."""

    report_metadata: dict[str, Any] = Field(default_factory=dict)
    frames: list[FindingFrame] = Field(default_factory=list)
    other_important_findings: list[FindingFrame] = Field(default_factory=list)
    overall_confidence: float = 0.0
    critical_ambiguities: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class EvidenceQualityCheck:
    """Evidence verification result for one frame."""

    source_verifiable: bool
    readable_span: bool
    concept_supported: bool
    assertion_supported: bool
    span_start: int = -1
    span_end: int = -1
    issues: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.issues


def _has_token_boundaries(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    first = text[start] if start < len(text) else ""
    last = text[end - 1] if end > start else ""
    if before.isalnum() and first.isalnum():
        return False
    if after.isalnum() and last.isalnum():
        return False
    return True


def locate_evidence_span(report_text: str, evidence_text: str) -> tuple[int, int]:
    """Find evidence text in the source report with word-boundary protection."""
    if not report_text or not evidence_text:
        return (-1, -1)

    query = normalize_evidence_text(evidence_text)
    if not query:
        return (-1, -1)

    for match in re.finditer(re.escape(query), report_text, flags=re.IGNORECASE):
        if _has_token_boundaries(report_text, match.start(), match.end()):
            return (match.start(), match.end())

    pieces = [re.escape(piece) for piece in re.split(r"\s+", query) if piece]
    if not pieces:
        return (-1, -1)
    flexible = re.compile(r"\s+".join(pieces), flags=re.IGNORECASE)
    for match in flexible.finditer(report_text):
        if _has_token_boundaries(report_text, match.start(), match.end()):
            return (match.start(), match.end())

    # Punctuation-flexible fallback: tokenize into words + individual punctuation
    # and allow optional whitespace between every token. Handles pre-tokenized
    # corpora (e.g. RadGraph2) where the source has spaces around punctuation that
    # the model dropped ("cardiomegaly." vs source "cardiomegaly ."). Runs only
    # after the exact and space-flexible matches fail, so existing behavior is
    # unchanged.
    punct_tokens = re.findall(r"\w+|[^\w\s]", query)
    if punct_tokens:
        punct_flexible = re.compile(
            r"\s*".join(re.escape(tok) for tok in punct_tokens), flags=re.IGNORECASE
        )
        for match in punct_flexible.finditer(report_text):
            if _has_token_boundaries(report_text, match.start(), match.end()):
                return (match.start(), match.end())

    return (-1, -1)


def _tokenize_text(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


def evidence_mentions_any(evidence_text: str, terms: list[str] | tuple[str, ...]) -> bool:
    """Return true when evidence contains any finding term as a token phrase."""
    normalized = " ".join(_tokenize_text(evidence_text))
    if not normalized:
        return False
    for term in terms:
        term_tokens = _tokenize_text(term.replace("_", " "))
        if not term_tokens:
            continue
        pattern = r"\b" + r"\s+".join(re.escape(t) for t in term_tokens) + r"\b"
        if re.search(pattern, normalized):
            return True
    return False


def _readable_evidence(evidence_text: str) -> bool:
    text = normalize_evidence_text(evidence_text)
    tokens = _tokenize_text(text)
    if len(text) < 5 or len(tokens) < 2:
        return False
    if text.startswith(",") or text.startswith(";") or text.endswith(","):
        return False
    return True


def _assertion_supported(frame: FindingFrame) -> bool:
    evidence = frame.evidence_text
    if frame.assertion == "absent":
        return bool(_NEGATION_RE.search(evidence)) or evidence_mentions_any(
            evidence,
            _ABSENT_ASSERTION_SUPPORT_TERMS_BY_TYPE.get(frame.finding_type, ()),
        )
    if frame.assertion == "uncertain":
        return bool(_UNCERTAIN_RE.search(evidence))
    if frame.assertion == "present":
        return not bool(_NEGATION_RE.search(evidence))
    return True


def check_evidence_quality(
    frame: FindingFrame,
    report_text: str,
    concept_terms: list[str] | tuple[str, ...] = (),
) -> EvidenceQualityCheck:
    """
    Check whether evidence is source-verifiable, readable, and slot-supporting.

    The checks are intentionally conservative and deterministic. They do not
    claim clinical validity; they catch obvious extraction contract failures.
    """
    issues: list[str] = []
    start, end = locate_evidence_span(report_text, frame.evidence_text)
    source_verifiable = start >= 0 and end > start
    if not source_verifiable:
        issues.append("evidence_not_found_in_source_report")

    readable = _readable_evidence(frame.evidence_text)
    if not readable:
        issues.append("evidence_not_readable_span")

    concept_supported = True
    if concept_terms:
        concept_supported = evidence_mentions_any(frame.evidence_text, concept_terms)
        if not concept_supported:
            issues.append("evidence_missing_finding_concept")

    assertion_supported = _assertion_supported(frame)
    if not assertion_supported:
        issues.append(f"evidence_does_not_support_{frame.assertion}_assertion")

    return EvidenceQualityCheck(
        source_verifiable=source_verifiable,
        readable_span=readable,
        concept_supported=concept_supported,
        assertion_supported=assertion_supported,
        span_start=start,
        span_end=end,
        issues=issues,
    )
