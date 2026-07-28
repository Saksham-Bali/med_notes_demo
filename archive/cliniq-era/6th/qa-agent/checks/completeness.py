from __future__ import annotations

from models.issue import Issue
from models.response import DischargeSummary
from utils import is_missing


REQUIRED_SECTIONS = [
    "patient_demographics",
    "admission_diagnosis",
    "chief_complaint",
    "investigations",
    "treatment_given",
    "medications_on_discharge",
    "condition_at_discharge",
    "follow_up_schedule",
    "brief_summary",
]

CRITICAL_SECTIONS = {"medications_on_discharge", "follow_up_schedule"}


def check_completeness(summary: DischargeSummary) -> list[Issue]:
    issues: list[Issue] = []
    for section in REQUIRED_SECTIONS:
        value = getattr(summary, section, None)
        if is_missing(value):
            issues.append(
                Issue(
                    type="MISSING_FIELD",
                    severity="critical" if section in CRITICAL_SECTIONS else "moderate",
                    section=section,
                    message=f"Required section '{section}' is missing or empty.",
                )
            )
    return issues


def count_completeness_checks() -> int:
    return len(REQUIRED_SECTIONS)
