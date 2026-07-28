"""Org-scoped analytics aggregates for the FindingFrame dashboard.

Every query in this module is filtered by ``org_id`` — the backend connects to Postgres as
the superuser (the tenant boundary), so org scoping is enforced here in the service layer,
never by RLS. The numbers are read straight from the durable clinical tables (frames,
tracks, extraction_runs, recist_assessments, reviews, review_sessions) and the
hash-chained audit trail; nothing is fabricated.

Shapes (all under ``/api/v1/analytics``):
  - overview            KPI counters for the org (patients, runs, gate-failed rate, ...)
  - recist_distribution PD/SD/PR/CR/NE counts over recist_assessments + per-run best-overall
  - review_throughput   attested review time, tracks reviewed, correction rate, leaderboard
  - agreement           best-effort IRR summary if any annotation data exists, else unavailable
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ExtractionRun,
    Frame,
    Patient,
    RecistAssessment,
    Report,
    Review,
    ReviewSession,
    Track,
    Profile,
)
from app.services.recist import best_overall

# The RECIST classes we always surface (so the UI can render a stable set of buckets even
# when a class has zero rows).
RECIST_CLASSES = ("CR", "PR", "SD", "PD", "NE")

# Slot-correctness booleans on ff.reviews: False means the model got that slot wrong, i.e. a
# human correction was needed. false_merge / false_split flag a linking error.
_CORRECTNESS_SLOTS = (
    Review.link_correct,
    Review.type_correct,
    Review.progression_correct,
    Review.latest_status_correct,
    Review.evidence_valid,
)


async def overview(session: AsyncSession, *, org_id: uuid.UUID) -> dict:
    """Top-line KPI counters for an org."""
    patients = (
        await session.execute(
            select(func.count(Patient.id)).where(Patient.org_id == org_id)
        )
    ).scalar_one()

    runs = (
        await session.execute(
            select(func.count(ExtractionRun.id)).where(ExtractionRun.org_id == org_id)
        )
    ).scalar_one()

    status_rows = (
        await session.execute(
            select(ExtractionRun.status, func.count(ExtractionRun.id))
            .where(ExtractionRun.org_id == org_id)
            .group_by(ExtractionRun.status)
        )
    ).all()
    runs_by_status = {status: count for status, count in status_rows}

    frames_total = (
        await session.execute(
            select(func.count(Frame.id)).where(Frame.org_id == org_id)
        )
    ).scalar_one()

    frames_gate_failed = (
        await session.execute(
            select(func.count(Frame.id)).where(
                Frame.org_id == org_id, Frame.evidence_verified.is_(False)
            )
        )
    ).scalar_one()

    tracks_total = (
        await session.execute(
            select(func.count(Track.id)).where(Track.org_id == org_id)
        )
    ).scalar_one()

    reports_total = (
        await session.execute(
            select(func.count(Report.id)).where(Report.org_id == org_id)
        )
    ).scalar_one()

    gate_failed_rate = (frames_gate_failed / frames_total) if frames_total else 0.0
    avg_reports_per_patient = (reports_total / patients) if patients else 0.0

    return {
        "patients": patients,
        "runs": runs,
        "runs_by_status": runs_by_status,
        "frames_total": frames_total,
        "frames_gate_failed": frames_gate_failed,
        "tracks_total": tracks_total,
        "reports_total": reports_total,
        "gate_failed_rate": round(gate_failed_rate, 4),
        "avg_reports_per_patient": round(avg_reports_per_patient, 2),
    }


async def recist_distribution(session: AsyncSession, *, org_id: uuid.UUID) -> dict:
    """PD/SD/PR/CR/NE distribution over persisted RECIST assessments (per-timepoint), plus a
    per-run best-overall-response distribution (progression trumps, else best achieved)."""
    rows = (
        await session.execute(
            select(RecistAssessment.classification, func.count(RecistAssessment.id))
            .where(RecistAssessment.org_id == org_id)
            .group_by(RecistAssessment.classification)
        )
    ).all()
    by_assessment = {cls: 0 for cls in RECIST_CLASSES}
    total_assessments = 0
    for cls, count in rows:
        total_assessments += count
        if cls in by_assessment:
            by_assessment[cls] += count
        else:  # tolerate any unexpected enum value without dropping it
            by_assessment[cls] = count

    # Per-run best overall response: fold each run's timepoint classifications into one call.
    run_rows = (
        await session.execute(
            select(RecistAssessment.run_id, RecistAssessment.classification)
            .where(RecistAssessment.org_id == org_id)
            .order_by(RecistAssessment.run_id, RecistAssessment.assessment_date)
        )
    ).all()
    per_run: dict[uuid.UUID, list[str]] = {}
    for run_id, cls in run_rows:
        per_run.setdefault(run_id, []).append(cls or "NE")
    by_run_best_overall = {cls: 0 for cls in RECIST_CLASSES}
    for classes in per_run.values():
        bor = best_overall(classes)
        by_run_best_overall[bor] = by_run_best_overall.get(bor, 0) + 1

    return {
        "by_assessment": by_assessment,
        "total_assessments": total_assessments,
        "by_run_best_overall": by_run_best_overall,
        "runs_assessed": len(per_run),
    }


async def review_throughput(session: AsyncSession, *, org_id: uuid.UUID) -> dict:
    """Attested review timing + correction rate + reviewer leaderboard, org-scoped.

    Review time comes from the ``review_sessions`` instrumentation (active_seconds); the
    correction rate comes from the slot-correctness booleans on ``reviews``.
    """
    # --- session-derived timing (per attested review session) ---
    session_agg = (
        await session.execute(
            select(
                func.coalesce(func.sum(ReviewSession.active_seconds), 0),
                func.coalesce(func.sum(ReviewSession.tracks_reviewed), 0),
                func.count(ReviewSession.id),
                func.count(func.distinct(ReviewSession.patient_id)),
            ).where(ReviewSession.org_id == org_id)
        )
    ).one()
    total_active_seconds, tracks_reviewed_sessions, session_count, patients_reviewed = session_agg

    avg_review_seconds_per_patient = (
        (total_active_seconds / patients_reviewed) if patients_reviewed else 0.0
    )
    avg_review_seconds_per_session = (
        (total_active_seconds / session_count) if session_count else 0.0
    )

    # --- correction rate from reviews slot-correctness bools ---
    # A review "needed a correction" if any correctness slot is explicitly False, or a
    # false_merge / false_split linking error was flagged.
    needs_correction = or_(
        *[slot.is_(False) for slot in _CORRECTNESS_SLOTS],
        Review.false_merge.is_(True),
        Review.false_split.is_(True),
    )
    review_agg = (
        await session.execute(
            select(
                func.count(Review.id),
                func.coalesce(
                    func.sum(case((needs_correction, 1), else_=0)), 0
                ),
            ).where(Review.org_id == org_id)
        )
    ).one()
    reviews_total, corrections = review_agg
    correction_rate = (corrections / reviews_total) if reviews_total else 0.0

    # --- reviewer leaderboard: reviews + corrections per reviewer, joined to profile name ---
    leaderboard_rows = (
        await session.execute(
            select(
                Review.reviewer_id,
                Profile.full_name,
                func.count(Review.id),
                func.coalesce(func.sum(case((needs_correction, 1), else_=0)), 0),
            )
            .select_from(Review)
            .outerjoin(Profile, Profile.id == Review.reviewer_id)
            .where(Review.org_id == org_id)
            .group_by(Review.reviewer_id, Profile.full_name)
            .order_by(func.count(Review.id).desc())
        )
    ).all()

    # Active review seconds per reviewer (from sessions), to enrich the leaderboard.
    reviewer_seconds_rows = (
        await session.execute(
            select(
                ReviewSession.reviewer_id,
                func.coalesce(func.sum(ReviewSession.active_seconds), 0),
                func.coalesce(func.sum(ReviewSession.tracks_reviewed), 0),
            )
            .where(ReviewSession.org_id == org_id)
            .group_by(ReviewSession.reviewer_id)
        )
    ).all()
    seconds_by_reviewer = {
        rid: {"active_seconds": secs, "tracks_reviewed": tr}
        for rid, secs, tr in reviewer_seconds_rows
    }

    leaderboard = []
    for reviewer_id, full_name, count, corr in leaderboard_rows:
        extra = seconds_by_reviewer.get(reviewer_id, {})
        leaderboard.append(
            {
                "reviewer_id": str(reviewer_id),
                "name": full_name or "Unknown reviewer",
                "reviews": count,
                "corrections": corr,
                "correction_rate": round((corr / count) if count else 0.0, 4),
                "active_seconds": extra.get("active_seconds", 0),
                "tracks_reviewed": extra.get("tracks_reviewed", 0),
            }
        )

    return {
        "reviews_total": reviews_total,
        "corrections": corrections,
        "correction_rate": round(correction_rate, 4),
        "tracks_reviewed": tracks_reviewed_sessions,
        "review_sessions": session_count,
        "patients_reviewed": patients_reviewed,
        "total_active_review_seconds": int(total_active_seconds or 0),
        "avg_review_seconds_per_patient": round(avg_review_seconds_per_patient, 1),
        "avg_review_seconds_per_session": round(avg_review_seconds_per_session, 1),
        "reviewer_leaderboard": leaderboard,
        "source": "review_sessions + reviews (attested)",
    }


async def agreement(session: AsyncSession, *, org_id: uuid.UUID) -> dict:
    """Best-effort inter-rater agreement summary. The annotation tables have no ORM models
    (they are IRR-only), so we probe them with org-scoped raw SQL. When no annotation data
    exists yet, return ``{available: False}`` so the UI can render an honest empty state."""
    counts: dict[str, int] = {}
    for label, table in (
        ("tasks", "annotation_tasks"),
        ("assignments", "annotation_assignments"),
        ("records", "annotation_records"),
        ("adjudications", "adjudications"),
        ("gold_candidates", "gold_candidates"),
    ):
        try:
            n = (
                await session.execute(
                    text(f"select count(*) from ff.{table} where org_id = :org"),
                    {"org": org_id},
                )
            ).scalar_one()
        except Exception:  # noqa: BLE001 - table missing / not readable -> treat as none
            n = 0
        counts[label] = int(n or 0)

    if counts.get("records", 0) == 0:
        return {
            "available": False,
            "reason": (
                "No blinded annotation data for this org yet. Inter-rater agreement becomes "
                "available once annotators submit independent labels for an annotation task."
            ),
            "counts": counts,
        }

    # Records exist: summarize coverage. A full kappa needs paired labels per item across
    # independent annotators; we surface the coverage and how many items reached adjudicated
    # consensus, which is the honest best-effort signal at this stage.
    items_with_records = (
        await session.execute(
            text(
                "select count(distinct r.item_ref) from ff.annotation_records r "
                "where r.org_id = :org"
            ),
            {"org": org_id},
        )
    ).scalar_one()
    return {
        "available": True,
        "counts": counts,
        "items_annotated": int(items_with_records or 0),
        "items_adjudicated": counts.get("adjudications", 0),
        "note": (
            "Coverage summary only. A blinded kappa/alpha score requires >=2 independent "
            "annotators per item; showing annotation volume and adjudicated consensus."
        ),
    }
