from checks.consistency import check_consistency
from models.response import ClinicalFact, DischargeSummary


def test_consistency_detects_diagnosis_medication_and_date_mismatches() -> None:
    summary = DischargeSummary(
        patient_demographics={
            "name": "Rahul Verma",
            "patient_id": "PAT-22",
            "date_of_admission": "2026-03-20",
            "date_of_discharge": "2026-03-19",
        },
        admission_diagnosis=["Asthma exacerbation"],
        chief_complaint="Shortness of breath",
        investigations=["Chest X-ray"],
        treatment_given=["Nebulization"],
        medications_on_discharge=["Warfarin 5 mg once daily"],
        condition_at_discharge="Improved",
        follow_up_schedule="Pulmonology review in 1 week",
        brief_summary="Admitted with breathing difficulty and improved after treatment.",
    )
    facts = [
        ClinicalFact(entity="COPD exacerbation", entity_type="PRIMARY", certainty=0.97, evidence="Pulmonology note"),
        ClinicalFact(entity="Salbutamol inhaler", entity_type="MEDICATION", certainty=0.93, evidence="Medication chart"),
        ClinicalFact(entity="Shortness of breath", entity_type="SYMPTOM", certainty=0.99, evidence="ED triage"),
    ]

    issues = check_consistency(summary, facts)

    messages = [issue.message for issue in issues]
    assert any("Asthma exacerbation" in message for message in messages)
    assert any("Warfarin" in message for message in messages)
    assert any("Discharge date occurs before admission date" in message for message in messages)
