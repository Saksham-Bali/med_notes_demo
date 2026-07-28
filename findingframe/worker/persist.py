"""Map an engine PatientArtifact into ff.frames / ff.tracks / ff.track_events rows.

All inserts are idempotent (ON CONFLICT DO NOTHING against the dedupe unique indexes) so a
crash-resume never duplicates immutable rows. Persistence + the run's status flip to
'succeeded' happen in a single transaction (atomic), so partial state cannot leak.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Frame, Track, TrackEvent
from app.engine.types import PatientArtifact

_ASSERTIONS = {"present", "absent", "uncertain", "not_mentioned"}
_WORSE = {"new", "worsened", "increased", "enlarged", "progressed", "worse", "larger"}
_BETTER = {"improved", "decreased", "smaller", "reduced", "resolving"}


def _assertion(value: Any) -> str:
    v = str(value or "").strip().lower()
    return v if v in _ASSERTIONS else "uncertain"


def _verified(span_start: Any, span_end: Any) -> bool:
    try:
        s, e = int(span_start), int(span_end)
    except (TypeError, ValueError):
        return False
    return s >= 0 and e >= 0 and e > s


def _parse_date(value: Any) -> dt.datetime | None:
    if not value or str(value).lower() == "unknown":
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            return dt.datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            return None


def derive_section(track: dict[str, Any]) -> str:
    if track.get("unresolved_link"):
        return "uncertain"
    status = str(track.get("latest_status") or "").lower()
    events = track.get("events") or []
    latest_tc = str((events[-1].get("temporal_change") if events else "") or "").lower()
    if status == "active":
        if latest_tc in _WORSE:
            return "needs_attention"
        if latest_tc in _BETTER:
            return "resolved"
        return "stable"
    if status == "resolved":
        return "resolved"
    if status == "absent":
        return "routine_negatives"
    return "uncertain"


async def persist_artifact(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    org_id: uuid.UUID,
    patient_id: uuid.UUID,
    report_manifest: list[dict[str, Any]],
    artifact: PatientArtifact,
) -> dict[str, int]:
    version_map: dict[str, uuid.UUID] = {}
    date_map: dict[str, dt.datetime | None] = {}
    for entry in report_manifest:
        srid = entry.get("source_report_id")
        if not srid:
            continue
        rvid = entry.get("report_version_id")
        if rvid:
            version_map[srid] = uuid.UUID(str(rvid))
        date_map[srid] = _parse_date(entry.get("chart_date"))

    # --- frames ---
    for f in artifact.frames:
        srid = f.get("source_report_id")
        stmt = (
            pg_insert(Frame.__table__)
            .values(
                run_id=run_id,
                org_id=org_id,
                patient_id=patient_id,
                report_version_id=version_map.get(srid),
                source_report_id=srid,
                frame_index=f.get("frame_index"),
                track_key=f.get("track_key") or "unknown",
                finding_type=f.get("finding_type") or "unknown",
                finding_surface=f.get("finding_surface"),
                assertion=_assertion(f.get("assertion")),
                anatomy=f.get("anatomy"),
                laterality=f.get("laterality"),
                uncertainty=f.get("uncertainty"),
                temporal_change=f.get("temporal_change"),
                measurement=f.get("measurement"),
                clinical_importance=f.get("clinical_importance"),
                severity=f.get("severity"),
                evidence_text=f.get("evidence_text") or "",
                evidence_span_start=int(f.get("evidence_span_start", -1) or -1),
                evidence_span_end=int(f.get("evidence_span_end", -1) or -1),
                evidence_verified=_verified(
                    f.get("evidence_span_start"), f.get("evidence_span_end")
                ),
                review_only=bool(f.get("review_only", False)),
                lesion_key=f.get("lesion_key"),
            )
            .on_conflict_do_nothing(
                index_elements=["run_id", "source_report_id", "frame_index"]
            )
        )
        await session.execute(stmt)
    await session.flush()

    # frame id lookup by (source_report_id, frame_index)
    frame_rows = (
        await session.execute(
            select(Frame.id, Frame.source_report_id, Frame.frame_index).where(
                Frame.run_id == run_id
            )
        )
    ).all()
    frame_ids = {(srid, fidx): fid for fid, srid, fidx in frame_rows}

    # --- tracks ---
    false_split_keys: set[str] = set()
    for cand in artifact.false_split_candidates:
        if cand.get("left_track_key"):
            false_split_keys.add(cand["left_track_key"])
        if cand.get("right_track_key"):
            false_split_keys.add(cand["right_track_key"])

    tracks_dict: dict[str, dict[str, Any]] = artifact.tracks or {}
    for track_key, track in tracks_dict.items():
        events = track.get("events") or []
        dates = [d for d in (_parse_date(e.get("report_date")) for e in events) if d]
        report_range = None
        if dates:
            report_range = f"{min(dates).date().isoformat()}..{max(dates).date().isoformat()}"
        stmt = (
            pg_insert(Track.__table__)
            .values(
                run_id=run_id,
                org_id=org_id,
                patient_id=patient_id,
                track_key=track_key,
                finding_type=track.get("finding_type"),
                anatomy=track.get("anatomy"),
                laterality=track.get("laterality"),
                latest_status=track.get("latest_status"),
                progression=track.get("progression"),
                progression_detail=track.get("progression_detail"),
                event_count=int(track.get("event_count", len(events)) or 0),
                measurement_trend=track.get("measurement_trend"),
                report_range=report_range,
                unresolved_link=bool(track.get("unresolved_link", False)),
                false_split_candidate=track_key in false_split_keys,
                clinical_section=derive_section(track),
            )
            .on_conflict_do_nothing(index_elements=["run_id", "track_key"])
        )
        await session.execute(stmt)
    await session.flush()

    track_rows = (
        await session.execute(
            select(Track.id, Track.track_key).where(Track.run_id == run_id)
        )
    ).all()
    track_ids = {tk: tid for tid, tk in track_rows}

    # --- track_events (only if none exist yet for this run's tracks — idempotent resume) ---
    existing_events = (
        await session.execute(
            select(TrackEvent.id)
            .join(Track, Track.id == TrackEvent.track_id)
            .where(Track.run_id == run_id)
            .limit(1)
        )
    ).first()
    event_count = 0
    if existing_events is None:
        for e in artifact.frame_events:
            track_id = track_ids.get(e.get("track_key"))
            if track_id is None:
                continue
            srid = e.get("source_report_id")
            frame_id = frame_ids.get((srid, e.get("frame_index")))
            session.add(
                TrackEvent(
                    track_id=track_id,
                    frame_id=frame_id,
                    org_id=org_id,
                    report_version_id=version_map.get(srid),
                    event_date=date_map.get(srid) or _parse_date(e.get("report_date")),
                    assertion=_assertion(e.get("assertion")),
                    evidence_text=e.get("evidence_text"),
                    temporal_change=e.get("temporal_change"),
                    measurement=e.get("measurement"),
                )
            )
            event_count += 1
        await session.flush()

    return {
        "frames": len(artifact.frames),
        "tracks": len(tracks_dict),
        "track_events": event_count,
    }
