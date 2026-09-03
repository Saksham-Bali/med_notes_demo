# Pilot Data Deep-Dive — SC Judgment Structure Findings

**Date:** 2026-08-14 · **Status:** v2 (post-critic-pass; corrections recorded in §6)
**Data:** `tyrone:~/data/legal/pilot_families/` (SC PDFs, extracted text)
**Purpose:** verify the legal frame schema against real judgment text before writing the curation protocol.

---

## 1. What reading the judgments taught us

### 1.1 The longitudinal structure is explicit in the text — and it is a forest, not a track

The M.C. Mehta v. Union of India "family" (21 decisions, 1991–2009) is **not one case**. Verified root dockets from PDF headers:

| Root proceeding | Decisions | Subject line |
|---|---|---|
| WP(C) No. 4677 of 1985 | 1996_1179, 1996_677, 1996_705, 2000_421, 2001_273, 2009_750 | Aravalli mining ban |
| WP(C) No. 13029 of 1985 | 1991_75, 1997_804, 2002_185 | Delhi vehicular pollution |
| WP(C) No. 4077 of 1985 | 1996_676 | (sister petition) |
| WP(C) No. 860 of 1991 | 1991_305 | (sister petition) |
| WP(C) No. 13029 of 1986 | 1998_274 | (possibly OCR typo of 1985 — a real data-quality case) |

Children are explicitly nested in headers: *"I.A. No. 1967 In I.A. No. 1785 In Writ Petition (C) No. 4677 of 1985"* (2009 INSC 750). Cross-root references exist: 2009 INSC 750 cites both WP 4677/1985 and WP 202/1995.

**Implication:** the schema's `proceeding_id` (root docket) + `parent_application` (IA nesting) + multi-root forests is exactly what the data provides. The `case_id|issue|party_role` key from the pivot doc is **wrong** — it must be `proceeding_id | application_chain` for case tracks, plus citation links for precedent tracks.

### 1.2 Party names are NOT identity keys — the Darshan Singh trap

Verified: the "Darshan Singh v. State of Punjab" family is **name collision**:
- 1952 INSC 66: constitutional challenge to cotton-cloth export controls (5-judge bench)
- 2024 INSC 19: murder conviction appeal (Criminal Appeal No. 163 of 2010)
- 2019 INSC 1327: different criminal appeal (No. 1688 of 2009)

Same common names, different people, different cases. **Any party-pair-based linking heuristic produces fabricated longitudinal tracks.** Only docket numbers + IA chains + dated prior-order references are valid track keys. This validates the plan's Tier-1 rule ("never auto-merge what we cannot prove") with a concrete negative control.

### 1.3 The evidence-anchor substrate is stronger than radiology

SCR-format judgments provide **two** anchors per fact:
1. **Verbatim sentence in the judgment PDF** (our standard span anchor)
2. **Pin-cite**: every holding is numbered and tied to a published page reference — `[870A-B]`, `[871E-G]` (1991 INSC 75). Modern cases use paragraph numbers ("para 18 of the judgment in M.C. Mehta case").

Prior-order references are date-keyed: *"By orders dated 29/30.10.2002, the Supreme Court prohibited and banned all mining activities"* — the temporal link for track stitching is present in the text itself.

### 1.4 OCR reality check

- Born-digital modern cases (2016+): clean extraction, `Issue for Consideration` and `Headnotes` sections present.
- 1990s SCR scans: broken glyphs ("indispensable neces­sity", "sustaine~ effort"), ligature artifacts — **the evidence gate's substring check will fail on some spans**. The "mangled span" problem (pivot §4.3 item 4) is real in this dataset and must be handled with fuzzy span matching + OCR-confidence surfacing.
- The 1952 case is a 16-page scan with heavy noise — usable as an OCR stress-test, not for v0 gold.

## 2. Frame schema v3 (data-informed corrections to pivot §4.1)

| Slot | Change from pivot v2 | Reason |
|---|---|---|
| `proceeding_id` | **new, mandatory**: `proceeding_type | number | year` (e.g., WP(C)|4677|1985) | real identity anchor found in every header |
| `parent_application` | **new**: IA chain (I.A. 1967 → I.A. 1785 → root) | explicit nesting in headers |
| `speaker` | keep | court_majority / court_dissent / party_argument / lower_court_finding |
| `issue` | keep; seed taxonomy from subject-matter headers (EPA 1986, MMDR Act 1957, Articles 21/48-A/51-A) | headers provide a natural seed vocabulary |
| `procedural_event_type` | keep; add `order_reference(date)` | prior-order mentions are the temporal stitches |
| `holding` | keep; holdings come pre-numbered (`HELD: 1. ...`) | natural frame boundaries |
| `pin_cite` | **demote from slot to span property** — anchor metadata (`[870A-B]`, `para 18`), absent in most HC corpus | critic fix: not a slot; property of evidence span |
| `evidence_text` + span | keep, plus **span confidence + two-tier anchoring** (see §3 OCR policy) | OCR noise (see 1.4); exact for born-digital, fuzzy≥0.9 with confidence for scans |
| `party` + `role` | **key-adjacent, not display-only** — searchable, collision-aware, human-confirm resolution | Darshan Singh trap (1.2) forbids key use; lawyers search by caption — resolve via queue (pivot §4.2) |

**Track keys v3:** case tracks = `proceeding_id | application_chain`; precedent tracks = `citation | issue`; cross-case links = dated order references + para citations. Never party-pair.

## 3. Pilot gold protocol (v2 — critic-corrected 2026-08-14)

- **Corpus (4 litigation shapes, 9 decisions):**
  1. **WP(C) 4677/1985 chain** (M.C. Mehta, PIL/continuing-mandamus control): 1996 INSC 1179 → 1996 INSC 677 → 2009 INSC 750 — IA nesting, cross-root references, temporal stitching
  2. **Raj Kumar Mohan Singh v. Raj Kumar Pasupatinath Saran Singh** (private civil): 1968 INSC 112, 1969 INSC 130 — Civil Appeal No. 380 of 1965 chain
  3. **CIT, U.P. v. Nainital Bank Ltd.** (institutional tax appeals): 1964 INSC 197, 1966 INSC 166
  4. **Darshan Singh name-collision negative control** (criminal appeals): hard pair 2019 INSC 1327 vs 2024 INSC 19 AND easy pair 1952 INSC 66 vs 2024 INSC 19 — score false-merge rate over both; gold must NOT link either.
- **v0 scope (critic fix #4):** ONE root chain first — WP 4677/1985 chain (3 decisions), est. 60–100 frames, 2–4 days solo curation; frame/hour estimates written BEFORE curation, not after; expand only after a review pass.
- **Gold unit:** one frame per holding / procedural event / prior-order reference, slots per §2 + verbatim span + pin-cite.
- **Linking gold:** group decisions by root proceeding; link IA chains; mark cross-references (date-keyed orders, para citations). Never party-pair.
- **OCR policy (critic fix #6 — chosen BEFORE curation, recorded here):** two-tier anchoring. Tier-1 exact verbatim substring (born-digital); Tier-2 fuzzy ≥0.9 similarity with per-span `confidence` recorded in gold, used only for pre-1998 scans, scored on a separate path. No silent fuzzy fallback.
- **Docket validation (critic fix #5):** `proceeding_id` candidates must agree across ≥2 header mentions in the same PDF; cross-check SC-AWS metadata `cnr` where present; disagreements (WP(C) 13029 of 1985 vs 1986) become `resolver_test` items for the human queue — positive tests of resolution, not exclusions.
- **Party slots (critic fix #7):** party/role restored to key-adjacent: searchable, collision-aware, human-confirm resolution per pivot §4.2. Displayed always; trusted never.
- **Metadata trust rule (found 2026-08-14):** SC-AWS metadata mislabels case_ids (1968 INSC 112 listed under both CIT and Raj Kumar families; the PDF is Raj Kumar's). Gold verifies identity from PDF text; metadata is a hint, recorded but never authoritative. Duplicate rows exist — dedup before counting.
- **Annotator plan (critic fix #8):** v0 = LLM-assisted curation + founder verification. Public-benchmark claims require a named legal advisor + κ ≥ 0.6 on a random 10% sample; until then this is a dev tool and Phase 4's benchmark gate is demoted accordingly.
- **Geography amendment (critic fix #2 — records the C#4 reversal):** pivot v2 said US-first pilot gold. Amended deliberately: India SC gold ships first because the data is free, instant, verified on tyrone, while CourtListener needs a paid membership; US gold starts the day membership is secured. A decision, not a drift.
- **Discipline (from tmc):** engineering-curated label, source evidence per frame, corrections recorded not deleted, frozen manifest before any scoring.
- **Held-out rule (added 2026-08-14, B4):** scoring conventions (frame format, slot vocabularies, matching/tolerance rules, track-key definitions) are frozen on the WP 4677/1985 v0 chain. 2004 INSC 188, the Darshan Singh pairs, Raj Kumar Mohan Singh, and Nainital Bank are curated as **held-out**: once the extraction system first runs on them, no convention changes; any convention change requires re-annotating v0 or declaring a new gold version.
- **Minimum reportable size (added 2026-08-14, B5):** no metric is quoted outside dev until gold covers **≥100 link annotations across ≥3 litigation shapes** (track metrics) and **≥200 frames across ≥3 shapes with per-shape breakdowns** (frame metrics). The v0 set (40 frames, ~12 links, 1 shape) is a dev fixture, not a benchmark.
- **Vocabulary freeze before scoring (added 2026-08-14, B6/C15):** v0 gold uses ad-hoc vocabularies — verified 6 `holding` values ({orders:17, none:11, restate:6, adopts:4, clarifies:1, follows:1}) and 17 `procedural_event_type` values across 40 frames, no enum spec. Before any Type-F1-style scoring: define both enums (target ≤12 event types, ≤8 holding values, each with a one-line definition + one inclusion/exclusion example), re-tag v0 under the frozen enums as a recorded gold version bump, never silently.

## 4. v0 gold status (2026-08-14)

**v0 COMPLETE — 3 decisions curated, track-linked, frozen:**

| File (tyrone:~/data/legal/gold/) | Frames | Status |
|---|---|---|
| `legal_gold_v0_1996_INSC_1179.json` | 16 | I.A. 29 — Badkhal/Surajkund construction ban clarification |
| `legal_gold_v0_1996_INSC_677.json` | 12 | I.A. 22 — hazardous-industry relocation land use |
| `legal_gold_v0_2009_INSC_750.json` | 12 | I.A. 1785/1967 — Aravalli mining suspension (448 sq km) |
| `legal_tracks_v0.json` | 1 case track, 1 clarifies-link, 4 prior-order refs, 3 cross-refs, 2 negative-control pairs, 1 resolver test | |
| `legal_gold_v0_manifest.sha256` | SHA-256 frozen manifest | |

**Total: 40 frames, all tier-1 anchored (verbatim extracted text + positions), 0 span mismatches on verification.** All three decisions share root proceeding WP(C) 4677/1985 spanning 1996–2009; the clarifies-link chains 677's direction 4 → 1179's directions 1–4; 750's para-18 cross-ref resolves to 2004 INSC 188 (downloaded, uncurated).

**Curation pace (measured):** ~1.5 hours/decision including anchor debugging for 1990s scans; 2009 (born-digital) ~30 min. **Full-chain extrapolation: ~4–6 decisions/day solo.**

**Next curation order (amended 2026-08-14, B6/C8):** Raj Kumar Mohan Singh (1968 INSC 112 / 1969 INSC 130, private civil) or Nainital Bank (1964/1966, tax) comes **before** Darshan Singh — the open question is whether `proceeding_id | application_chain` keys even exist in non-PIL shapes (schema generality), which outranks false-merge resistance. Darshan Singh second (both pairs, running the negative-control test). 2004 INSC 188 continues the same PIL chain — lowest information; curate last.

### Curation-methodology lessons (recorded, not hidden)

1. **Anchor to the ACTUAL extracted text, never reconstructed English.** Three failed script iterations proved that hand-recalled fragments do not exist in 1990s OCR ("artd" for "and", "(1987]" for "[1987]", "Articles 21. 47," with a period). The working method: search for a short distinctive phrase in the extracted text, verify, then record that exact string + span.
2. **SCR page-marker interleaving is pervasive**: standalone column letters ("law E of the land") and page breaks fragment sentences throughout. Spans must tolerate markers; a span-cleaning normalizer (strip standalone letters) is the first normalizer the legal adapter needs.
3. **OCR errors concentrate in known patterns**: l/I confusion ("l:J.dia"), slash/letter confusion ("Ve/lore", "Foram"), soft hyphens, comma/period swaps. These become the evidence-gate's legal-specific fuzzy rules.
4. **The tier-2 fuzzy policy was validated by failure, not theory**: exact-only anchoring would have excluded this entire 1996 decision from gold. The two-tier policy (exact on born-digital; the 1990s scans need care) is the right call, now with data.
5. **Page/para pin-cites in SCR format** (`[870A-B]`) are a second, publication-stable anchor that survives OCR noise better than character spans — consider pin-cite as the primary anchor for pre-1998 scans in the next curation pass.
