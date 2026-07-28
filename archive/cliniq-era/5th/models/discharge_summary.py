from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LabResult(BaseModel):
    test_name: str
    value: str
    unit: str
    reference_range: str
    collected_at: str


class ImagingFinding(BaseModel):
    study_name: str
    study_date: str
    finding: str
    impression: str


class PathResult(BaseModel):
    specimen: str
    result: str
    reported_at: str


class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str
    duration: str
    route: str


class Procedure(BaseModel):
    name: str
    performed_at: str
    outcome: str


class ChemoDetails(BaseModel):
    regimen: str
    cycles_completed: str
    last_cycle_date: str
    toxicities: list[str]


class RadiationDetails(BaseModel):
    site: str
    total_dose: str
    fractions: str
    completion_date: str


class MeasurementTrend(BaseModel):
    lesion_name: str
    study_date: str
    measurement_mm: str
    response_note: str


class FollowUp(BaseModel):
    date: str
    department: str
    purpose: str


class DischargeSummary(BaseModel):
    patient_name: str
    patient_id: str
    age: int
    gender: str
    admission_date: str
    discharge_date: str
    department: str
    attending_physician: str

    admission_diagnosis: str
    chief_complaint: str
    history_of_present_illness: str

    past_medical_history: str
    family_history: str
    social_history: str
    allergies: list[str]

    laboratory_results: list[LabResult]
    imaging_findings: list[ImagingFinding]
    pathology_results: list[PathResult]

    medications_during_stay: list[Medication]
    procedures_performed: list[Procedure]
    chemotherapy_details: ChemoDetails | None
    radiation_details: RadiationDetails | None

    tumor_response: str
    measurement_trends: list[MeasurementTrend]

    counselling_notes: str
    patient_concerns_addressed: list[str]

    condition_at_discharge: str
    functional_status: str

    medications_on_discharge: list[Medication]
    follow_up_schedule: list[FollowUp]
    dietary_instructions: str
    activity_restrictions: str
    warning_signs: list[str]

    brief_summary: str


class SummaryContext(BaseModel):
    patient_state: dict[str, Any]
    recist_data: dict[str, Any] | list[Any] | None = None
    counselling_facts: list[dict[str, Any]] = Field(default_factory=list)
