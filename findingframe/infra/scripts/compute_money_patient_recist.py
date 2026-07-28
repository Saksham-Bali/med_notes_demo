#!/usr/bin/env python3
"""Compute BOTH RECIST outcomes for the SYNTHETIC money patient from the frozen artifact,
using the backend's REAL RECIST logic (app/services/recist.py::classify), to prove the
naive-PD vs confirmed-PR discrepancy.

  NAIVE     : the split is rubber-stamped. Target lesions = lung primary (track A) +
              baseline liver track B1 (segment VII). The follow-up liver track B2 is a
              confirmed NON-target that first appears AFTER baseline -> RECIST new-lesion
              rule -> Progressive Disease.
  CONFIRMED : a human merges B1 + B2 into one liver target. SLD over {lung, merged liver}
              falls -35% -> Partial Response. No new lesion.

Run:  backend/.venv/bin/python infra/scripts/compute_money_patient_recist.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_DIR = FF_ROOT / "backend"
SEED_DATA_DIR = INFRA_DIR / "seed_data"

sys.path.insert(0, str(BACKEND_DIR))

LUNG_KEY = "primary_tumor|thorax|left"
LIVER_BASELINE_KEY = "liver_metastasis|liver_segment_vii|right"   # B1
LIVER_FOLLOWUP_KEY = "liver_metastasis|liver|right"              # B2
LIVER_MERGED_KEY = "liver_metastasis|liver|right|CONFIRMED_MERGE"

_MM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|millimeter[s]?|centimeter[s]?)\b", re.IGNORECASE)


def _mm(meas: dict | None) -> float | None:
    if not meas:
        return None
    v = meas.get("normalized_mm")
    if isinstance(v, (int, float)):
        return float(v)
    v = meas.get("value")
    if isinstance(v, (int, float)):
        return float(v)
    vals = meas.get("values")
    if isinstance(vals, list) and vals:
        nums = [float(x) for x in vals if isinstance(x, (int, float))]
        if nums:
            return max(nums)
    m = _MM_RE.search(str(meas.get("raw") or meas.get("text") or ""))
    if m:
        val = float(m.group(1))
        return val * 10.0 if m.group(2).lower()[0] == "c" else val
    return None


def _series(track: dict) -> list[tuple[datetime, float]]:
    out = []
    for e in track.get("events", []):
        mm = _mm(e.get("measurement"))
        d = e.get("report_date")
        if mm is not None and d:
            out.append((datetime.fromisoformat(d[:19].replace(" ", "T")), mm))
    out.sort(key=lambda x: x[0])
    return out


def _mm_at(series: list[tuple[datetime, float]], when: datetime) -> float | None:
    latest = None
    for d, mm in series:
        if d <= when:
            latest = mm
        else:
            break
    return latest


def compute(targets: list[dict], nontarget_tracks: list[dict], classify) -> list[dict]:
    """Mirror app/services/recist.py::compute_recist over an in-memory track set."""
    for t in targets:
        t["series"] = t.get("series") or []
    timepoints = sorted({d for t in targets for d, _ in t["series"]})
    baseline_sld = sum(t["baseline_mm"] for t in targets)

    # new-lesion signal: a non-target track whose first PRESENT event is after baseline tp
    baseline_date = timepoints[0] if timepoints else None
    new_lesion_dates = set()
    if baseline_date is not None:
        for nt in nontarget_tracks:
            present = [datetime.fromisoformat(d[:19].replace(" ", "T"))
                      for d, a in nt["present_dates"]]
            if present and min(present) > baseline_date:
                new_lesion_dates.add(min(present))

    rows = []
    nadir = baseline_sld if baseline_sld > 0 else None
    for tp in timepoints:
        sld = 0.0
        for t in targets:
            v = _mm_at(t["series"], tp)
            sld += v if v is not None else t["baseline_mm"]
        if nadir is None:
            nadir = sld
        nadir = min(nadir, sld)
        new_lesion = tp in new_lesion_dates
        cls = classify(sld, baseline_sld, nadir, new_lesion)
        rows.append({
            "date": tp.date().isoformat(),
            "sld": sld,
            "pct_baseline": (sld - baseline_sld) / baseline_sld * 100.0 if baseline_sld else None,
            "new_lesion": new_lesion,
            "classification": cls,
        })
    return rows


def _best_overall(rows: list[dict]) -> str:
    order = {"PD": 4, "SD": 2, "PR": 3, "CR": 5, "NE": 1}
    if any(r["classification"] == "PD" for r in rows):
        return "PD"
    best = max(rows, key=lambda r: order.get(r["classification"], 0))
    return best["classification"]


def _print_table(title: str, rows: list[dict]) -> None:
    print(f"\n{title}")
    print(f"  {'date':<12}{'SLD(mm)':<10}{'%baseline':<12}{'new_lesion':<12}{'RECIST'}")
    for r in rows:
        pct = f"{r['pct_baseline']:+.1f}%" if r["pct_baseline"] is not None else "n/a"
        print(f"  {r['date']:<12}{r['sld']:<10.0f}{pct:<12}{str(r['new_lesion']):<12}{r['classification']}")
    print(f"  => BEST OVERALL RESPONSE: {_best_overall(rows)}")


def main() -> int:
    from app.services.recist import classify  # noqa: PLC0415

    art = json.load((SEED_DATA_DIR / "money_patient_artifact.json").open())
    tracks = art["tracks"]

    lung = tracks[LUNG_KEY]
    b1 = tracks[LIVER_BASELINE_KEY]
    b2 = tracks[LIVER_FOLLOWUP_KEY]

    lung_series = _series(lung)
    b1_series = _series(b1)
    b2_series = _series(b2)
    print("=== Verified measured series (from frozen engine artifact) ===")
    print(f"  lung  A  [{LUNG_KEY}]: {[(d.date().isoformat(), mm) for d, mm in lung_series]}")
    print(f"  liver B1 [{LIVER_BASELINE_KEY}]: {[(d.date().isoformat(), mm) for d, mm in b1_series]}")
    print(f"  liver B2 [{LIVER_FOLLOWUP_KEY}]: {[(d.date().isoformat(), mm) for d, mm in b2_series]}")

    baseline_lung = lung_series[0][1]
    baseline_liver = b1_series[0][1]

    # -- NAIVE: target = A + B1; B2 is a confirmed non-target => new lesion --------
    naive_targets = [
        {"key": LUNG_KEY, "organ": "lung", "baseline_mm": baseline_lung, "series": lung_series},
        {"key": LIVER_BASELINE_KEY, "organ": "liver", "baseline_mm": baseline_liver,
         "series": b1_series},
    ]
    naive_nontarget = [
        {"key": LIVER_FOLLOWUP_KEY,
         "present_dates": [(e["report_date"], e["assertion"])
                          for e in b2["events"] if e.get("assertion") == "present"]},
    ]
    naive_rows = compute(naive_targets, naive_nontarget, classify)
    _print_table("NAIVE (split rubber-stamped: B2 = new lesion)", naive_rows)

    # -- CONFIRMED: merge B1 + B2 into one liver target ---------------------------
    merged_series = sorted(b1_series + b2_series, key=lambda x: x[0])
    confirmed_targets = [
        {"key": LUNG_KEY, "organ": "lung", "baseline_mm": baseline_lung, "series": lung_series},
        {"key": LIVER_MERGED_KEY, "organ": "liver", "baseline_mm": baseline_liver,
         "series": merged_series},
    ]
    confirmed_rows = compute(confirmed_targets, [], classify)
    _print_table("CONFIRMED (human merge B1+B2 into one liver target)", confirmed_rows)

    naive_bor = _best_overall(naive_rows)
    confirmed_bor = _best_overall(confirmed_rows)
    print("\n=== THE MOMENT ===")
    print(f"  NAIVE best overall response     : {naive_bor}")
    print(f"  CONFIRMED best overall response : {confirmed_bor}")
    ok = naive_bor == "PD" and confirmed_bor == "PR"
    print("  " + ("OK: discrepancy proven (naive PD vs confirmed PR)." if ok
                  else "FAIL: expected naive=PD, confirmed=PR."))

    # emit machine-readable summary for the seed + doc
    out = {
        "naive": {"rows": naive_rows, "best_overall": naive_bor,
                  "target_keys": [LUNG_KEY, LIVER_BASELINE_KEY],
                  "new_lesion_key": LIVER_FOLLOWUP_KEY},
        "confirmed": {"rows": confirmed_rows, "best_overall": confirmed_bor,
                      "target_keys": [LUNG_KEY, LIVER_MERGED_KEY],
                      "merged_from": [LIVER_BASELINE_KEY, LIVER_FOLLOWUP_KEY]},
        "baseline_mm": {"lung": baseline_lung, "liver": baseline_liver},
    }
    (SEED_DATA_DIR / "money_patient_recist.json").write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {SEED_DATA_DIR / 'money_patient_recist.json'}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
