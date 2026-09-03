"""Extraction run service: build the reproducibility manifest over current report versions,
dedupe by manifest_hash (idempotent), enqueue a run row for the worker to pick up.

Building the manifest uses the engine adapter (deterministic, no LLM call). The worker does
the actual extraction.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, NotFound
from app.db.models import ExtractionRun
from app.engine.adapter import get_engine
from app.engine.types import ReportInput
from app.services import reports as reports_svc
from app.services.patients import get_patient


def build_report_inputs(current_versions: list[dict]) -> list[ReportInput]:
    """Map current report versions to engine ReportInputs. source_report_id is a stable
    ``report_N`` ordinal so the manifest hash is reproducible."""
    inputs: list[ReportInput] = []
    for row in current_versions:
        report = row["report"]
        version = row["version"]
        ordinal = row["ordinal"]
        inputs.append(
            ReportInput(
                source_report_id=f"report_{ordinal}",
                text=version.text,
                chart_date=report.report_date,
                study_type=report.note_type or "RR",
                note_id=report.external_note_id or f"report_{ordinal}",
                report_version_id=str(version.id),
                text_sha256=version.text_sha256,
            )
        )
    return inputs


async def _extendable_parent(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    manifest: Any,
) -> ExtractionRun | None:
    """The most recent succeeded run whose reports are a strict subset of the current set.

    That is the run a new one *extends* rather than replaces: every report it covered is
    still here unchanged (matched on report_version_id, so an addendum creates a new
    version and correctly disqualifies the parent), and at least one report is new. When
    no such run exists — first run, or a report was edited or removed — the new run is a
    plain full run with no parent.
    """
    current_ids = {
        e.get("report_version_id") for e in manifest.report_manifest if e.get("report_version_id")
    }
    candidates = (
        await session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.org_id == org_id,
                ExtractionRun.patient_id == patient_id,
                ExtractionRun.status == "succeeded",
            )
            .order_by(ExtractionRun.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    for run in candidates:
        parent_ids = {
            e.get("report_version_id")
            for e in (run.report_manifest or [])
            if e.get("report_version_id")
        }
        if parent_ids and parent_ids < current_ids:
            return run
    return None


async def create_run(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    created_by: uuid.UUID,
) -> tuple[ExtractionRun, bool]:
    """Returns (run, created). If an identical succeeded run exists, returns it with
    created=False (idempotent).

    When the patient already has a succeeded run covering a subset of the current
    reports, the new run is marked ``incremental`` and points at it. That does not change
    what gets recorded — ``report_manifest`` still describes every report in the history,
    so the run stays independently reproducible from its manifest alone. What it changes
    is what the new run may reuse: the clinician's confirmations carry forward by track
    key (see ``services/carry_forward.py``) instead of being silently orphaned.
    """
    await get_patient(session, org_id=org_id, patient_id=patient_id)
    current_versions = await reports_svc.current_report_versions(
        session, org_id=org_id, patient_id=patient_id
    )
    if not current_versions:
        raise BadRequest("Patient has no reports to extract", code="no_reports")

    inputs = build_report_inputs(current_versions)
    manifest = get_engine().build_manifest(inputs)

    existing = (
        await session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.org_id == org_id,
                ExtractionRun.patient_id == patient_id,
                ExtractionRun.manifest_hash == manifest.manifest_hash,
                ExtractionRun.status == "succeeded",
            )
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    parent = await _extendable_parent(
        session, org_id=org_id, patient_id=patient_id, manifest=manifest
    )
    run = ExtractionRun(
        org_id=org_id,
        patient_id=patient_id,
        status="queued",
        parent_run_id=parent.id if parent else None,
        run_kind="incremental" if parent else "full",
        engine_git_sha=manifest.engine_git_sha,
        model_provider=manifest.model_provider,
        model_id=manifest.model_id,
        prompt_version=manifest.prompt_version,
        schema_version=manifest.schema_version,
        temperature=manifest.temperature,
        reasoning_effort=manifest.reasoning_effort,
        manifest_hash=manifest.manifest_hash,
        report_manifest=manifest.report_manifest,
        progress_total=len(inputs),
        progress_done=0,
        created_by=created_by,
    )
    session.add(run)
    await session.flush()
    return run, True


async def get_run(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> ExtractionRun:
    run = (
        await session.execute(
            select(ExtractionRun).where(
                ExtractionRun.id == run_id, ExtractionRun.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFound("Run not found")
    return run


async def list_runs(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[ExtractionRun]:
    rows = (
        await session.execute(
            select(ExtractionRun)
            .where(ExtractionRun.patient_id == patient_id, ExtractionRun.org_id == org_id)
            .order_by(ExtractionRun.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
