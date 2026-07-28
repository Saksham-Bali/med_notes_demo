"""Central configuration. All secrets come from the environment / .env (never committed).

Read the companion .env.example for the full list. Nothing here has a real secret as a
default; production must supply them.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo layout: <repo>/findingframe/backend/app/core/config.py
BACKEND_DIR = Path(__file__).resolve().parents[2]
FINDINGFRAME_DIR = BACKEND_DIR.parent
PRE_DIR = FINDINGFRAME_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env"),
        env_prefix="FF_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    env: str = "dev"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- database (Supabase Postgres, async DSN) ---
    # e.g. postgresql+asyncpg://postgres:PW@db.<ref>.supabase.co:5432/postgres
    database_url: str = ""
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_schema: str = "ff"

    # --- Supabase ---
    supabase_url: str = ""            # https://<ref>.supabase.co
    supabase_project_ref: str = ""    # <ref>
    supabase_publishable_key: str = ""
    supabase_service_role_key: str = ""  # server-only; bypasses RLS — keep secret
    # JWT verification: Supabase signs user JWTs; we verify via JWKS (asymmetric) or the
    # legacy shared secret (HS256). Prefer JWKS.
    supabase_jwt_secret: str = ""     # legacy HS256 fallback
    supabase_jwks_url: str = ""       # https://<ref>.supabase.co/auth/v1/.well-known/jwks.json
    jwt_audience: str = "authenticated"

    # --- PII encryption (pgcrypto sym key for patient_identifiers) ---
    pii_encryption_key: str = ""

    # --- engine (FindingFrame at ../../tmc) ---
    engine_path: str = str(PRE_DIR / "tmc")
    engine_git_sha: str = ""          # resolved at runtime if empty
    llm_provider: str = "openrouter"
    llm_model: str = "openai/gpt-5.5"
    llm_reasoning_effort: str = "medium"
    llm_temperature: float = 0.0
    openrouter_api_key: str = ""
    openai_api_key: str = ""

    # --- worker / jobs ---
    worker_id: str = "worker-1"
    worker_poll_interval_s: float = 2.0
    llm_rate_limit_per_min: int = 5   # shared token bucket across workers

    @property
    def jwks_url_resolved(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
