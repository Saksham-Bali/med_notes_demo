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

    azure_api_key: str | None = Field(default=None, alias="AZURE_API_KEY")
    azure_endpoint: str = Field(default="https://sherpartap1101-5077-resource.cognitiveservices.azure.com/", alias="AZURE_ENDPOINT")
    azure_deployment: str = Field(default="gpt-4o-mini", alias="AZURE_DEPLOYMENT")
    azure_api_version: str = Field(default="2025-03-01-preview", alias="SUMMARY_AZURE_API_VERSION")
    openai_model: str = "gpt-4o-mini"  # kept for compatibility
    openai_timeout: float = 90.0

    default_template: str = "nabh_standard"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
