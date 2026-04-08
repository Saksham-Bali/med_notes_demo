from __future__ import annotations

from agents.output_formatter import OutputFormatter
from models.discharge_summary import SummaryContext
from models.request import GenerateSummaryRequest
from tests.helpers import build_summary


def test_completeness_score_tracks_missing_fields() -> None:
    formatter = OutputFormatter()
    summary = build_summary(
        family_history="Not available",
        pathology_results=[],
        radiation_details=None,
    )
    request = GenerateSummaryRequest(
        patient_id="PAT-12345",
        admission_date="2026-03-01",
        discharge_date="2026-03-25",
        attending_physician="Dr. Seema Gulia",
        department="Medical Oncology",
    )
    context = SummaryContext(
        patient_state={},
        recist_data=None,
        counselling_facts=[],
    )

    response = formatter.format(request, summary, context)

    assert "family_history" in response.result.missing_sections
    assert "pathology_results" in response.result.missing_sections
    assert "radiation_details" in response.result.missing_sections
    assert response.result.completeness_score < 1.0
