"""Clinician digest built from persisted frames/tracks for a run.

Sections group confirmed-machine tracks by clinical_section. Every event carries its verbatim
evidence sentence plus the full source report text (click-through). Gate-failed frames
(evidence_verified=false) are collected into a mandatory-review ``gate_failed`` list and are
NEVER silently folded into the sections.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Frame, ReportVersion, Track, TrackEvent
from app.services.runs import get_run

SECTION_ORDER = ["needs_attention", "stable", "resolved", "uncertain", "routine_negatives"]


def normalize_section(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in SECTION_ORDER:
        return v
    # tolerate engine/humans labels like "needs attention" / "routine negatives"
    v = v.replace(" ", "_").replace("/", "_")
    if v in SECTION_ORDER:
        return v
    if "attention" in v:
        return "needs_attention"
    if "resolved" in v or "improved" in v:
        return "resolved"
    if "negative" in v:
        return "routine_negatives"
    if "stable" in v or "present" in v:
        return "stable"
    return "uncertain"


async def build_digest(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict:
    run = await get_run(session, org_id=org_id, run_id=run_id)

    tracks = (
        await session.execute(
            select(Track).where(Track.run_id == run_id, Track.org_id == org_id)
        )
    ).scalars().all()
    frames = (
        await session.execute(
            select(Frame).where(Frame.run_id == run_id, Frame.org_id == org_id)
        )
    ).scalars().all()
    events = (
        await session.execute(
            select(TrackEvent)
            .join(Track, Track.id == TrackEvent.track_id)
            .where(Track.run_id == run_id, Track.org_id == org_id)
            .order_by(TrackEvent.event_date)
        )
    ).scalars().all()

    # Batch-load report full texts for click-through.
    version_ids = {
        e.report_version_id for e in events if e.report_version_id is not None
    } | {f.report_version_id for f in frames if f.report_version_id is not None}
    full_texts = await _load_full_texts(session, version_ids)

    events_by_track: dict[uuid.UUID, list[TrackEvent]] = {}
    for e in events:
        events_by_track.setdefault(e.track_id, []).append(e)

    sections: dict[str, list[dict]] = {s: [] for s in SECTION_ORDER}
    for track in tracks:
        section = normalize_section(track.clinical_section)
        sections[section].append(
            _track_view(track, events_by_track.get(track.id, []), full_texts)
        )

    gate_failed = [
        _gate_failed_view(f, full_texts) for f in frames if not f.evidence_verified
    ]

    return {
        "run_id": str(run_id),
        "patient_id": str(run.patient_id),
        "status": run.status,
        "sections": sections,
        "section_order": SECTION_ORDER,
        "counts": {s: len(sections[s]) for s in SECTION_ORDER},
        "gate_failed": gate_failed,
        "gate_failed_count": len(gate_failed),
        "unresolved_link_count": sum(1 for t in tracks if t.unresolved_link),
        "false_split_candidate_count": sum(1 for t in tracks if t.false_split_candidate),
        "track_count": len(tracks),
        "frame_count": len(frames),
    }


async def _load_full_texts(
    session: AsyncSession, version_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not version_ids:
        return {}
    rows = (
        await session.execute(
            select(ReportVersion.id, ReportVersion.text).where(
                ReportVersion.id.in_(version_ids)
            )
        )
    ).all()
    return {rid: txt for rid, txt in rows}


def _event_view(event: TrackEvent, full_texts: dict[uuid.UUID, str]) -> dict:
    return {
        "date": event.event_date.isoformat() if event.event_date else None,
        "assertion": event.assertion,
        "evidence_text": event.evidence_text,
        "temporal_change": event.temporal_change,
        "measurement": event.measurement,
        "report_version_id": str(event.report_version_id)
        if event.report_version_id
        else None,
        "full_text": full_texts.get(event.report_version_id)
        if event.report_version_id
        else None,
    }


def _track_view(track: Track, events: list[TrackEvent], full_texts) -> dict:
    return {
        "track_key": track.track_key,
        "finding_type": track.finding_type,
        "anatomy": track.anatomy,
        "laterality": track.laterality,
        "latest_status": track.latest_status,
        "progression": track.progression,
        "progression_detail": track.progression_detail,
        "measurement_trend": track.measurement_trend,
        "report_range": track.report_range,
        "event_count": track.event_count,
        "unresolved_link": track.unresolved_link,
        "false_split_candidate": track.false_split_candidate,
        "clinical_section": normalize_section(track.clinical_section),
        "events": [_event_view(e, full_texts) for e in events],
    }


def _gate_failed_view(frame: Frame, full_texts: dict[uuid.UUID, str]) -> dict:
    return {
        "track_key": frame.track_key,
        "finding_type": frame.finding_type,
        "finding_surface": frame.finding_surface,
        "anatomy": frame.anatomy,
        "laterality": frame.laterality,
        "assertion": frame.assertion,
        "evidence_text": frame.evidence_text,
        "evidence_span_start": frame.evidence_span_start,
        "evidence_span_end": frame.evidence_span_end,
        "source_report_id": frame.source_report_id,
        "report_version_id": str(frame.report_version_id)
        if frame.report_version_id
        else None,
        "full_text": full_texts.get(frame.report_version_id)
        if frame.report_version_id
        else None,
        "reason": "evidence_span_not_located",
    }
