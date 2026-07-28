"""Tamper-evident ROI timing.

Review elapsed time is derived from the hash-chained, timestamped ``audit_log`` and the
``review_sessions`` instrumentation — never fabricated. The audit_log is append-only with a
per-org row-hash chain (ff.chain_audit trigger), so the timestamps that bound the elapsed
window are cryptographically attested: any edit to a bounding row breaks the chain.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, ReviewSession, Signoff


async def compute_timing(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> dict:
    """Measured review timing for a run/patient.

    - ``first_action_at``: earliest of the first run-scoped audit action and the first
      review-session start (whichever came first) — when the human review clock began.
    - ``signoff_at``: when the record was signed off (the latest sign-off for this run).
    - ``elapsed_seconds``: wall-clock from first action to sign-off (null until signed).
    - ``active_review_seconds``: summed active review time from ``review_sessions``.

    All values are read straight from the attested audit_log / review_sessions — no manual
    baseline is invented.
    """
    first_audit = (
        await session.execute(
            select(func.min(AuditLog.created_at)).where(
                AuditLog.org_id == org_id, AuditLog.entity_id == str(run_id)
            )
        )
    ).scalar_one_or_none()

    session_scope = or_(
        ReviewSession.run_id == run_id, ReviewSession.patient_id == patient_id
    )
    first_session = (
        await session.execute(
            select(func.min(ReviewSession.started_at)).where(
                ReviewSession.org_id == org_id, session_scope
            )
        )
    ).scalar_one_or_none()

    candidates = [t for t in (first_audit, first_session) if t is not None]
    first_action_at = min(candidates) if candidates else None

    signoff_at = (
        await session.execute(
            select(func.max(Signoff.signed_at)).where(
                Signoff.org_id == org_id, Signoff.run_id == run_id
            )
        )
    ).scalar_one_or_none()

    active_review_seconds = (
        await session.execute(
            select(func.coalesce(func.sum(ReviewSession.active_seconds), 0)).where(
                ReviewSession.org_id == org_id, session_scope
            )
        )
    ).scalar_one()

    elapsed_seconds: float | None = None
    if first_action_at is not None and signoff_at is not None:
        elapsed_seconds = (signoff_at - first_action_at).total_seconds()

    return {
        "first_action_at": first_action_at.isoformat() if first_action_at else None,
        "signoff_at": signoff_at.isoformat() if signoff_at else None,
        "elapsed_seconds": elapsed_seconds,
        "active_review_seconds": int(active_review_seconds or 0),
        "source": "hash-chained audit_log",
    }
