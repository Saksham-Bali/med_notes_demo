"""Patients + PII erasure + patient-scoped sign-off and audit."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.api.v1.deps import CtxDep, ReviewerCtxDep, SessionDep
from app.schemas.dto import (
    AuditOut,
    PatientCreate,
    PatientDetailOut,
    PatientListItemOut,
    PatientOut,
    RunBrief,
    SignoffCreate,
    SignoffOut,
)
from app.services import audit, export, patients, signoff

router = APIRouter(tags=["patients"])


@router.post("/patients", response_model=PatientOut, status_code=201)
async def create_patient(body: PatientCreate, ctx: ReviewerCtxDep, session: SessionDep):
    identifiers = body.identifiers.model_dump(exclude_none=True) if body.identifiers else None
    patient = await patients.create_patient(
        session,
        org_id=ctx.org_id,
        created_by=ctx.user.id,
        subject_code=body.subject_code,
        cancer_type=body.cancer_type,
        identifiers=identifiers,
    )
    # DPDP: never log plaintext identifiers; record only which fields were present.
    id_meta = (
        {"present": True, "fields": sorted(identifiers.keys())} if identifiers else {"present": False}
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="patient.create",
        entity_type="patient",
        entity_id=str(patient.id),
        after={"subject_code": patient.subject_code, "cancer_type": patient.cancer_type,
               "identifiers": id_meta},
    )
    return patient


@router.get("/patients", response_model=list[PatientListItemOut])
async def list_patients(ctx: CtxDep, session: SessionDep):
    rows = await patients.list_patients_enriched(session, org_id=ctx.org_id)
    return [
        PatientListItemOut(
            **PatientOut.model_validate(r["patient"]).model_dump(),
            report_count=r["report_count"],
            latest_run=RunBrief.model_validate(r["latest_run"]) if r["latest_run"] else None,
        )
        for r in rows
    ]


@router.get("/patients/{patient_id}", response_model=PatientDetailOut)
async def get_patient(patient_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    detail = await patients.get_patient_detail(
        session, org_id=ctx.org_id, patient_id=patient_id
    )
    return PatientDetailOut(
        patient=PatientOut.model_validate(detail["patient"]),
        report_count=detail["report_count"],
        has_identifiers=detail["has_identifiers"],
        latest_run=RunBrief.model_validate(detail["latest_run"]) if detail["latest_run"] else None,
    )


@router.delete("/patients/{patient_id}/identifiers", status_code=204)
async def delete_identifiers(patient_id: uuid.UUID, ctx: ReviewerCtxDep, session: SessionDep):
    deleted = await patients.delete_identifiers(
        session, org_id=ctx.org_id, patient_id=patient_id
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="patient.identifiers.delete",
        entity_type="patient",
        entity_id=str(patient_id),
        after={"deleted": deleted, "reason": "dpdp_erasure"},
    )
    return Response(status_code=204)


@router.post("/patients/{patient_id}/signoff", response_model=SignoffOut, status_code=201)
async def create_signoff(
    patient_id: uuid.UUID, body: SignoffCreate, ctx: ReviewerCtxDep, session: SessionDep
):
    row = await signoff.create_signoff(
        session,
        org_id=ctx.org_id,
        patient_id=patient_id,
        signed_by=ctx.user.id,
        run_id=body.run_id,
        scope=body.scope,
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="signoff.create",
        entity_type="signoff",
        entity_id=str(row.id),
        after={"payload_sha256": row.payload_sha256, "run_id": str(row.run_id)},
    )
    return row


@router.get("/patients/{patient_id}/audit", response_model=list[AuditOut])
async def patient_audit(patient_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    # org-scoped audit; ensure the patient belongs to the org first.
    await patients.get_patient(session, org_id=ctx.org_id, patient_id=patient_id)
    return await export.list_audit(session, org_id=ctx.org_id)
