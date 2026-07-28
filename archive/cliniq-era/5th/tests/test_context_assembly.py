from __future__ import annotations

import httpx
import pytest

from agents.context_assembler import ContextAssembler
from config import Settings
from models.request import GenerateSummaryRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_context_assembler_reads_fact_graph_sources() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/patient/PAT-12345/state":
            return httpx.Response(
                200,
                json={"result": {"demographics": {"patient_name": "Meera Rao"}}},
            )
        if request.url.path == "/api/v1/patient/PAT-12345/measurements":
            return httpx.Response(
                200,
                json={"data": {"measurements": [{"certainty": 0.91, "size_mm": 28}]}},
            )
        if request.url.path == "/api/v1/patient/PAT-12345/facts":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "facts": [
                            {"id": "cf-001", "text": "Discussed follow-up dates."},
                            {"id": "cf-003", "text": "Explained warning signs."},
                        ]
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="http://fact-graph:5006",
        transport=transport,
    ) as client:
        assembler = ContextAssembler(
            Settings(fact_graph_base_url="http://fact-graph:5006"),
            client=client,
        )
        request = GenerateSummaryRequest(
            patient_id="PAT-12345",
            admission_date="2026-03-01",
            discharge_date="2026-03-25",
            attending_physician="Dr. Seema Gulia",
            department="Medical Oncology",
            approved_counselling_fact_ids=["cf-001", "cf-003"],
            include_recist=True,
        )

        context = await assembler.assemble_context(request)

    assert context.patient_state["demographics"]["patient_name"] == "Meera Rao"
    assert context.recist_data["measurements"][0]["size_mm"] == 28
    assert [fact["id"] for fact in context.counselling_facts] == ["cf-001", "cf-003"]
