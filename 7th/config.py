from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "translation-layer"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 5010

    sarvam_api_key: str | None = None
    sarvam_translation_model: str = "sarvam-translate:v1"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_output_audio_codec: str = "mp3"
    sarvam_tts_speaker: str | None = None
    sarvam_timeout_seconds: float = 60.0

    default_source_language: str = "en-IN"
    supported_translation_languages: tuple[str, ...] = (
        "as-IN",
        "bn-IN",
        "brx-IN",
        "doi-IN",
        "en-IN",
        "gu-IN",
        "hi-IN",
        "kn-IN",
        "ks-IN",
        "kok-IN",
        "mai-IN",
        "ml-IN",
        "mni-IN",
        "mr-IN",
        "ne-IN",
        "od-IN",
        "pa-IN",
        "sa-IN",
        "sat-IN",
        "sd-IN",
        "ta-IN",
        "te-IN",
        "ur-IN",
    )
    supported_tts_languages: tuple[str, ...] = (
        "bn-IN",
        "en-IN",
        "gu-IN",
        "hi-IN",
        "kn-IN",
        "ml-IN",
        "mr-IN",
        "od-IN",
        "pa-IN",
        "ta-IN",
        "te-IN",
    )

    pdf_template_dir: Path = Field(default_factory=lambda: Path("templates"))
    output_dir: Path = Field(default_factory=lambda: Path("outputs"))
    fhir_version: str = "R4"

    translation_max_chars: int = 1900
    tts_max_chars: int = 2500


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.pdf_template_dir.mkdir(parents=True, exist_ok=True)
    return settings

