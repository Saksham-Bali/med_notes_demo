from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx

from agents.parallel_extractor import SOAPExtractorClient
from models.department_note import DepartmentNote


def test_extract_all_departments_runs_requests_in_parallel() -> None:
    async def run_test() -> None:
        state = {"active": 0, "peak": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.05)
            payload = json.loads(request.content.decode("utf-8"))
            state["active"] -= 1
            return httpx.Response(
                200,
                json={
                    "result": {
                        "clinical_facts": [
                            {
                                "entity": f"{payload['department']} pain plan",
                                "category": "medication",
                                "value": "continue opioid titration",
                                "status": "active",
                                "evidence": payload["text"],
                            }
                        ]
                    }
                },
            )

        transport = httpx.MockTransport(handler)
        client = SOAPExtractorClient(
            base_url="http://soap-extractor:5002",
            timeout_seconds=2.0,
            transport=transport,
        )
        notes = [
            DepartmentNote(
                department="oncology",
                text="Continue current chemotherapy and pain plan.",
                date=date(2026, 3, 24),
                author="Dr. A",
            ),
            DepartmentNote(
                department="palliative_care",
                text="Escalate morphine for uncontrolled pain.",
                date=date(2026, 3, 25),
                author="Dr. B",
            ),
            DepartmentNote(
                department="surgery",
                text="Pain control adequate after procedure.",
                date=date(2026, 3, 25),
                author="Dr. C",
            ),
        ]

        extracted = await client.extract_all_departments(patient_id="PAT-12345", department_notes=notes)

        assert len(extracted) == 3
        assert state["peak"] > 1
        assert extracted[0].facts[0].source_department == "oncology"

    asyncio.run(run_test())
