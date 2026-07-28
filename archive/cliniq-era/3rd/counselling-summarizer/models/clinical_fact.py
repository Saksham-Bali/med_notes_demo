from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EntityType = Literal["PRIMARY"]
SourceType = Literal["COUNSELLING"]
StatusType = Literal["PRESENT"]


class ClinicalFact(BaseModel):
    entity: str = Field(min_length=1)
    radlex_id: str | None = None
    entity_type: EntityType = "PRIMARY"
    certainty: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)
    source_type: SourceType = "COUNSELLING"
    source_department: str = "unknown"
    timestamp: datetime
    negated: bool = False
    status: StatusType = "PRESENT"
