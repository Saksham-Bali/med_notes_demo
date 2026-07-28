#!/usr/bin/env python3
"""Extract the SYNTHETIC "money patient" with the REAL FindingFrame engine, verify the
liver-track split, and freeze the artifact to infra/seed_data/ for offline re-seeding.

Run with the backend venv (needs a live OpenRouter key in backend/.env):
    backend/.venv/bin/python infra/scripts/build_money_patient.py

Outputs (infra/seed_data/):
    money_patient_reports.json    - frozen report inputs (text + metadata)
    money_patient_artifact.json   - the engine PatientArtifact (frames/tracks/graph/manifest)

The script prints a verification block proving the liver lesion split into >=2 tracks
and that target measurements populate, then exits non-zero if the split did not occur.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_MM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|millimeter[s]?|centimeter[s]?)\b", re.IGNORECASE)


def _parse_mm_from_text(text: str | None) -> float | None:
    """Parse a millimetre value from a raw measurement string like '55 mm' or '5.5 cm'."""
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

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_DIR = FF_ROOT / "backend"
SEED_DATA_DIR = INFRA_DIR / "seed_data"

# import the report definitions
sys.path.insert(0, str(SCRIPT_DIR))
from money_patient_reports import CANCER_TYPE, REPORTS, SUBJECT_CODE  # noqa: E402

# make `app` importable (backend package root)
sys.path.insert(0, str(BACKEND_DIR))


def _mm_from_measurement(meas: dict | None) -> float | None:
    """Deterministic mm resolution mirroring app/services/recist.py::_mm, with cm->mm."""
    if not meas:
        return None
    unit = (meas.get("unit") or "").strip().lower()
    scale = 10.0 if unit in {"cm", "centimeter", "centimeters"} else 1.0
    for field in ("normalized_mm",):
        v = meas.get(field)
        if isinstance(v, (int, float)):
            return float(v)
    for field in ("value",):
        v = meas.get(field)
        if isinstance(v, (int, float)):
            return float(v) * scale
    values = meas.get("values")
    if isinstance(values, list) and values:
        nums = [float(x) for x in values if isinstance(x, (int, float))]
        if nums:
            return max(nums) * scale
    # LLM frequently emits only raw/text ("55 mm"); parse it deterministically.
    return _parse_mm_from_text(meas.get("raw") or meas.get("text"))


def _ensure_normalized_mm(artifact: dict) -> int:
    """Populate measurement.normalized_mm on every frame/event that carries a measurement.

    The engine does not compute normalized_mm; RECIST needs it (or falls back to value).
    This is deterministic data-prep on the engine output (the engine itself is untouched).
    Returns the count of measurements normalized.
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


def main() -> int:
    import pandas as pd  # noqa: PLC0415

    from app.engine.adapter import get_engine  # noqa: PLC0415
    from app.engine.types import ReportInput  # noqa: PLC0415

    SEED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    report_inputs: list[ReportInput] = []
    frozen_reports: list[dict] = []
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
        frozen_reports.append(r)

    print(f"=== Extracting {SUBJECT_CODE} ({len(report_inputs)} reports) with the real engine ===")
    engine = get_engine()
    # engine._prepare() puts tmc on sys.path and feeds the LLM client via env (the same
    # setup the adapter's process_patient() performs).
    engine._prepare()
    base = engine.manifest_base()
    manifest = engine.build_manifest(report_inputs)
    print(f"  engine_git_sha={base.engine_git_sha[:12]} model={base.model_id} "
          f"prompt={base.prompt_version} schema={base.schema_version}")

    # NOTE: EngineAdapter.process_patient() builds a reports_df with a string "subject_id"
    # column, but the engine processor filters rows via `== int(subject_id)`, which drops
    # every row for a non-integer subject code (a pre-existing engine limitation). We drive
    # the same engine class the adapter wraps (FindingFramePatientProcessor) directly with a
    # DataFrame that omits the subject_id column, so all reports are processed. The engine
    # (tmc) is not modified.
    from pipeline.finding_frame_processor import FindingFramePatientProcessor  # noqa: PLC0415

    rows = []
    for r in report_inputs:
        rows.append({
            "charttime": r.chart_date,
            "note_id": r.note_id or r.source_report_id,
            "note_type": r.study_type,
            "text": r.text,
        })
    reports_df = pd.DataFrame(rows).sort_values("charttime").reset_index(drop=True)
    proc = FindingFramePatientProcessor(output_dir=str(SEED_DATA_DIR / "_engine_tmp"),
                                        save_artifacts=False)
    result = proc.process_patient(SUBJECT_CODE, reports_df)
    raw = dict(result.artifact)

    class _A:  # lightweight holder mirroring PatientArtifact fields we use below
        pass
    artifact = _A()
    artifact.subject_id = SUBJECT_CODE
    artifact.manifest = manifest
    artifact.tracks = raw.get("tracks", {})
    artifact.frames = raw.get("frames", [])
    artifact.frame_events = raw.get("frame_events", [])
    normalized_count = _ensure_normalized_mm(raw)
    # also normalize the top-level tracks dict returned on the DTO (same objects as raw usually)
    _ensure_normalized_mm({"tracks": artifact.tracks, "frames": artifact.frames,
                           "frame_events": artifact.frame_events})

    # ---- freeze to disk -----------------------------------------------------
    reports_path = SEED_DATA_DIR / "money_patient_reports.json"
    artifact_path = SEED_DATA_DIR / "money_patient_artifact.json"
    reports_path.write_text(json.dumps(
        {"subject_code": SUBJECT_CODE, "cancer_type": CANCER_TYPE, "reports": frozen_reports},
        indent=2,
    ))
    frozen = {
        "subject_id": artifact.subject_id,
        "manifest": artifact.manifest.model_dump(),
        "frames": raw.get("frames", []),
        "frame_events": raw.get("frame_events", []),
        "tracks": raw.get("tracks", {}),
        "track_graph": raw.get("track_graph", {}),
        "unresolved_link_queue": raw.get("unresolved_link_queue", []),
        "false_split_candidates": raw.get("false_split_candidates", []),
        "link_summary": raw.get("link_summary", {}),
        "metrics": raw.get("metrics", {}),
    }
    artifact_path.write_text(json.dumps(frozen, indent=2, sort_keys=True))
    print(f"  normalized_mm populated on {normalized_count} measurements")
    print(f"  froze reports  -> {reports_path}")
    print(f"  froze artifact -> {artifact_path}")

    # ---- verification -------------------------------------------------------
    print("\n=== Tracks ===")
    tracks = raw.get("tracks", {})
    liver_tracks = []
    for key in sorted(tracks):
        t = tracks[key]
        ft = t.get("finding_type")
        la = t.get("link_anatomy")
        lat = t.get("link_laterality")
        ev = t.get("events", [])
        meas_series = []
        for e in ev:
            mm = _mm_from_measurement(e.get("measurement"))
            meas_series.append(
                f"{e.get('report_date','?')[:10]}:{e.get('assertion','?')}"
                f"{'/'+str(mm)+'mm' if mm is not None else ''}"
            )
        print(f"  [{ft}] key={key}")
        print(f"       link_anatomy={la} link_laterality={lat} "
              f"latest_status={t.get('latest_status')} unresolved={t.get('unresolved_link')} "
              f"events={len(ev)}")
        print(f"       series: {meas_series}")
        if ft == "liver_metastasis":
            liver_tracks.append((key, t))

    print("\n=== false_split_candidates ===")
    for c in raw.get("false_split_candidates", []):
        print(f"  {c}")
    print("=== unresolved_link_queue ===")
    for q in raw.get("unresolved_link_queue", []):
        print(f"  {q.get('track_key')} :: {q.get('reason')}")

    print("\n=== link_summary ===")
    print(f"  {json.dumps(raw.get('link_summary', {}), indent=2)}")

    # ---- assert the demo invariants ----------------------------------------
    ok = True
    n_liver = len(liver_tracks)
    print(f"\nLiver metastasis tracks: {n_liver}")
    if n_liver < 2:
        print("  FAIL: expected >=2 liver_metastasis tracks (the split). "
              "Adjust anatomy phrasing and re-run.")
        ok = False
    else:
        print("  OK: liver lesion SPLIT into >=2 tracks.")

    # each liver track must carry at least one measured event
    for key, t in liver_tracks:
        measured = any(_mm_from_measurement(e.get("measurement")) is not None
                       for e in t.get("events", []))
        if not measured:
            print(f"  FAIL: liver track {key} has no measured event.")
            ok = False

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
