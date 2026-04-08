from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateSummaryRequest(BaseModel):
    patient_id: str
    admission_date: str | None = None
    discharge_date: str | None = None
    attending_physician: str | None = None
    department: str | None = None
    approved_counselling_fact_ids: list[str] = Field(default_factory=list)
    include_recist: bool = False
    template: str = "nabh_standard"
