"""Pydantic v2 request/response DTOs for the API. Response models use from_attributes so
ORM rows serialize directly."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / me ---
class OrgRef(BaseModel):
    id: str
    name: str
    role: str


class UserOut(BaseModel):
    id: str
    email: str | None = None
    full_name: str | None = None


class MeResponse(BaseModel):
    user: UserOut
    orgs: list[OrgRef]


class HealthResponse(BaseModel):
    status: str
    engine_sha: str
    db: str


# --- patients ---
class IdentifiersIn(BaseModel):
    mrn: str | None = None
    name: str | None = None
    dob: str | None = None
    model_config = ConfigDict(extra="allow")  # any other identifiers -> extra_enc


class PatientCreate(BaseModel):
    subject_code: str = Field(min_length=1)
    cancer_type: str | None = None
    identifiers: IdentifiersIn | None = None


class PatientOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    subject_code: str
    cancer_type: str | None
    created_at: dt.datetime


class RunBrief(ORMModel):
    id: uuid.UUID
    status: str
    manifest_hash: str | None
    progress_done: int
    progress_total: int
    created_at: dt.datetime


class PatientDetailOut(BaseModel):
    patient: PatientOut
    report_count: int
    has_identifiers: bool
    latest_run: RunBrief | None = None


class PatientListItemOut(PatientOut):
    report_count: int = 0
    latest_run: RunBrief | None = None


# --- reports ---
class ReportItemIn(BaseModel):
    report_date: dt.datetime
    note_type: str = "RR"
    external_note_id: str | None = None
    text: str = Field(min_length=1)


ReportsCreateIn = ReportItemIn | list[ReportItemIn]


class ReportVersionOut(ORMModel):
    id: uuid.UUID
    version_no: int
    text_sha256: str
    is_addendum: bool
    created_at: dt.datetime


class ReportOut(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    report_date: dt.datetime
    note_type: str
    external_note_id: str | None


class ReportWithVersionOut(BaseModel):
    report: ReportOut
    current_version: ReportVersionOut | None = None


class ReportCreatedOut(BaseModel):
    report: ReportOut
    version: ReportVersionOut


# --- runs ---
class RunOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    patient_id: uuid.UUID
    status: str
    manifest_hash: str | None
    engine_git_sha: str | None
    model_provider: str | None
    model_id: str | None
    prompt_version: str | None
    schema_version: str | None
    progress_done: int
    progress_total: int
    attempts: int
    error: str | None
    report_manifest: list[dict[str, Any]]
    created_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None


# --- reviews ---
class ReviewCreate(BaseModel):
    track_key: str
    reviewed_value: dict[str, Any] = Field(default_factory=dict)
    link_correct: bool | None = None
    type_correct: bool | None = None
    progression_correct: bool | None = None
    latest_status_correct: bool | None = None
    false_merge: bool | None = None
    false_split: bool | None = None
    evidence_valid: bool | None = None
    clinically_significant: bool | None = None
    correction_finding_type: str | None = None
    correction_anatomy: str | None = None
    correction_laterality: str | None = None
    comment: str | None = None


class ReviewOut(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    track_key: str
    reviewer_id: uuid.UUID
    link_correct: bool | None
    type_correct: bool | None
    progression_correct: bool | None
    latest_status_correct: bool | None
    evidence_valid: bool | None
    clinically_significant: bool | None
    comment: str | None
    model_output_visible: bool
    created_at: dt.datetime


# --- linking ---
class LinkDecisionCreate(BaseModel):
    decision: Literal["confirm", "merge", "split", "mark_unresolved", "reject"]
    primary_track_key: str
    related_track_keys: list[str] = Field(default_factory=list)
    resulting_track_key: str | None = None
    rationale: str | None = None


class LinkDecisionOut(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    decision: str
    primary_track_key: str
    related_track_keys: list[Any]
    resulting_track_key: str | None
    rationale: str | None
    decided_by: uuid.UUID
    decided_at: dt.datetime
    signature_sha256: str | None


# --- recist ---
class TargetLesionIn(BaseModel):
    confirmed_track_key: str
    organ: str
    baseline_mm: float


class TargetSelectionCreate(BaseModel):
    baseline_report_version_id: uuid.UUID | None = None
    selections: list[TargetLesionIn]


class TargetSelectionOut(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    baseline_report_version_id: uuid.UUID | None
    selections: list[dict[str, Any]]
    selected_by: uuid.UUID
    selected_at: dt.datetime
    signature_sha256: str | None


# --- signoff ---
class SignoffCreate(BaseModel):
    run_id: uuid.UUID | None = None
    scope: Literal["patient", "track"] = "patient"


class SignoffOut(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    run_id: uuid.UUID
    scope: str
    payload_sha256: str
    prev_signoff_sha256: str | None
    signed_by: uuid.UUID
    signed_at: dt.datetime


# --- sessions ---
class SessionStart(BaseModel):
    patient_id: uuid.UUID
    run_id: uuid.UUID | None = None


class SessionEnd(BaseModel):
    active_seconds: int | None = None
    tracks_reviewed: int | None = None


class SessionOut(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    run_id: uuid.UUID | None
    reviewer_id: uuid.UUID
    started_at: dt.datetime
    ended_at: dt.datetime | None
    active_seconds: int
    tracks_reviewed: int


# --- analytics ---
class AnalyticsOverview(BaseModel):
    patients: int
    runs: int
    runs_by_status: dict[str, int]
    frames_total: int
    frames_gate_failed: int
    tracks_total: int
    reports_total: int
    gate_failed_rate: float
    avg_reports_per_patient: float


class RecistDistribution(BaseModel):
    by_assessment: dict[str, int]
    total_assessments: int
    by_run_best_overall: dict[str, int]
    runs_assessed: int


class ReviewerLeaderboardRow(BaseModel):
    reviewer_id: str
    name: str
    reviews: int
    corrections: int
    correction_rate: float
    active_seconds: int
    tracks_reviewed: int


class ReviewThroughput(BaseModel):
    reviews_total: int
    corrections: int
    correction_rate: float
    tracks_reviewed: int
    review_sessions: int
    patients_reviewed: int
    total_active_review_seconds: int
    avg_review_seconds_per_patient: float
    avg_review_seconds_per_session: float
    reviewer_leaderboard: list[ReviewerLeaderboardRow]
    source: str


class AgreementSummary(BaseModel):
    available: bool
    counts: dict[str, int] = Field(default_factory=dict)
    reason: str | None = None
    note: str | None = None
    items_annotated: int | None = None
    items_adjudicated: int | None = None


# --- IRR / inter-rater reliability (Cohen's kappa) pilot ---
class IrrTaskCreate(BaseModel):
    name: str = Field(min_length=1)
    protocol_id: str = "irr_pilot_v1"
    unit_of_agreement: Literal["slot", "frame", "track"] = "frame"
    run_id: uuid.UUID
    description: str | None = None
    sample_size: int = Field(default=15, ge=1, le=1000)


class IrrTaskOut(BaseModel):
    id: str
    name: str
    protocol_id: str
    unit_of_agreement: str
    description: str | None = None
    run_id: str | None = None
    sampling: dict[str, Any] = Field(default_factory=dict)
    item_refs: list[str] = Field(default_factory=list)
    n_items: int
    created_at: dt.datetime
    n_assignments: int | None = None
    n_groups: int | None = None
    n_annotators: int | None = None
    assignments: list[dict[str, Any]] | None = None


class IrrAssignmentCreate(BaseModel):
    annotator_id: uuid.UUID
    independence_group: str = Field(min_length=1)


class IrrRecordCreate(BaseModel):
    item_ref: str = Field(min_length=1)
    labels: dict[str, Any]


class IrrAdjudicationCreate(BaseModel):
    item_ref: str = Field(min_length=1)
    resolves_assignment_ids: list[str] = Field(default_factory=list)
    consensus: dict[str, Any]
    emit_gold: bool = False


# --- settings ---
class SettingsOut(BaseModel):
    llm_provider: str
    llm_model: str
    available_models: list[str]
    reasoning_effort: str
    temperature: float
    engine_git_sha: str
    region: str
    env: str
    read_only: bool
    prompt_version: str | None = None
    schema_version: str | None = None


# --- audit ---
class AuditOut(ORMModel):
    id: int
    action: str
    entity_type: str | None
    entity_id: str | None
    actor_id: uuid.UUID | None
    request_id: str | None
    prev_hash: str | None
    row_hash: str | None
    created_at: dt.datetime
