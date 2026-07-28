# The Money Patient — FindingFrame Flagship Demo (`DEMO-NSCLC-01`)

> **This patient and all four reports are 100% SYNTHETIC.** They are hand-authored
> fiction for a product demonstration. They are **not** derived from Tata Memorial,
> MIMIC, or any real patient. The demo org is literally named "Tata Memorial (Demo)".

This is the single case that shows *why FindingFrame exists*. It turns the engine's
known-weakest metric — deterministic track-linking — into the product's reason to
be: **naive composite-key linking silently splits one shrinking liver lesion into
two tracks and fires a FALSE "new lesion → Progressive Disease" call. The human
link-confirmation workflow merges them, and the correct response is Partial
Response.**

Everything below was produced by the **real engine** (`deepseek/deepseek-v4-pro`
via OpenRouter, engine `e04d3c6d9c79`) and the **real backend RECIST logic**
(`app/services/recist.py::classify`), then verified — not asserted.

---

## 1. The clinical story (synthetic)

`DEMO-NSCLC-01` is a Stage IV non-small-cell lung cancer patient started on
first-line systemic therapy, imaged by CT chest/abdomen/pelvis at four timepoints
~9 weeks apart. Two measurable RECIST target lesions:

| Target | Lesion | Baseline (2025-01-15) | FU1 (03-20) | FU2 (05-22) | FU3 (07-24) |
|--------|--------|------:|------:|------:|------:|
| **A** | Left lower lobe primary lung mass (index NSCLC) | 55 mm | 46 mm | 38 mm | 34 mm |
| **B** | Right-hepatic liver metastasis | 40 mm | 32 mm | 26 mm | 24 mm |
| | **Sum of longest diameters (SLD)** | **95** | **78** | **64** | **58** |

Both lesions shrink monotonically. The true best overall response is **Partial
Response** (SLD −38.9% from baseline by FU3; crosses the −30% PR threshold at FU2).

Also present for realism: routine negatives at every timepoint (no ascites, no
pleural effusion, no pneumothorax, no hydronephrosis, no osseous metastasis, no
malignant lymphadenopathy) and one **genuinely gate-uncertain finding** — an
"indeterminate 6 mm right upper lobe nodule, too small to characterize" that is
carried as review-only and, at one timepoint, is **gate-failed** (evidence span
not located → `evidence_verified=false`) and therefore force-routed to mandatory
human review per the product's evidence gate.

---

## 2. The exact discrepancy (verified numbers)

The liver lesion is described with a **narrower label at baseline** ("hepatic
segment VII") and a **broader label at follow-up** ("right hepatic lobe" / "liver").
The engine's deterministic linker keys tracks on
`finding_type | anatomy | laterality` and has **no alias** collapsing these hepatic
sub-labels to one token — so it splits the one lesion into two tracks:

```
Track A  (lung, links correctly): primary_tumor|thorax|left            55 → 46 → 38 → 34 mm  (t0..t3)
Track B1 (liver, baseline only):  liver_metastasis|liver_segment_vii|right   40 mm         (t0)
Track B2 (liver, follow-ups):     liver_metastasis|liver|right          32 → 26 → 24 mm      (t1..t3)
```

B2's first **present** event is at **FU1 (2025-03-20)** — *after* baseline. RECIST's
new-lesion rule (`app/services/recist.py::_new_lesion_dates` + `classify`) treats a
confirmed non-target track that first appears after baseline as unconditional PD.

**NAIVE** (the split is rubber-stamped: target = A + B1; B2 is a confirmed non-target):

| Date | SLD | % baseline | new lesion? | RECIST |
|------|----:|-----------:|:-----------:|:------:|
| 2025-01-15 | 95 | +0.0% | no | SD |
| 2025-03-20 | 86 | −9.5% | **YES (B2)** | **PD** |
| 2025-05-22 | 78 | −17.9% | no | SD |
| 2025-07-24 | 74 | −22.1% | no | SD |
| | | | | **Best overall: PD** |

**CONFIRMED** (a human merges B1 + B2 into one liver target: A + merged-liver):

| Date | SLD | % baseline | new lesion? | RECIST |
|------|----:|-----------:|:-----------:|:------:|
| 2025-01-15 | 95 | +0.0% | no | SD |
| 2025-03-20 | 78 | −17.9% | no | SD |
| 2025-05-22 | 64 | −32.6% | no | **PR** |
| 2025-07-24 | 58 | −38.9% | no | **PR** |
| | | | | **Best overall: PR** |

### → NAIVE = **PD** (treatment "failing", switch therapy) vs CONFIRMED = **PR** (treatment working, stay the course).

Same reports, same engine, same RECIST math. The **only** difference is one human
link decision. That is the product.

---

## 3. Which track_keys split and merge

- **Split (verified in the frozen engine artifact):** the liver metastasis exists as
  **two** `liver_metastasis` tracks —
  `liver_metastasis|liver_segment_vii|right` (baseline) and
  `liver_metastasis|liver|right` (follow-ups). The linker did not even flag them as a
  false-split candidate (its automated detector compares normalized anatomy against a
  parent map that has no `liver_segment_vii → liver` edge), so the split is *silent* —
  the scariest failure mode: RECIST would fire PD with nothing flagged.
- **Product surfacing:** the seed marks **both** liver tracks
  `false_split_candidate = true` so the review workbench proactively offers the merge
  (they are the same lesion under two labels). Both are `latest_status=active` liver
  metastases — a reviewer sees two "active" liver lesions and recognizes the duplicate.
- **Merge (the fix):** a `merge` link-decision with
  `primary_track_key = liver_metastasis|liver|right`,
  `related_track_keys = [liver_metastasis|liver_segment_vii|right]`,
  `resulting_track_key = liver_metastasis|liver|right` (or any confirmed key).
  `derive_confirmed_tracks` folds both members' events into one confirmed liver identity
  with the full series 40 → 32 → 26 → 24 mm.

Note (honest detail): report 2's sentence literally says "segment VII" yet the
extractor assigned it `anatomy=liver` — so the split boundary is *baseline vs all
follow-ups*. This is a real artifact of slot extraction variance, exactly the kind of
inconsistency a deterministic composite key cannot absorb and a human must confirm.

---

## 4. Click-by-click demo script

Log in as the demo reviewer (`demo@findingframe.dev` / `demo1234`), org
**Tata Memorial (Demo)**, and open patient **DEMO-NSCLC-01**.

1. **Open the run digest.** Point out the clean parts first: the lung primary
   (`primary_tumor|thorax|left`) tracked cleanly across all four scans, 55 → 34 mm,
   with each number backed by its verbatim source sentence (click to reveal the full
   report). Show the routine negatives collapsed away and the **gate-failed**
   indeterminate nodule quarantined into mandatory review — "100% source-linked;
   gate-failed facts quarantined."
2. **Land on the trap.** Scroll to the liver. There are **two** active liver-metastasis
   tracks, both flagged as **false-split candidates**:
   `…|liver_segment_vii|right` (one event, 40 mm at baseline) and `…|liver|right`
   (three events, 32 → 26 → 24 mm). Read the verbatim evidence side by side — obviously
   the same shrinking lesion, described "segment VII" then "right hepatic lobe".
3. **Show the false PD (before merging).** Try to compute RECIST selecting the lung
   track + the baseline `…|liver_segment_vii|right` as targets. The follow-up
   `…|liver|right` track is a confirmed non-target that first appears after baseline →
   **new-lesion → Progressive Disease at FU1.** The dashboard says the patient is
   progressing. This is the number that would switch a real patient's therapy.
4. **The human moment — merge.** Issue the merge link-decision (append-only, signed):
   `POST /runs/{id}/link-decisions {decision:"merge", primary_track_key:"liver_metastasis|liver|right",
   related_track_keys:["liver_metastasis|liver_segment_vii|right"]}`. The two liver
   tracks fold into one confirmed liver lesion, 40 → 32 → 26 → 24 mm.
5. **Recompute RECIST over confirmed tracks.** Select the lung track + the merged liver
   track as the two targets (≤5 total, ≤2/organ). SLD 95 → 78 → 64 → 58, no new lesion:
   **Partial Response (−38.9%).** The PD vanishes.
6. **Close on the thesis.** RECIST renders **only** over human-confirmed tracks; the
   product refused to let a silent linker error become a signed "progressive disease"
   verdict. One link decision flipped PD → PR. *That* is why link-confirmation is not a
   nice-to-have.

---

## 5. Seeded identifiers and how to reproduce

| Thing | Value |
|-------|-------|
| Org | `Tata Memorial (Demo)` — `613b2f05-57cc-4fa3-9098-f678c308f1f0` |
| Patient | `DEMO-NSCLC-01` — `d11d4144-dcd1-45e8-bb54-b6ff2e953ffb` (cancer_type `lung`) |
| Extraction run | `47f529e8-f82a-4560-a6f7-ef7226bbaa99` (status `succeeded`) |
| Rows | 4 reports / 4 report_versions / 19 tracks / 41 frames / 41 track_events |

(The run/patient UUIDs are from the current seed. Re-seeding onto a fresh DB assigns
new UUIDs; the `subject_code` `DEMO-NSCLC-01` and the track_keys are stable.)

### Files (all under `infra/`)
- `infra/scripts/money_patient_reports.py` — the four synthetic reports + rationale.
- `infra/scripts/build_money_patient.py` — extracts with the **real engine**, populates
  `normalized_mm`, freezes the artifact, and **verifies the split** (exits non-zero if
  the liver lesion does not split into ≥2 measured tracks).
- `infra/scripts/compute_money_patient_recist.py` — computes NAIVE vs CONFIRMED RECIST
  using the backend's real `classify`; asserts naive=PD, confirmed=PR.
- `infra/scripts/seed_money_patient.py` — idempotent, **offline** seed into the demo org
  (no live LLM key needed). Does **not** TRUNCATE; seeds alongside the existing demo
  patient.
- `infra/seed_data/money_patient_reports.json` — frozen report inputs.
- `infra/seed_data/money_patient_artifact.json` — frozen engine `PatientArtifact`
  (frames / tracks / graph / manifest).
- `infra/seed_data/money_patient_recist.json` — frozen naive-vs-confirmed RECIST result.

### Commands
```bash
# 1. (needs live OpenRouter key) extract with the real engine + verify the split
backend/.venv/bin/python infra/scripts/build_money_patient.py

# 2. prove the discrepancy with the backend's real RECIST logic
backend/.venv/bin/python infra/scripts/compute_money_patient_recist.py

# 3. (offline) seed into the demo DB — idempotent, non-destructive
backend/.venv/bin/python infra/scripts/seed_money_patient.py
```

Step 3 reads only the frozen `infra/seed_data/` files, so the demo re-seeds without a
live LLM key. Step 1 uses the engine's on-disk cache, so re-runs are instant and free.
