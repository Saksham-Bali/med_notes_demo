"""Carry a clinician's confirmed work from one extraction run onto the next.

Why this exists
---------------
Adding one report to a patient creates a new run over the whole history, and every
human artifact is keyed to ``run_id`` — ``link_decisions`` even carries a composite FK
``(run_id, primary_track_key) -> tracks(run_id, track_key)``. So without this module,
recording an eleventh scan silently invalidates ten reports of confirmed linking,
target selection and sign-off, and the reviewer starts again from nothing. That is
logged as P0-4 in ``PRE_UPDATE_PLAN_2026-07-30.md``.

The fix is possible because human decisions reference STABLE STRINGS — ``track_key``
(``finding_type|anatomy|laterality``) and ``confirmed_track_key`` — rather than row
identity. A decision can therefore be replayed onto the next run by key.

What may be carried, and what may not
-------------------------------------
The distinction that matters is between the two different things a clinician attested:

* a ``link_decision`` attests **identity** — "these machine tracks are one lesion";
* new measurements on that lesion are **evidence**, which is what a longitudinal track
  exists to accumulate.

A new measurement on an already-identified lesion does not disturb the identity claim,
so re-asking for it at every scan would make longitudinal tracking self-defeating. What
*can* disturb it is a change in the identity picture: the member set changing, a new
ambiguous link candidate appearing, or a new false-split flag.

There is one further trigger, and it exists because of a real gap in the linker.
``_compatible_track_keys`` (``tmc/fact_graph/frame_linker.py``) matches on finding type,
lesion key, link family, anatomy and laterality — and on **nothing about size**. A
lesion recorded at 12 mm and then at 44 mm links to the same track silently, raising no
ambiguity and no false-split flag. All three structural triggers stay quiet in exactly
the case that matters most. So a fourth trigger is applied, on decision impact rather
than on an invented size threshold: **if the new evidence is enough to move the RECIST
category, the track escalates from acknowledgement to full identity re-confirmation.**
The human re-attests precisely when the new evidence is what changes the answer.

Everything carried is recorded as carried. ``carried_from_run_id`` /
``carried_from_decision_id`` mark the replay, and ``decided_by`` / ``decided_at`` keep
the original act's attribution — a carried decision is a different act from a fresh one
and the record must be able to tell them apart.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest
from app.db.models import (
    ExtractionRun,
    LinkDecision,
    Review,
    TargetLesionSelection,
    Track,
)
from app.services.linking import derive_confirmed_tracks, list_link_decisions
from app.services.recist import _mm, _is_nodal, compute_timeline, latest_target_selection
from app.services.runs import get_run

# Outcome of planning one previously-confirmed identity onto the new run.
CARRY = "carry"              # identity picture unchanged -> replay the decision
ACKNOWLEDGE = "acknowledge"  # carried, and gained new evidence the reviewer must see
REOPEN = "reopen"            # identity picture changed -> needs full re-confirmation
NEW = "new"                  # track absent from the parent run -> needs a fresh decision


@dataclass
class IdentityPlan:
    confirmed_track_key: str
    status: str
    reason: str
    member_track_keys: list[str] = field(default_factory=list)
    gained_event_dates: list[str] = field(default_factory=list)
    review_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmed_track_key": self.confirmed_track_key,
            "status": self.status,
            "reason": self.reason,
            "member_track_keys": self.member_track_keys,
            "gained_event_dates": self.gained_event_dates,
            "review_only": self.review_only,
        }


def _track_flags(track: Track | None) -> tuple[bool, bool]:
    if track is None:
        return (False, False)
    return (bool(track.unresolved_link), bool(track.false_split_candidate))


def plan_identities(
    parent_confirmed: list[dict],
    parent_flags: dict[str, tuple[bool, bool]],
    new_flags: dict[str, tuple[bool, bool]],
    parent_event_dates: dict[str, set[str]],
    new_event_dates: dict[str, set[str]],
    category_moved: bool,
    target_keys: set[str],
) -> list[IdentityPlan]:
    """Decide, per previously-confirmed identity, whether its confirmation still stands.

    Pure: takes plain dicts keyed by track_key so it is offline-testable. ``parent_flags``
    / ``new_flags`` map a machine track_key to ``(unresolved_link, false_split_candidate)``.
    ``category_moved`` says whether the new evidence changed the RECIST call.
    """
    plans: list[IdentityPlan] = []
    for c in parent_confirmed:
        key = c["confirmed_track_key"]
        members = sorted(c.get("member_track_keys") or [])

        missing = [m for m in members if m not in new_flags]
        if missing:
            plans.append(IdentityPlan(
                key, REOPEN,
                f"member track(s) no longer present on the new run: {', '.join(missing)}",
                members,
            ))
            continue

        newly_ambiguous = [
            m for m in members
            if new_flags[m][0] and not parent_flags.get(m, (False, False))[0]
        ]
        if newly_ambiguous:
            plans.append(IdentityPlan(
                key, REOPEN,
                "a new ambiguous link candidate appeared for "
                f"{', '.join(newly_ambiguous)}",
                members,
            ))
            continue

        newly_split = [
            m for m in members
            if new_flags[m][1] and not parent_flags.get(m, (False, False))[1]
        ]
        if newly_split:
            plans.append(IdentityPlan(
                key, REOPEN,
                f"a new false-split candidate was flagged for {', '.join(newly_split)}",
                members,
            ))
            continue

        before: set[str] = set()
        after: set[str] = set()
        for m in members:
            before |= parent_event_dates.get(m, set())
            after |= new_event_dates.get(m, set())
        gained = sorted(after - before)

        if gained and category_moved and key in target_keys:
            plans.append(IdentityPlan(
                key, REOPEN,
                "new measurement moves the RECIST category, so lesion identity is "
                "re-attested rather than assumed",
                members, gained,
            ))
            continue

        if gained:
            plans.append(IdentityPlan(
                key, ACKNOWLEDGE,
                "identity unchanged; new evidence added and awaiting acknowledgement",
                members, gained,
            ))
            continue

        plans.append(IdentityPlan(key, CARRY, "identity picture unchanged", members))
    return plans


def _series_from_events(events: list[dict], *, nodal: bool) -> list[tuple[datetime, float]]:
    out: list[tuple[datetime, float]] = []
    for ev in events:
        if ev.get("assertion") != "present" or not ev.get("date"):
            continue
        mm = _mm(ev.get("measurement"), nodal=nodal)
        if mm is not None:
            out.append((datetime.fromisoformat(ev["date"]), mm))
    out.sort()
    return out


def _targets_for(confirmed: list[dict], selections: list[dict]) -> list[dict]:
    """Build compute_timeline() targets for the selected lesions out of a confirmed set."""
    by_key = {c["confirmed_track_key"]: c for c in confirmed}
    targets: list[dict] = []
    for sel in selections:
        key = sel.get("confirmed_track_key")
        c = by_key.get(key)
        if c is None:
            continue
        nodal = _is_nodal(
            finding_type=c.get("finding_type"),
            anatomy=c.get("anatomy"),
            organ=sel.get("organ"),
        )
        series = _series_from_events(c.get("events") or [], nodal=nodal)
        baseline = sel.get("baseline_mm")
        if not isinstance(baseline, (int, float)) or baseline <= 0:
            baseline = series[0][1] if series else 0.0
        targets.append({
            "series": series,
            "baseline_mm": float(baseline),
            "is_nodal": nodal,
        })
    return targets


def _call_of(targets: list[dict]) -> str | None:
    """The RECIST classification at the latest timepoint, or None if not computable."""
    if not targets or not any(t["series"] for t in targets):
        return None
    rows = compute_timeline(targets, set())
    return rows[-1]["classification"] if rows else None


async def _flags_and_dates(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[dict[str, tuple[bool, bool]], dict[str, uuid.UUID]]:
    rows = (
        await session.execute(
            select(Track).where(Track.run_id == run_id, Track.org_id == org_id)
        )
    ).scalars().all()
    return (
        {t.track_key: _track_flags(t) for t in rows},
        {t.track_key: t.id for t in rows},
    )


def _event_dates(confirmed: list[dict]) -> dict[str, set[str]]:
    """member track_key -> set of event dates. Confirmed identities fold members
    together, so dates are recorded against the identity's whole member set."""
    out: dict[str, set[str]] = {}
    for c in confirmed:
        dates = {ev["date"] for ev in (c.get("events") or []) if ev.get("date")}
        for m in c.get("member_track_keys") or []:
            out.setdefault(m, set()).update(dates)
    return out


async def plan_carry_forward(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict[str, Any]:
    """Dry-run: what would carry, what needs acknowledging, what must be re-confirmed."""
    run = await get_run(session, org_id=org_id, run_id=run_id)
    if not run.parent_run_id:
        raise BadRequest("Run has no parent to carry forward from", code="no_parent_run")
    parent_id = run.parent_run_id

    parent_confirmed = await derive_confirmed_tracks(session, org_id=org_id, run_id=parent_id)
    parent_flags, _ = await _flags_and_dates(session, org_id=org_id, run_id=parent_id)
    new_flags, _ = await _flags_and_dates(session, org_id=org_id, run_id=run_id)

    # The confirmed set as it WOULD look on the new run if every identity carried. This is
    # the dry run used to test whether the new evidence moves the RECIST category.
    provisional = await _provisional_confirmed(
        session, org_id=org_id, run_id=run_id, parent_confirmed=parent_confirmed
    )

    selection = await latest_target_selection(session, org_id=org_id, run_id=parent_id)
    selections = list(selection.selections) if selection else []
    target_keys = {s.get("confirmed_track_key") for s in selections}

    parent_call = _call_of(_targets_for(parent_confirmed, selections))
    new_call = _call_of(_targets_for(provisional, selections))
    category_moved = bool(parent_call and new_call and parent_call != new_call)

    plans = plan_identities(
        parent_confirmed,
        parent_flags,
        new_flags,
        _event_dates(parent_confirmed),
        _event_dates(provisional),
        category_moved,
        {k for k in target_keys if k},
    )

    carried_member_keys = {
        m for p in plans if p.status in (CARRY, ACKNOWLEDGE) for m in p.member_track_keys
    }
    known = set(parent_flags)
    for key in sorted(set(new_flags) - known):
        # The engine mints a per-report key for catch-all / review-only frames
        # (`|review_only|<report>|<kind>|<index>`) so they can never link across
        # timepoints. Every new report therefore contributes some of these, and counting
        # them alongside genuinely new lesions would overstate what the report found.
        # Flag them so the reviewer can see which is which rather than reading one number.
        is_review_only = "|review_only|" in key
        plans.append(IdentityPlan(
            key,
            NEW,
            "catch-all fragment from this report; review-only, never linked across scans"
            if is_review_only else "track first seen on this run",
            [key],
            review_only=is_review_only,
        ))

    parent_report_ids = {
        e.get("report_version_id")
        for e in ((await get_run(session, org_id=org_id, run_id=parent_id)).report_manifest or [])
    }
    added_reports = [
        {
            "report_version_id": e.get("report_version_id"),
            "source_report_id": e.get("source_report_id"),
            "chart_date": e.get("chart_date"),
        }
        for e in (run.report_manifest or [])
        if e.get("report_version_id") not in parent_report_ids
    ]

    return {
        "run_id": str(run_id),
        "parent_run_id": str(parent_id),
        "recist_call_before": parent_call,
        "recist_call_after": new_call,
        "category_moved": category_moved,
        # What this run cost, and what it covered. reports_total is the whole history;
        # llm_calls is how many of them the model actually had to read.
        "reports_total": len(run.report_manifest or []),
        "reports_added": added_reports,
        "llm_calls": (run.extraction_provenance or {}).get("llm_calls"),
        "cache_served": len((run.extraction_provenance or {}).get("cache_served") or []),
        "identities": [p.to_dict() for p in plans],
        "counts": {
            status: sum(1 for p in plans if p.status == status)
            for status in (CARRY, ACKNOWLEDGE, REOPEN, NEW)
        },
        "carried_member_track_keys": sorted(carried_member_keys),
    }


async def _provisional_confirmed(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    parent_confirmed: list[dict],
) -> list[dict]:
    """The parent's confirmed identities re-read against the NEW run's track events.

    Used only to test whether the new evidence changes the RECIST call. Nothing is
    written; this is the question "if we carried everything, what would the answer be?"
    """
    from app.services.linking import _events_for_tracks  # local import: avoids a cycle

    _, id_by_key = await _flags_and_dates(session, org_id=org_id, run_id=run_id)
    out: list[dict] = []
    for c in parent_confirmed:
        members = [m for m in (c.get("member_track_keys") or []) if m in id_by_key]
        if not members:
            continue
        events = await _events_for_tracks(session, [id_by_key[m] for m in members])
        out.append({**c, "member_track_keys": members, "events": events})
    return out


async def _track_event_dates(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict[str, set[str]]:
    """track_key -> the set of event dates on that track, for one run.

    Used to decide whether a track is *identical* between two runs. A review attests
    "I read this track's slots and evidence"; if the track carries exactly the same events
    on the new run, that reading still holds and re-asking for it is pure busywork.
    """
    from app.db.models import TrackEvent  # local import: keeps the module import graph flat

    rows = (
        await session.execute(
            select(Track.track_key, TrackEvent.event_date)
            .join(TrackEvent, TrackEvent.track_id == Track.id)
            .where(Track.run_id == run_id, Track.org_id == org_id)
        )
    ).all()
    out: dict[str, set[str]] = {}
    for key, when in rows:
        out.setdefault(key, set()).add(when.isoformat() if when else "")
    return out


async def apply_carry_forward(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID, applied_by: uuid.UUID
) -> dict[str, Any]:
    """Replay the parent's carryable decisions onto this run.

    Only identities planned as ``carry`` or ``acknowledge`` are replayed. Anything
    ``reopen`` or ``new`` is deliberately left for the reviewer — that is the honest,
    bounded workload the new report actually created.
    """
    plan = await plan_carry_forward(session, org_id=org_id, run_id=run_id)
    run = await get_run(session, org_id=org_id, run_id=run_id)
    parent_id = run.parent_run_id
    assert parent_id is not None  # plan_carry_forward already rejected a parentless run

    carryable = {
        p["confirmed_track_key"]
        for p in plan["identities"]
        if p["status"] in (CARRY, ACKNOWLEDGE)
    }
    carryable_members = {
        m
        for p in plan["identities"]
        if p["status"] in (CARRY, ACKNOWLEDGE)
        for m in p["member_track_keys"]
    }

    existing = {
        (d.decision, d.primary_track_key, d.resulting_track_key)
        for d in await list_link_decisions(session, org_id=org_id, run_id=run_id)
    }

    carried_decisions = 0
    for d in await list_link_decisions(session, org_id=org_id, run_id=parent_id):
        result_key = d.resulting_track_key or d.primary_track_key
        if result_key not in carryable or d.primary_track_key not in carryable_members:
            continue
        if (d.decision, d.primary_track_key, d.resulting_track_key) in existing:
            continue
        session.add(
            LinkDecision(
                org_id=org_id,
                patient_id=run.patient_id,
                run_id=run_id,
                decision=d.decision,
                primary_track_key=d.primary_track_key,
                related_track_keys=list(d.related_track_keys or []),
                resulting_track_key=d.resulting_track_key,
                rationale=d.rationale,
                # The clinical act happened once, then, by that person. Preserved.
                decided_by=d.decided_by,
                decided_at=d.decided_at,
                signature_sha256=d.signature_sha256,
                carried_from_run_id=parent_id,
                carried_from_decision_id=d.id,
            )
        )
        carried_decisions += 1

    carried_selection = False
    parent_sel = await latest_target_selection(session, org_id=org_id, run_id=parent_id)
    own_sel = await latest_target_selection(session, org_id=org_id, run_id=run_id)
    if parent_sel is not None and own_sel is None:
        planned_keys = {p["confirmed_track_key"] for p in plan["identities"]}
        still_valid = all(
            (s.get("confirmed_track_key") in planned_keys) for s in parent_sel.selections
        )
        if still_valid:
            session.add(
                TargetLesionSelection(
                    org_id=org_id,
                    patient_id=run.patient_id,
                    run_id=run_id,
                    baseline_report_version_id=parent_sel.baseline_report_version_id,
                    selections=list(parent_sel.selections),
                    selected_by=parent_sel.selected_by,
                    selected_at=parent_sel.selected_at,
                    signature_sha256=parent_sel.signature_sha256,
                    carried_from_run_id=parent_id,
                    carried_from_selection_id=parent_sel.id,
                )
            )
            carried_selection = True

    # --- reviews -------------------------------------------------------------
    # Identity is not the only thing a clinician attested in act one. They also reviewed
    # each track's slots, and that verdict is what puts the "reviewed" tick on a track card.
    # Without carrying it, the workbench shows every previously-reviewed track as
    # outstanding and the reviewer cannot tell settled work from new work -- which defeats
    # the whole point. Reviews carry under the same gate as identities: an identity that
    # was re-opened does NOT bring its old review with it.
    parent_reviews = (
        await session.execute(
            select(Review).where(Review.run_id == parent_id, Review.org_id == org_id)
        )
    ).scalars().all()
    own_reviews = (
        await session.execute(
            select(Review).where(Review.run_id == run_id, Review.org_id == org_id)
        )
    ).scalars().all()
    # Deduped separately, because a track legitimately gets BOTH: the carried act-one
    # review ("I checked these slots") and an acknowledgement ("and here is what report 11
    # added"). Collapsing them into one set silently drops every acknowledgement.
    already = {r.track_key for r in own_reviews if r.review_kind != "acknowledgement"}
    already_ack = {r.track_key for r in own_reviews if r.review_kind == "acknowledgement"}
    # A review carries when EITHER the track belongs to a carried identity, OR the track
    # itself is byte-identical between runs (same key, same events). The second case is
    # what covers the per-report catch-all fragments: the engine mints a key per report for
    # them, so reports 1..N are untouched by report N+1 and their reviews plainly still
    # stand. Without it the workbench buries the few genuinely new items under dozens of
    # already-read fragments -- which is exactly how this bug was found.
    parent_dates = await _track_event_dates(session, org_id=org_id, run_id=parent_id)
    child_dates = await _track_event_dates(session, org_id=org_id, run_id=run_id)
    unchanged = {
        k for k, v in parent_dates.items() if k in child_dates and child_dates[k] == v
    }

    carried_reviews = 0
    for r in parent_reviews:
        carryable = r.track_key in carryable_members or r.track_key in unchanged
        if not carryable or r.track_key in already:
            continue
        session.add(
            Review(
                org_id=org_id,
                patient_id=run.patient_id,
                run_id=run_id,
                track_key=r.track_key,
                reviewer_id=r.reviewer_id,
                reviewed_value=r.reviewed_value,
                link_correct=r.link_correct,
                type_correct=r.type_correct,
                progression_correct=r.progression_correct,
                latest_status_correct=r.latest_status_correct,
                false_merge=r.false_merge,
                false_split=r.false_split,
                evidence_valid=r.evidence_valid,
                clinically_significant=r.clinically_significant,
                correction_finding_type=r.correction_finding_type,
                correction_anatomy=r.correction_anatomy,
                correction_laterality=r.correction_laterality,
                comment=r.comment,
                model_output_visible=r.model_output_visible,
                review_kind=r.review_kind,
                created_at=r.created_at,
            )
        )
        already.add(r.track_key)
        carried_reviews += 1

    # --- acknowledgements ----------------------------------------------------
    # A carried track that gained evidence needs the reviewer to SEE what was added. The
    # row records the dates added and which run they came from, so "they saw it" is a fact
    # in the record rather than an assumption that they scrolled far enough.
    acknowledgements = 0
    for p in plan["identities"]:
        if p["status"] != ACKNOWLEDGE or not p["gained_event_dates"]:
            continue
        for member in p["member_track_keys"]:
            if member in already_ack:
                continue
            session.add(
                Review(
                    org_id=org_id,
                    patient_id=run.patient_id,
                    run_id=run_id,
                    track_key=member,
                    reviewer_id=applied_by,
                    reviewed_value={
                        "acknowledgement": {
                            "confirmed_track_key": p["confirmed_track_key"],
                            "gained_event_dates": p["gained_event_dates"],
                            "carried_from_run_id": str(parent_id),
                            "reason": p["reason"],
                        }
                    },
                    review_kind="acknowledgement",
                    comment=(
                        "New evidence added to a track whose identity was already "
                        f"confirmed: {', '.join(p['gained_event_dates'])}."
                    ),
                )
            )
            already_ack.add(member)
            acknowledgements += 1

    await session.flush()
    return {
        **plan,
        "carried_link_decisions": carried_decisions,
        "carried_target_selection": carried_selection,
        "carried_reviews": carried_reviews,
        "acknowledgements": acknowledgements,
    }


async def parent_run_for(
    session: AsyncSession, *, org_id: uuid.UUID, patient_id: uuid.UUID
) -> ExtractionRun | None:
    """The most recent succeeded run for this patient — the one a new run extends."""
    return (
        await session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.org_id == org_id,
                ExtractionRun.patient_id == patient_id,
                ExtractionRun.status == "succeeded",
            )
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
