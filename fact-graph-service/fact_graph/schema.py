"""
Fact graph Pydantic models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Measurement(BaseModel):
    value: float | None = None
    unit: str | None = None
    normalized_mm: float | None = None
    is_qualitative: bool = False
    raw_text: str | None = None
    delta_mm: float | None = None


class Event(BaseModel):
    event_id: str
    entity_id: str
    date: str
    source_report_id: str
    hadm_id: str
    modality: str
    measurement: Measurement = Field(default_factory=Measurement)
    certainty: float = 0.0
    certainty_label: str = "unknown"
    uncertainty_language: str | None = None
    comparison_to_prior: str | None = None
    trend: Literal["increasing", "decreasing", "stable", "new", "resolved", "unknown"] = "unknown"

    # Negation handling (Phase 2)
    is_negated: bool = False
    """True if the finding was explicitly absent, ruled out, or negated in the report."""

    negation_language: str | None = None
    """Verbatim negation phrase from the report, e.g. 'no evidence of', 'without'."""

    # Provenance fields (v14)
    span_start: int = -1
    """Character offset of the start of the source sentence in the de-identified report text."""

    span_end: int = -1
    """Character offset of the end of the source sentence in the de-identified report text."""

    source: str = "llm"
    """Source of extraction: 'rule', 'llm', or 'human'."""

    confidence: float = 0.0
    """Confidence score derived from extraction certainty (0.0–1.0)."""


class CertaintyPoint(BaseModel):
    date: str
    certainty: float = 0.0
    certainty_label: str = "unknown"
    language_used: str | None = None


class EntityNode(BaseModel):
    entity_id: str
    canonical_name: str
    radlex_id: str | None = None
    radlex_preferred_label: str | None = None
    """The RadLex preferred label for the grounded concept, stored as metadata.
    This is separate from canonical_name which is always the extracted surface form."""
    snomed_id: str | None = None
    entity_type: str = "finding"
    anatomical_site: str | None = None
    first_documented: str
    last_documented: str
    events: list[Event] = Field(default_factory=list)
    certainty_trajectory: list[CertaintyPoint] = Field(default_factory=list)
    status: Literal["active", "resolved", "uncertain", "absent", "ruled_out"] = "active"

    body_region: str | None = None
    """Coarse anatomical region for deduplication scoping.
    Values: head_neck | chest | abdomen_pelvis | musculoskeletal | spine | other"""


class FactGraph(BaseModel):
    schema_version: int = 2
    subject_id: str
    entities: dict[str, EntityNode] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
