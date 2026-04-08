from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranscriptSegment(BaseModel):
    speaker: Literal["doctor", "patient", "unknown"] = "unknown"
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    text: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_time_window(self) -> "TranscriptSegment":
        if self.end_time < self.start_time:
            raise ValueError("end_time must be greater than or equal to start_time")
        return self


class TranscriptEnglish(BaseModel):
    segments: list[TranscriptSegment] = Field(default_factory=list)


class SummarizeRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    transcript_english: TranscriptEnglish
    full_text_english: str = ""
    session_type: str = "counselling"
    department: str = "unknown"

    model_config = ConfigDict(str_strip_whitespace=True)
