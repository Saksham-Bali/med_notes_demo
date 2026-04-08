from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    azure_api_key: str | None = Field(default=None, validation_alias="AZURE_API_KEY")
    azure_endpoint: str = Field(default="https://sherpartap1101-5077-resource.cognitiveservices.azure.com/", validation_alias="AZURE_ENDPOINT")
    azure_deployment: str = Field(default="gpt-4o-mini", validation_alias="AZURE_DEPLOYMENT")
    azure_api_version: str = Field(default="2025-01-01-preview", validation_alias="AZURE_API_VERSION")
    llm_model: str = "gpt-4o-mini"  # kept for compatibility
    soap_extractor_url: str = Field(
        default="http://soap-extractor:5002",
        validation_alias="SOAP_EXTRACTOR_URL",
    )
    fact_graph_url: str = Field(
        default="http://fact-graph:5006",
        validation_alias="FACT_GRAPH_URL",
    )
    conflict_auto_resolve: bool = Field(
        default=False,
        validation_alias="CONFLICT_AUTO_RESOLVE",
    )
    radlex_db_path: str = Field(default="/data/radlex.db", validation_alias="RADLEX_DB_PATH")
    request_timeout_seconds: float = Field(
        default=20.0,
        gt=0.0,
        validation_alias="REQUEST_TIMEOUT_SECONDS",
    )
    max_conflict_analysis_tokens: int = Field(
        default=400,
        ge=128,
        le=4096,
        validation_alias="MAX_CONFLICT_ANALYSIS_TOKENS",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    port: int = 5007

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
