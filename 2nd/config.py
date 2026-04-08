from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "voice-transcription"
    host: str = "0.0.0.0"
    port: int = 5004
    log_level: str = "INFO"

    sarvam_api_key: str | None = Field(default=None, alias="SARVAM_API_KEY")
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_translation_model: str = "sarvam-translate:v1"
    sarvam_non_english_mode: str = "codemix"
    sarvam_request_timeout_seconds: float = 120.0
    sarvam_batch_threshold_seconds: float = 30.0
    sarvam_batch_poll_interval_seconds: int = 5
    sarvam_batch_timeout_seconds: int = 900
    use_batch_for_long_audio: bool = True
    enable_batch_diarization: bool = True

    max_audio_duration_seconds: int = 3600
    consent_required: bool = True
    enable_google_fallback: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
