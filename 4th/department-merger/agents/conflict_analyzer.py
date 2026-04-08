from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from config import Settings
from models.conflict import Conflict

try:
    from openai import AsyncAzureOpenAI
except ImportError:  # pragma: no cover
    AsyncAzureOpenAI = None


class ConflictAnalyzer:
    def __init__(
        self,
        settings: Settings,
        prompt_path: Path | None = None,
    ) -> None:
        self.model_name = settings.azure_deployment
        self.max_tokens = settings.max_conflict_analysis_tokens
        self.prompt_template = (prompt_path or _default_prompt_path()).read_text(encoding="utf-8")
        self._client = None

        if settings.azure_api_key and AsyncAzureOpenAI is not None:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_endpoint,
                api_key=settings.azure_api_key,
                api_version=settings.azure_api_version,
            )

    async def analyze_many(self, conflicts: list[Conflict]) -> list[Conflict]:
        if not conflicts:
            return []

        if self._client is None:
            return [self._fallback_analysis(conflict) for conflict in conflicts]

        tasks = [self._analyze_single(conflict) for conflict in conflicts]
        return list(await asyncio.gather(*tasks))

    async def _analyze_single(self, conflict: Conflict) -> Conflict:
        fallback = self._fallback_analysis(conflict)
        prompt = self.prompt_template.format(
            entity=conflict.entity,
            conflict_type=conflict.conflict_type,
            dept_a=conflict.department_a,
            dept_b=conflict.department_b,
            description=conflict.description,
            fact_a_evidence=conflict.fact_a.evidence or "No evidence supplied",
            fact_b_evidence=conflict.fact_b.evidence or "No evidence supplied",
            fact_a_value=conflict.fact_a.value or "Unknown",
            fact_b_value=conflict.fact_b.value or "Unknown",
            fact_a_status=conflict.fact_a.status or "Unknown",
            fact_b_status=conflict.fact_b.status or "Unknown",
        )

        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.choices[0].message.content if response.choices and response.choices[0].message.content else ""
            parsed = _extract_json_object(raw_text)
        except Exception:
            return fallback

        return fallback.model_copy(
            update={
                "description": parsed.get("description") or fallback.description,
                "authoritative_department": parsed.get("authoritative_department")
                or fallback.authoritative_department,
                "suggested_resolution": parsed.get("suggested_resolution")
                or fallback.suggested_resolution,
            }
        )

    def _fallback_analysis(self, conflict: Conflict) -> Conflict:
        authoritative_department = _guess_authoritative_department(conflict)
        suggested_resolution = (
            f"{authoritative_department} is usually the authoritative source for this type of finding. "
            "Keep both versions visible and escalate to clinician review before updating the fact graph."
            if authoritative_department
            else "Keep both versions visible and escalate to clinician review before updating the fact graph."
        )
        return conflict.model_copy(
            update={
                "authoritative_department": authoritative_department,
                "suggested_resolution": suggested_resolution,
            }
        )


def _default_prompt_path() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "conflict_analysis.txt"


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
                continue
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts).strip()
    return str(content)


def _extract_json_object(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _guess_authoritative_department(conflict: Conflict) -> str | None:
    combined_text = " ".join(
        filter(
            None,
            [
                conflict.entity.lower(),
                conflict.description.lower(),
                (conflict.fact_a.evidence or "").lower(),
                (conflict.fact_b.evidence or "").lower(),
            ],
        )
    )
    hints = {
        "radiology": {"ct", "mri", "pet", "scan", "imaging", "lesion", "mass", "effusion"},
        "pathology": {"biopsy", "histology", "pathology", "specimen", "tnm", "stage", "grade"},
        "palliative_care": {"pain", "nausea", "symptom", "comfort", "analgesic", "opioid"},
        "surgery": {"resection", "margin", "operative", "surgery", "anastomosis"},
        "oncology": {"chemotherapy", "oncology", "regimen", "cycle", "metastatic", "tumor"},
    }
    departments = [conflict.department_a, conflict.department_b]

    for department, keywords in hints.items():
        if any(keyword in combined_text for keyword in keywords) and department in departments:
            return department

    for department in ("pathology", "radiology", "oncology", "surgery", "palliative_care"):
        if department in departments:
            return department

    return departments[0] if departments else None
