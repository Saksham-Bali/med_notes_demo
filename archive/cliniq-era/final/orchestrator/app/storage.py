from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .errors import SessionNotFoundError


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CounsellingSessionStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        patient_id: str,
        transcript_result: dict[str, Any],
        summarizer_result: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = f"csl-{uuid4().hex[:12]}"
        counselling_facts = []
        clinical_facts = []
        raw_counselling_facts = summarizer_result["result"].get("counselling_facts", [])
        raw_clinical_facts = summarizer_result["result"].get("clinical_facts", [])

        for index, fact in enumerate(raw_counselling_facts, start=1):
            fact_id = fact.get("id") or f"cf-{session_id}-{index}"
            counselling_facts.append({**fact, "id": fact_id})
            if index - 1 < len(raw_clinical_facts):
                clinical_facts.append({**raw_clinical_facts[index - 1], "id": fact_id})

        if len(raw_clinical_facts) > len(counselling_facts):
            for index, fact in enumerate(raw_clinical_facts[len(counselling_facts) :], start=len(counselling_facts) + 1):
                fact_id = fact.get("id") or f"cf-{session_id}-{index}"
                clinical_facts.append({**fact, "id": fact_id})

        raw_bullet_points = summarizer_result["result"].get("bullet_points", [])
        corrected_transcript = summarizer_result["result"].get("corrected_transcript", "")

        bullet_points = []
        for bp in raw_bullet_points:
            bp_id = bp.get("id") or f"bp-{session_id}-{len(bullet_points) + 1}"
            bullet_points.append({**bp, "id": bp_id})

        record = {
            "session_id": session_id,
            "patient_id": patient_id,
            "created_at": _utc_now().isoformat(),
            "transcription_result": transcript_result,
            "corrected_transcript": corrected_transcript,
            "session_summary": summarizer_result["result"].get("session_summary"),
            "counselling_facts": counselling_facts,
            "clinical_facts": clinical_facts,
            "bullet_points": bullet_points,
            "stats": summarizer_result["result"].get("stats", {}),
        }
        self._write(session_id, record)
        return record

    def get(self, session_id: str) -> dict[str, Any]:
        path = self.root / f"{session_id}.json"
        if not path.exists():
            raise SessionNotFoundError(session_id)
        return json.loads(path.read_text())

    def mark_approved(
        self,
        session_id: str,
        approved_fact_ids: list[str],
        approved_bullet_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        record = self.get(session_id)
        record["approved_fact_ids"] = approved_fact_ids
        record["approved_bullet_ids"] = approved_bullet_ids or []
        record["approved_at"] = _utc_now().isoformat()
        self._write(session_id, record)
        return record

    def _write(self, session_id: str, record: dict[str, Any]) -> None:
        (self.root / f"{session_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True))


class DeferredJobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        dependency: str,
        job_type: str,
        patient_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        job_id = f"job-{uuid4().hex[:12]}"
        record = {
            "job_id": job_id,
            "dependency": dependency,
            "job_type": job_type,
            "patient_id": patient_id,
            "status": "pending",
            "created_at": _utc_now().isoformat(),
            "payload": payload,
        }
        (self.root / f"{job_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True))
        return record
