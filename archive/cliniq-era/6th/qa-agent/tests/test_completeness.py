from checks.completeness import check_completeness
from models.response import DischargeSummary


def test_completeness_flags_missing_required_sections() -> None:
    summary = DischargeSummary(
        patient_demographics={"name": "Asha", "patient_id": "PAT-1"},
        admission_diagnosis="Community acquired pneumonia",
        chief_complaint="Fever and cough",
        investigations="CBC, chest X-ray",
        treatment_given="IV antibiotics",
        condition_at_discharge="Stable",
        brief_summary="Improved on antibiotics.",
    )

    issues = check_completeness(summary)

    assert {issue.section for issue in issues} == {"follow_up_schedule", "medications_on_discharge"}
    assert {issue.severity for issue in issues} == {"critical"}
