"""Inter-rater reliability (IRR / Cohen's kappa) pilot service.

Implements the blinded double-read clinician validation described in docs/IRR_PROTOCOL.md on
top of the ff.annotation_tasks / annotation_assignments / annotation_records / adjudications /
gold_candidates tables. The kappa arithmetic is factored into app.services.kappa (shared with
infra/scripts/compute_kappa.py).

Two structurally different things a clinician can do in this product; only one is IRR:
  * PRODUCTION review  -> ff.reviews, model_output_visible=true, anchored on the model. NOT IRR.
  * BLINDED IRR read   -> ff.annotation_assignments(model_output_visible=false); readers in one
                          independence_group label items WITHOUT seeing the model's extraction.

THE KEY INVARIANT (enforced here): for a blinded assignment we NEVER return the model's slot
values for its items. ``assignment_items`` projects each frame down to source-only fields
(the evidence sentence + full report text) via ``blinded_frame_item`` — the six model slots
(finding_type, anatomy, laterality, assertion, temporal_change, measurement) and the model's
finding_surface are dropped. ``tests/test_irr.py`` asserts this projection can never leak them.

These IRR tables have no ORM models (they are IRR-only); like app.services.analytics.agreement
we access them with org-scoped raw SQL. jsonb columns round-trip as native dicts (asyncpg
codec); we write them with ``cast(:param as jsonb)`` binding a JSON string.

Storage note: ff.annotation_tasks has no jsonb column for the sampled item set, and the app
role (ff_app) has no DDL privilege to add one, so the machine payload (run_id, sampling config,
and the frozen item_refs list) is stored as a JSON document in ff.annotation_tasks.description
alongside the human summary text. Everything else uses first-class columns (unit_of_agreement
enum, annotation_assignments.run_id / model_output_visible / independence_group, etc.).
"""
from __future__ import annotations

import json
import random
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Forbidden, NotFound
from app.services.kappa import CANONICAL_SLOT_ORDER, interpret_kappa, score_pair

# The six canonical clinical slots a reader fills for a frame/slot task (blinded).
FRAME_SLOT_FIELDS = list(CANONICAL_SLOT_ORDER)
# The linking judgment a reader fills for a track task (blinded).
TRACK_SLOT_FIELDS = ["belongs_to_same_track"]
# Fields on ff.frames that ARE model output and must never reach a blinded reader.
MODEL_SLOT_COLUMNS = frozenset(
    {"finding_type", "anatomy", "laterality", "assertion", "temporal_change",
     "measurement", "finding_surface", "clinical_importance", "severity", "uncertainty"}
)
_VALID_UNITS = {"slot", "frame", "track"}


# ---------------------------------------------------------------------------
# task.description JSON payload (holds run_id + sampling + frozen item_refs)
# ---------------------------------------------------------------------------
def _encode_description(human: str | None, run_id: uuid.UUID, unit: str,
                        sampling: dict, item_refs: list[str]) -> str:
    return json.dumps(
        {
            "text": human or "",
            "run_id": str(run_id),
            "unit_of_agreement": unit,
            "sampling": sampling,
            "item_refs": item_refs,
        }
    )


def _decode_description(raw: str | None) -> dict:
    if not raw:
        return {"text": "", "run_id": None, "sampling": {}, "item_refs": []}
    try:
        d = json.loads(raw)
        if isinstance(d, dict) and "item_refs" in d:
            return {
                "text": d.get("text", ""),
                "run_id": d.get("run_id"),
                "sampling": d.get("sampling", {}) or {},
                "item_refs": list(d.get("item_refs", []) or []),
            }
    except (ValueError, TypeError):
        pass
    # legacy / hand-created task: plain human text, no machine payload
    return {"text": raw, "run_id": None, "sampling": {}, "item_refs": []}


def _task_public(row: dict) -> dict:
    """Normalize a raw ff.annotation_tasks row into the API shape (description decoded)."""
    meta = _decode_description(row.get("description"))
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "protocol_id": row["protocol_id"],
        "unit_of_agreement": row["unit_of_agreement"],
        "description": meta["text"],
        "run_id": meta["run_id"],
        "sampling": meta["sampling"],
        "item_refs": meta["item_refs"],
        "n_items": len(meta["item_refs"]),
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# stratified sampling (IRR_PROTOCOL §2.2)
# ---------------------------------------------------------------------------
async def _sample_frames(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID, total: int, seed: int
) -> tuple[list[str], dict]:
    rows = (
        await session.execute(
            text(
                """
                select f.id::text as id,
                       f.evidence_verified,
                       f.uncertainty,
                       coalesce(t.unresolved_link, false) as unresolved_link,
                       coalesce(t.false_split_candidate, false) as false_split_candidate
                from ff.frames f
                left join ff.tracks t
                  on t.run_id = f.run_id and t.track_key = f.track_key
                where f.run_id = :run and f.org_id = :org
                """
            ),
            {"run": run_id, "org": org_id},
        )
    ).mappings().all()

    hard, lowconf, standard = [], [], []
    for r in rows:
        if r["unresolved_link"] or r["false_split_candidate"]:
            hard.append(r["id"])
        elif (not r["evidence_verified"]) or (r["uncertainty"] is not None):
            lowconf.append(r["id"])
        else:
            standard.append(r["id"])
    return _stratified_pick(
        {"unresolved_or_false_split": (hard, 0.25),
         "low_confidence_or_gate_adjacent": (lowconf, 0.25),
         "standard": (standard, 0.50)},
        total=total, seed=seed,
    )


async def _sample_tracks(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID, total: int, seed: int
) -> tuple[list[str], dict]:
    rows = (
        await session.execute(
            text(
                """
                select id::text as id,
                       coalesce(unresolved_link, false) as unresolved_link,
                       coalesce(false_split_candidate, false) as false_split_candidate
                from ff.tracks
                where run_id = :run and org_id = :org
                """
            ),
            {"run": run_id, "org": org_id},
        )
    ).mappings().all()
    hard = [r["id"] for r in rows if r["unresolved_link"] or r["false_split_candidate"]]
    standard = [r["id"] for r in rows if not (r["unresolved_link"] or r["false_split_candidate"])]
    return _stratified_pick(
        {"unresolved_or_false_split": (hard, 0.50), "standard": (standard, 0.50)},
        total=total, seed=seed,
    )


def _stratified_pick(strata: dict[str, tuple[list[str], float]], *, total: int, seed: int
                     ) -> tuple[list[str], dict]:
    """Pick ~proportion of `total` from each stratum, filling any shortfall from the others,
    reproducibly (seeded). Returns (ordered item_refs, realized-count metadata)."""
    rng = random.Random(seed)
    picked: list[str] = []
    realized: dict[str, int] = {}
    seen: set[str] = set()

    # first pass: target counts per stratum, capped by availability
    for name, (pool, frac) in strata.items():
        want = round(total * frac)
        avail = [x for x in pool if x not in seen]
        rng.shuffle(avail)
        take = avail[: min(want, len(avail))]
        for x in take:
            seen.add(x)
        picked.extend(take)
        realized[name] = len(take)

    # second pass: fill any remaining budget from whatever is left, largest pools first
    if len(picked) < total:
        leftovers: list[str] = []
        for pool, _ in strata.values():
            leftovers.extend(x for x in pool if x not in seen)
        rng.shuffle(leftovers)
        for x in leftovers:
            if len(picked) >= total:
                break
            seen.add(x)
            picked.append(x)
            realized["fill"] = realized.get("fill", 0) + 1

    meta = {
        "seed": seed,
        "requested": total,
        "realized_total": len(picked),
        "per_stratum": realized,
        "strategy": "stratified: 50% standard / 25% unresolved-link|false-split / "
                    "25% low-confidence|gate-adjacent (IRR_PROTOCOL §2.2)",
    }
    return picked, meta


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------
async def create_task(
    session: AsyncSession, *, org_id: uuid.UUID, created_by: uuid.UUID,
    name: str, protocol_id: str, unit_of_agreement: str, run_id: uuid.UUID,
    description: str | None = None, sample_size: int = 15,
) -> dict:
    unit = (unit_of_agreement or "").strip().lower()
    if unit not in _VALID_UNITS:
        raise BadRequest(f"unit_of_agreement must be one of {sorted(_VALID_UNITS)}",
                         code="invalid_unit")
    if sample_size < 1:
        raise BadRequest("sample_size must be >= 1", code="invalid_sample_size")

    run = (
        await session.execute(
            text("select id from ff.extraction_runs where id = :run and org_id = :org"),
            {"run": run_id, "org": org_id},
        )
    ).first()
    if run is None:
        raise NotFound("Run not found for this org", code="run_not_found")

    seed = (int(uuid.UUID(str(run_id))) ^ (sample_size * 2654435761)) & 0x7FFFFFFF
    if unit == "track":
        item_refs, sampling = await _sample_tracks(
            session, org_id=org_id, run_id=run_id, total=sample_size, seed=seed)
    else:
        item_refs, sampling = await _sample_frames(
            session, org_id=org_id, run_id=run_id, total=sample_size, seed=seed)
    if not item_refs:
        raise BadRequest("Run has no frames/tracks to sample for an IRR task",
                         code="empty_sample")

    desc = _encode_description(description, run_id, unit, sampling, item_refs)
    row = (
        await session.execute(
            text(
                """
                insert into ff.annotation_tasks
                    (org_id, protocol_id, name, unit_of_agreement, description, created_by)
                values
                    (:org, :protocol, :name, cast(:unit as ff.agreement_unit), :desc, :by)
                returning id, org_id, protocol_id, name,
                          unit_of_agreement::text as unit_of_agreement, description, created_at
                """
            ),
            {"org": org_id, "protocol": protocol_id, "name": name, "unit": unit,
             "desc": desc, "by": created_by},
        )
    ).mappings().one()
    return _task_public(dict(row))


async def list_tasks(session: AsyncSession, *, org_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select t.id, t.org_id, t.protocol_id, t.name,
                       t.unit_of_agreement::text as unit_of_agreement, t.description, t.created_at,
                       count(distinct a.id) as n_assignments,
                       count(distinct a.independence_group) as n_groups,
                       count(distinct a.annotator_id) as n_annotators
                from ff.annotation_tasks t
                left join ff.annotation_assignments a on a.task_id = t.id
                where t.org_id = :org
                group by t.id
                order by t.created_at desc
                """
            ),
            {"org": org_id},
        )
    ).mappings().all()
    out = []
    for r in rows:
        pub = _task_public(dict(r))
        pub["n_assignments"] = int(r["n_assignments"])
        pub["n_groups"] = int(r["n_groups"])
        pub["n_annotators"] = int(r["n_annotators"])
        out.append(pub)
    return out


async def _get_task_row(session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                """
                select id, org_id, protocol_id, name,
                       unit_of_agreement::text as unit_of_agreement, description, created_at
                from ff.annotation_tasks where id = :id and org_id = :org
                """
            ),
            {"id": task_id, "org": org_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFound("IRR task not found", code="task_not_found")
    return dict(row)


async def _assignments_for_task(session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID
                                ) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select a.id, a.annotator_id, a.run_id, a.independence_group,
                       a.model_output_visible, a.status, a.created_at,
                       p.full_name,
                       (select count(*) from ff.annotation_records r
                          where r.assignment_id = a.id) as n_records
                from ff.annotation_assignments a
                left join ff.profiles p on p.id = a.annotator_id
                where a.task_id = :task and a.org_id = :org
                order by a.independence_group nulls last, a.created_at
                """
            ),
            {"task": task_id, "org": org_id},
        )
    ).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "annotator_id": str(r["annotator_id"]),
            "annotator_name": r["full_name"],
            "run_id": str(r["run_id"]) if r["run_id"] else None,
            "independence_group": r["independence_group"],
            "model_output_visible": bool(r["model_output_visible"]),
            "status": r["status"],
            "n_records": int(r["n_records"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def get_task(session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID) -> dict:
    task = _task_public(await _get_task_row(session, org_id=org_id, task_id=task_id))
    task["assignments"] = await _assignments_for_task(session, org_id=org_id, task_id=task_id)
    return task


# ---------------------------------------------------------------------------
# assignments
# ---------------------------------------------------------------------------
async def create_assignment(
    session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID,
    annotator_id: uuid.UUID, independence_group: str | None,
) -> dict:
    task = await _get_task_row(session, org_id=org_id, task_id=task_id)
    run_id = _decode_description(task["description"]).get("run_id")

    # The annotator must be a member of this org (their profile+membership must exist). This
    # also guarantees annotator_id is a real auth.users id, so the FK below cannot fail.
    member = (
        await session.execute(
            text(
                "select 1 from ff.memberships where user_id = :uid and org_id = :org"
            ),
            {"uid": annotator_id, "org": org_id},
        )
    ).first()
    if member is None:
        raise BadRequest("annotator must be a member of this org", code="annotator_not_member")

    row = (
        await session.execute(
            text(
                """
                insert into ff.annotation_assignments
                    (task_id, org_id, annotator_id, run_id, model_output_visible,
                     independence_group, status)
                values
                    (:task, :org, :uid, :run, false, :group, 'assigned')
                returning id
                """
            ),
            {"task": task_id, "org": org_id, "uid": annotator_id,
             "run": run_id, "group": independence_group},
        )
    ).mappings().one()
    return {
        "id": str(row["id"]),
        "task_id": str(task_id),
        "annotator_id": str(annotator_id),
        "run_id": run_id,
        "independence_group": independence_group,
        "model_output_visible": False,
        "status": "assigned",
    }


async def list_my_assignments(session: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID
                              ) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select a.id, a.task_id, a.independence_group, a.model_output_visible, a.status,
                       a.created_at, t.name as task_name,
                       t.unit_of_agreement::text as unit_of_agreement, t.description,
                       (select count(*) from ff.annotation_records r
                          where r.assignment_id = a.id) as n_records
                from ff.annotation_assignments a
                join ff.annotation_tasks t on t.id = a.task_id
                where a.annotator_id = :uid and a.org_id = :org
                order by a.created_at desc
                """
            ),
            {"uid": user_id, "org": org_id},
        )
    ).mappings().all()
    out = []
    for r in rows:
        meta = _decode_description(r["description"])
        n_items = len(meta["item_refs"])
        out.append({
            "id": str(r["id"]),
            "task_id": str(r["task_id"]),
            "task_name": r["task_name"],
            "unit_of_agreement": r["unit_of_agreement"],
            "independence_group": r["independence_group"],
            "model_output_visible": bool(r["model_output_visible"]),
            "status": r["status"],
            "n_items": n_items,
            "n_records": int(r["n_records"]),
            "created_at": r["created_at"],
        })
    return out


async def _load_assignment(session: AsyncSession, *, org_id: uuid.UUID, assignment_id: uuid.UUID
                           ) -> dict:
    row = (
        await session.execute(
            text(
                """
                select a.id, a.task_id, a.org_id, a.annotator_id, a.run_id,
                       a.independence_group, a.model_output_visible, a.status,
                       t.name as task_name, t.unit_of_agreement::text as unit_of_agreement,
                       t.description
                from ff.annotation_assignments a
                join ff.annotation_tasks t on t.id = a.task_id
                where a.id = :id and a.org_id = :org
                """
            ),
            {"id": assignment_id, "org": org_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFound("Assignment not found", code="assignment_not_found")
    return dict(row)


# ---------------------------------------------------------------------------
# BLINDED item projection — the load-bearing invariant
# ---------------------------------------------------------------------------
def blinded_frame_item(frame_row: dict, full_text: str | None) -> dict:
    """Project a ff.frames row down to SOURCE-ONLY fields for a blinded reader: the evidence
    sentence and its location, plus the full report text for context. The model's extracted
    slot values (finding_type/anatomy/laterality/assertion/temporal_change/measurement, and
    finding_surface) are DROPPED — a blinded reader must never see them. Pure + tested."""
    return {
        "item_ref": str(frame_row["id"]),
        "source_report_id": frame_row.get("source_report_id"),
        "evidence_text": frame_row.get("evidence_text"),
        "evidence_span_start": frame_row.get("evidence_span_start"),
        "evidence_span_end": frame_row.get("evidence_span_end"),
        "report_version_id": (str(frame_row["report_version_id"])
                              if frame_row.get("report_version_id") else None),
        "full_text": full_text,
    }


async def assignment_items(
    session: AsyncSession, *, org_id: uuid.UUID, assignment_id: uuid.UUID, caller_id: uuid.UUID,
    caller_is_admin: bool = False,
) -> dict:
    a = await _load_assignment(session, org_id=org_id, assignment_id=assignment_id)
    if str(a["annotator_id"]) != str(caller_id) and not caller_is_admin:
        raise Forbidden("This assignment belongs to another annotator", code="not_your_assignment")

    meta = _decode_description(a["description"])
    item_refs: list[str] = meta["item_refs"]
    unit = a["unit_of_agreement"]
    slot_fields = TRACK_SLOT_FIELDS if unit == "track" else FRAME_SLOT_FIELDS

    # which items has this reader already recorded (resume/progress)
    done_rows = (
        await session.execute(
            text("select item_ref from ff.annotation_records where assignment_id = :a"),
            {"a": assignment_id},
        )
    ).mappings().all()
    done = {r["item_ref"] for r in done_rows}

    items: list[dict] = []
    if item_refs:
        if unit == "track":
            items = await _blinded_track_items(session, org_id=org_id, run_id=a["run_id"],
                                               item_refs=item_refs)
        else:
            items = await _blinded_frame_items(session, item_refs=item_refs)
    for it in items:
        it["submitted"] = it["item_ref"] in done

    return {
        "assignment": {
            "id": str(a["id"]),
            "task_id": str(a["task_id"]),
            "task_name": a["task_name"],
            "unit_of_agreement": unit,
            "independence_group": a["independence_group"],
            "status": a["status"],
        },
        # This endpoint is blinded by construction; surface the flag so the UI can assert it.
        "blinded": True,
        "model_output_visible": bool(a["model_output_visible"]),
        "slot_fields": slot_fields,
        "n_items": len(item_refs),
        "n_submitted": len(done),
        "items": items,
    }


async def _blinded_frame_items(session: AsyncSession, *, item_refs: list[str]) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select f.id::text as id, f.source_report_id, f.evidence_text,
                       f.evidence_span_start, f.evidence_span_end, f.report_version_id,
                       rv.text as full_text
                from ff.frames f
                left join ff.report_versions rv on rv.id = f.report_version_id
                where f.id::text = any(:refs)
                """
            ),
            {"refs": item_refs},
        )
    ).mappings().all()
    by_id = {r["id"]: dict(r) for r in rows}
    # preserve the frozen sample order; drop any refs no longer present
    out = []
    for ref in item_refs:
        r = by_id.get(ref)
        if r is not None:
            out.append(blinded_frame_item(r, r.get("full_text")))
    return out


async def _blinded_track_items(session: AsyncSession, *, org_id: uuid.UUID,
                               run_id: str | None, item_refs: list[str]) -> list[dict]:
    """For a track-linking judgment: show the source evidence sentences of the track's member
    frames (so the reader can judge whether they belong together) WITHOUT the model's track
    slot values or its linking decision."""
    rows = (
        await session.execute(
            text(
                """
                select t.id::text as id, t.track_key,
                       f.evidence_text, f.source_report_id, f.report_version_id,
                       rv.text as full_text
                from ff.tracks t
                left join ff.frames f on f.run_id = t.run_id and f.track_key = t.track_key
                left join ff.report_versions rv on rv.id = f.report_version_id
                where t.id::text = any(:refs) and t.org_id = :org
                order by f.report_version_id
                """
            ),
            {"refs": item_refs, "org": org_id},
        )
    ).mappings().all()
    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(r["id"], {"item_ref": r["id"], "member_evidence": []})
        if r["evidence_text"]:
            g["member_evidence"].append({
                "evidence_text": r["evidence_text"],
                "source_report_id": r["source_report_id"],
                "full_text": r["full_text"],
            })
    return [grouped[ref] for ref in item_refs if ref in grouped]


# ---------------------------------------------------------------------------
# records (append-only)
# ---------------------------------------------------------------------------
async def create_record(
    session: AsyncSession, *, org_id: uuid.UUID, assignment_id: uuid.UUID,
    caller_id: uuid.UUID, item_ref: str, labels: dict[str, Any],
) -> dict:
    a = await _load_assignment(session, org_id=org_id, assignment_id=assignment_id)
    if str(a["annotator_id"]) != str(caller_id):
        raise Forbidden("Only the assigned annotator may submit records", code="not_your_assignment")

    meta = _decode_description(a["description"])
    if meta["item_refs"] and item_ref not in meta["item_refs"]:
        raise BadRequest("item_ref is not in this task's sampled item set", code="item_not_in_task")
    if not isinstance(labels, dict) or not labels:
        raise BadRequest("labels must be a non-empty object", code="empty_labels")

    unit = a["unit_of_agreement"]
    allowed = set(TRACK_SLOT_FIELDS if unit == "track" else FRAME_SLOT_FIELDS)
    # tolerate track-linking aliases too
    allowed |= {"belongs_to_same_track", "linked", "same_track"}
    unknown = set(labels) - allowed
    if unknown:
        raise BadRequest(f"unknown slot fields: {sorted(unknown)}", code="unknown_slots")

    row = (
        await session.execute(
            text(
                """
                insert into ff.annotation_records (assignment_id, org_id, item_ref, labels)
                values (:a, :org, :ref, cast(:labels as jsonb))
                returning id, created_at
                """
            ),
            {"a": assignment_id, "org": org_id, "ref": item_ref, "labels": json.dumps(labels)},
        )
    ).mappings().one()
    return {
        "id": str(row["id"]),
        "assignment_id": str(assignment_id),
        "item_ref": item_ref,
        "labels": labels,
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# kappa
# ---------------------------------------------------------------------------
async def _records_by_item(session: AsyncSession, assignment_id: str) -> dict[str, dict]:
    rows = (
        await session.execute(
            text("select item_ref, labels from ff.annotation_records where assignment_id = :a"),
            {"a": assignment_id},
        )
    ).mappings().all()
    # If an item was (append-only) recorded more than once, the latest label wins for scoring.
    out: dict[str, dict] = {}
    for r in rows:
        out[r["item_ref"]] = r["labels"]
    return out


async def compute_kappa(session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID) -> dict:
    task = _task_public(await _get_task_row(session, org_id=org_id, task_id=task_id))
    assignments = await _assignments_for_task(session, org_id=org_id, task_id=task_id)

    # group by independence_group
    groups: dict[str | None, list[dict]] = {}
    for a in assignments:
        groups.setdefault(a["independence_group"], []).append(a)

    group_results: list[dict] = []
    readers_with_records = 0
    for group_key, members in groups.items():
        if group_key is None or len(members) != 2:
            group_results.append({
                "independence_group": group_key,
                "scoreable": False,
                "reason": ("no independence_group set" if group_key is None
                           else f"expected exactly 2 readers, found {len(members)}"),
                "readers": [{"annotator_id": m["annotator_id"],
                             "annotator_name": m["annotator_name"],
                             "n_records": m["n_records"]} for m in members],
                "slots": [],
            })
            continue

        a1, a2 = members
        recs_a = await _records_by_item(session, a1["id"])
        recs_b = await _records_by_item(session, a2["id"])
        if recs_a:
            readers_with_records += 1
        if recs_b:
            readers_with_records += 1

        anchored = a1["model_output_visible"] or a2["model_output_visible"]
        rows = score_pair(recs_a, recs_b) if (recs_a and recs_b) else []
        slots = [
            {
                "slot": r["slot"],
                "n": int(r["n"]),
                "observed_agreement": None if r["po"] != r["po"] else round(r["po"], 4),
                "kappa": None if r["kappa"] != r["kappa"] else round(r["kappa"], 4),
                "ci_low": None if r["ci"][0] != r["ci"][0] else round(r["ci"][0], 4),
                "ci_high": None if r["ci"][1] != r["ci"][1] else round(r["ci"][1], 4),
                "band": r["band"],
            }
            for r in rows
        ]
        only_a = set(recs_a) - set(recs_b)
        only_b = set(recs_b) - set(recs_a)
        group_results.append({
            "independence_group": group_key,
            "scoreable": bool(slots),
            "anchored_warning": anchored,
            "readers": [
                {"annotator_id": a1["annotator_id"], "annotator_name": a1["annotator_name"],
                 "n_records": len(recs_a), "model_output_visible": a1["model_output_visible"]},
                {"annotator_id": a2["annotator_id"], "annotator_name": a2["annotator_name"],
                 "n_records": len(recs_b), "model_output_visible": a2["model_output_visible"]},
            ],
            "n_common_items": len(set(recs_a) & set(recs_b)),
            "coverage_only_a": len(only_a),
            "coverage_only_b": len(only_b),
            "slots": slots,
        })

    available = any(g.get("slots") for g in group_results)
    result = {
        "available": available,
        "task": task,
        "groups": group_results,
        "landis_koch": [
            {"range": "< 0.00", "label": "poor"},
            {"range": "0.00–0.20", "label": "slight"},
            {"range": "0.20–0.40", "label": "fair"},
            {"range": "0.40–0.60", "label": "moderate"},
            {"range": "0.60–0.80", "label": "substantial"},
            {"range": "0.80–1.00", "label": "almost perfect"},
        ],
    }
    if not available:
        result["reason"] = (
            "Kappa requires >=2 blinded readers in a shared independence_group who have each "
            "submitted records for overlapping items. Not enough annotation data yet."
        )
    return result


# ---------------------------------------------------------------------------
# disagreements (adjudication worklist) — NOT blinded (senior adjudicator context)
# ---------------------------------------------------------------------------
async def disagreements(session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID) -> dict:
    task = _task_public(await _get_task_row(session, org_id=org_id, task_id=task_id))
    assignments = await _assignments_for_task(session, org_id=org_id, task_id=task_id)
    groups: dict[str | None, list[dict]] = {}
    for a in assignments:
        groups.setdefault(a["independence_group"], []).append(a)

    # model values for context (adjudication is explicitly not blinded, IRR_PROTOCOL §4)
    model_by_ref: dict[str, dict] = {}
    if task["unit_of_agreement"] != "track" and task["item_refs"]:
        mrows = (
            await session.execute(
                text(
                    """
                    select id::text as item_ref, finding_type, anatomy, laterality,
                           assertion::text as assertion, temporal_change,
                           evidence_text
                    from ff.frames where id::text = any(:refs) and org_id = :org
                    """
                ),
                {"refs": task["item_refs"], "org": org_id},
            )
        ).mappings().all()
        model_by_ref = {r["item_ref"]: dict(r) for r in mrows}

    worklist: list[dict] = []
    for group_key, members in groups.items():
        if group_key is None or len(members) != 2:
            continue
        a1, a2 = members
        recs_a = await _records_by_item(session, a1["id"])
        recs_b = await _records_by_item(session, a2["id"])
        for ref in sorted(set(recs_a) & set(recs_b)):
            la, lb = recs_a[ref] or {}, recs_b[ref] or {}
            differing = sorted(
                k for k in set(la) | set(lb)
                if json.dumps(la.get(k), sort_keys=True, default=str)
                != json.dumps(lb.get(k), sort_keys=True, default=str)
            )
            if not differing:
                continue
            model = model_by_ref.get(ref, {})
            worklist.append({
                "item_ref": ref,
                "independence_group": group_key,
                "resolves_assignment_ids": [a1["id"], a2["id"]],
                "differing_slots": differing,
                "reader_a": {"annotator_id": a1["annotator_id"],
                             "annotator_name": a1["annotator_name"], "labels": la},
                "reader_b": {"annotator_id": a2["annotator_id"],
                             "annotator_name": a2["annotator_name"], "labels": lb},
                "evidence_text": model.get("evidence_text"),
                "model": {k: v for k, v in model.items() if k != "evidence_text"},
            })
    return {"task": task, "count": len(worklist), "disagreements": worklist}


# ---------------------------------------------------------------------------
# adjudications + gold candidates (append-only)
# ---------------------------------------------------------------------------
async def create_adjudication(
    session: AsyncSession, *, org_id: uuid.UUID, task_id: uuid.UUID, adjudicator_id: uuid.UUID,
    item_ref: str, resolves_assignment_ids: list[str], consensus: dict[str, Any],
    emit_gold: bool = False,
) -> dict:
    await _get_task_row(session, org_id=org_id, task_id=task_id)
    if not isinstance(consensus, dict) or not consensus:
        raise BadRequest("consensus must be a non-empty object", code="empty_consensus")

    adj = (
        await session.execute(
            text(
                """
                insert into ff.adjudications
                    (task_id, org_id, item_ref, resolves_assignment_ids, consensus, adjudicator_id)
                values
                    (:task, :org, :ref, cast(:resolves as jsonb), cast(:consensus as jsonb), :adj)
                returning id, created_at
                """
            ),
            {"task": task_id, "org": org_id, "ref": item_ref,
             "resolves": json.dumps(resolves_assignment_ids or []),
             "consensus": json.dumps(consensus), "adj": adjudicator_id},
        )
    ).mappings().one()

    gold_id = None
    if emit_gold:
        # descends from a blinded read -> contamination_model_visible=false, source='adjudication'
        gold = (
            await session.execute(
                text(
                    """
                    insert into ff.gold_candidates
                        (org_id, task_id, item_ref, gold, contamination_model_visible, source)
                    values
                        (:org, :task, :ref, cast(:gold as jsonb), false, 'adjudication')
                    returning id
                    """
                ),
                {"org": org_id, "task": task_id, "ref": item_ref, "gold": json.dumps(consensus)},
            )
        ).mappings().one()
        gold_id = str(gold["id"])

    return {
        "id": str(adj["id"]),
        "task_id": str(task_id),
        "item_ref": item_ref,
        "resolves_assignment_ids": resolves_assignment_ids or [],
        "consensus": consensus,
        "adjudicator_id": str(adjudicator_id),
        "gold_candidate_id": gold_id,
        "created_at": adj["created_at"],
    }
