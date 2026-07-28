from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.bullet_point import BulletPoint
from models.clinical_fact import ClinicalFact
from models.counselling_fact import CounsellingFact


class ProcessingStats(BaseModel):
    total_segments_analyzed: int = Field(ge=0)
    clinically_relevant_segments: int = Field(ge=0)
    facts_extracted: int = Field(ge=0)


class ProcessingResult(BaseModel):
    counselling_facts: list[CounsellingFact] = Field(default_factory=list)
    clinical_facts: list[ClinicalFact] = Field(default_factory=list)
    bullet_points: list[BulletPoint] = Field(default_factory=list)
    corrected_transcript: str = ""
    session_summary: str
    stats: ProcessingStats


class ProcessingMetadata(BaseModel):
    llm_used: str
    processing_time_ms: int = Field(ge=0)


class SummarizeResponse(BaseModel):
    agent_id: str
    patient_id: str
    timestamp: datetime
    result: ProcessingResult
    metadata: ProcessingMetadata
    errors: list[str] = Field(default_factory=list)
