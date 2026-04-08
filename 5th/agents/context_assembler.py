from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx

from config import Settings
from models.discharge_summary import SummaryContext
from models.request import GenerateSummaryRequest


class ContextAssembler:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    @asynccontextmanager
    async def _client_context(self) -> httpx.AsyncClient:
        if self._client is not None:
            yield self._client
            return

        async with httpx.AsyncClient(
            base_url=self.settings.fact_graph_base_url.rstrip("/"),
            timeout=self.settings.fact_graph_timeout,
        ) as client:
            yield client

    async def assemble_context(self, request: GenerateSummaryRequest) -> SummaryContext:
        async with self._client_context() as client:
            patient_state = await self._get_json(
                client,
                f"/api/v1/patient/{request.patient_id}/state",
            )

            recist_data: dict[str, Any] | list[Any] | None = None
            if request.include_recist:
                try:
                    recist_data = await self._get_json(
                        client,
                        f"/api/v1/patient/{request.patient_id}/measurements",
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        recist_data = None  # endpoint not implemented yet
                    else:
                        raise

            counselling_facts: list[dict[str, Any]] = []
            if request.approved_counselling_fact_ids:
                facts_payload = await self._post_json(
                    client,
                    f"/api/v1/patient/{request.patient_id}/facts",
                    {
                        "source_type": "COUNSELLING",
                        "ids": request.approved_counselling_fact_ids,
                    },
                )
                counselling_facts = self._coerce_fact_list(facts_payload)

        if not isinstance(patient_state, dict):
            raise ValueError("Fact Graph patient state must be a JSON object.")

        return SummaryContext(
            patient_state=patient_state,
            recist_data=recist_data,
            counselling_facts=counselling_facts,
        )

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
    ) -> dict[str, Any] | list[Any]:
        response = await client.get(path)
        response.raise_for_status()
        return self._unwrap_payload(response.json())

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | list[Any]:
        response = await client.post(path, json=payload)
        response.raise_for_status()
        return self._unwrap_payload(response.json())

    def _unwrap_payload(self, payload: Any) -> dict[str, Any] | list[Any]:
        if not isinstance(payload, dict):
            return payload

        for key in ("result", "data", "payload"):
            candidate = payload.get(key)
            if candidate is None:
                continue
            other_keys = set(payload) - {key}
            if other_keys <= {"status", "message", "errors", "meta"}:
                return candidate

        return payload

    def _coerce_fact_list(self, payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        for key in ("facts", "items", "entries", "rows"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]

        return []
