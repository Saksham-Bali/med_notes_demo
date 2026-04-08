from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    agent: str
    status: Literal["success", "needs_review", "pending_dependency", "skipped"]
    detail: str | None = None


class DeferredJobInfo(BaseModel):
    job_id: str
    dependency: str
    job_type: str
    status: str


class WorkflowEnvelope(BaseModel):
    workflow: str
    status: str
    message: str | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    deferred_jobs: list[DeferredJobInfo] = Field(default_factory=list)


class CounsellingApproveRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    approved_fact_ids: list[str] = Field(default_factory=list)
    approved_bullet_ids: list[str] = Field(default_factory=list)


class DepartmentNoteInput(BaseModel):
    department: str = Field(min_length=2)
    text: str = Field(min_length=1)
    date: DateType
    author: str | None = None


class DepartmentMergeRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    department_notes: list[DepartmentNoteInput] = Field(min_length=1)


class DepartmentResolveRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    resolved_facts: list[dict[str, Any]] = Field(min_length=1)
    resolution_note: str | None = None


class RadiologyWorkflowRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    report_text: str = Field(min_length=1)
    modality: str | None = None
    body_region: str | None = None


class SummaryWorkflowRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    admission_date: DateType | None = None
    discharge_date: DateType | None = None
    attending_physician: str | None = None
    department: str | None = None
    approved_counselling_fact_ids: list[str] = Field(default_factory=list)
    include_recist: bool = False
    template: str = "nabh_standard"
    discharge_summary: dict[str, Any] | None = None
    source_facts: list[dict[str, Any]] = Field(default_factory=list)
    patient_name: str | None = None
    target_language: str = "en"
    generate_audio: bool = True
    generate_pdf: bool = True
    generate_fhir: bool = True


class PreviewConfirmRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    approved_facts: list[dict[str, Any]] = Field(min_length=1)


class RadiologyPreviewRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    report_text: str = Field(min_length=1)
    prior_report_text: str | None = None
    modality: str | None = None
    body_region: str | None = None
    report_date: str | None = None
    report_id: str | None = None
    hadm_id: str | None = None


class HealthAgentStatus(BaseModel):
    agent: str
    status: str
    details: dict[str, Any] | None = None
    error: str | None = None
    notes: str | None = None


class HealthResponse(BaseModel):
    service: str
    timestamp: datetime
    agents: list[HealthAgentStatus]
