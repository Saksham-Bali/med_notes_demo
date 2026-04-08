from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    patient_id: str = Field(..., min_length=1)
    patient_name: str | None = None
    discharge_summary: dict[str, Any] | str
    target_language: str = Field(..., min_length=2)
    source_language: str = "en-IN"
    generate_audio: bool = True
    generate_pdf: bool = True
    generate_fhir: bool = True

