from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from models.discharge_summary import DischargeSummary


class SectionMetadata(BaseModel):
    section: str
    fact_count: int
    avg_certainty: float | None = None


class GenerateSummaryResult(BaseModel):
    discharge_summary: DischargeSummary
    prose_version: str
    section_metadata: list[SectionMetadata]
    completeness_score: float
    missing_sections: list[str] = Field(default_factory=list)


class GenerateSummaryResponse(BaseModel):
    agent_id: str = "summary-generator"
    patient_id: str
    result: GenerateSummaryResult
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str
    model: str
    fact_graph_base_url: str
    details: dict[str, Any] = Field(default_factory=dict)
