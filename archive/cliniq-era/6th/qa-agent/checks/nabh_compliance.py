from __future__ import annotations

from models.issue import Issue
from models.response import DischargeSummary
from utils import extract_demographic_value, is_missing, split_into_items


def _has_patient_identifier(summary: DischargeSummary) -> bool:
    return bool(
        extract_demographic_value(summary, "patient_id", "medical_record_number", "mrn")
    )


def _medications_have_details(summary: DischargeSummary) -> bool:
    medications = split_into_items(getattr(summary, "medications_on_discharge", None))
    if not medications:
        return False
    return all(len(medication.split()) >= 3 for medication in medications)


def check_nabh_compliance(summary: DischargeSummary) -> list[Issue]:
    issues: list[Issue] = []

    if not extract_demographic_value(summary, "name", "patient_name"):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="moderate",
                section="patient_demographics",
                message="NABH discharge summary template expects the patient name in demographics.",
            )
        )

    if not _has_patient_identifier(summary):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="moderate",
                section="patient_demographics",
                message="NABH discharge summary template expects a patient ID or medical record number.",
            )
        )

    if not extract_demographic_value(summary, "date_of_admission", "admission_date"):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="moderate",
                section="patient_demographics",
                message="NABH discharge summary template expects the admission date.",
            )
        )

    if not extract_demographic_value(summary, "date_of_discharge", "discharge_date"):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="moderate",
                section="patient_demographics",
                message="NABH discharge summary template expects the discharge date.",
            )
        )

    if is_missing(getattr(summary, "urgent_care_instructions", None)):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="critical",
                section="urgent_care_instructions",
                message="NABH standards require instructions about when and how to obtain urgent care.",
            )
        )

    if not _medications_have_details(summary):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="moderate",
                section="medications_on_discharge",
                message="Discharge medications should include understandable details such as dosage, frequency, or duration.",
            )
        )

    if is_missing(getattr(summary, "lifestyle_dietary_instructions", None)):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="low",
                section="lifestyle_dietary_instructions",
                message="The 2025 NABH discharge summary template includes lifestyle or dietary instructions for recovery.",
            )
        )

    if summary.death_case and is_missing(summary.cause_of_death):
        issues.append(
            Issue(
                type="NABH_COMPLIANCE",
                severity="critical",
                section="cause_of_death",
                message="For death cases, NABH requires the summary to include the cause of death.",
            )
        )

    return issues


def count_nabh_checks(summary: DischargeSummary) -> int:
    count = 7
    if summary.death_case:
        count += 1
    return count
