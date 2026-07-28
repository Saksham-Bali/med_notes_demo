"""Review-session instrumentation (time-saved ROI): start a session, end it with
active_seconds + tracks_reviewed."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.db.models import ReviewSession
from app.services.patients import get_patient


async def start_session(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
) -> ReviewSession:
    await get_patient(session, org_id=org_id, patient_id=patient_id)
    row = ReviewSession(
        org_id=org_id,
        patient_id=patient_id,
        run_id=run_id,
        reviewer_id=reviewer_id,
    )
    session.add(row)
    await session.flush()
    return row


async def end_session(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
    active_seconds: int | None,
    tracks_reviewed: int | None,
) -> ReviewSession:
    row = (
        await session.execute(
            select(ReviewSession).where(
                ReviewSession.id == session_id, ReviewSession.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("Review session not found")
    row.ended_at = dt.datetime.now(dt.timezone.utc)
    if active_seconds is not None:
        row.active_seconds = active_seconds
    if tracks_reviewed is not None:
        row.tracks_reviewed = tracks_reviewed
    await session.flush()
    return row
