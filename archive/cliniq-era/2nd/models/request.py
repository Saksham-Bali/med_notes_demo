from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TranscriptionRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    patient_consent: bool
    consent_timestamp: datetime
    language_hint: str | None = None
    session_type: Literal["counselling", "consultation", "follow_up"] | None = None
    department: str | None = None
