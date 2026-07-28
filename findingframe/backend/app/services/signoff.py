"""Hash-chained sign-off. The signed payload = run manifest + review deltas + link decisions
+ recist inputs. payload_sha256 = sha256(canonical(payload)); the chain links to the prior
sign-off for the same (org, patient)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnprocessableEntity
from app.db.models import (
    ExtractionRun,
    LinkDecision,
    RecistAssessment,
    Review,
    Signoff,
    TargetLesionSelection,
)
from app.services.patients import get_patient


async def _latest_succeeded_run(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> ExtractionRun | None:
    return (
        await session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.patient_id == patient_id,
                ExtractionRun.org_id == org_id,
                ExtractionRun.status == "succeeded",
            )
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_signoff(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    signed_by: uuid.UUID,
    run_id: uuid.UUID | None = None,
    scope: str = "patient",
) -> Signoff:
    await get_patient(session, org_id=org_id, patient_id=patient_id)

    if run_id is not None:
        run = (
            await session.execute(
                select(ExtractionRun).where(
                    ExtractionRun.id == run_id,
                    ExtractionRun.org_id == org_id,
                    ExtractionRun.patient_id == patient_id,
                )
            )
        ).scalar_one_or_none()
    else:
        run = await _latest_succeeded_run(session, org_id=org_id, patient_id=patient_id)
    if run is None:
        raise UnprocessableEntity(
            "No succeeded run to sign off for this patient", code="no_run_to_sign"
        )

    payload = await _build_payload(session, org_id=org_id, run=run)

    # payload_sha256, prev_signoff_sha256, row_sha256 are computed by the DB trigger
    # ff.chain_signoff() on INSERT — insert only the meaningful columns.
    row = Signoff(
        org_id=org_id,
        patient_id=patient_id,
        run_id=run.id,
        scope=scope,
        payload=payload,
        signed_by=signed_by,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)  # load trigger-computed hash columns
    return row


async def _build_payload(
    session: AsyncSession, *, org_id: uuid.UUID, run: ExtractionRun
) -> dict:
    reviews = (
        await session.execute(
            select(Review).where(Review.run_id == run.id, Review.org_id == org_id)
        )
    ).scalars().all()
    link_decisions = (
        await session.execute(
            select(LinkDecision).where(
                LinkDecision.run_id == run.id, LinkDecision.org_id == org_id
            )
        )
    ).scalars().all()
    target = (
        await session.execute(
            select(TargetLesionSelection)
            .where(
                TargetLesionSelection.run_id == run.id,
                TargetLesionSelection.org_id == org_id,
            )
            .order_by(TargetLesionSelection.selected_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    recist = (
        await session.execute(
            select(RecistAssessment)
            .where(RecistAssessment.run_id == run.id, RecistAssessment.org_id == org_id)
            .order_by(RecistAssessment.assessment_date)
        )
    ).scalars().all()

    return {
        "run": {
            "id": str(run.id),
            "manifest_hash": run.manifest_hash,
            "engine_git_sha": run.engine_git_sha,
            "model_provider": run.model_provider,
            "model_id": run.model_id,
            "prompt_version": run.prompt_version,
            "schema_version": run.schema_version,
            "report_manifest": run.report_manifest,
        },
        "review_deltas": [
            {
                "track_key": r.track_key,
                "link_correct": r.link_correct,
                "type_correct": r.type_correct,
                "progression_correct": r.progression_correct,
                "latest_status_correct": r.latest_status_correct,
                "false_merge": r.false_merge,
                "false_split": r.false_split,
                "evidence_valid": r.evidence_valid,
                "clinically_significant": r.clinically_significant,
                "correction_finding_type": r.correction_finding_type,
                "correction_anatomy": r.correction_anatomy,
                "correction_laterality": r.correction_laterality,
            }
            for r in reviews
        ],
        "link_decisions": [
            {
                "decision": d.decision,
                "primary_track_key": d.primary_track_key,
                "related_track_keys": d.related_track_keys,
                "resulting_track_key": d.resulting_track_key,
                "signature_sha256": d.signature_sha256,
            }
            for d in link_decisions
        ],
        "target_selection": {
            "selections": target.selections,
            "baseline_report_version_id": str(target.baseline_report_version_id)
            if target and target.baseline_report_version_id
            else None,
            "signature_sha256": target.signature_sha256,
        }
        if target
        else None,
        "recist": [
            {
                "assessment_date": a.assessment_date.isoformat(),
                "sld_mm": float(a.sld_mm) if a.sld_mm is not None else None,
                "classification": a.classification,
                "new_lesion": a.new_lesion,
            }
            for a in recist
        ],
    }


async def list_signoffs(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[Signoff]:
    rows = (
        await session.execute(
            select(Signoff)
            .where(Signoff.patient_id == patient_id, Signoff.org_id == org_id)
            .order_by(Signoff.signed_at)
        )
    ).scalars().all()
    return list(rows)
