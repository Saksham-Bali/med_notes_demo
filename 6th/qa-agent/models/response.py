from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from models.audit_trail import AuditTrail
from models.issue import Issue


class ClinicalFact(BaseModel):
    entity: str
    entity_type: str
    certainty: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: str | None = None
    normalized_value: str | None = None
    source_section: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class DischargeSummary(BaseModel):
    patient_demographics: Any | None = None
    admission_diagnosis: Any | None = None
    chief_complaint: Any | None = None
    investigations: Any | None = None
    treatment_given: Any | None = None
    medications_on_discharge: Any | None = None
    condition_at_discharge: Any | None = None
    follow_up_schedule: Any | None = None
    brief_summary: Any | None = None
    urgent_care_instructions: Any | None = None
    lifestyle_dietary_instructions: Any | None = None
    cause_of_death: str | None = None
    death_case: bool = False

    model_config = ConfigDict(extra="allow")


class ValidateRequest(BaseModel):
    patient_id: str
    discharge_summary: DischargeSummary
    source_facts: list[ClinicalFact] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ValidationStats(BaseModel):
    total_checks_run: int
    passed: int
    failed: int
    critical_failures: int


class ValidationResult(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    issues: list[Issue]
    stats: ValidationStats
    audit_trail: AuditTrail


class ValidateResponse(BaseModel):
    agent_id: str
    result: ValidationResult
