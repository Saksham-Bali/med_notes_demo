from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Issue(BaseModel):
    type: str
    severity: Literal["critical", "moderate", "low"]
    message: str
    section: str | None = None
    evidence: str | None = None

    model_config = ConfigDict(extra="allow")
