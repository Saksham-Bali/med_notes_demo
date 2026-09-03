#!/usr/bin/env python3
"""SYNTHETIC longitudinal CT reports for the FindingFrame "dynamicity" demo.

THESE REPORTS ARE 100% SYNTHETIC. They are hand-authored fiction for a product
demo. They are NOT derived from Tata Memorial, MIMIC, or any real patient data.

Clinical story (synthetic): DEMO-NSCLC-LONG-01, a stage IV non-small-cell lung
cancer patient on systemic therapy, imaged by CT chest/abdomen/pelvis at ELEVEN
timepoints roughly eight weeks apart, with three measurable RECIST target lesions:

  A - left lower lobe primary lung mass       (organ: thorax)
  B - liver metastasis                        (organ: liver)
  C - right upper lobe lung metastasis        (organ: lung)

The demo hinges on ONE authoring choice, and it is a choice about *arithmetic*,
not about language:

    The sum of diameters falls to a NADIR of 60 mm at timepoint 6, then climbs
    back to 78 mm at timepoint 11. At timepoint 11 the patient is still 35% BELOW
    the 120 mm baseline -- a system that tracks only baseline reads that as a
    continuing Partial Response. But RECIST 1.1 measures progression against the
    nadir, and 78 mm is +30% and +18 mm above it, which is Progressive Disease.

So two numbers sit on screen disagreeing, and the correct answer cannot be
computed from report 11, nor from reports 10 and 11 together. It depends on a
minimum recorded six scans earlier. That is the point of the demo: the system
carries longitudinal state, and the state is what makes the call correct.

RECIST 1.1 requires BOTH >=20% and >=5 mm above nadir for progression. Both are
authored. Verified against the real backend classifier by
`build_long_patient.py`, which refuses to write the artifact if the series does
not produce PR at timepoint 10 and PD at timepoint 11.

The third target is `lung_metastasis` (right upper lobe). `adrenal_metastasis` is
NOT in the active FindingFrame taxonomy (20-type, finding_type_taxonomy.py), so
the LLM cannot extract it and the linker cannot track it. The right upper lobe
nodule in earlier versions was an "indeterminate 5 mm" finding; it is now an
explicitly measured metastasis present at baseline.

Liver anatomy uses "liver" consistently rather than "right hepatic lobe" to
prevent the linker from splitting tracks across anatomy label variations (the
LLM may enforce "liver" -> "right_hepatic_lobe" -> "liver_right_lobe").

TWO AUTHORING CONSTRAINTS worth recording, because both are load-bearing:

1. Every *present* finding appears at BASELINE. `recist.py::_new_lesion_dates`
   fires unconditional PD for any human-confirmed non-target track whose first
   present event post-dates baseline. Had a pleural effusion appeared at
   timepoint 5 and been confirmed, RECIST would have called PD there and the
   nadir story would never have run. Routine negatives are safe -- the rule only
   inspects events asserted `present`.

2. Timepoint 11 introduces exactly ONE genuinely new finding: a 7 mm
   indeterminate subpleural nodule, too small to characterize. It is deliberately
   NOT confirmable from this data, and in the demo the reviewer marks it
   unresolved rather than confirming it. That keeps the progression call anchored
   to measured regrowth rather than to an indeterminate speck -- two different
   reasons to call PD, and only one of them is defensible from what the report
   actually says.
"""
from __future__ import annotations

# subject-level metadata
SUBJECT_CODE = "DEMO-NSCLC-LONG-01"
CANCER_TYPE = "lung"

NOTE_TYPE = "CT CHEST/ABDOMEN/PELVIS W CONTRAST"

# ---------------------------------------------------------------------------
# The clinical series. One row per timepoint. Sizes in mm.
#   lung     = left lower lobe primary mass          (target A)
#   liver    = liver metastatic deposit              (target B)
#   lung_mets= right upper lobe lung metastasis      (target C)
# SLD = lung + liver + lung_mets. Baseline 120. Nadir 60 at t6. 78 at t11.
# ---------------------------------------------------------------------------
TIMEPOINTS: list[dict] = [
    {"n": 1,  "date": "2024-02-05 09:30:00", "lung": 52, "liver": 40, "lung_mets": 28},
    {"n": 2,  "date": "2024-04-01 10:05:00", "lung": 46, "liver": 35, "lung_mets": 24},
    {"n": 3,  "date": "2024-05-27 09:45:00", "lung": 40, "liver": 30, "lung_mets": 21},
    {"n": 4,  "date": "2024-07-22 10:20:00", "lung": 34, "liver": 26, "lung_mets": 18},
    {"n": 5,  "date": "2024-09-16 09:15:00", "lung": 29, "liver": 22, "lung_mets": 15},
    {"n": 6,  "date": "2024-11-11 10:40:00", "lung": 26, "liver": 20, "lung_mets": 14},
    {"n": 7,  "date": "2025-01-06 09:25:00", "lung": 26, "liver": 20, "lung_mets": 14},
    {"n": 8,  "date": "2025-03-03 10:10:00", "lung": 27, "liver": 21, "lung_mets": 14},
    {"n": 9,  "date": "2025-04-28 09:50:00", "lung": 29, "liver": 22, "lung_mets": 15},
    {"n": 10, "date": "2025-06-23 10:30:00", "lung": 31, "liver": 23, "lung_mets": 16},
    {"n": 11, "date": "2025-08-18 09:35:00", "lung": 34, "liver": 26, "lung_mets": 18},
]

BASELINE_SLD = 120   # t1
NADIR_SLD = 60       # t6
FINAL_SLD = 78       # t11

SYNTHETIC_HEADER = "SYNTHETIC DEMONSTRATION REPORT - NOT A REAL PATIENT"


def _delta_phrase(now: int, prev: int | None) -> str:
    """How a radiologist would describe this interval change."""
    if prev is None:
        return ""
    if now < prev:
        return f"decreased from {prev} mm"
    if now > prev:
        return f"increased from {prev} mm"
    return f"unchanged from {prev} mm"


def _history(n: int) -> str:
    if n == 1:
        return ("Stage IV non-small cell lung carcinoma. Baseline staging prior to\n"
                "initiation of first-line systemic therapy.")
    if n <= 6:
        return ("Stage IV non-small cell lung carcinoma on first-line systemic therapy.\n"
                "Restaging.")
    if n <= 10:
        return ("Stage IV non-small cell lung carcinoma on maintenance systemic therapy.\n"
                "Surveillance restaging.")
    return ("Stage IV non-small cell lung carcinoma on maintenance systemic therapy.\n"
            "Surveillance restaging. Rising tumour markers reported clinically.")


def _impression(tp: dict, prev: dict | None) -> str:
    n, lung, liver, lung_mets = tp["n"], tp["lung"], tp["liver"], tp["lung_mets"]
    lines: list[str] = []
    if n == 1:
        lines += [
            f"1. Left lower lobe primary NSCLC measuring {lung} mm (target lesion).",
            f"2. Liver metastatic deposit measuring {liver} mm (target lesion).",
            f"3. Right upper lobe lung metastasis measuring {lung_mets} mm (target lesion).",
            "4. No osseous metastatic disease. No malignant lymphadenopathy.",
        ]
    elif n <= 6:
        lines += [
            f"1. Decreasing left lower lobe primary NSCLC, now {lung} mm.",
            f"2. Decreasing liver metastatic deposit, now {liver} mm.",
            f"3. Decreasing right upper lobe lung metastasis, now {lung_mets} mm.",
            "4. Overall favorable interval response to therapy.",
        ]
    elif n == 7:
        lines += [
            f"1. Left lower lobe primary NSCLC unchanged at {lung} mm.",
            f"2. Liver metastatic deposit unchanged at {liver} mm.",
            f"3. Right upper lobe lung metastasis unchanged at {lung_mets} mm.",
            "4. No interval change. Response to therapy is maintained.",
        ]
    elif n <= 10:
        lines += [
            f"1. Left lower lobe primary NSCLC measures {lung} mm, marginally larger.",
            f"2. Liver metastatic deposit measures {liver} mm, marginally larger.",
            f"3. Right upper lobe lung metastasis measures {lung_mets} mm, marginally larger.",
            "4. Measurements remain well below the pre-treatment baseline, but all three",
            "   target lesions have shown incremental growth on consecutive examinations.",
        ]
    else:
        lines += [
            f"1. Left lower lobe primary NSCLC measures {lung} mm, further increased.",
            f"2. Liver metastatic deposit measures {liver} mm, further increased.",
            f"3. Right upper lobe lung metastasis measures {lung_mets} mm, further increased.",
            "4. Interval increase in all three target lesions relative to the nadir",
            "   examination of 2024-11-11. Sizes nonetheless remain below the pre-treatment",
            "   baseline of 2024-02-05.",
            "5. New 7 mm subpleural nodule in the right lower lobe, indeterminate and too",
            "   small to characterize. Attention on follow-up imaging is recommended.",
        ]
    return "\n".join(lines)


def _chest(tp: dict, prev: dict | None) -> str:
    n, lung, lung_mets = tp["n"], tp["lung"], tp["lung_mets"]
    prev_lung = prev["lung"] if prev else None
    prev_lung_mets = prev["lung_mets"] if prev else None
    if n == 1:
        body = (
            f"There is a spiculated primary mass in the left lower lobe measuring {lung} mm\n"
            "in greatest dimension, consistent with the patient's known non-small cell lung\n"
            f"carcinoma. A metastatic deposit in the right upper lobe measures {lung_mets} mm."
        )
    else:
        body = (
            f"The left lower lobe primary mass measures {lung} mm, "
            f"{_delta_phrase(lung, prev_lung)}.\n"
            f"The right upper lobe lung metastasis measures {lung_mets} mm, "
            f"{_delta_phrase(lung_mets, prev_lung_mets)}."
        )
    if n == 11:
        body += (
            "\nThere is a new 7 mm subpleural nodule in the right lower lobe. It is\n"
            "indeterminate and too small to characterize on this examination."
        )
    body += (
        "\nNo pleural effusion. No pneumothorax. Heart size is normal. No malignant\n"
        "mediastinal or hilar lymphadenopathy."
    )
    return body


def _abdomen(tp: dict, prev: dict | None) -> str:
    n, liver = tp["n"], tp["liver"]
    prev_liver = prev["liver"] if prev else None
    if n == 1:
        body = f"A liver metastatic deposit measures {liver} mm."
    else:
        body = (
            f"The liver metastatic deposit measures {liver} mm, "
            f"{_delta_phrase(liver, prev_liver)}."
        )
    body += (
        "\nNo biliary ductal dilatation. The spleen, pancreas and adrenal glands are"
        " unremarkable. No ascites. The kidneys enhance symmetrically without"
        " hydronephrosis."
    )
    return body


def _build_report(tp: dict, prev: dict | None) -> dict:
    n = tp["n"]
    comparison = "None available." if prev is None else (
        f"CT chest/abdomen/pelvis dated {prev['date'][:10]}."
    )
    text = f"""{SYNTHETIC_HEADER}

EXAM: CT of the chest, abdomen and pelvis with IV contrast.

CLINICAL HISTORY: {_history(n)}

COMPARISON: {comparison}

TECHNIQUE: Contrast-enhanced multidetector CT from the thoracic inlet through the
pubic symphysis.

FINDINGS:

CHEST:
{_chest(tp, prev)}

ABDOMEN:
{_abdomen(tp, prev)}

PELVIS:
No pelvic lymphadenopathy. Urinary bladder is unremarkable. No free pelvic fluid.

OSSEOUS STRUCTURES:
No aggressive osseous lesion. No fracture.

IMPRESSION:
{_impression(tp, prev)}
"""
    return {
        "source_report_id": f"report_{n}",
        "chart_date": tp["date"],
        "note_id": f"{SUBJECT_CODE}-CT-{n:04d}",
        "note_type": NOTE_TYPE,
        "text": text,
    }


def build_reports() -> list[dict]:
    out: list[dict] = []
    prev: dict | None = None
    for tp in TIMEPOINTS:
        out.append(_build_report(tp, prev))
        prev = tp
    return out


REPORTS: list[dict] = build_reports()

# The first ten are the record the clinician builds and signs (act one).
# The eleventh is the report that arrives afterwards (act two).
BASELINE_REPORTS: list[dict] = REPORTS[:10]
INCREMENTAL_REPORT: dict = REPORTS[10]


if __name__ == "__main__":
    for r in REPORTS:
        print("=" * 78)
        print(f"{r['source_report_id']}  {r['chart_date']}  {r['note_id']}")
        print("=" * 78)
        print(r["text"])
