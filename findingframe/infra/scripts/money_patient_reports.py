#!/usr/bin/env python3
"""SYNTHETIC longitudinal CT reports for the FindingFrame flagship "money patient" demo.

THESE REPORTS ARE 100% SYNTHETIC. They are hand-authored fiction for a product
demo. They are NOT derived from Tata Memorial, MIMIC, or any real patient data.

Clinical story (synthetic): DEMO-NSCLC-01, a stage IV non-small-cell lung cancer
patient on systemic therapy with two measurable RECIST target lesions:
  - a left-lower-lobe primary lung mass (index NSCLC), and
  - a right-hepatic liver metastasis,
both shrinking across four timepoints (overall SLD -35% by follow-up = PR).

The demo hinges on ONE authoring choice: the liver metastasis is described with
a *narrower* anatomic label at baseline ("hepatic segment VII") and a *broader*
label at later follow-ups ("right hepatic lobe"). The engine's deterministic
composite-key linker (finding_type|anatomy|laterality) has no alias collapsing
these two hepatic sub-labels to a single "liver" token, so it SPLITS the one
shrinking lesion into two tracks. Naive linking then treats the later track as a
NEW lesion appearing after baseline -> RECIST new-lesion rule -> automatic PD.
The human merge link-decision reunifies them -> the correct call is PR.

The liver sentences deliberately use "metastatic deposit"/"metastasis" and avoid
the words lesion/mass/hypodensity, so the engine's deterministic liver rescue
(which hardcodes anatomy="liver") does not fire and collapse the split.
"""
from __future__ import annotations

# subject-level metadata
SUBJECT_CODE = "DEMO-NSCLC-01"
CANCER_TYPE = "lung"

# Each report: source_report_id (engine-facing), chart_date (YYYY-MM-DD HH:MM:SS),
# note_id (external), note_type, text.
REPORTS = [
    {
        "source_report_id": "report_1",
        "chart_date": "2025-01-15 09:30:00",
        "note_id": "DEMO-NSCLC-01-CT-0001",
        "note_type": "CT CHEST/ABDOMEN/PELVIS W CONTRAST",
        "text": """SYNTHETIC DEMONSTRATION REPORT - NOT A REAL PATIENT

EXAM: CT of the chest, abdomen and pelvis with IV contrast.

CLINICAL HISTORY: Stage IV non-small cell lung carcinoma. Baseline staging prior
to initiation of first-line systemic therapy.

COMPARISON: None available.

TECHNIQUE: Multidetector CT was performed from the thoracic inlet through the
pubic symphysis following administration of intravenous contrast.

FINDINGS:

CHEST:
There is a spiculated primary mass in the left lower lobe measuring 55 mm in
greatest dimension, consistent with the patient's known non-small cell lung
carcinoma. No cavitation. A subcentimeter pulmonary nodule in the right upper
lobe measures 6 mm and is indeterminate, too small to characterize. No pleural
effusion. No pneumothorax. Heart size is normal.

ABDOMEN:
A hepatic segment VII metastatic deposit measures 40 mm. No biliary ductal
dilatation. The spleen, pancreas, and adrenal glands are unremarkable. No
ascites. The kidneys enhance symmetrically without hydronephrosis.

PELVIS:
No pelvic lymphadenopathy. Urinary bladder is unremarkable. No free pelvic fluid.

OSSEOUS STRUCTURES:
No aggressive osseous lesion. No fracture.

IMPRESSION:
1. Left lower lobe primary NSCLC measuring 55 mm (target lesion).
2. Hepatic segment VII metastatic deposit measuring 40 mm (target lesion).
3. Indeterminate 6 mm right upper lobe nodule, too small to characterize;
   recommend follow-up.
4. No osseous metastatic disease. No malignant lymphadenopathy.
""",
    },
    {
        "source_report_id": "report_2",
        "chart_date": "2025-03-20 10:05:00",
        "note_id": "DEMO-NSCLC-01-CT-0002",
        "note_type": "CT CHEST/ABDOMEN/PELVIS W CONTRAST",
        "text": """SYNTHETIC DEMONSTRATION REPORT - NOT A REAL PATIENT

EXAM: CT of the chest, abdomen and pelvis with IV contrast.

CLINICAL HISTORY: Stage IV non-small cell lung carcinoma on first-line systemic
therapy. Restaging.

COMPARISON: CT chest/abdomen/pelvis dated 2025-01-15.

TECHNIQUE: Contrast-enhanced multidetector CT from the thoracic inlet through the
pubic symphysis.

FINDINGS:

CHEST:
The left lower lobe primary mass has decreased in size and now measures 46 mm,
previously 55 mm. The indeterminate 6 mm right upper lobe nodule is unchanged and
remains too small to characterize. No pleural effusion. No pneumothorax.

ABDOMEN:
The segment VII hepatic metastatic deposit has decreased and now measures 32 mm,
previously 40 mm. No biliary ductal dilatation. No ascites. No hydronephrosis.

PELVIS:
No pelvic lymphadenopathy. No free pelvic fluid.

OSSEOUS STRUCTURES:
No aggressive osseous lesion. No fracture.

IMPRESSION:
1. Decreasing left lower lobe primary NSCLC, now 46 mm (previously 55 mm).
2. Decreasing segment VII hepatic metastatic deposit, now 32 mm (previously
   40 mm).
3. Stable indeterminate 6 mm right upper lobe nodule.
4. Overall favorable interval response to therapy.
""",
    },
    {
        "source_report_id": "report_3",
        "chart_date": "2025-05-22 09:50:00",
        "note_id": "DEMO-NSCLC-01-CT-0003",
        "note_type": "CT CHEST/ABDOMEN/PELVIS W CONTRAST",
        "text": """SYNTHETIC DEMONSTRATION REPORT - NOT A REAL PATIENT

EXAM: CT of the chest, abdomen and pelvis with IV contrast.

CLINICAL HISTORY: Stage IV non-small cell lung carcinoma on systemic therapy.
Restaging.

COMPARISON: CT chest/abdomen/pelvis dated 2025-03-20.

TECHNIQUE: Contrast-enhanced multidetector CT from the thoracic inlet through the
pubic symphysis.

FINDINGS:

CHEST:
The left lower lobe primary mass continues to decrease and now measures 38 mm,
previously 46 mm. The indeterminate right upper lobe nodule remains 6 mm and too
small to characterize. No pleural effusion. No pneumothorax.

ABDOMEN:
A metastatic deposit in the right hepatic lobe measures 26 mm and has decreased
compared with the prior examination. No biliary ductal dilatation. No ascites.
No hydronephrosis.

PELVIS:
No pelvic lymphadenopathy. No free pelvic fluid.

OSSEOUS STRUCTURES:
No aggressive osseous lesion. No fracture.

IMPRESSION:
1. Further decreasing left lower lobe primary NSCLC, now 38 mm.
2. Decreasing right hepatic lobe metastatic deposit, now 26 mm.
3. Stable indeterminate 6 mm right upper lobe nodule.
4. Continued favorable response to therapy.
""",
    },
    {
        "source_report_id": "report_4",
        "chart_date": "2025-07-24 10:15:00",
        "note_id": "DEMO-NSCLC-01-CT-0004",
        "note_type": "CT CHEST/ABDOMEN/PELVIS W CONTRAST",
        "text": """SYNTHETIC DEMONSTRATION REPORT - NOT A REAL PATIENT

EXAM: CT of the chest, abdomen and pelvis with IV contrast.

CLINICAL HISTORY: Stage IV non-small cell lung carcinoma on systemic therapy.
Restaging.

COMPARISON: CT chest/abdomen/pelvis dated 2025-05-22.

TECHNIQUE: Contrast-enhanced multidetector CT from the thoracic inlet through the
pubic symphysis.

FINDINGS:

CHEST:
The left lower lobe primary mass measures 34 mm, further decreased from 38 mm.
The indeterminate right upper lobe nodule remains 6 mm and too small to
characterize. No pleural effusion. No pneumothorax.

ABDOMEN:
The right hepatic lobe metastatic deposit measures 24 mm, further decreased from
26 mm. No biliary ductal dilatation. No ascites. No hydronephrosis.

PELVIS:
No pelvic lymphadenopathy. No free pelvic fluid.

OSSEOUS STRUCTURES:
No aggressive osseous lesion. No fracture.

IMPRESSION:
1. Further decreasing left lower lobe primary NSCLC, now 34 mm.
2. Further decreasing right hepatic lobe metastatic deposit, now 24 mm.
3. Stable indeterminate 6 mm right upper lobe nodule.
4. Sustained favorable response to therapy.
""",
    },
]
