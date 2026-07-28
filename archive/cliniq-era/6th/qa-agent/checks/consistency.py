from __future__ import annotations

from models.issue import Issue
from models.response import ClinicalFact, DischargeSummary
from utils import (
    extract_diagnoses,
    extract_medications,
    extract_patient_dates,
    fact_text,
    lexical_match,
    normalize_text,
)


DIAGNOSIS_TYPES = {"primary", "diagnosis", "admission_diagnosis", "problem"}
MEDICATION_TYPES = {"medication", "discharge_medication", "drug", "prescription"}


def _matching_fact_exists(candidate: str, facts: list[ClinicalFact]) -> bool:
    return any(lexical_match(candidate, fact_text(fact)) for fact in facts)


def check_consistency(summary: DischargeSummary, facts: list[ClinicalFact]) -> list[Issue]:
    issues: list[Issue] = []

    diagnoses = extract_diagnoses(summary)
    diagnosis_facts = [fact for fact in facts if fact.entity_type.strip().casefold() in DIAGNOSIS_TYPES]
    if diagnosis_facts:
        for diagnosis in diagnoses:
            if not _matching_fact_exists(diagnosis, diagnosis_facts):
                issues.append(
                    Issue(
                        type="INCONSISTENCY",
                        severity="critical",
                        section="admission_diagnosis",
                        message=f"Diagnosis '{diagnosis}' in summary not found in source facts.",
                    )
                )

    medications = extract_medications(summary)
    medication_facts = [fact for fact in facts if fact.entity_type.strip().casefold() in MEDICATION_TYPES]
    if medication_facts:
        for medication in medications:
            if not _matching_fact_exists(medication, medication_facts):
                issues.append(
                    Issue(
                        type="INCONSISTENCY",
                        severity="critical",
                        section="medications_on_discharge",
                        message=f"Medication '{medication}' in summary not found in source facts.",
                    )
                )

    admission_date, discharge_date = extract_patient_dates(summary)
    if admission_date and discharge_date and discharge_date < admission_date:
        issues.append(
            Issue(
                type="INCONSISTENCY",
                severity="critical",
                section="patient_demographics",
                message="Discharge date occurs before admission date.",
            )
        )

    chief_complaint = normalize_text(getattr(summary, "chief_complaint", None))
    if chief_complaint and facts and not _matching_fact_exists(chief_complaint, facts):
        issues.append(
            Issue(
                type="INCONSISTENCY",
                severity="moderate",
                section="chief_complaint",
                message="Chief complaint is not reflected in the available source facts.",
            )
        )

    return issues


def count_consistency_checks(summary: DischargeSummary, facts: list[ClinicalFact]) -> int:
    count = 0
    if facts:
        count += len(extract_diagnoses(summary))
        count += len(extract_medications(summary))
        if normalize_text(getattr(summary, "chief_complaint", None)):
            count += 1
    admission_date, discharge_date = extract_patient_dates(summary)
    if admission_date or discharge_date:
        count += 1
    return count
