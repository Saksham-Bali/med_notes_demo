from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    agent_id: str
    service_port: int
    low_confidence_threshold: float
    traceability_mode: str
    traceability_model: str
    traceability_reasoning_effort: str
    traceability_timeout_seconds: int
    azure_api_key: str | None
    azure_endpoint: str
    azure_deployment: str
    azure_api_version: str
    enable_nabh_checks: bool


def get_settings() -> Settings:
    return Settings(
        agent_id=os.getenv("QA_AGENT_ID", "qa-agent"),
        service_port=_get_int("PORT", 5009),
        low_confidence_threshold=_get_float("LOW_CONFIDENCE_THRESHOLD", 0.6),
        traceability_mode=os.getenv("TRACEABILITY_MODE", "auto").strip().casefold(),
        traceability_model=os.getenv("AZURE_DEPLOYMENT", "gpt-4o-mini"),
        traceability_reasoning_effort=os.getenv("TRACEABILITY_REASONING_EFFORT", "medium"),
        traceability_timeout_seconds=_get_int("TRACEABILITY_TIMEOUT_SECONDS", 30),
        azure_api_key=os.getenv("AZURE_API_KEY"),
        azure_endpoint=os.getenv("AZURE_ENDPOINT", "https://sherpartap1101-5077-resource.cognitiveservices.azure.com/"),
        azure_deployment=os.getenv("AZURE_DEPLOYMENT", "gpt-4o-mini"),
        azure_api_version=os.getenv("AZURE_API_VERSION", "2025-01-01-preview"),
        enable_nabh_checks=_get_bool("ENABLE_NABH_CHECKS", True),
    )
