from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuditTrail(BaseModel):
    validation_id: str
    timestamp: str
    checks_performed: list[str]
    summary_hash: str
    traceability_mode: str
    traceability_model: str | None = None

    model_config = ConfigDict(extra="allow")
