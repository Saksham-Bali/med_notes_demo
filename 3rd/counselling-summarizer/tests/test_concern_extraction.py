from fastapi.testclient import TestClient

from main import create_app
from models.counselling_fact import CounsellingFact


class FakeExtractor:
    model_name = "fake-llm"

    def __init__(self, facts: list[CounsellingFact]) -> None:
        self._facts = facts

    def extract(self, segments, full_transcript):  # noqa: ANN001
        return self._facts


def test_concern_extraction_endpoint_returns_fact_and_cfs() -> None:
    extractor = FakeExtractor(
        [
            CounsellingFact(
                fact="Patient expressed significant fear about chemotherapy side effects",
                category="CONCERN",
                certainty=0.92,
                evidence_start_time=5.8,
                evidence_end_time=12.4,
                evidence_text="I am very afraid of chemotherapy side effects",
                speaker="patient",
                selectable=True,
            )
        ]
    )
    app = create_app(fact_extractor=extractor)
    client = TestClient(app)

    response = client.post(
        "/api/v1/summarize",
        json={
            "patient_id": "PAT-12345",
            "transcript_english": {
                "segments": [
                    {
                        "speaker": "doctor",
                        "start_time": 0.0,
                        "end_time": 5.2,
                        "text": "Do you have any concerns?",
                    },
                    {
                        "speaker": "patient",
                        "start_time": 5.8,
                        "end_time": 12.4,
                        "text": "I am very afraid of chemotherapy side effects",
                    },
                ]
            },
            "full_text_english": (
                "Doctor: Do you have any concerns?\n"
                "Patient: I am very afraid of chemotherapy side effects"
            ),
            "session_type": "counselling",
            "department": "oncology",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["agent_id"] == "counselling-summarizer"
    assert payload["result"]["stats"]["facts_extracted"] == 1
    assert payload["result"]["counselling_facts"][0]["category"] == "CONCERN"
    assert payload["result"]["clinical_facts"][0]["source_type"] == "COUNSELLING"
    assert payload["metadata"]["llm_used"] == "fake-llm"
