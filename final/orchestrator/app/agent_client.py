from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .errors import AgentCallError, MissingDependencyError
from .registry import AgentDefinition, AgentRegistry


class AgentClient:
    def __init__(
        self,
        registry: AgentRegistry,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.registry = registry
        self._client = httpx.AsyncClient(transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self, agent_name: str) -> dict[str, Any]:
        agent = self.registry.get(agent_name)
        if not agent.enabled:
            return {"status": "disabled", "agent": agent.name, "notes": agent.notes}
        try:
            response = await self._client.get(agent.health_url, timeout=agent.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            return {"status": "ok", "agent": agent.name, "details": payload}
        except (httpx.HTTPError, ValueError) as exc:
            return {"status": "unhealthy", "agent": agent.name, "error": str(exc)}

    async def call(
        self,
        agent_name: str,
        endpoint: str,
        *,
        method: str = "POST",
        path_params: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        agent = self.registry.get(agent_name)
        if not agent.enabled:
            raise MissingDependencyError(agent_name, agent.notes)

        url = agent.endpoint_url(endpoint, path_params=path_params)
        last_error: Exception | None = None
        for attempt in range(agent.retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    timeout=agent.timeout_seconds,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code >= 500 and attempt < agent.retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise AgentCallError(
                    agent_name,
                    f"{agent_name} returned {exc.response.status_code}: {exc.response.text}",
                    status_code=502,
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < agent.retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise AgentCallError(
                    agent_name,
                    f"{agent_name} request failed: {exc}",
                    status_code=503,
                ) from exc

        raise AgentCallError(
            agent_name,
            f"{agent_name} request failed: {last_error}",
            status_code=503,
        )


async def collect_agent_health(agent_client: AgentClient) -> list[dict[str, Any]]:
    return await asyncio.gather(
        *(agent_client.health(agent.name) for agent in agent_client.registry.all())
    )
