from __future__ import annotations

from datetime import date as DateType
from typing import Any

from pydantic import BaseModel, Field


class ClinicalFact(BaseModel):
    entity: str
    category: str | None = None
    value: str | None = None
    status: str | None = None
    negated: bool = False
    radlex_id: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    date: DateType | None = None
    source_department: str | None = None
    source_author: str | None = None
    source_document_date: DateType | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeptExtraction(BaseModel):
    dept: str
    facts: list[ClinicalFact] = Field(default_factory=list)
    source_author: str | None = None
    source_document_date: DateType | None = None


class FactProvenance(BaseModel):
    department: str
    author: str | None = None
    document_date: DateType | None = None
    evidence: str | None = None
    status: str | None = None
    negated: bool = False
    value: str | None = None
    confidence: float | None = None


class AlignedEntity(BaseModel):
    canonical_name: str
    normalized_key: str
    radlex_id: str | None = None
    facts: list[ClinicalFact] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    has_conflict: bool = False


class UnifiedFact(BaseModel):
    entity: str
    canonical_name: str
    normalized_key: str
    radlex_id: str | None = None
    category: str | None = None
    value: str | None = None
    statuses: list[str] = Field(default_factory=list)
    negated: bool | None = None
    departments: list[str] = Field(default_factory=list)
    provenance: list[FactProvenance] = Field(default_factory=list)
    fact_count: int = 0
    latest_document_date: DateType | None = None
    has_conflict: bool = False
