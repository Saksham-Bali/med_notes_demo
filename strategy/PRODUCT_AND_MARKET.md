# IndigoEdge — Product & Market Reference

**Version:** 2026-07-16 · **Companion docs:** `PITCH.md`, `MARKET_RESEARCH.md`
**One-line:** Audit-grade oncology data abstraction — every fact traceable to its source sentence, RECIST progression computed deterministically — validated at India's largest cancer network, sold to pharma/CRO worldwide.

> **Number discipline:** Market figures are analyst estimates; scope definitions vary. Ranges and sources are named. Where a figure is *our* estimate (not an analyst report), it is flagged. Do not pitch the broad "$20B RWE" number — anchoring on the oncology-specific figure signals diligence-readiness; the big number signals the opposite.

---

## 1. What the product is

FindingFrame is an **evidence-anchored, slot-based oncology extraction and longitudinal-tracking pipeline.** The design principle: *LLMs handle language understanding; deterministic code handles identity, verification, and linking.*

**Pipeline:**
```
Radiology reports
  → Report cleaner (section segmentation)
  → LLM frame extractor (structured slots + mandatory evidence span)
  → Evidence gate (drops any finding whose source sentence isn't verbatim-locatable)
  → Deterministic slot normalizer (anatomy / laterality / temporal)
  → Composite-key track linker (finding_type | anatomy | laterality) — no fuzzy LLM matching
  → TrackGraph + RECIST 1.1 engine (deterministic SLD tracking, PD/SD/PR/CR)
  → Clinician review UI (approve/reject each fact) → longitudinal patient record
```

**Each finding = a "frame" with 6 slots** (finding_type, anatomy, laterality, measurement, temporal_change, assertion) **+ a verbatim evidence sentence.** Nothing enters the record without a source anchor and a human sign-off.

**Validated capability (engineering gold, 30 MIMIC-IV patients — *pre-clinical-validation*):**
- Type F1 **0.855**, Identity F1 **0.751**, Full-Frame F1 **0.639**; mean per-slot accuracy **0.924** on the 20 held-out patients. (The 8 development patients score 0.962, but prompts and rules were tuned on them, so that figure measures fit, not capability — and it averages in a temporal-change accuracy of 1.000 that the deterministic normaliser earns at scoring time, not the model.)
- On a 208-question longitudinal QA benchmark over the same cohort: **0% hallucination by construction**, 95.2% evidence-grounding rate.
- Domain-transfer to chest X-ray (RadGraph2 / ImaGenome): Type F1 0.74–0.78 with no retraining, 96.3–96.6% evidence-anchoring.
- Backend-agnostic across GPT-5, DeepSeek-V4-Pro, GLM-5.2, MiniMax — Type-F1 spread only 0.030.
- **Honest weakness:** track-linking F1 = **0.382** under strict Jaccard≥0.5 matching (all 30 patients); a permissive frame-cluster match gives 0.741 — the two are not interchangeable. No clinician κ yet. → product is a *reviewer accelerator*, not an autonomous system, until validation says otherwise.

> **Reading these figures:** they are patient-macro averages over the frozen 30-patient cohort, under one scorer convention. That convention collapses metastasis anatomy to an organ family, so a wrong anatomy value is not penalised on 41.1% of gold frames — a `liver_metastasis` frame recorded with anatomy `spleen` scores as correct. A clinician reading a track should know the anatomy field was not independently checked there.

## 2. Key differentiators (ranked)

1. **Verified per-fact provenance — 0% hallucination by construction.** Every fact carries a gate-checked verbatim source sentence. This is *architectural*, not statistical — the only claim that survives a pharma audit or an FDA RWE submission. **Lead with this always.**
2. **Deterministic linking + RECIST 1.1.** Same reports in → same tracks and progression out, every time. Reproducibility is a regulatory requirement that end-to-end-LLM competitors cannot honestly make.
3. **Model-agnostic (4 backends, zero retraining).** No vendor lock-in; on-prem / sovereign deployment — decisive under India's DPDP localization and pharma security review. Also a cost hedge as model prices fall.
4. **Human-in-the-loop by design.** Clinician approves each fact — turns the track-F1 weakness into the product story (abstractor acceleration with a measured path to more automation).
5. **India-native multilingual (Sarvam).** No US competitor can process the National Cancer Grid's multilingual report streams. Sole credible claimant to the 860K-patients/yr asset.
6. **India cost structure.** Clinician review at Indian rates + AI = **5–10× cost advantage** over US abstraction shops on identical audit-grade output.

## 3. Market sizing (2030 horizon)

**Anchor:** the **oncology RWE solutions market — $974.1M (2026) → $3,088.1M (2036), ~12.2% CAGR** — *not* the broad $20–22B RWE figure (analyst scope ranges $2.8B–$24.6B, a ~9× spread; includes consulting/claims/analytics we don't touch).

### TAM — total oncology data abstraction / RWE opportunity: **$4–6B**
| # | Component | 2030 value | Basis |
|---|---|---|---|
| 1 | Oncology RWE solutions | **$1.55B** | Anchor figure, grown to 2030 |
| 2 | Oncology trial data-management spend | **$2.3–4.0B** | Global trials ~$128B (2030) × ~35–40% oncology × ~5–8% data mgmt |
| 3 | Imaging central review (BICR / RECIST) | **$0.3–0.9B** | *Our estimate:* ~500–800 onc trials/yr × ~$0.5–1.5M read+adjudication |
| 4 | Cancer registry software | **$0.175B** | $108M (2026) at 12.85% CAGR |

Sum ≈ **$4.3–6.6B → call it $4–6B.** Caveat: items 2–3 are *spend pools we substitute into*, not software markets; pure software TAM (items 1+4) ≈ **$1.7B.**

### SAM — audit-grade oncology abstraction + RECIST, pharma/CRO/registries, India + global: **$0.9–1.3B**
- Curation/abstraction share of oncology RWE (~50% of $1.55B) → **~$775M**
- RECIST/BICR automatable as pre-reads/QC (30–50% of item 3) → **$150–300M**
- Registry abstraction → **~$100M**
- India CRO oncology data services (abstraction-reachable slice) → **$50–100M**

Midpoint **~$1.1B.** Variance dominated by the BICR estimate (least analyst-verified number here).

### SOM — 3–5 yr capture, India-first: **$6–12M ARR by year 5** (0.6–1.1% of SAM — deliberately unglamorous; anything >2% top-down at this stage is fiction)

**Bottom-up, three revenue lines:**
1. **NCG registry deployments** *(validation, not riches)* — 60 of 244–380 centers × ~$25K/center/yr ≈ **~$1.5M ARR.** Strategically priceless (validation + data rights); do not pitch as the business.
2. **Pharma/CRO trial abstraction + RECIST pre-reads** *(the dollar engine)* — price AI-assisted, clinician-approved abstraction + RECIST pre-read at **$500–1,000/patient** vs ~$1.5–3K manual BICR (50–70% savings). Year-5: 10–15 trials × 250–400 patients = **$2.5–6M/yr.**
3. **RWE dataset licensing** *(the Flatiron option, year 3+)* — 50–100K curated provenance-complete records; 2–4 pharma deals at $250K–1M → **$1–3M** in year 5.

**Year-5 total: $5–10.5M base, $6–12M with licensing upside.** At oncology-data multiples (8–15× revenue with a provenance moat), a **$60–150M trajectory at Series B** — the *NCG data asset* (860K patients/yr through a provenance-complete pipeline) is what re-rates the company beyond services multiples, mirroring Flatiron's $1.9B → reported $10–15B arc.

## 4. Competitive positioning

| Competitor | Their strength | Where we win | Verdict |
|---|---|---|---|
| **Flatiron Health** ($1.9B exit → reported $10–15B) | US community-oncology EHR data, armies of abstractors, pharma trust | Geography (860K-pt/yr India), cost, per-fact traceability granularity | Don't fight in US; be "Flatiron's data factory rebuilt provenance-first, for the market they can't enter" |
| **Tempus AI** (public, ~$690M rev) | Sequencing-anchored multimodal molecular data | Different wedge (we structure imaging narrative, not molecular) | Cite as *category validation*, not competitor |
| **ConcertAI** ($70M Series C, ~$630M val) | US enterprise RWE SaaS, pharma relationships | RECIST automation (they don't), deterministic reproducibility, India | Their stage-valuation is your Series B comp |
| **Carta Healthcare / John Snow Labs** | *Same* "regulatory-grade, full-traceability abstraction" language, live in registries now | Longitudinal tracks + RECIST progression (they abstract snapshots), architectural gate vs post-hoc QC, model-agnostic, India | **The real threat — track quarterly; if they announce RECIST, compress timeline** |
| **Ambient scribes** (Abridge $5.3B; $1.2B→$15B mkt) | Encounter documentation for billing | N/A — different job entirely | **Do not enter, do not get compared.** "Scribes produce notes for humans; we produce audited data for regulators." |

## 5. What we must NOT claim (diligence killers)

- **No clinical-validation claims yet** — 30 MIMIC-IV patients, engineering gold, no κ. Say *"architecturally validated; clinical validation underway at Tata Memorial."*
- **Never conflate 0% hallucination with 0% error** — the gate guarantees no *fabricated* facts, not recall/slot accuracy. Precise phrasing: *"zero unsupported facts by construction."*
- **No autonomous RECIST / BICR-replacement claims** — track F1 is 0.382 under strict Jaccard matching; it's a *pre-read + abstraction accelerator with clinician sign-off* until data says otherwise.
- **No regulatory-clearance implication** — say *"audit-ready architecture,"* never "FDA-cleared." (Carta/JSL's "regulatory-grade" is aspirational too — but you'll be held to yours.)
- **Don't pitch the broad $20B RWE TAM.**

## 6. Focus discipline — keep / park / kill

**KEEP (this is the product):** FindingFrame extractor · deterministic Fact Graph · RECIST engine · QA gatekeeper · clinician-review UI.
**PARK (18 months):** patient-facing views · department-merge · discharge-summary generation (unless TMC contractually requires it).
**KILL / spin down:** voice-counselling transcription · TTS + multilingual translation · general handwriting OCR — each is a separate company (and the speech pieces are Sarvam's business, not ours).

## 7. The critical path (what unlocks the check)

1. **200-patient clinician-adjudicated validation at Tata Memorial** — inter-rater κ per slot + track level; push track-linking F1 toward >0.7. *This is simultaneously the FindingFrame paper's #1 blocker and the startup's #1 fundability unlock — one body of work serves both.*
2. **One killer ROI number** — "RECIST abstraction: ~1 hour → ~20 minutes per patient, 100% source-traceable."
3. **A paid TMC engagement or National Cancer Grid LOI.**
4. **2 pharma/CRO pilots** priced per patient.
5. **Regulatory story as offense** — "the 2026 rules require exactly what we architected in 2024."
