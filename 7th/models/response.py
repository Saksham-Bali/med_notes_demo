from __future__ import annotations

from pydantic import BaseModel, Field


class GeneratedFiles(BaseModel):
    pdf_english: str | None = None
    pdf_translated: str | None = None
    audio: str | None = None
    fhir_bundle: str | None = None


class TranslationPayload(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    translation_model: str
    files: GeneratedFiles
    warnings: list[str] = Field(default_factory=list)


class TranslateResponse(BaseModel):
    agent_id: str = "translation-layer"
    result: TranslationPayload

