from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


ConflictType = Literal["medication", "staging", "date", "status", "other"]
ConflictSeverity = Literal["critical", "moderate", "minor"]


class ConflictFactSnapshot(BaseModel):
    department: str
    author: str | None = None
    document_date: date | None = None
    value: str | None = None
    status: str | None = None
    negated: bool = False
    evidence: str | None = None
    radlex_id: str | None = None


class Conflict(BaseModel):
    entity: str
    conflict_type: ConflictType
    department_a: str
    department_b: str
    description: str
    severity: ConflictSeverity
    suggested_resolution: str | None = None
    authoritative_department: str | None = None
    requires_clinician_review: bool = True
    fact_a: ConflictFactSnapshot
    fact_b: ConflictFactSnapshot
