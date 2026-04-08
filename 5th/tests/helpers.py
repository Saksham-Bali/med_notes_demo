from __future__ import annotations

from models.discharge_summary import (
    ChemoDetails,
    DischargeSummary,
    FollowUp,
    ImagingFinding,
    LabResult,
    MeasurementTrend,
    Medication,
    PathResult,
    Procedure,
    RadiationDetails,
)


def build_summary(**overrides: object) -> DischargeSummary:
    payload = {
        "patient_name": "Meera Rao",
        "patient_id": "PAT-12345",
        "age": 54,
        "gender": "Female",
        "admission_date": "2026-03-01",
        "discharge_date": "2026-03-25",
        "department": "Medical Oncology",
        "attending_physician": "Dr. Seema Gulia",
        "admission_diagnosis": "Metastatic breast carcinoma",
        "chief_complaint": "Progressive back pain",
        "history_of_present_illness": "Back pain with reduced oral intake for 2 weeks.",
        "past_medical_history": "Hypertension on treatment.",
        "family_history": "No known family history of malignancy.",
        "social_history": "Lives with family and is independent in basic activities.",
        "allergies": ["No known drug allergies"],
        "laboratory_results": [
            LabResult(
                test_name="Hemoglobin",
                value="10.2",
                unit="g/dL",
                reference_range="12-15",
                collected_at="2026-03-02",
            )
        ],
        "imaging_findings": [
            ImagingFinding(
                study_name="CECT Chest Abdomen Pelvis",
                study_date="2026-03-03",
                finding="Multiple hepatic lesions with interval decrease in size.",
                impression="Partial response compared with prior imaging.",
            )
        ],
        "pathology_results": [
            PathResult(
                specimen="Liver biopsy",
                result="Metastatic carcinoma consistent with breast primary.",
                reported_at="2026-03-04",
            )
        ],
        "medications_during_stay": [
            Medication(
                name="Morphine",
                dosage="5 mg",
                frequency="Every 4 hours as needed",
                duration="During admission",
                route="Oral",
            )
        ],
        "procedures_performed": [
            Procedure(
                name="Ultrasound-guided liver biopsy",
                performed_at="2026-03-04",
                outcome="Completed without immediate complication.",
            )
        ],
        "chemotherapy_details": ChemoDetails(
            regimen="Paclitaxel + trastuzumab",
            cycles_completed="6",
            last_cycle_date="2026-02-25",
            toxicities=["Grade 1 neuropathy"],
        ),
        "radiation_details": RadiationDetails(
            site="Thoracic spine",
            total_dose="20 Gy",
            fractions="5",
            completion_date="2026-03-10",
        ),
        "tumor_response": "Partial response per RECIST 1.1.",
        "measurement_trends": [
            MeasurementTrend(
                lesion_name="Segment VIII liver lesion",
                study_date="2026-03-03",
                measurement_mm="28",
                response_note="Reduced from prior 35 mm.",
            )
        ],
        "counselling_notes": "Diagnosis, treatment intent, and red-flag symptoms were discussed.",
        "patient_concerns_addressed": ["Pain control", "Follow-up plan"],
        "condition_at_discharge": "Hemodynamically stable and symptomatically improved.",
        "functional_status": "Ambulatory with support.",
        "medications_on_discharge": [
            Medication(
                name="Morphine",
                dosage="5 mg",
                frequency="Every 6 hours as needed",
                duration="5 days",
                route="Oral",
            )
        ],
        "follow_up_schedule": [
            FollowUp(
                date="2026-04-02",
                department="Medical Oncology",
                purpose="Review and next chemotherapy cycle planning.",
            )
        ],
        "dietary_instructions": "High-protein soft diet as tolerated.",
        "activity_restrictions": "Avoid heavy lifting for 1 week.",
        "warning_signs": ["Fever", "Worsening breathlessness", "Uncontrolled pain"],
        "brief_summary": (
            "Meera Rao, a 54-year-old woman with metastatic breast carcinoma, "
            "was admitted for back pain and supportive care. Investigations during "
            "admission confirmed metastatic disease with interval imaging response. "
            "She received analgesic optimization and oncology review, remained stable "
            "at discharge, and was given a dated follow-up plan."
        ),
    }
    payload.update(overrides)
    return DischargeSummary.model_validate(payload)
