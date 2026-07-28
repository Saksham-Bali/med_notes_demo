"""DTOs at the engine boundary. Deliberately thin — engine internals stay as dicts and
are mapped to DB rows in the service layer, so engine churn cannot leak into the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportInput(BaseModel):
    """One radiology report version fed to the engine."""
    source_report_id: str                 # engine-facing id, e.g. "report_1"
    text: str
    chart_date: datetime
    study_type: str = "RR"
    note_id: str | None = None
    report_version_id: str | None = None   # FK back to ff.report_versions
    text_sha256: str | None = None


class ExtractionManifest(BaseModel):
    """Reproducibility manifest for an extraction run (Fable R3)."""
    engine_git_sha: str = ""
    model_provider: str = ""
    model_id: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    temperature: float = 0.0
    reasoning_effort: str = ""
    manifest_hash: str = ""
    report_manifest: list[dict[str, Any]] = Field(default_factory=list)


class ReportExtraction(BaseModel):
    """Result of extracting a single report."""
    source_report_id: str
    frames: list[dict[str, Any]] = Field(default_factory=list)
    other_important_findings: list[dict[str, Any]] = Field(default_factory=list)
    overall_confidence: float = 0.0
    critical_ambiguities: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class PatientArtifact(BaseModel):
    """The FindingFrame patient artifact (frames + deterministic tracks + graph)."""
    subject_id: str
    frames: list[dict[str, Any]] = Field(default_factory=list)
    frame_events: list[dict[str, Any]] = Field(default_factory=list)
    tracks: dict[str, Any] = Field(default_factory=dict)
    track_graph: dict[str, Any] = Field(default_factory=dict)
    unresolved_link_queue: list[dict[str, Any]] = Field(default_factory=list)
    false_split_candidates: list[dict[str, Any]] = Field(default_factory=list)
    link_summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    manifest: ExtractionManifest = Field(default_factory=ExtractionManifest)
    raw: dict[str, Any] = Field(default_factory=dict)   # full artifact, for provenance
