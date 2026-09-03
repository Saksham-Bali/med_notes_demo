# HANDOFF — FindingFrame → Evidence-Anchored Memory Layer (Legal-First Pivot)

**Written:** 2026-08-14 · **Handing off from:** prior agent session (pivot research + legal pilot gold build)
**Where to continue:** see §5 "Where to pick up"

---

## 1. Context in one paragraph

The repo pair is: `~/project/tmc` (FindingFrame research engine — oncology radiology pipeline: LLM slot-typed "frame" extraction with verbatim evidence spans, deterministic composite-key track linking, human review + hash-chained audit, slot-level F1 evaluation) and `~/project/pre` (IndigoEdge monorepo: the productized version "Dasyante" in `pre/findingframe/`, strategy docs in `pre/strategy/`, vendored engine at `pre/tmc/`). Over 2026-08-13/14 the founder pivoted strategy: generalize the engine into a horizontal **evidence-anchored memory layer** with **legal judgments as the first vertical**, guided by the agent-memory survey arXiv 2602.06052v4 (TMLR 2026). Research is done, strategy docs are written and critic-passed, datasets are downloaded to the remote server **tyrone**, and the first legal gold frames are curated and frozen.

## 2. Key documents (read first, in this order)

All paths absolute:

1. **`/Users/sher/project/pre/strategy/PIVOT_MEMORY_LAYER_2026-08-13.md`** — the pivot strategy (v2, critic-passed). Legal-first vertical, GATE 0 demand validation (one written willingness-to-pay signal before any build commit), India-corpus/US-gold-and-revenue hybrid, unit economics, risks. Critic-pass record in §11.
2. **`/Users/sher/project/pre/strategy/MEMORY_LAYER_IMPLEMENTATION_PLAN_2026-08-13.md`** — unified build plan v2. Three-tier actor model (deterministic core never learned / RL policy proposes + verifier disposes / human adjudicates; plus Tier 2.5 = MemRL-style runtime utility learning), phases −1..7 with kill gates, Memory Gym spec (Prime Intellect methodology), RL reward spec, economics ledger.
3. **`/Users/sher/project/pre/strategy/DATASET_ACQUISITION_PLAN_2026-08-13.md`** — verified dataset sources with working download commands; §8 has the tyrone-verified stats.
4. **`/Users/sher/project/pre/strategy/PILOT_DATA_FINDINGS_2026-08-14.md`** — the data deep-dive: judgment structure findings (forest of parallel writs, name-collision trap, metadata mislabels), frame schema v3, critic-corrected pilot gold protocol (v2), and v0 gold status + curation-methodology lessons. **This is the doc that describes the work in progress.**
5. `/Users/sher/project/tmc/AGENTS.md` — repo conventions and number discipline (the team's documented failure modes: post-hoc measurement conventions, class-average mislabels, never mixing benchmark sources, corrections recorded not deleted).

Supporting research artifacts (raw scrapes + agent deliverables): `/Users/sher/project/tmc/.firecrawl/memory-survey/` (PI research `PRIME_INTELLECT_MEMORY_RESEARCH.md`, five-model critique panel `MODEL_CRITIQUES.md`, RL paper scrapes memalpha/mem1/memoryr1/memagent…, OSS scrapes supermemory/mem0/letta/graphiti) and `/Users/sher/project/tmc/.firecrawl/pivot-legal-memory/` (legal market + pricing research).

## 3. The data (on tyrone — `ssh tyrone`, user `deep`, 112 cores)

| Path on tyrone | What |
|---|---|
| `~/data/legal/kanoongpt/` | KanoonGPT Indian case laws, year-parquets 2015–2025, **13.1M rows**, 7.8GB. 39 columns incl. parties/docket/CNR/court/disposition/quality flags; `indexable_text` is header-summary only |
| `~/data/legal/sc-aws/` | AWS Open Data Supreme Court metadata parquets 1950–2026, **43,532 rows**, 47MB (no-account S3: `indian-supreme-court-judgments` bucket) |
| `~/data/legal/pilot_families/` | 31 SC judgment PDFs + extracted `.txt` (pypdf): M.C. Mehta forest, CIT v. Nainital Bank, Raj Kumar Mohan Singh, Darshan Singh pairs, Common Cause |
| `~/data/legal/gold/` | **THE GOLD** — see §4 |
| `~/data/legal/analyze*.py`, `gold_v0_curate*.py`, `gold_v0_tracks.py` | analysis + curation scripts (working copies; the curation methodology is encoded here) |
| `~/venv-data/` | python venv with pyarrow, pandas, pypdf |

Key verified data facts (do not re-derive; details in DATASET_ACQUISITION_PLAN §8):
- SC full-text PDFs are directly addressable: `https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/data/pdf/year={Y}/english/{path}_EN.pdf` where `path` comes from the SC-AWS metadata parquet (100% coverage; born-digital, clean extraction).
- HC full text: JSONs on `indian-high-court-judgments` S3 contain header HTML only; full text via PDFs.
- **SC-AWS metadata has duplicate rows and mislabeled case_ids** (1968 INSC 112 listed under two families) — verify identity from PDF text, never trust metadata.
- 188 SC case families (same parties ≥2 decision-years); party-pair alone is NOT a valid track key (Darshan Singh = name collision of different people).

## 4. The gold work (v0 COMPLETE, frozen)

Files in `tyrone:~/data/legal/gold/`:
- `legal_gold_v0_1996_INSC_1179.json` — **16 frames** (I.A. 29, Badkhal/Surajkund construction-ban clarification)
- `legal_gold_v0_1996_INSC_677.json` — **12 frames** (I.A. 22, hazardous-industry relocation land use; the 10.5.1996 order)
- `legal_gold_v0_2009_INSC_750.json` — **12 frames** (I.A. 1785→1967, Aravalli mining suspension, 448 sq km)
- `legal_tracks_v0.json` — track-linking gold: 1 case track (3 children of root Writ Petition (C) 4677/1985, 1996–2009), 1 clarifies-link (677 direction 4 → 1179 directions 1–4), 4 prior-order refs, 3 cross-refs (incl. para-18 of **2004 INSC 188** — downloaded, NOT yet curated), 2 Darshan Singh negative-control pairs (hard pair 2019-vs-2024 + easy pair 1952-vs-2024), 1 resolver test (WP 13029 of 1985-vs-1986)
- `legal_gold_v0_manifest.sha256` — frozen manifest; verification pass was **0 span mismatches**

Gold frame format: frame_id, speaker, issue, procedural_event_type, holding, application_chain, prior_order/citation/pin (optional), evidence{start, end, tier, confidence, actual} — `actual` is the verbatim extracted text with positions into the `.txt` file. Anchoring policy: **tier-1 exact substring on extracted text**; tier-2 fuzzy ≥0.75 (policy defined but unused so far — all v0 frames are tier-1).

**Curation methodology (the hard-won lessons — in PILOT_DATA_FINDINGS §4):**
1. Anchor to the ACTUAL extracted text, never hand-recalled English. OCR errors are pervasive: "artd"/"and", "(1987]"/"[1987]", "Articles 21. 47,", "l:J.dia", "rnining", "opE~rations".
2. SCR page-marker letters interleave mid-sentence ("law E of the land") — spans must tolerate them; a marker-stripping normalizer is the legal adapter's first need.
3. Working method: read the decision → test anchor phrases against the extracted text in a batch → curate with short distinctive anchors + window → verify span positions resolve → freeze.
4. Measured pace: ~1.5 hrs per 1990s-scan decision, ~30 min per born-digital decision → 4–6 decisions/day solo.

## 5. Where to pick up (three candidate next steps, in recommended order)

1. **Expand gold to complete the pilot corpus** (~1 day): curate **2004 INSC 188** (target of the para-18 cross-ref — already downloaded at `tyrone:~/data/legal/pilot_families/2004_INSC_188.pdf`), and the **Darshan Singh negative-control decisions** (2019 INSC 1327 + 2024 INSC 19 + 1952 INSC 66 — all downloaded) so the negative-control tests can actually run. Protocol: PILOT_DATA_FINDINGS §3.
2. **Build the extraction baseline probe**: run the existing oncology `FindingFrameExtractor` prompt on one curatable judgment (expected to fail badly on legal slots) — this is the pre-adapter baseline measurement the schema work will be graded against.
3. **KeySpec spike**: start the `DomainAdapter` refactor (MEMORY_LAYER_IMPLEMENTATION_PLAN Phase 1; pivot §6.2 lists the 10-method interface). Extract the composite-key spec from `tmc/fact_graph/frame_linker.py` and test it against the legal gold's `root_proceeding | application_chain` keys.

Do NOT start before re-reading: PILOT_DATA_FINDINGS §3 (protocol v2 incl. all 8 critic fixes — especially: PIL-only corpus is fixed, OCR two-tier policy is pre-committed, geography amendment is recorded, annotator/κ plan demotes benchmark claims to dev-tool until a named legal advisor exists).

## 6. Hard rules and traps

- **Number discipline**: every figure needs a source + caveat; never mix standard-benchmark scores with frozen-benchmark scores in one table; pre-commit thresholds BEFORE running evals; corrections recorded, never silently deleted (this team's own documented failure mode).
- **Never use `pre/tmc` or `pre/findingframe` code paths** without checking they match `~/project/tmc` (engine copy drift was a past incident — see `/Users/sher/project/pre/PRE_UPDATE_PLAN_2026-07-30.md`).
- **Simulated data never cited**: `tmc/outputs/finding_frame_runs/simulated/` is fake by construction.
- **Gold status honesty**: everything curated so far is engineering-curated dev gold — NOT lawyer-adjudicated. Say so in every artifact and doc.
- **On tyrone**: use `~/venv-data/bin/python`; SSH sometimes times out when the server is busy — retry with `-o ConnectTimeout=15`; run long jobs with `nohup ... &` and check via `pgrep`.
- **Secrets**: none live in any of these docs; tyrone `.env` files exist but are out of scope. Never copy them anywhere.

## 7. Suggested skills for the next agent

- `decision-mapping` — the open-decision list (§5 of the implementation plan + PIVOT doc §10) is a ready-made ticket queue
- `domain-modeling` — pin down the frame schema v3 vocabulary (proceeding_id, application_chain, speaker, holding…) as ubiquitous language
- `tdd` / `test-driven-development` — for the KeySpec spike and the extraction probe (gold JSONs are the test fixtures)
- `goal-forge` — if the founder wants to convert the implementation plan into a /goal contract
- `firecrawl` — for any further web research (authenticated; store scrapes in `tmc/.firecrawl/`)
