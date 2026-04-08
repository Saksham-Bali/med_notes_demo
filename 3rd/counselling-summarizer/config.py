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
    min_certainty_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        validation_alias="MIN_CERTAINTY_THRESHOLD",
    )
    diagnosis_filter_enabled: bool = Field(
        default=True,
        validation_alias="DIAGNOSIS_FILTER_ENABLED",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    port: int = 5005

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
