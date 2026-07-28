"""Reviews service: append slot-level review feedback that pins a run and snapshots exactly
what the reviewer saw (reviewed_value). Production reviews are anchored
(model_output_visible=true) and are NOT blinded IRR annotations."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Review, Track
from app.services.runs import get_run


async def create_review(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    data: dict,
) -> Review:
    run = await get_run(session, org_id=org_id, run_id=run_id)
    track_key = data["track_key"]
    track_id = (
        await session.execute(
            select(Track.id).where(Track.run_id == run_id, Track.track_key == track_key)
        )
    ).scalar_one_or_none()

    review = Review(
        org_id=org_id,
        patient_id=run.patient_id,
        run_id=run_id,
        track_id=track_id,
        track_key=track_key,
        reviewer_id=reviewer_id,
        reviewed_value=data.get("reviewed_value") or {},
        link_correct=data.get("link_correct"),
        type_correct=data.get("type_correct"),
        progression_correct=data.get("progression_correct"),
        latest_status_correct=data.get("latest_status_correct"),
        false_merge=data.get("false_merge"),
        false_split=data.get("false_split"),
        evidence_valid=data.get("evidence_valid"),
        clinically_significant=data.get("clinically_significant"),
        correction_finding_type=data.get("correction_finding_type"),
        correction_anatomy=data.get("correction_anatomy"),
        correction_laterality=data.get("correction_laterality"),
        comment=data.get("comment"),
        model_output_visible=True,
    )
    session.add(review)
    await session.flush()
    return review


async def list_reviews(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> list[Review]:
    await get_run(session, org_id=org_id, run_id=run_id)
    rows = (
        await session.execute(
            select(Review)
            .where(Review.run_id == run_id, Review.org_id == org_id)
            .order_by(Review.created_at)
        )
    ).scalars().all()
    return list(rows)
