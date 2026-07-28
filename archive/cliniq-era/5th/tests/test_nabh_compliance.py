from __future__ import annotations

from fastapi.testclient import TestClient

from agents.output_formatter import OutputFormatter
from main import create_app
from models.discharge_summary import SummaryContext
from models.request import GenerateSummaryRequest
from tests.helpers import build_summary


class StubAssembler:
    async def assemble_context(self, request: GenerateSummaryRequest) -> SummaryContext:
        return SummaryContext(
            patient_state={
                "laboratory_results": [{"certainty": 0.94, "test_name": "Hemoglobin"}],
                "medications": [{"certainty": 0.97, "name": "Morphine"}],
            },
            recist_data={
                "measurements": [{"certainty": 0.9, "lesion": "Liver lesion"}]
            },
            counselling_facts=[
                {"id": "cf-001", "certainty": 0.92, "text": "Follow-up explained."}
            ],
        )


class StubComposer:
    async def compose_summary(self, request: GenerateSummaryRequest, context: SummaryContext):
        return build_summary(family_history="Not available")


def test_generate_endpoint_returns_nabh_shaped_payload() -> None:
    app = create_app(
        assembler=StubAssembler(),
        composer=StubComposer(),
        formatter=OutputFormatter(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/generate",
        json={
            "patient_id": "PAT-12345",
            "admission_date": "2026-03-01",
            "discharge_date": "2026-03-25",
            "attending_physician": "Dr. Seema Gulia",
            "department": "Medical Oncology",
            "approved_counselling_fact_ids": ["cf-001"],
            "include_recist": True,
            "template": "nabh_standard",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["agent_id"] == "summary-generator"
    assert body["patient_id"] == "PAT-12345"
    assert "discharge_summary" in body["result"]
    assert "section_metadata" in body["result"]
    assert "completeness_score" in body["result"]
    assert "missing_sections" in body["result"]
    assert "family_history" in body["result"]["missing_sections"]

    summary = body["result"]["discharge_summary"]
    required_fields = {
        "patient_name",
        "patient_id",
        "admission_diagnosis",
        "laboratory_results",
        "medications_during_stay",
        "tumor_response",
        "medications_on_discharge",
        "brief_summary",
    }
    assert required_fields.issubset(summary)
