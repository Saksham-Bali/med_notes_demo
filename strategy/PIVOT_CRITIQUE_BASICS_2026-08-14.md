# Pivot Basics Review — Critique + Clearing List

**Date:** 2026-08-14 · **Status:** v1 — B1 resolved by founder decision; B2–B9 amendments in progress (resolution log at bottom)
**Reviewed:** `PIVOT_MEMORY_LAYER_2026-08-13.md` (v2), `MEMORY_LAYER_IMPLEMENTATION_PLAN_2026-08-13.md`, `DATASET_ACQUISITION_PLAN_2026-08-13.md`, `PILOT_DATA_FINDINGS_2026-08-14.md`, `PRODUCT_AND_MARKET.md`, `PRODUCT_BUILD_PLAN.md`, `PITCH.md`, `MARKET_RESEARCH.md`, `tmc/AGENTS.md`, handoff of 2026-08-14; plus the v0 gold itself on tyrone (spot inspection).
**Convention:** corrections recorded, never silently deleted. Amendments below are marked with dates in the source docs.

---

## 1. The steps so far, in order

1. **Oncology FindingFrame** (tmc): LLM slot extraction + verbatim evidence gate + deterministic composite-key linking. Frozen 30-patient benchmark: Type F1 0.855 / Identity 0.751 / Full-Frame 0.639 (patient-macro, engineering gold, no clinician κ, strict track-linking F1 0.382).
2. **Oncology product** (pre/findingframe): FastAPI + review UI + audit; P0-4/P0-5 open.
3. **Pivot (2026-08-13):** generalize to a horizontal evidence-anchored memory layer, legal first. Critic-passed v2.
4. **Implementation plan (2026-08-13):** 3-tier actor model, phases −1..7, 28–44 person-weeks, kill gates.
5. **Dataset acquisition (2026-08-13):** KanoonGPT 13.1M rows, SC-AWS 43,532 SC cases, pilot PDFs — verified on tyrone.
6. **Pilot findings + v0 gold (2026-08-14):** schema v3, 40 frames on the WP(C) 4677/1985 chain, frozen manifest, curation methodology lessons.
7. **Handoff + this review (2026-08-14).**

## 2. What holds up (do not re-litigate)

- The architectural invariants are domain-free and correct: hybrid split, evidence anchoring, composite-key identity, human sign-off, hash-chained audit.
- The pilot-data pass was the right method and caught three real errors before they calcified: the `case_id|issue|party_role` key was wrong (→ `proceeding_id | application_chain`); party names collide (Darshan Singh trap — a genuine negative control); anchors must target extracted text, not reconstructed English.
- GATE 0 (demand validation before build) is the right discipline and cheap.

## 3. The critique (14 findings + 1 found during verification)

**C1 — The pivot's own logic cuts against it on the annotator bottleneck.** Pivot reason #2 for leaving oncology is the 18-month failure to find a second annotator. The legal plan inherits the identical constraint (κ descoped to feasibility until a named legal advisor exists). **RESOLVED 2026-08-14 (B1): founder accepted the counter-argument — the annotator problem is *cheaper* to solve in legal even if not easier: public data (no DUA/IRB/HIPAA gatekeeper), annotator pool is law graduates/paralegals rather than scarce Tata Memorial clinicians, annotation can run remote/async. Residual: benchmark claims still require a named legal advisor; κ stays feasibility-only (D7 stands).**

**C2 — The gold-status failure mode was about to repeat.** 40 frames, one litigation shape, one curator, conventions defined while curating — the same shape as the oncology dev-cohort overfit (the 0.051-vs-0.037 class-average incident). Fixed via B4: held-out rule + convention freeze added to the protocol.

**C3 — GATE 0 measures the wrong thing for the riskiest claim.** "Would you pay?" doesn't distinguish standalone purchase from platform-absorption (risk #1). GATE 0 should require standalone-purchase intent at a stated price. → folded into B2 amendment.

**C4 — Founder capacity is the real critical path.** ~19–29 weeks of solo engineering that cannot parallelize with the selling GATE 0 requires. The docs state this (§8, C#10) but the phase structure doesn't price it.

**C5 — The "45 lines of domain config" precedent doesn't evidence what it's cited for.** Echo shares radiology *slot semantics*; legal doesn't. The engine's domain-agnosticism is an open empirical question whose first real test is the legal adapter. Pivot §6.1 half-says this; it should be stated as the open question, not a qualified success.

**C6 — The handoff's next steps quietly violated the gate.** Plan Phase 0: "the only pre-GATE-0 work is Phase −1 and this phase." The v0 gold was built the next day; the handoff recommended another day of gold. Cheap and valuable work — but no doc authorized it. Fixed via B2 (bounded pre-GATE-0 feasibility work, capped).

**C7 — "The paper track is unaffected" is false.** The paper's one `\PENDING` is B2 clinician IRR — the same annotator search the pivot redirects. The pivot freezes the paper at 55 pp + 1 pending marker. Legitimate if conscious; priced at zero in the docs. Fixed via B3.

**C8 — v0 gold tests one litigation shape, and the next curation targets answered the wrong question first.** Schema v3's keys were induced from PIL continuing-mandamus alone; civil/tax chains (Raj Kumar Mohan Singh, Nainital Bank) may have degenerate IA nesting. Curating more PIL + Darshan Singh next (the handoff's order) tests false-merge resistance before testing whether the key design exists elsewhere. Order corrected in protocol (B6).

**C9 — Three slot-design problems in schema v3.** (a) `proceeding_id` is OCR-dependent → track quality becomes OCR quality unless a docket parser/normalizer exists — an unpriced core component. (b) `speaker` taxonomy is designed for US polyvocal opinions; verified on the gold: **39/40 frames are `court_majority`** — the slot is degenerate on this corpus. (c) `holding` vocabulary is ad-hoc: verified values on the 40 frames are `{orders:17, none:11, restate:6, adopts:4, clarifies:1, follows:1}` — mixing speech acts with outcomes, 27.5% empty, no enum spec, and it matches neither the pivot's US appellate enum nor KanoonGPT's final-disposition values.

**C10 — Track gold too small to quote.** ~12 link annotations cannot support any F1. B5 pre-commits: no track metric quoted until ≥100 links across ≥3 litigation shapes.

**C11 — Gold durability.** Verified on tyrone: the manifest hashes only the 4 gold JSONs — **no source PDF/txt hashes, no extractor version**; `anchoring_policy` recorded in only 1 of 3 files. Spans are positions into one pypdf run's output and anchor OCR-mangled text ("artd", "l:J.dia"); a better OCR pass orphans them. Fixed via B7 (supplementary source manifest + policy backfill).

**C12 — The headline claim is inconsistent across docs.** PRODUCT_AND_MARKET §2 still says "0% hallucination by construction — lead with this always"; PRODUCT_BUILD_PLAN R5 retracted it the next day; the pivot never propagated the retraction; on OCR'd scans the guarantee is weaker still ("anchored to this mangled string"). Fixed via B8 (one canonical sentence, all docs aligned).

**C13 — Phases 5–7 are a different company inside this plan.** Substrate generalization / RL / Memory Gym / MCP ecosystem answer a developer-memory demand hypothesis that GATE 0 doesn't test. Split out via B9; near-term plan is Phases −1..4 only.

**C14 — Two wording/ledger hazards.** (a) Dataset plan §8 says "the real longitudinal keys: party pair + docket_number + neutral citation" — invites the exact party-pair mistake the pilot disproved; one-line fix applied. (b) Corpus-scale track mining needs a docket parser over 43K PDF headers — added to the effort ledger.

**C15 — (Found during B6 verification) The gold's own vocabularies are uncontrolled.** 17 distinct `procedural_event_type` values across 40 frames (each with 1–8 instances), 6 ad-hoc `holding` values, no enum spec anywhere. This is the oncology 21-class trap *at birth*: any Type-F1-style score against this vocabulary is uninterpretable. Fixed via B6: vocabulary freeze requirement added to the protocol before any scoring.

## 4. The basics-clearing list

| # | Item | Status |
|---|---|---|
| B1 | Pivot vs annotator bottleneck (C1) | **RESOLVED — founder decision 2026-08-14** (counter-argument accepted; D7 residual stands) |
| B2 | Pre-GATE-0 work: allowed? cap? GATE-0 question strengthened (C3, C6) | Amended: impl-plan Phase 0 |
| B3 | Oncology paper consciously frozen (C7) | Amended: PIVOT §8 |
| B4 | Held-out rule + convention freeze for legal gold (C2) | Amended: PILOT_DATA_FINDINGS §3 |
| B5 | Minimum reportable gold size (C10) | Amended: PILOT_DATA_FINDINGS §3 |
| B6 | Vocabulary freeze (`holding`, `procedural_event_type`) + curation retarget to civil/tax shapes (C8, C9, C15) | Amended: PILOT_DATA_FINDINGS §3–4 |
| B7 | Manifest hashes sources + extractor version; backfill anchoring_policy (C11) | Fixed on tyrone: supplementary manifest |
| B8 | One canonical provenance claim across docs (C12) | Amended: PIVOT §3.1, PRODUCT_AND_MARKET §2 |
| B9 | Phases 5–7 split out of near-term plan (C13) | Split: `MEMORY_PLATFORM_TRACK_2026-08-14.md` |

Not separately numbered, done in the same pass: C5 (stated as open question in PIVOT §6.1), C14 (dataset plan wording + docket-parser ledger row). C4 (founder capacity) is a founder scheduling reality, recorded here, no doc fix applies.

## 5. Resolution log

| Date | Item | What changed |
|---|---|---|
| 2026-08-14 | B1 | Resolved by founder decision; recorded in §3 C1 |
| 2026-08-14 | B2 | Impl-plan Phase 0 amended: ≤3 person-days pre-GATE-0 feasibility work allowed; GATE-0 question strengthened to standalone-purchase intent at a stated price (C3) |
| 2026-08-14 | B3 | PIVOT §8 amended: paper track honestly frozen, resumption conditions stated |
| 2026-08-14 | B4 | PILOT §3: held-out rule — conventions frozen on v0 chain; 2004 INSC 188, Darshan Singh pairs, Raj Kumar Mohan Singh, Nainital Bank curated as held-out |
| 2026-08-14 | B5 | PILOT §3: minimum reportable size — ≥100 links / ≥3 shapes (track), ≥200 frames / ≥3 shapes (frame) |
| 2026-08-14 | B6 | Gold verified on tyrone: holdings `{orders:17, none:11, restate:6, adopts:4, clarifies:1, follows:1}`; speakers 39/40 court_majority; 17 event types / 40 frames. PILOT §3: vocabulary freeze before scoring (≤12 event types, ≤8 holding values, re-tag as version bump). PILOT §4: curation retargeted — civil/tax shapes before Darshan Singh; 2004 INSC 188 last |
| 2026-08-14 | B7 | Fixed on tyrone: `legal_gold_v0_sources.sha256` (6 source files) + `README.md` sidecar (extractor pypdf 6.16.0, anchoring policy backfilled). Frozen JSONs untouched; original manifest still verifies OK |
| 2026-08-14 | B8 | Canonical claim added to PIVOT §3.1; PRODUCT_AND_MARKET §2 item 1 re-phrased with pointer to R5 retraction |
| 2026-08-14 | B9 | Phases 5–7 moved verbatim to `MEMORY_PLATFORM_TRACK_2026-08-14.md`; impl-plan near-term total now 22–36 wks (Phases −1..4) |
| 2026-08-14 | C5 | PIVOT §6.1: domain-agnosticism stated as open empirical question pending legal-adapter eval |
| 2026-08-14 | C14 | DATASET §8 party-pair wording fixed; docket-parser workstream added to PIVOT §6.3 (total 19–29 → 20–31) |
| 2026-08-14 | — | Handoff copied `/tmp/` → `pre/docs/handoff_2026-08-14_memory_layer.md` for durability |

**All B1–B9 closed 2026-08-14.** Open carry-forwards (not doc-fixable): C4 founder capacity (decision at GATE-0 exit, D8); the B6 vocabulary freeze and held-out curation are the first tasks of the next gold session; GATE 0 itself remains unstarted — it is now the only unblocked high-priority action.
