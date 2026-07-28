from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


@dataclass(slots=True)
class Settings:
    service_name: str = "clinical-orchestrator"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 5000
    data_dir: Path = Path("final/orchestrator/data")
    agent_timeout_seconds: int = 30
    agent_retry_count: int = 2
    enable_ocr_agent: bool = False
    enable_soap_extractor: bool = False
    enable_radiology_extractor: bool = False
    enable_voice_transcription: bool = True
    enable_counselling_summarizer: bool = True
    enable_fact_graph: bool = False
    enable_department_merger: bool = True
    enable_summary_generator: bool = False
    enable_qa_agent: bool = True
    enable_translation_layer: bool = True
    ocr_agent_url: str = "http://localhost:5001"
    soap_extractor_url: str = "http://localhost:5002"
    radiology_extractor_url: str = "http://localhost:5003"
    voice_transcription_url: str = "http://localhost:5004"
    counselling_summarizer_url: str = "http://localhost:5005"
    fact_graph_url: str = "http://localhost:5006"
    department_merger_url: str = "http://localhost:5007"
    summary_generator_url: str = "http://localhost:5008"
    qa_agent_url: str = "http://localhost:5009"
    translation_layer_url: str = "http://localhost:5010"

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            service_name=os.getenv("SERVICE_NAME", defaults.service_name),
            version=os.getenv("SERVICE_VERSION", defaults.version),
            host=os.getenv("HOST", defaults.host),
            port=_env_int("PORT", defaults.port),
            data_dir=Path(os.getenv("DATA_DIR", str(defaults.data_dir))).resolve(),
            agent_timeout_seconds=_env_int("AGENT_TIMEOUT_SECONDS", defaults.agent_timeout_seconds),
            agent_retry_count=_env_int("AGENT_RETRY_COUNT", defaults.agent_retry_count),
            enable_ocr_agent=_env_bool("ENABLE_OCR_AGENT", defaults.enable_ocr_agent),
            enable_soap_extractor=_env_bool("ENABLE_SOAP_EXTRACTOR", defaults.enable_soap_extractor),
            enable_radiology_extractor=_env_bool("ENABLE_RADIOLOGY_EXTRACTOR", defaults.enable_radiology_extractor),
            enable_voice_transcription=_env_bool("ENABLE_VOICE_TRANSCRIPTION", defaults.enable_voice_transcription),
            enable_counselling_summarizer=_env_bool(
                "ENABLE_COUNSELLING_SUMMARIZER",
                defaults.enable_counselling_summarizer,
            ),
            enable_fact_graph=_env_bool("ENABLE_FACT_GRAPH", defaults.enable_fact_graph),
            enable_department_merger=_env_bool("ENABLE_DEPARTMENT_MERGER", defaults.enable_department_merger),
            enable_summary_generator=_env_bool("ENABLE_SUMMARY_GENERATOR", defaults.enable_summary_generator),
            enable_qa_agent=_env_bool("ENABLE_QA_AGENT", defaults.enable_qa_agent),
            enable_translation_layer=_env_bool("ENABLE_TRANSLATION_LAYER", defaults.enable_translation_layer),
            ocr_agent_url=os.getenv("OCR_AGENT_URL", defaults.ocr_agent_url),
            soap_extractor_url=os.getenv("SOAP_EXTRACTOR_URL", defaults.soap_extractor_url),
            radiology_extractor_url=os.getenv("RADIOLOGY_EXTRACTOR_URL", defaults.radiology_extractor_url),
            voice_transcription_url=os.getenv("VOICE_TRANSCRIPTION_URL", defaults.voice_transcription_url),
            counselling_summarizer_url=os.getenv("COUNSELLING_SUMMARIZER_URL", defaults.counselling_summarizer_url),
            fact_graph_url=os.getenv("FACT_GRAPH_URL", defaults.fact_graph_url),
            department_merger_url=os.getenv("DEPARTMENT_MERGER_URL", defaults.department_merger_url),
            summary_generator_url=os.getenv("SUMMARY_GENERATOR_URL", defaults.summary_generator_url),
            qa_agent_url=os.getenv("QA_AGENT_URL", defaults.qa_agent_url),
            translation_layer_url=os.getenv("TRANSLATION_LAYER_URL", defaults.translation_layer_url),
        )
