from fastapi.testclient import TestClient

from main import app


def test_validate_endpoint_returns_expected_contract(monkeypatch) -> None:
    monkeypatch.setenv("TRACEABILITY_MODE", "heuristic")
    monkeypatch.setenv("ENABLE_NABH_CHECKS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/validate",
        json={
            "patient_id": "PAT-12345",
            "discharge_summary": {
                "patient_demographics": {
                    "name": "Anita Rao",
                    "patient_id": "PAT-12345",
                    "date_of_admission": "2026-03-20",
                    "date_of_discharge": "2026-03-26",
                },
                "admission_diagnosis": "Community acquired pneumonia",
                "chief_complaint": "Fever and cough",
                "investigations": ["CBC", "Chest X-ray"],
                "treatment_given": ["IV ceftriaxone"],
                "medications_on_discharge": ["Azithromycin 500 mg once daily for 3 days"],
                "condition_at_discharge": "Stable",
                "follow_up_schedule": "Review after 5 days",
                "brief_summary": "Improved after IV antibiotics.",
                "urgent_care_instructions": "Return to the ER for worsening breathlessness or persistent fever.",
                "lifestyle_dietary_instructions": "Maintain hydration and rest at home.",
            },
            "source_facts": [
                {
                    "entity": "Community acquired pneumonia",
                    "entity_type": "diagnosis",
                    "certainty": 0.98,
                    "evidence": "Admission note",
                },
                {
                    "entity": "Fever and cough",
                    "entity_type": "symptom",
                    "certainty": 0.95,
                    "evidence": "Triage note",
                },
                {
                    "entity": "Azithromycin 500 mg once daily for 3 days",
                    "entity_type": "medication",
                    "certainty": 0.94,
                    "evidence": "Discharge prescription",
                },
            ],
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["agent_id"] == "qa-agent"
    assert body["result"]["verdict"] in {"PASS", "FAIL"}
    assert "validation_id" in body["result"]["audit_trail"]
    assert body["result"]["audit_trail"]["traceability_mode"] == "heuristic"
