"""Patient service: create/list/get (org-scoped), PII encrypted with pgcrypto, DPDP erasure.

Direct identifiers live only in ff.patient_identifiers, encrypted at rest with
pgp_sym_encrypt(value, FF_PII_ENCRYPTION_KEY). The key is supplied by the app and never
stored in the DB. DPDP erasure = delete the identifiers row; clinical artifacts remain
pseudonymized under patients.subject_code.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import canonical_json
from app.core.errors import BadRequest, Conflict, NotFound
from app.db.models import ExtractionRun, Patient, PatientIdentifier, Report


async def create_patient(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    subject_code: str,
    cancer_type: str | None,
    identifiers: dict | None = None,
) -> Patient:
    existing = (
        await session.execute(
            select(Patient.id).where(
                Patient.org_id == org_id, Patient.subject_code == subject_code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"subject_code '{subject_code}' already exists in this org")

    patient = Patient(
        org_id=org_id,
        subject_code=subject_code,
        cancer_type=cancer_type,
        created_by=created_by,
    )
    session.add(patient)
    await session.flush()

    if identifiers:
        await _upsert_identifiers(
            session, org_id=org_id, patient_id=patient.id, created_by=created_by,
            identifiers=identifiers,
        )
    return patient


async def _upsert_identifiers(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    created_by: uuid.UUID,
    identifiers: dict,
) -> None:
    key = settings.pii_encryption_key
    if not key:
        raise BadRequest("PII encryption key is not configured", code="pii_key_missing")

    mrn = identifiers.get("mrn")
    name = identifiers.get("name")
    dob = identifiers.get("dob")
    extra = {k: v for k, v in identifiers.items() if k not in {"mrn", "name", "dob"}}
    extra_json = canonical_json(extra) if extra else None

    # pgp_sym_encrypt returns bytea; NULLs pass through untouched.
    await session.execute(
        text(
            """
            insert into ff.patient_identifiers
              (patient_id, org_id, mrn_enc, name_enc, dob_enc, extra_enc, created_by)
            values (
              :pid, :org,
              case when :mrn is null then null else pgp_sym_encrypt(:mrn, :key) end,
              case when :name is null then null else pgp_sym_encrypt(:name, :key) end,
              case when :dob is null then null else pgp_sym_encrypt(:dob, :key) end,
              case when :extra is null then null else pgp_sym_encrypt(:extra, :key) end,
              :created_by
            )
            on conflict (patient_id) do update set
              mrn_enc = excluded.mrn_enc,
              name_enc = excluded.name_enc,
              dob_enc = excluded.dob_enc,
              extra_enc = excluded.extra_enc,
              updated_at = now()
            """
        ),
        {
            "pid": patient_id,
            "org": org_id,
            "mrn": mrn,
            "name": name,
            "dob": dob,
            "extra": extra_json,
            "key": key,
            "created_by": created_by,
        },
    )


async def list_patients(session: AsyncSession, *, org_id: uuid.UUID) -> list[Patient]:
    rows = (
        await session.execute(
            select(Patient)
            .where(Patient.org_id == org_id)
            .order_by(Patient.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def list_patients_enriched(session: AsyncSession, *, org_id: uuid.UUID) -> list[dict]:
    """Patients with report_count + latest_run for the dashboard cards."""
    patients = await list_patients(session, org_id=org_id)
    counts = dict(
        (
            await session.execute(
                select(Report.patient_id, func.count(Report.id))
                .where(Report.org_id == org_id)
                .group_by(Report.patient_id)
            )
        ).all()
    )
    out: list[dict] = []
    for p in patients:
        latest_run = (
            await session.execute(
                select(ExtractionRun)
                .where(ExtractionRun.patient_id == p.id, ExtractionRun.org_id == org_id)
                .order_by(ExtractionRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append(
            {"patient": p, "report_count": int(counts.get(p.id, 0)), "latest_run": latest_run}
        )
    return out


async def get_patient(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> Patient:
    patient = (
        await session.execute(
            select(Patient).where(Patient.id == patient_id, Patient.org_id == org_id)
        )
    ).scalar_one_or_none()
    if patient is None:
        raise NotFound("Patient not found")
    return patient


async def get_patient_detail(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> dict:
    patient = await get_patient(session, org_id=org_id, patient_id=patient_id)
    report_count = (
        await session.execute(
            select(func.count(Report.id)).where(
                Report.patient_id == patient_id, Report.org_id == org_id
            )
        )
    ).scalar_one()
    latest_run = (
        await session.execute(
            select(ExtractionRun)
            .where(ExtractionRun.patient_id == patient_id, ExtractionRun.org_id == org_id)
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    has_identifiers = (
        await session.execute(
            select(PatientIdentifier.patient_id).where(
                PatientIdentifier.patient_id == patient_id
            )
        )
    ).scalar_one_or_none() is not None
    return {
        "patient": patient,
        "report_count": report_count,
        "latest_run": latest_run,
        "has_identifiers": has_identifiers,
    }


async def delete_identifiers(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> bool:
    """DPDP erasure: remove the PII row only. Returns True if a row was deleted."""
    await get_patient(session, org_id=org_id, patient_id=patient_id)  # 404 if not in org
    result = await session.execute(
        text(
            "delete from ff.patient_identifiers where patient_id = :pid and org_id = :org"
        ),
        {"pid": patient_id, "org": org_id},
    )
    return (result.rowcount or 0) > 0
