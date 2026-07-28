"""Reports (versioned) under a patient."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.v1.deps import CtxDep, ReviewerCtxDep, SessionDep
from app.schemas.dto import (
    ReportCreatedOut,
    ReportItemIn,
    ReportOut,
    ReportVersionOut,
    ReportWithVersionOut,
)
from app.services import audit, reports

router = APIRouter(tags=["reports"])


@router.post("/patients/{patient_id}/reports", response_model=list[ReportCreatedOut], status_code=201)
async def add_reports(
    patient_id: uuid.UUID,
    body: ReportItemIn | list[ReportItemIn],
    ctx: ReviewerCtxDep,
    session: SessionDep,
):
    items = body if isinstance(body, list) else [body]
    created = await reports.add_reports(
        session,
        org_id=ctx.org_id,
        patient_id=patient_id,
        created_by=ctx.user.id,
        items=[i.model_dump() for i in items],
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="report.create",
        entity_type="patient",
        entity_id=str(patient_id),
        after={"count": len(created),
               "report_ids": [str(c["report"].id) for c in created]},
    )
    return [
        ReportCreatedOut(
            report=ReportOut.model_validate(c["report"]),
            version=ReportVersionOut.model_validate(c["version"]),
        )
        for c in created
    ]


@router.get("/patients/{patient_id}/reports", response_model=list[ReportWithVersionOut])
async def list_reports(patient_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    rows = await reports.list_reports(session, org_id=ctx.org_id, patient_id=patient_id)
    return [
        ReportWithVersionOut(
            report=ReportOut.model_validate(r["report"]),
            current_version=ReportVersionOut.model_validate(r["current_version"])
            if r["current_version"]
            else None,
        )
        for r in rows
    ]
