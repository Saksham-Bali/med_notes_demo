"""SQLAlchemy 2.0 ORM models for the R6 slice tables (schema ``ff``).

Columns and enum types mirror infra/supabase/migrations/0001_init.sql exactly. The DB is
already applied — these models bind to the live schema and never create it. PG enum types
already exist (``create_type=False``).

Append-only tables (frames, tracks, track_events, link_decisions, target_lesion_selections,
recist_assessments, reviews, signoffs, audit_log, report_versions) are only ever INSERTed by
the service layer; extraction_runs is UPDATEd only by the worker.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Uuid,
    text as sa_text,
)
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "ff"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


def _enum(name: str, *values: str) -> ENUM:
    return ENUM(*values, name=name, schema=SCHEMA, create_type=False)


member_role = _enum("member_role", "admin", "reviewer", "viewer")
run_status = _enum("run_status", "queued", "running", "succeeded", "failed", "canceled")
assertion_enum = _enum("assertion", "present", "absent", "uncertain", "not_mentioned")
link_decision_kind = _enum(
    "link_decision_kind", "confirm", "merge", "split", "mark_unresolved", "reject"
)
recist_class = _enum("recist_class", "CR", "PR", "SD", "PD", "NE")
signoff_scope = _enum("signoff_scope", "patient", "track")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=sa_text("gen_random_uuid()"))


def _now() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=sa_text("now()"))


# ---------------------------------------------------------------------------
# Identity & tenancy
# ---------------------------------------------------------------------------
class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(Text, server_default=sa_text("'ap-southeast-1'"))
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.orgs.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    role: Mapped[str] = mapped_column(member_role, server_default=sa_text("'reviewer'"))
    created_at: Mapped[dt.datetime] = _now()


# ---------------------------------------------------------------------------
# Patients / PII
# ---------------------------------------------------------------------------
class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.orgs.id"))
    subject_code: Mapped[str] = mapped_column(Text)
    cancer_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class PatientIdentifier(Base):
    __tablename__ = "patient_identifiers"
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{SCHEMA}.patients.id"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    mrn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    name_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    extra_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


# ---------------------------------------------------------------------------
# Reports (versioned)
# ---------------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.patients.id"))
    report_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    note_type: Mapped[str] = mapped_column(Text, server_default=sa_text("'RR'"))
    external_note_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    id: Mapped[uuid.UUID] = _pk()
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.reports.id"))
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version_no: Mapped[int] = mapped_column(Integer, server_default=sa_text("1"))
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(Text)
    is_addendum: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    created_at: Mapped[dt.datetime] = _now()
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


# ---------------------------------------------------------------------------
# Extraction runs + artifacts
# ---------------------------------------------------------------------------
class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.patients.id"))
    status: Mapped[str] = mapped_column(run_status, server_default=sa_text("'queued'"))
    engine_git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    reasoning_effort: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_manifest: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=sa_text("'[]'::jsonb")
    )
    cost_usd: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default=sa_text("0"))
    locked_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_total: Mapped[int] = mapped_column(Integer, server_default=sa_text("0"))
    progress_done: Mapped[int] = mapped_column(Integer, server_default=sa_text("0"))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa_text("'{}'::jsonb"))
    # Run lineage (0008). An incremental run extends parent_run_id rather than replacing it;
    # extraction_provenance records which reports were cache-served vs freshly read, so the
    # "only the new report was read" claim is checkable rather than asserted.
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    run_kind: Mapped[str] = mapped_column(Text, server_default=sa_text("'full'"))
    extraction_provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sa_text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = _now()
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Frame(Base):
    __tablename__ = "frames"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source_report_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track_key: Mapped[str] = mapped_column(Text)
    finding_type: Mapped[str] = mapped_column(Text)
    finding_surface: Mapped[str | None] = mapped_column(Text, nullable=True)
    assertion: Mapped[str] = mapped_column(assertion_enum, server_default=sa_text("'present'"))
    anatomy: Mapped[str | None] = mapped_column(Text, nullable=True)
    laterality: Mapped[str | None] = mapped_column(Text, nullable=True)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    clinical_importance: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_text: Mapped[str] = mapped_column(Text)
    evidence_span_start: Mapped[int] = mapped_column(Integer, server_default=sa_text("-1"))
    evidence_span_end: Mapped[int] = mapped_column(Integer, server_default=sa_text("-1"))
    evidence_verified: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    review_only: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    lesion_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()


class Track(Base):
    __tablename__ = "tracks"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    track_key: Mapped[str] = mapped_column(Text)
    finding_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    anatomy: Mapped[str | None] = mapped_column(Text, nullable=True)
    laterality: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    progression: Mapped[str | None] = mapped_column(Text, nullable=True)
    progression_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, server_default=sa_text("0"))
    measurement_trend: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    unresolved_link: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    false_split_candidate: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    clinical_section: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()


class TrackEvent(Base):
    __tablename__ = "track_events"
    id: Mapped[uuid.UUID] = _pk()
    track_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.tracks.id"))
    frame_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    event_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assertion: Mapped[str | None] = mapped_column(assertion_enum, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = _now()


# ---------------------------------------------------------------------------
# R1 human-confirmed linking + RECIST
# ---------------------------------------------------------------------------
class LinkDecision(Base):
    __tablename__ = "link_decisions"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    decision: Mapped[str] = mapped_column(link_decision_kind)
    primary_track_key: Mapped[str] = mapped_column(Text)
    related_track_keys: Mapped[list[Any]] = mapped_column(
        JSONB, server_default=sa_text("'[]'::jsonb")
    )
    resulting_track_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    decided_at: Mapped[dt.datetime] = _now()
    signature_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Carry-forward provenance (0008). Set when this row replays a decision a clinician
    # made on an earlier run; decided_by/decided_at keep the ORIGINAL act's attribution.
    carried_from_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    carried_from_decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class TargetLesionSelection(Base):
    __tablename__ = "target_lesion_selections"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    baseline_report_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    selections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    selected_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    selected_at: Mapped[dt.datetime] = _now()
    signature_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Carry-forward provenance (0008); see LinkDecision.
    carried_from_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    carried_from_selection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class RecistAssessment(Base):
    __tablename__ = "recist_assessments"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    target_selection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    assessment_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    sld_mm: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    baseline_sld_mm: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    nadir_sld_mm: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    pct_from_baseline: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    pct_from_nadir: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    classification: Mapped[str | None] = mapped_column(recist_class, nullable=True)
    new_lesion: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa_text("'{}'::jsonb"))
    computed_at: Mapped[dt.datetime] = _now()


# ---------------------------------------------------------------------------
# Reviews / sessions
# ---------------------------------------------------------------------------
class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    track_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    track_key: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    reviewed_value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    link_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    type_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    progression_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latest_status_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    false_merge: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    false_split: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evidence_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    clinically_significant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    correction_finding_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_anatomy: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_laterality: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_output_visible: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("true"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # 'review' = full slot-correctness review. 'acknowledgement' = the reviewer saw new
    # evidence added to a track whose identity they had already confirmed (0008).
    review_kind: Mapped[str] = mapped_column(Text, server_default=sa_text("'review'"))
    created_at: Mapped[dt.datetime] = _now()


class ReviewSession(Base):
    __tablename__ = "review_sessions"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    started_at: Mapped[dt.datetime] = _now()
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tracks_reviewed: Mapped[int] = mapped_column(Integer, server_default=sa_text("0"))
    active_seconds: Mapped[int] = mapped_column(Integer, server_default=sa_text("0"))


# ---------------------------------------------------------------------------
# Sign-off + audit
# ---------------------------------------------------------------------------
class Signoff(Base):
    __tablename__ = "signoffs"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey(f"{SCHEMA}.extraction_runs.id"))
    scope: Mapped[str] = mapped_column(signoff_scope, server_default=sa_text("'patient'"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # payload_sha256 / prev_signoff_sha256 / row_sha256 are filled by the DB trigger
    # ff.chain_signoff() on INSERT — never set them in Python.
    payload_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_signoff_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    signed_at: Mapped[dt.datetime] = _now()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()
