"""Extraction runs + digest, reviews, human-confirmed linking, RECIST, audit packet."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response

from app.api.v1.deps import CtxDep, ReviewerCtxDep, SessionDep
from app.core.crypto import canonical_json
from app.schemas.dto import (
    LinkDecisionCreate,
    LinkDecisionOut,
    ReviewCreate,
    ReviewOut,
    RunOut,
    TargetSelectionCreate,
    TargetSelectionOut,
)
from app.services import (
    audit,
    carry_forward,
    digest,
    export,
    linking,
    recist,
    reviews,
    runs,
)

router = APIRouter(tags=["runs"])


# --- runs lifecycle ---------------------------------------------------------
@router.post("/patients/{patient_id}/runs", response_model=RunOut)
async def create_run(patient_id: uuid.UUID, ctx: ReviewerCtxDep, session: SessionDep, response: Response):
    run, created = await runs.create_run(
        session, org_id=ctx.org_id, patient_id=patient_id, created_by=ctx.user.id
    )
    response.status_code = 201 if created else 200
    if created:
        await audit.record(
            session,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="run.enqueue",
            entity_type="run",
            entity_id=str(run.id),
            after={"manifest_hash": run.manifest_hash, "status": run.status},
        )
    return run


@router.get("/patients/{patient_id}/runs", response_model=list[RunOut])
async def list_runs(patient_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    return await runs.list_runs(session, org_id=ctx.org_id, patient_id=patient_id)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    return await runs.get_run(session, org_id=ctx.org_id, run_id=run_id)


# --- what one new report actually changed ------------------------------------
@router.get("/runs/{run_id}/delta")
async def run_delta(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    """What this run changed relative to the run it extends.

    Read-only. Reports which previously-confirmed lesion identities still stand, which
    gained evidence the reviewer should acknowledge, which must be re-confirmed, and what
    is new — plus the RECIST call before and after.
    """
    return await carry_forward.plan_carry_forward(session, org_id=ctx.org_id, run_id=run_id)


@router.post("/runs/{run_id}/carry-forward")
async def apply_carry_forward(
    run_id: uuid.UUID, ctx: ReviewerCtxDep, session: SessionDep
) -> dict:
    """Replay the parent run's still-valid confirmations onto this run.

    Only identities whose picture is unchanged are replayed, each marked with
    ``carried_from_run_id`` and keeping the original reviewer and timestamp. Anything
    re-opened or new is deliberately left for a human.
    """
    result = await carry_forward.apply_carry_forward(
        session, org_id=ctx.org_id, run_id=run_id, applied_by=ctx.user.id
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="run.carry_forward",
        entity_type="run",
        entity_id=str(run_id),
        after={
            "parent_run_id": result["parent_run_id"],
            "counts": result["counts"],
            "carried_link_decisions": result["carried_link_decisions"],
            "carried_target_selection": result["carried_target_selection"],
            "recist_call_before": result["recist_call_before"],
            "recist_call_after": result["recist_call_after"],
        },
    )
    return result


# --- digest -----------------------------------------------------------------
@router.get("/runs/{run_id}/digest")
async def get_digest(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    return await digest.build_digest(session, org_id=ctx.org_id, run_id=run_id)


# --- reviews ----------------------------------------------------------------
@router.post("/runs/{run_id}/reviews", response_model=ReviewOut, status_code=201)
async def create_review(
    run_id: uuid.UUID, body: ReviewCreate, ctx: ReviewerCtxDep, session: SessionDep
):
    review = await reviews.create_review(
        session, org_id=ctx.org_id, run_id=run_id, reviewer_id=ctx.user.id, data=body.model_dump()
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="review.create",
        entity_type="review",
        entity_id=str(review.id),
        after={"track_key": review.track_key},
    )
    return review


@router.get("/runs/{run_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    return await reviews.list_reviews(session, org_id=ctx.org_id, run_id=run_id)


# --- human-confirmed linking (R1) -------------------------------------------
@router.post("/runs/{run_id}/link-decisions", response_model=LinkDecisionOut, status_code=201)
async def create_link_decision(
    run_id: uuid.UUID, body: LinkDecisionCreate, ctx: ReviewerCtxDep, session: SessionDep
):
    decision = await linking.create_link_decision(
        session, org_id=ctx.org_id, run_id=run_id, decided_by=ctx.user.id, data=body.model_dump()
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="link_decision.create",
        entity_type="link_decision",
        entity_id=str(decision.id),
        after={"decision": decision.decision, "primary_track_key": decision.primary_track_key,
               "signature_sha256": decision.signature_sha256},
    )
    return decision


@router.get("/runs/{run_id}/link-decisions", response_model=list[LinkDecisionOut])
async def list_link_decisions(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    return await linking.list_link_decisions(session, org_id=ctx.org_id, run_id=run_id)


@router.get("/runs/{run_id}/confirmed-tracks")
async def confirmed_tracks(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    tracks = await linking.derive_confirmed_tracks(session, org_id=ctx.org_id, run_id=run_id)
    return {"run_id": str(run_id), "confirmed_tracks": tracks, "count": len(tracks)}


# --- RECIST (R1 — only over confirmed tracks) -------------------------------
@router.post("/runs/{run_id}/target-lesions", response_model=TargetSelectionOut, status_code=201)
async def select_targets(
    run_id: uuid.UUID, body: TargetSelectionCreate, ctx: ReviewerCtxDep, session: SessionDep
):
    row = await recist.create_target_selection(
        session,
        org_id=ctx.org_id,
        run_id=run_id,
        selected_by=ctx.user.id,
        baseline_report_version_id=body.baseline_report_version_id,
        selections=[s.model_dump() for s in body.selections],
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="target_selection.create",
        entity_type="target_selection",
        entity_id=str(row.id),
        after={"count": len(row.selections), "signature_sha256": row.signature_sha256},
    )
    return row


@router.post("/runs/{run_id}/recist")
async def compute_recist(run_id: uuid.UUID, ctx: ReviewerCtxDep, session: SessionDep) -> dict:
    result = await recist.compute_recist(session, org_id=ctx.org_id, run_id=run_id)
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="recist.compute",
        entity_type="run",
        entity_id=str(run_id),
        after={"assessments": len(result["assessments"])},
    )
    return result


@router.get("/runs/{run_id}/recist/contrast")
async def recist_contrast(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    """The money moment: naive (machine tracks as-is) vs confirmed (human merges applied)
    RECIST, side by side. Read-only; returns 200 even when there is no confirmed merge yet."""
    return await recist.compute_contrast(session, org_id=ctx.org_id, run_id=run_id)


@router.get("/runs/{run_id}/recist/progression")
async def recist_progression(run_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    """Disease trajectory for one run — per-lesion diameters over time, the SLD timeline,
    and the nadir the progression test is measured against. Read-only, persists nothing."""
    return await recist.progression(session, org_id=ctx.org_id, run_id=run_id)


# --- audit packet (demo centerpiece) ----------------------------------------
@router.get("/runs/{run_id}/audit-packet")
async def audit_packet(
    run_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
):
    packet = await export.build_audit_packet(session, org_id=ctx.org_id, run_id=run_id)
    if format == "csv":
        return Response(
            content=export.packet_to_csv(packet),
            media_type="text/csv",
            headers={"content-disposition": f'attachment; filename="audit_packet_{run_id}.csv"'},
        )
    if format == "pdf":
        return Response(
            content=export.packet_to_pdf(packet),
            media_type="application/pdf",
            headers={"content-disposition": f'attachment; filename="audit_packet_{run_id}.pdf"'},
        )
    return Response(content=canonical_json(packet), media_type="application/json")
