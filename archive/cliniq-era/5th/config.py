from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "summary-generator"
    host: str = "0.0.0.0"
    port: int = 5008

    fact_graph_base_url: str = Field(default="http://localhost:5006", alias="FACT_GRAPH_BASE_URL")
    fact_graph_timeout: float = 20.0

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openai_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENAI_BASE_URL")
    llm_model: str = Field(default="openai/gpt-4o-mini", alias="LLM_MODEL")
    openai_model: str = "openai/gpt-4o-mini"
    openai_timeout: float = 90.0

    default_template: str = "nabh_standard"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
