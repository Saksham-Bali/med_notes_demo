from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, Field


class DepartmentNote(BaseModel):
    department: str = Field(min_length=2)
    text: str = Field(min_length=1)
    date: DateType
    author: str | None = None


class MergeRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    department_notes: list[DepartmentNote] = Field(min_length=1)
