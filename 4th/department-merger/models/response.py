from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.aligned_entity import UnifiedFact
from models.conflict import Conflict


class ProcessingStats(BaseModel):
    departments_processed: int
    total_facts_extracted: int
    facts_merged: int
    conflicts_detected: int


class MergeResult(BaseModel):
    unified_facts: list[UnifiedFact] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    stats: ProcessingStats


class MergeResponse(BaseModel):
    agent_id: str
    patient_id: str
    timestamp: datetime
    result: MergeResult
    errors: list[str] = Field(default_factory=list)
