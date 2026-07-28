"""Reports service: create reports + versioned report_versions (text_sha256).

Radiology addenda are routine, so reports are versioned. An item whose external_note_id
matches an existing report for the patient becomes a new version (addendum) on that report;
otherwise a new report + version 1 is created.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import sha256_hex
from app.db.models import Report, ReportVersion
from app.services.patients import get_patient


async def add_reports(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    created_by: uuid.UUID,
    items: list[dict],
) -> list[dict]:
    await get_patient(session, org_id=org_id, patient_id=patient_id)  # 404 if not in org
    created: list[dict] = []
    for item in items:
        report, version = await _add_one(
            session,
            org_id=org_id,
            patient_id=patient_id,
            created_by=created_by,
            item=item,
        )
        created.append({"report": report, "version": version})
    return created


async def _add_one(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    created_by: uuid.UUID,
    item: dict,
) -> tuple[Report, ReportVersion]:
    external_note_id = item.get("external_note_id")
    text_body = item["text"]
    digest = sha256_hex(text_body)

    report: Report | None = None
    if external_note_id:
        report = (
            await session.execute(
                select(Report).where(
                    Report.patient_id == patient_id,
                    Report.org_id == org_id,
                    Report.external_note_id == external_note_id,
                )
            )
        ).scalar_one_or_none()

    is_addendum = report is not None
    if report is None:
        report = Report(
            org_id=org_id,
            patient_id=patient_id,
            report_date=item["report_date"],
            note_type=item.get("note_type") or "RR",
            external_note_id=external_note_id,
            created_by=created_by,
        )
        session.add(report)
        await session.flush()

    next_version = (
        await session.execute(
            select(func.coalesce(func.max(ReportVersion.version_no), 0)).where(
                ReportVersion.report_id == report.id
            )
        )
    ).scalar_one() + 1

    version = ReportVersion(
        report_id=report.id,
        org_id=org_id,
        version_no=next_version,
        text=text_body,
        text_sha256=digest,
        is_addendum=is_addendum,
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return report, version


async def list_reports(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[dict]:
    """Reports with their current (highest version_no) version."""
    await get_patient(session, org_id=org_id, patient_id=patient_id)
    reports = (
        await session.execute(
            select(Report)
            .where(Report.patient_id == patient_id, Report.org_id == org_id)
            .order_by(Report.report_date)
        )
    ).scalars().all()

    out: list[dict] = []
    for report in reports:
        current = await current_version(session, report.id)
        out.append({"report": report, "current_version": current})
    return out


async def current_version(session: AsyncSession, report_id: uuid.UUID) -> ReportVersion | None:
    return (
        await session.execute(
            select(ReportVersion)
            .where(ReportVersion.report_id == report_id)
            .order_by(ReportVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def current_report_versions(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[dict]:
    """The current version of every report for a patient, ordered by report_date — the
    input set for an extraction run."""
    reports = (
        await session.execute(
            select(Report)
            .where(Report.patient_id == patient_id, Report.org_id == org_id)
            .order_by(Report.report_date)
        )
    ).scalars().all()
    out: list[dict] = []
    for idx, report in enumerate(reports, start=1):
        version = await current_version(session, report.id)
        if version is None:
            continue
        out.append({"report": report, "version": version, "ordinal": idx})
    return out
