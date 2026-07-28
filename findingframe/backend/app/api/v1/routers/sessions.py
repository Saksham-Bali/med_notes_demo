"""Review-session instrumentation (time-saved ROI)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.v1.deps import ReviewerCtxDep, SessionDep
from app.schemas.dto import SessionEnd, SessionOut, SessionStart
from app.services import sessions

router = APIRouter(tags=["review-sessions"])


@router.post("/review-sessions", response_model=SessionOut, status_code=201)
async def start_session(body: SessionStart, ctx: ReviewerCtxDep, session: SessionDep):
    return await sessions.start_session(
        session,
        org_id=ctx.org_id,
        patient_id=body.patient_id,
        reviewer_id=ctx.user.id,
        run_id=body.run_id,
    )


@router.patch("/review-sessions/{session_id}", response_model=SessionOut)
async def end_session(
    session_id: uuid.UUID, body: SessionEnd, ctx: ReviewerCtxDep, session: SessionDep
):
    return await sessions.end_session(
        session,
        org_id=ctx.org_id,
        session_id=session_id,
        active_seconds=body.active_seconds,
        tracks_reviewed=body.tracks_reviewed,
    )
