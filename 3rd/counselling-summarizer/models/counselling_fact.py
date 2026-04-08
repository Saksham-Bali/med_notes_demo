from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CounsellingCategory = Literal["CONCERN", "ACTION", "DECISION", "EMOTIONAL", "FOLLOW_UP"]
Speaker = Literal["doctor", "patient", "unknown"]


class CounsellingFact(BaseModel):
    fact: str = Field(min_length=1)
    category: CounsellingCategory
    certainty: float = Field(ge=0.0, le=1.0)
    evidence_start_time: float = Field(ge=0.0)
    evidence_end_time: float = Field(ge=0.0)
    evidence_text: str = Field(min_length=1)
    speaker: Speaker = "unknown"
    selectable: bool = True
    validation_flags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_time_window(self) -> "CounsellingFact":
        if self.evidence_end_time < self.evidence_start_time:
            raise ValueError("evidence_end_time must be greater than or equal to evidence_start_time")
        return self
