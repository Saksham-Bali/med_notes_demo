from __future__ import annotations

from pydantic import BaseModel, Field


class BulletPoint(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_time_start: float | None = None
    source_time_end: float | None = None
