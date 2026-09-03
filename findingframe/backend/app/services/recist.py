"""RECIST 1.1 worksheet — computed ONLY over human-confirmed target tracks.

Target-lesion selection is a human baseline act: <=5 target lesions total, <=2 per organ.
The assessment refuses (422) if there are no confirmed tracks or no target selection.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import canonical_json, sha256_hex
from app.core.errors import UnprocessableEntity
from app.db.models import RecistAssessment, TargetLesionSelection, Track, TrackEvent
from app.services.linking import derive_confirmed_tracks
from app.services.runs import get_run

MAX_TARGETS = 5
MAX_PER_ORGAN = 2

# RECIST 1.1 measurability thresholds and axis rules.
NON_NODAL_TARGET_MIN_MM = 10.0  # non-nodal target: LONGEST diameter must be >= 10mm
NODAL_TARGET_MIN_MM = 15.0      # pathological node target: SHORT axis must be >= 15mm
NODAL_CR_MAX_MM = 10.0          # a node is "normalised" (CR-eligible) at short axis < 10mm

# Substrings in finding_type / anatomy / organ that mark a target as a lymph node. "node"
# does not match "nodule" (n-o-d-u-l-e has no "node" substring), so pulmonary/hepatic
# nodules are correctly treated as non-nodal.
_NODAL_HINTS = ("lymph", "nodal", "node")


def _is_nodal(
    *, finding_type: str | None = None, anatomy: str | None = None, organ: str | None = None
) -> bool:
    """RECIST 1.1 measures lymph nodes by their SHORT axis (target threshold 15mm) and all
    other lesions by their LONGEST diameter (10mm). A target is nodal when its
    finding_type/anatomy/organ indicates a lymph node (e.g. finding_type
    ``lymph_node_metastasis`` or anatomy ``mediastinal lymph node``)."""
    for value in (finding_type, anatomy, organ):
        if not value:
            continue
        low = str(value).lower()
        if any(hint in low for hint in _NODAL_HINTS):
            return True
    return False


def validate_selection_caps(selections: list[dict]) -> None:
    """RECIST 1.1 baseline caps + measurability: >=1 target, <=5 total, <=2 per organ, and
    each target measurable (non-nodal longest >=10mm; nodal short axis >=15mm). Pure
    (offline-testable)."""
    if not selections:
        raise UnprocessableEntity("At least one target lesion is required", code="no_targets")
    if len(selections) > MAX_TARGETS:
        raise UnprocessableEntity(
            f"RECIST 1.1 allows at most {MAX_TARGETS} target lesions", code="too_many_targets"
        )
    per_organ: dict[str, int] = {}
    for sel in selections:
        organ = (sel.get("organ") or "unknown").strip().lower()
        per_organ[organ] = per_organ.get(organ, 0) + 1
        if per_organ[organ] > MAX_PER_ORGAN:
            raise UnprocessableEntity(
                f"RECIST 1.1 allows at most {MAX_PER_ORGAN} target lesions per organ "
                f"(organ '{organ}')",
                code="too_many_per_organ",
            )

        # Eligibility: a target lesion must be measurable at baseline. Nodes qualify only
        # at >=15mm short axis; non-nodal lesions only at >=10mm longest diameter.
        baseline_mm = sel.get("baseline_mm")
        if isinstance(baseline_mm, (int, float)) and baseline_mm > 0:
            nodal = _is_nodal(
                finding_type=sel.get("finding_type"),
                anatomy=sel.get("anatomy"),
                organ=sel.get("organ"),
            )
            if nodal and baseline_mm < NODAL_TARGET_MIN_MM:
                raise UnprocessableEntity(
                    f"Pathological lymph-node targets require a short axis >= "
                    f"{NODAL_TARGET_MIN_MM:.0f}mm (got {baseline_mm:g}mm)",
                    code="node_target_too_small",
                )
            if not nodal and baseline_mm < NON_NODAL_TARGET_MIN_MM:
                raise UnprocessableEntity(
                    f"Non-nodal target lesions require a longest diameter >= "
                    f"{NON_NODAL_TARGET_MIN_MM:.0f}mm (got {baseline_mm:g}mm)",
                    code="target_too_small",
                )


async def create_target_selection(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    selected_by: uuid.UUID,
    baseline_report_version_id: uuid.UUID | None,
    selections: list[dict],
) -> TargetLesionSelection:
    run = await get_run(session, org_id=org_id, run_id=run_id)

    validate_selection_caps(selections)

    # Every selected track must be human-confirmed.
    confirmed = await derive_confirmed_tracks(session, org_id=org_id, run_id=run_id)
    confirmed_keys = {c["confirmed_track_key"] for c in confirmed}
    for sel in selections:
        key = sel.get("confirmed_track_key")
        if key not in confirmed_keys:
            raise UnprocessableEntity(
                f"Target lesion '{key}' is not a human-confirmed track", code="unconfirmed_target"
            )

    payload = {
        "run_id": str(run_id),
        "baseline_report_version_id": str(baseline_report_version_id)
        if baseline_report_version_id
        else None,
        "selections": selections,
        "selected_by": str(selected_by),
    }
    row = TargetLesionSelection(
        org_id=org_id,
        patient_id=run.patient_id,
        run_id=run_id,
        baseline_report_version_id=baseline_report_version_id,
        selections=selections,
        selected_by=selected_by,
        signature_sha256=sha256_hex(canonical_json(payload)),
    )
    session.add(row)
    await session.flush()
    return row


async def latest_target_selection(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> TargetLesionSelection | None:
    return (
        await session.execute(
            select(TargetLesionSelection)
            .where(
                TargetLesionSelection.run_id == run_id,
                TargetLesionSelection.org_id == org_id,
            )
            .order_by(TargetLesionSelection.selected_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _mm(measurement: dict[str, Any] | None, *, nodal: bool = False) -> float | None:
    """The RECIST diameter (mm) for one measured event.

    A pre-normalised scalar (``normalized_mm``/``value``) is taken as-is. For a
    bi-dimensional measurement (``values``: [long, short] in either order) RECIST 1.1
    dictates the axis: lymph nodes use the SHORT axis (the smaller value), all other
    lesions the LONGEST diameter (the larger value)."""
    if not measurement:
        return None
    for field in ("normalized_mm", "value"):
        v = measurement.get(field)
        if isinstance(v, (int, float)):
            return float(v)
    values = measurement.get("values")
    if isinstance(values, list) and values:
        nums = [float(x) for x in values if isinstance(x, (int, float))]
        if nums:
            return min(nums) if nodal else max(nums)
    return None


def classify(
    sld: float,
    baseline_sld: float,
    nadir_sld: float,
    new_lesion: bool,
    *,
    cr_eligible: bool | None = None,
) -> str:
    """RECIST 1.1 overall response for a timepoint.

    ``cr_eligible`` carries the structural Complete-Response test computed over the target
    lesions: every non-nodal target has disappeared AND every nodal target has regressed to
    < 10mm short axis. When it is None (scalar-only callers) we fall back to the SLD summing
    to zero — but that fallback makes CR unreachable whenever a target is a lymph node
    (nodes floor near their short axis and never reach 0), which is exactly the bug the
    per-target signal fixes."""
    if new_lesion:
        return "PD"
    if baseline_sld <= 0:
        return "NE"
    is_cr = (sld == 0) if cr_eligible is None else cr_eligible
    if is_cr:
        return "CR"
    pct_baseline = (sld - baseline_sld) / baseline_sld * 100.0
    pct_nadir = (sld - nadir_sld) / nadir_sld * 100.0 if nadir_sld > 0 else 0.0
    abs_increase = sld - nadir_sld
    if pct_nadir >= 20.0 and abs_increase >= 5.0:
        return "PD"
    if pct_baseline <= -30.0:
        return "PR"
    return "SD"


async def _worksheet(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[TargetLesionSelection, list[dict], list[dict], dict[str, dict]]:
    """The RECIST worksheet for a run, computed and NOT persisted.

    Split out of ``compute_recist`` so a read-only caller (the progression view) can render
    the same numbers a reviewer would compute, without writing assessment rows or needing
    the reviewer role. ``compute_recist`` is this plus ``_persist``.
    """
    await get_run(session, org_id=org_id, run_id=run_id)

    confirmed = await derive_confirmed_tracks(session, org_id=org_id, run_id=run_id)
    if not confirmed:
        raise UnprocessableEntity(
            "No human-confirmed tracks; confirm track links before computing RECIST.",
            code="no_confirmed_tracks",
        )
    selection = await latest_target_selection(session, org_id=org_id, run_id=run_id)
    if selection is None:
        raise UnprocessableEntity(
            "No target-lesion selection; a clinician must select target lesions first.",
            code="no_target_selection",
        )

    confirmed_by_key = {c["confirmed_track_key"]: c for c in confirmed}

    # Per target lesion: sorted (date, mm) series from measured events + human baseline_mm.
    targets: list[dict] = []
    for sel in selection.selections:
        key = sel.get("confirmed_track_key")
        track = confirmed_by_key.get(key)
        is_nodal = _is_nodal(
            finding_type=track.get("finding_type") if track else None,
            anatomy=track.get("anatomy") if track else None,
            organ=sel.get("organ"),
        )
        series: list[tuple[datetime, float]] = []
        if track:
            for ev in track["events"]:
                mm = _mm(ev.get("measurement"), nodal=is_nodal)
                if mm is not None and ev.get("date"):
                    series.append((datetime.fromisoformat(ev["date"]), mm))
        series.sort(key=lambda x: x[0])
        targets.append(
            {
                "confirmed_track_key": key,
                "organ": sel.get("organ"),
                "is_nodal": is_nodal,
                "baseline_mm": float(sel.get("baseline_mm") or 0.0),
                "series": series,
            }
        )

    # Timepoints = union of all measured dates across targets (sorted).
    timepoints = sorted({d for t in targets for d, _ in t["series"]})
    baseline_sld = sum(t["baseline_mm"] for t in targets)

    # New-lesion signal: a confirmed NON-target track (present) first appearing after the
    # earliest timepoint => unconditional PD at that timepoint.
    target_keys = {t["confirmed_track_key"] for t in targets}
    new_lesion_dates = _new_lesion_dates(confirmed, target_keys, timepoints[:1])

    # The per-timepoint SLD/nadir/classification loop is shared with the naive-vs-confirmed
    # contrast endpoint (compute_contrast) so both compute RECIST identically — the only
    # difference is which track set feeds ``targets``.
    assessments = compute_timeline(targets, new_lesion_dates)
    return selection, targets, assessments, confirmed_by_key


async def compute_recist(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict:
    """Compute + persist per-timepoint RECIST over confirmed target tracks. 422 if there
    are no confirmed tracks or no target selection."""
    selection, targets, assessments, _ = await _worksheet(
        session, org_id=org_id, run_id=run_id
    )
    baseline_sld = sum(t["baseline_mm"] for t in targets)

    await _persist(
        session, org_id=org_id, run_id=run_id, selection=selection, assessments=assessments,
        targets=targets,
    )

    return {
        "run_id": str(run_id),
        "target_selection_id": str(selection.id),
        "baseline_sld_mm": baseline_sld,
        "targets": [
            {
                "confirmed_track_key": t["confirmed_track_key"],
                "organ": t["organ"],
                "baseline_mm": t["baseline_mm"],
            }
            for t in targets
        ],
        "assessments": [
            {
                **a,
                "assessment_date": a["assessment_date"].isoformat(),
            }
            for a in assessments
        ],
    }


def _name_from_key(key: str) -> dict:
    """Track keys are ``finding_type|anatomy|laterality[|…]``, so a lesion that is not
    currently confirmed can still be named — which is what the "waiting on
    re-confirmation" list needs."""
    parts = (key or "").split("|")
    return {
        "finding_type": parts[0] if len(parts) > 0 else None,
        "anatomy": parts[1] if len(parts) > 1 else None,
        "laterality": parts[2] if len(parts) > 2 else None,
    }


def _display_name(track: dict) -> str:
    """A lesion label a clinician reads, built from the same tokens as the track key."""
    finding = (track.get("finding_type") or "").replace("_", " ").strip()
    anatomy = (track.get("anatomy") or "").replace("_", " ").strip()
    laterality = (track.get("laterality") or "").strip()
    if laterality in {"not_applicable", "unknown", ""}:
        laterality = ""
    # "Liver metastasis — liver" says liver twice. Drop the site when it adds nothing,
    # but keep it whenever laterality needs somewhere to attach ("— right lung").
    if not laterality and anatomy and anatomy.lower() in finding.lower():
        anatomy = ""
    site = " ".join(p for p in (laterality, anatomy) if p)
    label = " — ".join(p for p in (finding, site) if p)
    return label[:1].upper() + label[1:] if label else ""


async def progression(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict:
    """Read-only disease trajectory for one run: per-lesion diameters over time plus the
    SLD timeline, the baseline, and the nadir the PD test is measured against.

    ``compute_recist`` already returns the SLD timeline, but not the per-lesion series it
    was summed from — so a reader can see the total move without seeing which lesion moved
    it. This adds that, and names the nadir timepoint, because RECIST progression is
    measured against the smallest the disease ever got, not against the previous scan.
    Nothing here is persisted; it recomputes what a reviewer would compute.
    """
    _, targets, assessments, confirmed_by_key = await _worksheet(
        session, org_id=org_id, run_id=run_id
    )

    nadir_date = None
    if assessments:
        smallest = min(assessments, key=lambda a: a["sld_mm"])
        nadir_date = smallest["assessment_date"]

    # A selected target that is not in the confirmed set on THIS run has no series, so the
    # trajectory is incomplete and the page must say why rather than imply the reports
    # carried no measurements. On an incremental run this is the normal state: identities
    # whose new evidence moved the RECIST call are reopened for re-attestation.
    unconfirmed = [
        {
            "confirmed_track_key": t["confirmed_track_key"],
            "display_name": _display_name(_name_from_key(t["confirmed_track_key"]))
            or t["confirmed_track_key"],
        }
        for t in targets
        if t["confirmed_track_key"] not in confirmed_by_key
    ]

    out_targets = []
    for t in targets:
        key = t["confirmed_track_key"]
        track = confirmed_by_key.get(key) or _name_from_key(key)
        out_targets.append(
            {
                "confirmed_track_key": t["confirmed_track_key"],
                "display_name": _display_name(track) or t["confirmed_track_key"],
                "finding_type": track.get("finding_type"),
                "anatomy": track.get("anatomy"),
                "organ": t["organ"],
                "is_nodal": t["is_nodal"],
                "baseline_mm": t["baseline_mm"],
                "series": [
                    {"date": d.date().isoformat(), "mm": mm} for d, mm in t["series"]
                ],
            }
        )

    return {
        "run_id": str(run_id),
        "baseline_sld_mm": sum(t["baseline_mm"] for t in targets),
        "baseline_date": assessments[0]["assessment_date"].date().isoformat()
        if assessments
        else None,
        "nadir_sld_mm": min((a["sld_mm"] for a in assessments), default=None),
        "nadir_date": nadir_date.date().isoformat() if nadir_date else None,
        "targets": out_targets,
        "unconfirmed_targets": unconfirmed,
        "timeline": [
            {
                "date": a["assessment_date"].date().isoformat(),
                "sld_mm": a["sld_mm"],
                "pct_from_baseline": a["pct_from_baseline"],
                "pct_from_nadir": a["pct_from_nadir"],
                # RECIST 1.1 needs BOTH >=20% and >=5mm over nadir to call PD, so the
                # absolute rise is a value the reader has to see, not derive.
                "abs_from_nadir_mm": a["sld_mm"] - a["nadir_sld_mm"],
                "classification": a["classification"],
                "new_lesion": a["new_lesion"],
            }
            for a in assessments
        ],
    }


def _mm_at(series: list[tuple[datetime, float]], when: datetime) -> float | None:
    """Carry-forward: the last measurement at or before ``when``."""
    latest = None
    for d, mm in series:
        if d <= when:
            latest = mm
        else:
            break
    return latest


def _new_lesion_dates(
    confirmed: list[dict], target_keys: set[str], baseline_tp: list[datetime]
) -> set[datetime]:
    if not baseline_tp:
        return set()
    baseline_date = baseline_tp[0]
    dates: set[datetime] = set()
    for c in confirmed:
        if c["confirmed_track_key"] in target_keys:
            continue
        present_dates = [
            datetime.fromisoformat(ev["date"])
            for ev in c["events"]
            if ev.get("date") and ev.get("assertion") == "present"
        ]
        if not present_dates:
            continue
        first = min(present_dates)
        if first > baseline_date:
            dates.add(first)
    return dates


async def _persist(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    selection: TargetLesionSelection,
    assessments: list[dict],
    targets: list[dict],
) -> None:
    run = await get_run(session, org_id=org_id, run_id=run_id)
    inputs = {
        "targets": [
            {
                "confirmed_track_key": t["confirmed_track_key"],
                "organ": t["organ"],
                "baseline_mm": t["baseline_mm"],
            }
            for t in targets
        ]
    }
    # recist_assessments is append-only with a unique (run_id, target_selection_id,
    # assessment_date) index. A re-compute is deterministic, so ignore-on-conflict keeps
    # the endpoint idempotent without violating immutability.
    for a in assessments:
        stmt = (
            pg_insert(RecistAssessment.__table__)
            .values(
                org_id=org_id,
                patient_id=run.patient_id,
                run_id=run_id,
                target_selection_id=selection.id,
                assessment_date=a["assessment_date"],
                sld_mm=a["sld_mm"],
                baseline_sld_mm=a["baseline_sld_mm"],
                nadir_sld_mm=a["nadir_sld_mm"],
                pct_from_baseline=a["pct_from_baseline"],
                pct_from_nadir=a["pct_from_nadir"],
                classification=a["classification"],
                new_lesion=a["new_lesion"],
                inputs=inputs,
            )
            .on_conflict_do_nothing(
                index_elements=["run_id", "target_selection_id", "assessment_date"]
            )
        )
        await session.execute(stmt)
    await session.flush()


# ===========================================================================
# Shared timeline math (used by compute_recist AND the contrast endpoint)
# ===========================================================================
def _series_from_events(
    events: list[dict], *, is_nodal: bool
) -> list[tuple[datetime, float]]:
    """Sorted (date, mm) series from a track's event list (machine or confirmed shape)."""
    series: list[tuple[datetime, float]] = []
    for ev in events:
        mm = _mm(ev.get("measurement"), nodal=is_nodal)
        date = ev.get("date")
        if mm is not None and date:
            series.append((datetime.fromisoformat(date), mm))
    series.sort(key=lambda x: x[0])
    return series


def compute_timeline(
    targets: list[dict], new_lesion_dates: set[datetime]
) -> list[dict]:
    """Per-timepoint SLD / nadir / RECIST classification over a set of target lesions.

    Each target dict needs ``series`` ([(datetime, mm)]), ``baseline_mm`` and ``is_nodal``.
    Pure and offline-testable. This is the single RECIST engine both the confirmed worksheet
    and the naive-vs-confirmed contrast run through — the ONLY difference between naive and
    confirmed is which tracks populate ``targets`` / ``new_lesion_dates``."""
    timepoints = sorted({d for t in targets for d, _ in t["series"]})
    baseline_sld = sum(t["baseline_mm"] for t in targets)
    assessments: list[dict] = []
    nadir = baseline_sld if baseline_sld > 0 else None
    for tp in timepoints:
        sld = 0.0
        # CR is structural: every non-nodal target gone AND every nodal target < 10mm short
        # axis. Carried-forward baseline values (no measurement at tp) keep CR conservative.
        cr_eligible = True
        for t in targets:
            mm = _mm_at(t["series"], tp)
            val = mm if mm is not None else t["baseline_mm"]
            sld += val
            if t["is_nodal"]:
                if val >= NODAL_CR_MAX_MM:
                    cr_eligible = False
            elif val != 0:
                cr_eligible = False
        if nadir is None:
            nadir = sld
        nadir = min(nadir, sld)
        new_lesion = tp in new_lesion_dates
        classification = classify(sld, baseline_sld, nadir, new_lesion, cr_eligible=cr_eligible)
        pct_baseline = (sld - baseline_sld) / baseline_sld * 100.0 if baseline_sld > 0 else None
        pct_nadir = (sld - nadir) / nadir * 100.0 if nadir and nadir > 0 else None
        assessments.append(
            {
                "assessment_date": tp,
                "sld_mm": sld,
                "baseline_sld_mm": baseline_sld,
                "nadir_sld_mm": nadir,
                "pct_from_baseline": pct_baseline,
                "pct_from_nadir": pct_nadir,
                "classification": classification,
                "new_lesion": new_lesion,
            }
        )
    return assessments


# Best-overall-response ranking. Progression trumps: any PD timepoint => PD best overall
# (a real patient who progressed at any scan is a treatment failure), otherwise the best
# achieved response wins (CR > PR > SD > NE).
_BOR_RANK = {"NE": 0, "SD": 1, "PR": 2, "CR": 3}


def best_overall(classifications: list[str]) -> str:
    if not classifications:
        return "NE"
    if any(c == "PD" for c in classifications):
        return "PD"
    return max(classifications, key=lambda c: _BOR_RANK.get(c, 0))


def _side_summary(
    rows: list[dict],
    targets: list[dict],
    *,
    source: str,
    nontarget_keys: list[str] | None = None,
) -> dict:
    """One side of the contrast: best-overall classification + full SLD timeline + the target
    track set + a plain-language rationale."""
    classifications = [r["classification"] for r in rows]
    best = best_overall(classifications)
    any_new = any(r["new_lesion"] for r in rows)
    return {
        "classification": best,
        "sld_timeline": [
            {
                "assessment_date": r["assessment_date"].isoformat(),
                "sld_mm": r["sld_mm"],
                "baseline_sld_mm": r["baseline_sld_mm"],
                "nadir_sld_mm": r["nadir_sld_mm"],
                "pct_from_baseline": r["pct_from_baseline"],
                "pct_from_nadir": r["pct_from_nadir"],
                "classification": r["classification"],
                "new_lesion": r["new_lesion"],
            }
            for r in rows
        ],
        "target_tracks": [
            {
                "track_key": t["track_key"],
                "organ": t["organ"],
                "baseline_mm": t["baseline_mm"],
                "is_nodal": t["is_nodal"],
                "source": source,
            }
            for t in targets
        ],
        "new_lesion": any_new,
        "rationale": _rationale(best, any_new, source, nontarget_keys),
    }


def _rationale(
    best: str, any_new: bool, source: str, nontarget_keys: list[str] | None
) -> str:
    if source == "machine":
        if any_new and nontarget_keys:
            return (
                f"Over the machine tracks as-is, {', '.join(nontarget_keys)} first appears "
                f"after baseline, so RECIST's new-lesion rule fires -> best overall {best}. "
                f"This reflects the deterministic linker's split, not a confirmed new lesion."
            )
        return f"Over the machine tracks as-is, best overall response is {best}."
    if any_new:
        return f"Over human-confirmed tracks a genuine new lesion drives best overall {best}."
    return (
        f"After applying the human link decisions (merging the split tracks), no new lesion "
        f"remains and the SLD trend gives best overall {best}."
    )


def build_confirmed_side(selections: list[dict], confirmed_by_key: dict[str, dict]) -> dict:
    """RECIST over the human-confirmed track set (merges applied). Pure."""
    targets: list[dict] = []
    for sel in selections:
        key = sel.get("confirmed_track_key")
        track = confirmed_by_key.get(key)
        is_nodal = _is_nodal(
            finding_type=track.get("finding_type") if track else None,
            anatomy=track.get("anatomy") if track else None,
            organ=sel.get("organ"),
        )
        series = _series_from_events(track["events"], is_nodal=is_nodal) if track else []
        targets.append(
            {
                "track_key": key,
                "organ": sel.get("organ"),
                "is_nodal": is_nodal,
                "baseline_mm": float(sel.get("baseline_mm") or 0.0),
                "series": series,
            }
        )
    timepoints = sorted({d for t in targets for d, _ in t["series"]})
    target_keys = {t["track_key"] for t in targets}
    new_lesion_dates = _new_lesion_dates(
        list(confirmed_by_key.values()), target_keys, timepoints[:1]
    )
    rows = compute_timeline(targets, new_lesion_dates)
    return _side_summary(rows, targets, source="confirmed")


def build_naive_side(
    selections: list[dict],
    member_map: dict[str, list[str]],
    machine: dict[str, dict],
) -> dict:
    """RECIST over the MACHINE tracks as-is (human merges NOT applied).

    For each selected target we expand its confirmed identity back to the underlying machine
    tracks. When a target was merged from several machine tracks (a false split), the machine
    track carrying the baseline measurement becomes the naive target and the other members
    become non-targets — so a member that first appears after baseline fires the new-lesion
    rule (the false PD). Pure."""
    naive_targets: list[dict] = []
    naive_nontargets: list[dict] = []
    for sel in selections:
        key = sel.get("confirmed_track_key")
        member_keys = member_map.get(key) or [key]
        members: list[dict] = []
        for mk in member_keys:
            m = machine.get(mk)
            if not m:
                continue
            is_nodal = _is_nodal(
                finding_type=m.get("finding_type"),
                anatomy=m.get("anatomy"),
                organ=sel.get("organ"),
            )
            members.append(
                {
                    "track_key": mk,
                    "series": _series_from_events(m["events"], is_nodal=is_nodal),
                    "is_nodal": is_nodal,
                    "events": m["events"],
                }
            )
        if not members:
            continue
        with_series = [m for m in members if m["series"]]
        baseline_member = (
            min(with_series, key=lambda m: m["series"][0][0]) if with_series else members[0]
        )
        naive_targets.append(
            {
                "track_key": baseline_member["track_key"],
                "organ": sel.get("organ"),
                "is_nodal": baseline_member["is_nodal"],
                "baseline_mm": float(sel.get("baseline_mm") or 0.0),
                "series": baseline_member["series"],
            }
        )
        naive_nontargets.extend(
            m for m in members if m["track_key"] != baseline_member["track_key"]
        )

    timepoints = sorted({d for t in naive_targets for d, _ in t["series"]})
    baseline_date = timepoints[0] if timepoints else None
    new_lesion_dates: set[datetime] = set()
    if baseline_date is not None:
        for nt in naive_nontargets:
            present = [
                datetime.fromisoformat(ev["date"])
                for ev in nt["events"]
                if ev.get("date") and ev.get("assertion") == "present"
            ]
            if present and min(present) > baseline_date:
                new_lesion_dates.add(min(present))
    rows = compute_timeline(naive_targets, new_lesion_dates)
    return _side_summary(
        rows,
        naive_targets,
        source="machine",
        nontarget_keys=[nt["track_key"] for nt in naive_nontargets],
    )


async def _machine_tracks(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict[str, dict]:
    """All machine tracks for a run (org-scoped) with their raw events — the un-linked set
    that feeds the naive computation."""
    tracks = (
        await session.execute(
            select(Track).where(Track.run_id == run_id, Track.org_id == org_id)
        )
    ).scalars().all()
    by_id = {t.id: t for t in tracks}
    machine: dict[str, dict] = {
        t.track_key: {
            "finding_type": t.finding_type,
            "anatomy": t.anatomy,
            "laterality": t.laterality,
            "events": [],
        }
        for t in tracks
    }
    if tracks:
        events = (
            await session.execute(
                select(TrackEvent)
                .where(TrackEvent.track_id.in_([t.id for t in tracks]))
                .order_by(TrackEvent.event_date)
            )
        ).scalars().all()
        for e in events:
            tk = by_id[e.track_id].track_key
            machine[tk]["events"].append(
                {
                    "date": e.event_date.isoformat() if e.event_date else None,
                    "assertion": e.assertion,
                    "measurement": e.measurement,
                }
            )
    return machine


def _contrast_note(naive: dict, confirmed: dict | None, discrepancy: bool) -> str:
    if confirmed is None:
        return (
            "No confirmed merge affects the target lesions yet; showing the naive result over "
            "the machine tracks. Merge any false-split tracks to see the corrected RECIST call."
        )
    if discrepancy:
        return (
            f"Naive RECIST over the machine tracks = {naive['classification']} (driven by a "
            f"false split), but after the human link decisions the confirmed call is "
            f"{confirmed['classification']}. One merge flips the response."
        )
    return (
        f"Naive and confirmed RECIST agree ({confirmed['classification']}); the human link "
        f"decisions did not change the response."
    )


async def compute_contrast(
    session: AsyncSession, *, org_id: uuid.UUID, run_id: uuid.UUID
) -> dict:
    """The money-moment endpoint: naive (machine tracks as-is) vs confirmed (human merges
    applied) RECIST, side by side. Never 422 — the whole point is to surface the contrast, so
    a run without a confirmed merge / target selection returns confirmed=null."""
    await get_run(session, org_id=org_id, run_id=run_id)
    selection = await latest_target_selection(session, org_id=org_id, run_id=run_id)
    if selection is None:
        return {
            "run_id": str(run_id),
            "naive": None,
            "confirmed": None,
            "discrepancy": False,
            "discrepancy_note": (
                "No target-lesion selection yet; select target lesions to compute the "
                "naive-vs-confirmed RECIST contrast."
            ),
        }

    confirmed_tracks = await derive_confirmed_tracks(session, org_id=org_id, run_id=run_id)
    confirmed_by_key = {c["confirmed_track_key"]: c for c in confirmed_tracks}
    member_map = {c["confirmed_track_key"]: list(c["member_track_keys"]) for c in confirmed_tracks}
    machine = await _machine_tracks(session, org_id=org_id, run_id=run_id)

    naive = build_naive_side(selection.selections, member_map, machine)

    # A "confirmed merge" is a selected target whose confirmed identity folds >1 machine track.
    has_merge = any(
        len(member_map.get(sel.get("confirmed_track_key")) or []) > 1
        for sel in selection.selections
    )
    confirmed = (
        build_confirmed_side(selection.selections, confirmed_by_key)
        if confirmed_tracks and has_merge
        else None
    )
    discrepancy = confirmed is not None and naive["classification"] != confirmed["classification"]
    return {
        "run_id": str(run_id),
        "naive": naive,
        "confirmed": confirmed,
        "discrepancy": discrepancy,
        "discrepancy_note": _contrast_note(naive, confirmed, discrepancy),
    }
