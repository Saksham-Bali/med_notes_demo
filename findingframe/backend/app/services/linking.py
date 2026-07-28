"""R1 human-confirmed linking: append-only, signed link decisions + derivation of the
confirmed-track set. RECIST is computed ONLY over these confirmed tracks."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import canonical_json, sha256_hex
from app.core.errors import BadRequest
from app.db.models import LinkDecision, Track, TrackEvent
from app.services.runs import get_run


def _signature(payload: dict) -> str:
    return sha256_hex(canonical_json(payload))


async def create_link_decision(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    decided_by: uuid.UUID,
    data: dict,
) -> LinkDecision:
    run = await get_run(session, org_id=org_id, run_id=run_id)

    # primary_track_key is FK-constrained to ff.tracks(run_id, track_key). Validate up front
    # (400) instead of surfacing a raw IntegrityError. related keys (for merge) too.
    known = set(
        (
            await session.execute(
                select(Track.track_key).where(
                    Track.run_id == run_id, Track.org_id == org_id
                )
            )
        )
        .scalars()
        .all()
    )
    if data["primary_track_key"] not in known:
        raise BadRequest(
            f"Unknown primary_track_key '{data['primary_track_key']}' for this run",
            code="unknown_track_key",
        )
    for key in data.get("related_track_keys") or []:
        if key not in known:
            raise BadRequest(
                f"Unknown related track_key '{key}' for this run", code="unknown_track_key"
            )

    payload = {
        "run_id": str(run_id),
        "decision": data["decision"],
        "primary_track_key": data["primary_track_key"],
        "related_track_keys": data.get("related_track_keys") or [],
        "resulting_track_key": data.get("resulting_track_key"),
        "rationale": data.get("rationale"),
        "decided_by": str(decided_by),
    }
    decision = LinkDecision(
        org_id=org_id,
        patient_id=run.patient_id,
        run_id=run_id,
        decision=data["decision"],
        primary_track_key=data["primary_track_key"],
        related_track_keys=data.get("related_track_keys") or [],
        resulting_track_key=data.get("resulting_track_key"),
        rationale=data.get("rationale"),
        decided_by=decided_by,
        signature_sha256=_signature(payload),
    )
    session.add(decision)
    await session.flush()
    return decision


async def list_link_decisions(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> list[LinkDecision]:
    await get_run(session, org_id=org_id, run_id=run_id)
    rows = (
        await session.execute(
            select(LinkDecision)
            .where(LinkDecision.run_id == run_id, LinkDecision.org_id == org_id)
            .order_by(LinkDecision.decided_at)
        )
    ).scalars().all()
    return list(rows)


async def derive_confirmed_tracks(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> list[dict]:
    """Apply link decisions (in decision order) over the machine tracks to produce the
    human-confirmed track set.

    - confirm : the primary track's identity is confirmed as resulting_track_key.
    - merge   : primary + related fold into resulting_track_key (one confirmed identity).
    - split   : resulting_track_key is confirmed as a distinct identity split off primary.
    - mark_unresolved / reject : the track is NOT confirmed.
    """
    await get_run(session, org_id=org_id, run_id=run_id)
    tracks = (
        await session.execute(
            select(Track).where(Track.run_id == run_id, Track.org_id == org_id)
        )
    ).scalars().all()
    tracks_by_key = {t.track_key: t for t in tracks}
    decisions = await list_link_decisions(session, org_id=org_id, run_id=run_id)

    # confirmed_key -> set(member machine track_keys)
    confirmed: dict[str, set[str]] = {}
    excluded: set[str] = set()

    for d in decisions:
        primary = d.primary_track_key
        related = list(d.related_track_keys or [])
        result_key = d.resulting_track_key or primary
        if d.decision in ("confirm",):
            confirmed.setdefault(result_key, set()).add(primary)
            excluded.discard(primary)
        elif d.decision == "merge":
            members = confirmed.setdefault(result_key, set())
            members.add(primary)
            members.update(related)
            excluded.discard(primary)
        elif d.decision == "split":
            confirmed.setdefault(result_key, set()).add(primary)
        elif d.decision in ("mark_unresolved", "reject"):
            excluded.add(primary)
            # drop from any prior confirmed identity
            for members in confirmed.values():
                members.discard(primary)

    out: list[dict] = []
    for confirmed_key, member_keys in confirmed.items():
        member_keys = {k for k in member_keys if k not in excluded}
        if not member_keys:
            continue
        members = [tracks_by_key[k] for k in member_keys if k in tracks_by_key]
        events = await _events_for_tracks(session, [m.id for m in members])
        out.append(
            {
                "confirmed_track_key": confirmed_key,
                "member_track_keys": sorted(member_keys),
                "finding_type": members[0].finding_type if members else None,
                "anatomy": members[0].anatomy if members else None,
                "laterality": members[0].laterality if members else None,
                "events": events,
            }
        )
    out.sort(key=lambda x: x["confirmed_track_key"])
    return out


async def _events_for_tracks(
    session: AsyncSession, track_ids: list[uuid.UUID]
) -> list[dict]:
    if not track_ids:
        return []
    rows = (
        await session.execute(
            select(TrackEvent)
            .where(TrackEvent.track_id.in_(track_ids))
            .order_by(TrackEvent.event_date)
        )
    ).scalars().all()
    return [
        {
            "date": e.event_date.isoformat() if e.event_date else None,
            "assertion": e.assertion,
            "evidence_text": e.evidence_text,
            "temporal_change": e.temporal_change,
            "measurement": e.measurement,
            "report_version_id": str(e.report_version_id) if e.report_version_id else None,
        }
        for e in rows
    ]
