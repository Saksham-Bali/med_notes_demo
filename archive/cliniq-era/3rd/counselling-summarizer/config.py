from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openai_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENAI_BASE_URL")
    llm_model: str = Field(default="openai/gpt-4o-mini", validation_alias="LLM_MODEL")
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
