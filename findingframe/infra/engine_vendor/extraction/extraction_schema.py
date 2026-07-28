"""
Pydantic v2 models for structured extraction output.

Used to validate LLM extraction responses, eliminating silent truncation
and malformed JSON failures.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Union, Any


class MeasurementOutput(BaseModel):
    current: Optional[Any] = None
    prior: Optional[Any] = None
    trend: Optional[Any] = None

    @field_validator("current", "prior", "trend", mode="before")
    @classmethod
    def coerce_to_string(cls, v: Any) -> Optional[str]:
        """LLM sometimes returns a dict like {'value': 12, 'unit': 'mm'}.
        Coerce to a readable string representation."""
        if v is None:
            return None
        if isinstance(v, dict):
            val = v.get("value") or v.get("size") or v.get("category") or ""
            unit = v.get("unit", "")
            note = v.get("note") or v.get("trend") or ""
            parts = [str(val)]
            if unit:
                parts.append(str(unit))
            if note:
                parts.append(f"({note[:60]})")
            return " ".join(p for p in parts if p).strip() or str(v)[:80]
        return str(v) if v is not None else None


class FindingOutput(BaseModel):
    entity: str
    anatomical_location: Optional[str] = None
    finding_type: Optional[str] = None
    measurement: MeasurementOutput = Field(default_factory=MeasurementOutput)
    modality: Optional[str] = None
    temporal_qualifier: Optional[str] = None
    temporal_change: Optional[str] = (
        None  # NEW: NEW, UNCHANGED, IMPROVED, WORSENED, RESOLVED
    )
    certainty: str = "unknown"
    confidence_score: float = 0.5
    evidence_text: Optional[str] = None
    is_negated: bool = False
    negation_language: Optional[str] = None
    comparison_to_prior: Optional[str] = None
    span_start: int = -1
    span_end: int = -1


class NegativeFindingOutput(BaseModel):
    finding: Optional[str] = None
    entity: Optional[str] = None
    anatomical_location: Optional[str] = None
    finding_type: Optional[str] = None
    evidence_text: Optional[str] = None
    is_negated: bool = True
    negation_language: Optional[str] = None
    certainty: Optional[str] = None
    confidence_score: Optional[float] = None
    temporal_qualifier: Optional[str] = None
    comparison_to_prior: Optional[str] = None
    span_start: int = -1
    span_end: int = -1


class ReportMetadata(BaseModel):
    study_date: Optional[str] = None
    study_type: Optional[str] = None
    comparison_study: Optional[Any] = None  # LLM sometimes returns dict; coerce to str
    modality: Optional[str] = None

    @field_validator("comparison_study", mode="before")
    @classmethod
    def coerce_comparison_study(cls, v: Any) -> Optional[str]:
        """Accept dict or str from LLM — convert dict to a short string."""
        if v is None:
            return None
        if isinstance(v, dict):
            # e.g. {"study_date": "2182-10-06", "note": "prior knee XR"}
            return v.get("note") or v.get("study_date") or str(v)
        return str(v)


class ExtractionOutput(BaseModel):
    """Top-level schema for LLM extraction response."""

    report_metadata: ReportMetadata = Field(default_factory=ReportMetadata)
    primary_findings: list[FindingOutput] = Field(default_factory=list)
    significant_negatives: list[NegativeFindingOutput] = Field(default_factory=list)
    overall_extraction_confidence: float = 0.0
    critical_ambiguities: list[str] = Field(default_factory=list)


# Schema version for cache key differentiation
EXTRACTION_SCHEMA_VERSION = "v15_paired"
