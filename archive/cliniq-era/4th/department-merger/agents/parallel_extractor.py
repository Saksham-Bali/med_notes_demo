from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

import httpx

from models.aligned_entity import ClinicalFact, DeptExtraction
from models.department_note import DepartmentNote


class ExtractionError(RuntimeError):
    """Raised when the SOAP extractor dependency cannot be reached or parsed."""


class SOAPExtractorClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def extract_all_departments(
        self,
        patient_id: str,
        department_notes: list[DepartmentNote],
    ) -> list[DeptExtraction]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            tasks = [
                self._extract_single_department(client, patient_id=patient_id, note=note)
                for note in department_notes
            ]
            return list(await asyncio.gather(*tasks))

    async def _extract_single_department(
        self,
        client: httpx.AsyncClient,
        patient_id: str,
        note: DepartmentNote,
    ) -> DeptExtraction:
        try:
            response = await client.post(
                f"{self.base_url}/api/v1/extract",
                json={
                    "text": note.text,
                    "patient_id": patient_id,
                    "department": note.department,
                    "document_date": note.date.isoformat(),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExtractionError(
                f"SOAP extractor request failed for department '{note.department}': {exc}"
            ) from exc

        payload = response.json()
        clinical_facts = payload.get("result", {}).get("clinical_facts", [])
        if not isinstance(clinical_facts, list):
            raise ExtractionError(
                f"SOAP extractor returned invalid clinical_facts for department '{note.department}'"
            )

        return DeptExtraction(
            dept=note.department,
            source_author=note.author,
            source_document_date=note.date,
            facts=self._coerce_facts(clinical_facts, note),
        )

    def _coerce_facts(
        self,
        raw_facts: list[dict[str, Any]],
        note: DepartmentNote,
    ) -> list[ClinicalFact]:
        facts: list[ClinicalFact] = []
        known_keys = {
            "entity",
            "fact",
            "name",
            "label",
            "term",
            "category",
            "type",
            "value",
            "observation",
            "status",
            "presence",
            "state",
            "negated",
            "is_negated",
            "radlex_id",
            "ontology_id",
            "evidence",
            "evidence_text",
            "confidence",
            "certainty",
            "date",
        }

        for raw_fact in raw_facts:
            if not isinstance(raw_fact, dict):
                continue

            entity = _to_string(
                raw_fact.get("entity")
                or raw_fact.get("name")
                or raw_fact.get("label")
                or raw_fact.get("term")
                or raw_fact.get("fact")
            )
            value = _to_string(raw_fact.get("value") or raw_fact.get("observation") or raw_fact.get("fact"))
            if not entity:
                entity = value
            if not entity:
                continue

            raw_confidence = raw_fact.get("confidence", raw_fact.get("certainty"))
            confidence = None
            if raw_confidence is not None:
                try:
                    confidence = float(raw_confidence)
                except (TypeError, ValueError):
                    confidence = None

            facts.append(
                ClinicalFact(
                    entity=entity,
                    category=_to_string(raw_fact.get("category") or raw_fact.get("type")),
                    value=value,
                    status=_to_string(raw_fact.get("status") or raw_fact.get("presence") or raw_fact.get("state")),
                    negated=_to_bool(raw_fact.get("negated", raw_fact.get("is_negated", False))),
                    radlex_id=_to_string(raw_fact.get("radlex_id") or raw_fact.get("ontology_id")),
                    evidence=_to_string(raw_fact.get("evidence") or raw_fact.get("evidence_text")),
                    confidence=confidence,
                    date=_parse_date(raw_fact.get("date")) or note.date,
                    source_department=note.department,
                    source_author=note.author,
                    source_document_date=note.date,
                    metadata={
                        key: value for key, value in raw_fact.items() if key not in known_keys
                    },
                )
            )

        return facts


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _to_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
