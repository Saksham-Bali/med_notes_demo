from pydantic import BaseModel, Field
from typing import Any, Optional
import uuid


class MeasurementInput(BaseModel):
    value: float | None = None
    unit: str | None = None
    normalized_mm: float | None = None
    raw_text: str | None = None


class ClinicalFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    department: str | None = None
    date: str  # ISO 8601 date string
    source_type: str = "radiology"  # "radiology" | "soap" | "counselling" | "lab"
    source_report_id: str = ""
    hadm_id: str = ""
    entity_name: str  # canonical name e.g. "pleural_effusion"
    radlex_id: str | None = None
    snomed_id: str | None = None
    body_region: str | None = None
    measurement: MeasurementInput | None = None
    certainty: float = 0.5
    certainty_label: str = "suspected"
    is_negated: bool = False
    temporal_change: str | None = None  # "NEW" | "UNCHANGED" | "IMPROVED" | "WORSENED" | "RESOLVED"
    evidence_text: str | None = None
    modality: str = "unknown"


class IngestRequest(BaseModel):
    patient_id: str
    facts: list[ClinicalFact]


class IngestResponse(BaseModel):
    patient_id: str
    facts_ingested: int
    entities_created: int
    entities_updated: int


class PatientSummary(BaseModel):
    patient_id: str
    entity_count: int
    event_count: int
    first_event_date: str | None = None
    last_event_date: str | None = None
    body_regions: list[str] = Field(default_factory=list)


class ImportRequest(BaseModel):
    """Import a raw TMC FactGraph JSON directly."""
    patient_id: str
    fact_graph: dict[str, Any]  # Raw TMC schema (schema_version 1 or 2)
