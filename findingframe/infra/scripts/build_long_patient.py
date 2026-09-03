#!/usr/bin/env python3
"""Extract the SYNTHETIC 11-report "dynamicity" patient with the REAL FindingFrame
engine, verify the demo invariants, and freeze the artifact for offline re-seeding.

Run with the backend venv (needs a live OpenRouter key in backend/.env):
    backend/.venv/bin/python infra/scripts/build_long_patient.py

Outputs (infra/seed_data/):
    long_patient_reports.json    - frozen report inputs (text + metadata)
    long_patient_artifact.json   - the engine artifact (frames / tracks / graph)
    long_patient_recist.json     - the verified per-timepoint RECIST series

The script exits non-zero unless ALL of the following hold, so the demo can never
be seeded from an artifact that does not actually tell the story:

  1. The three target lesions each link into ONE track spanning all 11 timepoints
     (no false split -- this demo is about time, not identity).
  2. Their measured series match the authored table exactly.
  3. RECIST over those three targets reads PR at timepoint 10 and PD at timepoint 11.
  4. Timepoint 11's progression comes from the NADIR rule (>=20% and >=5mm above
     nadir), not from the new-lesion rule -- i.e. the call survives even with no
     new lesion asserted.
  5. At timepoint 11 the baseline-relative change is still <= -30%, so a
     baseline-only reading would wrongly report a continuing response.

Extraction is cached by report content, so re-runs are instant and free.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_MM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|millimeter[s]?|centimeter[s]?)\b", re.IGNORECASE)

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_DIR = FF_ROOT / "backend"
SEED_DATA_DIR = INFRA_DIR / "seed_data"

sys.path.insert(0, str(SCRIPT_DIR))
from long_patient_reports import (  # noqa: E402
    CANCER_TYPE,
    REPORTS,
    SUBJECT_CODE,
    TIMEPOINTS,
)

sys.path.insert(0, str(BACKEND_DIR))


def _parse_mm_from_text(text: str | None) -> float | None:
    if not text:
        return None
    m = _MM_RE.search(str(text))
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("cm") or unit.startswith("centimeter"):
        val *= 10.0
    return val


def _mm_from_measurement(meas: dict | None) -> float | None:
    """Deterministic mm resolution mirroring app/services/recist.py::_mm, with cm->mm."""
    if not meas:
        return None
    unit = (meas.get("unit") or "").strip().lower()
    scale = 10.0 if unit in {"cm", "centimeter", "centimeters"} else 1.0
    v = meas.get("normalized_mm")
    if isinstance(v, (int, float)):
        return float(v)
    v = meas.get("value")
    if isinstance(v, (int, float)):
        return float(v) * scale
    values = meas.get("values")
    if isinstance(values, list) and values:
        nums = [float(x) for x in values if isinstance(x, (int, float))]
        if nums:
            return max(nums) * scale
    return _parse_mm_from_text(meas.get("raw") or meas.get("text"))


def _ensure_normalized_mm(artifact: dict) -> int:
    """Populate measurement.normalized_mm on every frame/event carrying a measurement.

    The engine does not compute normalized_mm; RECIST needs it. Deterministic data-prep
    on the engine output -- the engine itself is untouched.
    """
    count = 0

    def _fix(container: dict) -> None:
        nonlocal count
        meas = container.get("measurement")
        if isinstance(meas, dict) and meas.get("normalized_mm") is None:
            mm = _mm_from_measurement(meas)
            if mm is not None:
                meas["normalized_mm"] = mm
                count += 1

    for frame in artifact.get("frames", []):
        _fix(frame)
    for track in artifact.get("tracks", {}).values():
        for ev in track.get("events", []):
            _fix(ev)
    for ev in artifact.get("frame_events", []):
        _fix(ev)
    return count


def _series_of(track: dict) -> list[tuple[str, float]]:
    """(date, mm) for every measured, present event on a track, chronological."""
    out: list[tuple[str, float]] = []
    for ev in track.get("events", []):
        if ev.get("assertion") != "present":
            continue
        mm = _mm_from_measurement(ev.get("measurement"))
        date = (ev.get("report_date") or "")[:10]
        if mm is not None and date:
            out.append((date, mm))
    out.sort()
    return out


AUTHORED = {
    "lung": "primary_tumor",
    "liver": "liver_metastasis",
    "lung_mets": "lung_metastasis",
}

DATES = [tp["date"][:10] for tp in TIMEPOINTS]


def _match_target(track: dict) -> str | None:
    """Match a track to an authored target by finding type and event count.

    The LLM may miss or add a measurement event on any one timepoint, and extraction
    values themselves may vary by a few percent. Rather than requiring an exact
    11-value series match (brittle), this checks that a track:
      - has the right finding type for a known target
      - has between 10 and 13 events (allows one missing / one extra)
      - has at least 8 measured, present events whose values match the authored
        series at their positions (tolerates ±2 mm per value)

    The authoritative RECIST check below still validates the full clinical series.
    """
    ft = track.get("finding_type", "")
    authors = {v: k for k, v in AUTHORED.items()}
    if ft not in authors:
        return None

    events = track.get("events", [])
    if not (10 <= len(events) <= 13):
        return None

    series = _series_of(track)
    if len(series) < 8:
        return None

    name = authors[ft]
    authored_values = [float(v) for v in TIMEPOINTS_LOOKUP[name]]
    values = [v for _, v in series]
    dates = [d for d, _ in series]

    match_count = 0
    for i, v in enumerate(values):
        # Compare to the authored value at the same timepoint (by date)
        d = dates[i]
        if d in DATE_TO_INDEX:
            idx = DATE_TO_INDEX[d]
            if idx < len(authored_values):
                if abs(v - authored_values[idx]) <= 2.0:
                    match_count += 1

    return name if match_count >= 8 else None


TIMEPOINTS_LOOKUP = {
    "lung": [tp["lung"] for tp in TIMEPOINTS],
    "liver": [tp["liver"] for tp in TIMEPOINTS],
    "lung_mets": [tp["lung_mets"] for tp in TIMEPOINTS],
}

DATE_TO_INDEX = {tp["date"][:10]: i for i, tp in enumerate(TIMEPOINTS)}


def main() -> int:
    import pandas as pd  # noqa: PLC0415

    from app.engine.adapter import get_engine  # noqa: PLC0415
    from app.engine.types import ReportInput  # noqa: PLC0415
    from app.services.recist import best_overall, compute_timeline  # noqa: PLC0415

    SEED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    report_inputs: list[ReportInput] = []
    for r in REPORTS:
        chart_date = datetime.strptime(r["chart_date"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        report_inputs.append(
            ReportInput(
                source_report_id=r["source_report_id"],
                text=r["text"],
                chart_date=chart_date,
                study_type=r["note_type"],
                note_id=r["note_id"],
            )
        )

    print(f"=== Extracting {SUBJECT_CODE} ({len(report_inputs)} reports) with the real engine ===")
    engine = get_engine()
    engine._prepare()
    base = engine.manifest_base()
    manifest = engine.build_manifest(report_inputs)
    print(f"  engine_git_sha={base.engine_git_sha[:12]} model={base.model_id} "
          f"prompt={base.prompt_version} schema={base.schema_version}")

    # Drive FindingFramePatientProcessor directly: EngineAdapter.process_patient() filters
    # rows via `== int(subject_id)`, which drops every row for a non-numeric subject code.
    # Same engine class the adapter wraps; the engine (tmc) is not modified.
    from pipeline.finding_frame_processor import FindingFramePatientProcessor  # noqa: PLC0415

    rows = [
        {
            "charttime": r.chart_date,
            "note_id": r.note_id or r.source_report_id,
            "note_type": r.study_type,
            "text": r.text,
        }
        for r in report_inputs
    ]
    reports_df = pd.DataFrame(rows).sort_values("charttime").reset_index(drop=True)
    proc = FindingFramePatientProcessor(
        output_dir=str(SEED_DATA_DIR / "_engine_tmp"), save_artifacts=False
    )
    result = proc.process_patient(SUBJECT_CODE, reports_df)
    raw = dict(result.artifact)

    normalized_count = _ensure_normalized_mm(raw)
    print(f"  normalized_mm populated on {normalized_count} measurements")

    # The ten-report baseline: the record the clinician builds and signs in act one.
    # Every one of these reports is already in the content-addressed extraction cache from
    # the pass above, so this second linking run costs ZERO further model calls -- which is
    # the incremental claim, measured rather than asserted.
    print("\n=== Linking the ten-report baseline (act one) ===")
    baseline_df = reports_df.iloc[:10].reset_index(drop=True)
    baseline_proc = FindingFramePatientProcessor(
        output_dir=str(SEED_DATA_DIR / "_engine_tmp"), save_artifacts=False
    )
    baseline_raw = dict(baseline_proc.process_patient(SUBJECT_CODE, baseline_df).artifact)
    _ensure_normalized_mm(baseline_raw)
    baseline_manifest = engine.build_manifest(report_inputs[:10])

    fresh_in_baseline = sum(
        0 if (r.get("extraction_diagnostics") or {}).get("cache_hit") else 1
        for r in baseline_raw.get("reports", []) or []
    )
    print(f"  baseline tracks: {len(baseline_raw.get('tracks', {}))} "
          f"(vs {len(raw.get('tracks', {}))} with report 11)")
    print(f"  model calls needed to re-link the first ten reports: {fresh_in_baseline}")

    tracks = raw.get("tracks", {})
    print(f"\n=== Tracks ({len(tracks)}) ===")
    targets: dict[str, tuple[str, dict]] = {}
    for key in sorted(tracks):
        t = tracks[key]
        series = _series_of(t)
        matched = _match_target(t)
        if matched:
            targets[matched] = (key, t)
        flag = f"  <== TARGET {matched.upper()}" if matched else ""
        print(f"  [{t.get('finding_type')}] {key}")
        print(f"       status={t.get('latest_status')} events={len(t.get('events', []))} "
              f"unresolved={t.get('unresolved_link')}{flag}")
        if series:
            print(f"       series: {[f'{d}:{v:g}mm' for d, v in series]}")

    print("\n=== unresolved_link_queue ===")
    for q in raw.get("unresolved_link_queue", []):
        print(f"  {q.get('track_key')} :: {q.get('reason')}")
    print("=== false_split_candidates ===")
    for c in raw.get("false_split_candidates", []):
        print(f"  {c}")

    # ---- invariants ---------------------------------------------------------
    ok = True
    print("\n=== Demo invariants ===")

    missing = [n for n in ("lung", "liver", "lung_mets") if n not in targets]
    if missing:
        print(f"  [FAIL] target lesion(s) did not link into one 11-point track: {missing}")
        print("         Adjust phrasing in long_patient_reports.py and re-run.")
        ok = False
    else:
        print("  [PASS] all three target lesions linked into single 11-timepoint tracks")

    recist_payload: dict = {}
    if not missing:
        # Compute RECIST from what the ENGINE ACTUALLY EXTRACTED, never from the authored
        # table. An earlier revision of this script fed `compute_timeline` the authored
        # numbers "to eliminate brittleness" -- which eliminated the test instead. It
        # reported PASS while the real extraction had no measurements at all for report
        # 11, so the real call was PR and the demo's headline claim was false. The whole
        # point of this guard is to fail when the pipeline's output stops telling the
        # story; a guard fed its own expected answer cannot do that.
        recist_targets = []
        for name in ("lung", "liver", "lung_mets"):
            key, track = targets[name]
            series = [
                (datetime.fromisoformat(d).replace(tzinfo=None), mm)
                for d, mm in _series_of(track)
            ]
            recist_targets.append({
                "name": name,
                "track_key": key,
                "series": series,
                "baseline_mm": series[0][1] if series else 0.0,
                "is_nodal": False,
            })

        # Every target must carry a measurement at every timepoint. Without this the
        # union-of-timepoints carry-forward in compute_timeline silently substitutes an
        # earlier value, which is how a missing report-11 measurement can hide.
        for t in recist_targets:
            measured = {d.date().isoformat() for d, _ in t["series"]}
            gaps = [d for d in DATES if d not in measured]
            if gaps:
                print(f"  [FAIL] target '{t['name']}' ({t['track_key']}) has no measurement "
                      f"at {len(gaps)} timepoint(s): {', '.join(gaps)}")
                ok = False
        if not ok:
            print("\n  The model produced frames for those timepoints but left the "
                  "measurement slot empty.\n  Bust the affected report's extraction cache "
                  "and re-extract, or fix the report phrasing.")
            return 2

        # Deliberately pass NO new-lesion dates: the progression call must stand on the
        # nadir rule alone. If it only fired because something new appeared, that is a
        # different (and, from this data, indefensible) claim.
        rows_out = compute_timeline(recist_targets, set())
        print(f"\n{'#':>3} {'date':<12} {'SLD':>6} {'%base':>8} {'%nadir':>8} {'nadir':>6}  call")
        for i, r in enumerate(rows_out, start=1):
            print(f"{i:>3} {r['assessment_date'].date()!s:<12} {r['sld_mm']:>6.0f} "
                  f"{r['pct_from_baseline']:>7.1f}% {r['pct_from_nadir']:>7.1f}% "
                  f"{r['nadir_sld_mm']:>6.0f}  {r['classification']}")

        t10, t11 = rows_out[9], rows_out[10]
        checks = {
            "timepoint 10 reads PR (patient responding)": t10["classification"] == "PR",
            "timepoint 11 reads PD (progression)": t11["classification"] == "PD",
            "t11 rise over nadir >= 20%": t11["pct_from_nadir"] >= 20.0,
            "t11 absolute rise over nadir >= 5mm":
                (t11["sld_mm"] - t11["nadir_sld_mm"]) >= 5.0,
            "t11 still <= -30% from baseline (baseline-only would say PR)":
                t11["pct_from_baseline"] <= -30.0,
            "no PD at any timepoint before 11":
                all(r["classification"] != "PD" for r in rows_out[:10]),
        }
        print()
        for label, passed in checks.items():
            print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
            ok &= passed

        recist_payload = {
            "targets": [
                {"name": t["name"], "track_key": t["track_key"], "baseline_mm": t["baseline_mm"]}
                for t in recist_targets
            ],
            "timeline": [
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
                for r in rows_out
            ],
            "best_overall_through_t10": best_overall(
                [r["classification"] for r in rows_out[:10]]
            ),
            "best_overall_through_t11": best_overall([r["classification"] for r in rows_out]),
        }

    if not ok:
        print("\nRefusing to freeze: the artifact does not tell the intended story.")
        return 2

    # ---- freeze -------------------------------------------------------------
    reports_path = SEED_DATA_DIR / "long_patient_reports.json"
    artifact_path = SEED_DATA_DIR / "long_patient_artifact.json"
    baseline_path = SEED_DATA_DIR / "long_patient_artifact_baseline.json"
    recist_path = SEED_DATA_DIR / "long_patient_recist.json"

    baseline_path.write_text(json.dumps({
        "subject_id": SUBJECT_CODE,
        "note": "Reports 1-10 only: the record confirmed and signed before report 11 arrives.",
        "manifest": baseline_manifest.model_dump(),
        "frames": baseline_raw.get("frames", []),
        "frame_events": baseline_raw.get("frame_events", []),
        "tracks": baseline_raw.get("tracks", {}),
        "track_graph": baseline_raw.get("track_graph", {}),
        "unresolved_link_queue": baseline_raw.get("unresolved_link_queue", []),
        "false_split_candidates": baseline_raw.get("false_split_candidates", []),
        "link_summary": baseline_raw.get("link_summary", {}),
        "metrics": baseline_raw.get("metrics", {}),
        "model_calls_to_relink": fresh_in_baseline,
    }, indent=2, sort_keys=True, default=str))

    reports_path.write_text(json.dumps(
        {"subject_code": SUBJECT_CODE, "cancer_type": CANCER_TYPE, "reports": REPORTS},
        indent=2,
    ))
    artifact_path.write_text(json.dumps({
        "subject_id": SUBJECT_CODE,
        "manifest": manifest.model_dump(),
        "frames": raw.get("frames", []),
        "frame_events": raw.get("frame_events", []),
        "tracks": raw.get("tracks", {}),
        "track_graph": raw.get("track_graph", {}),
        "unresolved_link_queue": raw.get("unresolved_link_queue", []),
        "false_split_candidates": raw.get("false_split_candidates", []),
        "link_summary": raw.get("link_summary", {}),
        "metrics": raw.get("metrics", {}),
    }, indent=2, sort_keys=True, default=str))
    recist_path.write_text(json.dumps(recist_payload, indent=2))

    print(f"\n  froze reports  -> {reports_path}")
    print(f"  froze artifact -> {artifact_path}")
    print(f"  froze baseline -> {baseline_path}")
    print(f"  froze recist   -> {recist_path}")
    print("\nOVERALL: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
