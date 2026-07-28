"""Inter-rater reliability (IRR / Cohen's kappa) pilot API — the blinded 2-reader clinician
validation described in docs/IRR_PROTOCOL.md.

Org-scoped + role-gated; every mutation writes an audit_log row. Task/assignment/adjudication
management requires an admin or reviewer role; reader endpoints (mine / items / records) are
available to any org member but a reader may only see and write their OWN assignment.

BLINDING INVARIANT: GET /irr/assignments/{id}/items never returns the model's slot values for
the assignment's items (see app.services.irr.blinded_frame_item).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.v1.deps import CtxDep, ReviewerCtxDep, SessionDep
from app.schemas.dto import (
    IrrAdjudicationCreate,
    IrrAssignmentCreate,
    IrrRecordCreate,
    IrrTaskCreate,
    IrrTaskOut,
)
from app.services import audit, irr

router = APIRouter(prefix="/irr", tags=["irr"])


# --- tasks ------------------------------------------------------------------
@router.post("/tasks", response_model=IrrTaskOut, status_code=201)
async def create_task(body: IrrTaskCreate, ctx: ReviewerCtxDep, session: SessionDep):
    task = await irr.create_task(
        session,
        org_id=ctx.org_id,
        created_by=ctx.user.id,
        name=body.name,
        protocol_id=body.protocol_id,
        unit_of_agreement=body.unit_of_agreement,
        run_id=body.run_id,
        description=body.description,
        sample_size=body.sample_size,
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="irr_task.create",
        entity_type="annotation_task",
        entity_id=task["id"],
        after={"name": task["name"], "unit_of_agreement": task["unit_of_agreement"],
               "run_id": task["run_id"], "n_items": task["n_items"]},
    )
    return task


@router.get("/tasks", response_model=list[IrrTaskOut])
async def list_tasks(ctx: CtxDep, session: SessionDep):
    return await irr.list_tasks(session, org_id=ctx.org_id)


@router.get("/tasks/{task_id}", response_model=IrrTaskOut)
async def get_task(task_id: uuid.UUID, ctx: CtxDep, session: SessionDep):
    return await irr.get_task(session, org_id=ctx.org_id, task_id=task_id)


# --- assignments ------------------------------------------------------------
@router.post("/tasks/{task_id}/assignments", status_code=201)
async def create_assignment(
    task_id: uuid.UUID, body: IrrAssignmentCreate, ctx: ReviewerCtxDep, session: SessionDep
) -> dict:
    assignment = await irr.create_assignment(
        session,
        org_id=ctx.org_id,
        task_id=task_id,
        annotator_id=body.annotator_id,
        independence_group=body.independence_group,
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="irr_assignment.create",
        entity_type="annotation_assignment",
        entity_id=assignment["id"],
        after={"task_id": str(task_id), "annotator_id": assignment["annotator_id"],
               "independence_group": assignment["independence_group"],
               "model_output_visible": False},
    )
    return assignment


@router.get("/assignments/mine")
async def my_assignments(ctx: CtxDep, session: SessionDep) -> dict:
    rows = await irr.list_my_assignments(session, org_id=ctx.org_id, user_id=ctx.user.id)
    return {"assignments": rows, "count": len(rows)}


@router.get("/assignments/{assignment_id}/items")
async def assignment_items(assignment_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    return await irr.assignment_items(
        session,
        org_id=ctx.org_id,
        assignment_id=assignment_id,
        caller_id=ctx.user.id,
        caller_is_admin=ctx.role == "admin",
    )


@router.post("/assignments/{assignment_id}/records", status_code=201)
async def create_record(
    assignment_id: uuid.UUID, body: IrrRecordCreate, ctx: CtxDep, session: SessionDep
) -> dict:
    record = await irr.create_record(
        session,
        org_id=ctx.org_id,
        assignment_id=assignment_id,
        caller_id=ctx.user.id,
        item_ref=body.item_ref,
        labels=body.labels,
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="irr_record.create",
        entity_type="annotation_record",
        entity_id=record["id"],
        after={"assignment_id": record["assignment_id"], "item_ref": record["item_ref"],
               "slots": sorted(record["labels"].keys())},
    )
    return record


# --- kappa + disagreements + adjudication -----------------------------------
@router.get("/tasks/{task_id}/kappa")
async def task_kappa(task_id: uuid.UUID, ctx: CtxDep, session: SessionDep) -> dict:
    return await irr.compute_kappa(session, org_id=ctx.org_id, task_id=task_id)


@router.get("/tasks/{task_id}/disagreements")
async def task_disagreements(task_id: uuid.UUID, ctx: ReviewerCtxDep, session: SessionDep) -> dict:
    return await irr.disagreements(session, org_id=ctx.org_id, task_id=task_id)


@router.post("/tasks/{task_id}/adjudications", status_code=201)
async def create_adjudication(
    task_id: uuid.UUID, body: IrrAdjudicationCreate, ctx: ReviewerCtxDep, session: SessionDep
) -> dict:
    adj = await irr.create_adjudication(
        session,
        org_id=ctx.org_id,
        task_id=task_id,
        adjudicator_id=ctx.user.id,
        item_ref=body.item_ref,
        resolves_assignment_ids=body.resolves_assignment_ids,
        consensus=body.consensus,
        emit_gold=body.emit_gold,
    )
    await audit.record(
        session,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="irr_adjudication.create",
        entity_type="adjudication",
        entity_id=adj["id"],
        after={"task_id": str(task_id), "item_ref": adj["item_ref"],
               "gold_candidate_id": adj["gold_candidate_id"]},
    )
    return adj
