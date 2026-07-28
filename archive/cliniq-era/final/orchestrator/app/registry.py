from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings


@dataclass(slots=True)
class AgentDefinition:
    name: str
    url: str
    health_path: str
    endpoints: dict[str, str]
    timeout_seconds: int
    retries: int
    enabled: bool = True
    notes: str | None = None

    def endpoint_url(self, key: str, *, path_params: dict[str, str] | None = None) -> str:
        path = self.endpoints[key]
        if path_params:
            path = path.format(**path_params)
        return f"{self.url}{path}"

    @property
    def health_url(self) -> str:
        return f"{self.url}{self.health_path}"


@dataclass(slots=True)
class AgentRegistry:
    agents: dict[str, AgentDefinition] = field(default_factory=dict)

    def get(self, name: str) -> AgentDefinition:
        return self.agents[name]

    def is_enabled(self, name: str) -> bool:
        return self.get(name).enabled

    def all(self) -> list[AgentDefinition]:
        return list(self.agents.values())


def build_registry(settings: Settings) -> AgentRegistry:
    timeout = settings.agent_timeout_seconds
    retries = settings.agent_retry_count
    return AgentRegistry(
        agents={
            "ocr-agent": AgentDefinition(
                name="ocr-agent",
                url=settings.ocr_agent_url,
                health_path="/health",
                endpoints={"extract": "/api/v1/extract"},
                timeout_seconds=timeout,
                retries=retries,
                enabled=settings.enable_ocr_agent,
                notes="Not yet wired in this repository.",
            ),
            "soap-extractor": AgentDefinition(
                name="soap-extractor",
                url=settings.soap_extractor_url,
                health_path="/health",
                endpoints={"extract": "/api/v1/extract"},
                timeout_seconds=timeout,
                retries=retries,
                enabled=settings.enable_soap_extractor,
                notes="Not yet wired in this repository.",
            ),
            "radiology-extractor": AgentDefinition(
                name="radiology-extractor",
                url=settings.radiology_extractor_url,
                health_path="/health",
                endpoints={"extract": "/api/v1/extract"},
                timeout_seconds=timeout,
                retries=retries,
                enabled=settings.enable_radiology_extractor,
                notes="Not yet wired in this repository.",
            ),
            "voice-transcription": AgentDefinition(
                name="voice-transcription",
                url=settings.voice_transcription_url,
                health_path="/healthz",
                endpoints={"transcribe": "/api/v1/transcribe"},
                timeout_seconds=max(timeout, 60),
                retries=1,
                enabled=settings.enable_voice_transcription,
            ),
            "counselling-summarizer": AgentDefinition(
                name="counselling-summarizer",
                url=settings.counselling_summarizer_url,
                health_path="/health",
                endpoints={"summarize": "/api/v1/summarize"},
                timeout_seconds=timeout,
                retries=retries,
                enabled=settings.enable_counselling_summarizer,
            ),
            "fact-graph": AgentDefinition(
                name="fact-graph",
                url=settings.fact_graph_url,
                health_path="/health",
                endpoints={
                    "ingest": "/api/v1/ingest",
                    "patients": "/api/v1/patients",
                    "patient_state": "/api/v1/patient/{patient_id}/state",
                    "patient_timeline": "/api/v1/patient/{patient_id}/timeline",
                    "entity_history": "/api/v1/patient/{patient_id}/entity/{entity_id}",
                    "import_graph": "/api/v1/patient/{patient_id}/import",
                },
                timeout_seconds=10,
                retries=3,
                enabled=settings.enable_fact_graph,
                notes="Planned dependency. Orchestrator will queue deferred ingest jobs until it exists.",
            ),
            "department-merger": AgentDefinition(
                name="department-merger",
                url=settings.department_merger_url,
                health_path="/health",
                endpoints={"merge": "/api/v1/merge"},
                timeout_seconds=max(timeout, 45),
                retries=1,
                enabled=settings.enable_department_merger,
            ),
            "summary-generator": AgentDefinition(
                name="summary-generator",
                url=settings.summary_generator_url,
                health_path="/health",
                endpoints={"generate": "/api/v1/generate"},
                timeout_seconds=max(timeout, 120),
                retries=1,
                enabled=settings.enable_summary_generator,
                notes="Uses Azure OpenAI Responses API for structured output. Needs longer timeout for large patient graphs.",
            ),
            "qa-agent": AgentDefinition(
                name="qa-agent",
                url=settings.qa_agent_url,
                health_path="/health",
                endpoints={"validate": "/api/v1/validate"},
                timeout_seconds=max(timeout, 90),
                retries=retries,
                enabled=settings.enable_qa_agent,
            ),
            "translation-layer": AgentDefinition(
                name="translation-layer",
                url=settings.translation_layer_url,
                health_path="/health",
                endpoints={"translate": "/api/v1/translate"},
                timeout_seconds=max(timeout, 60),
                retries=1,
                enabled=settings.enable_translation_layer,
            ),
        }
    )
