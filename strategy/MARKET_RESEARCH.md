# Market Research — IndigoEdge / ClinIQ / FindingFrame

**Compiled:** 2026-07-16 · **Method:** Firecrawl web search + scrape (raw results in `pre/.firecrawl/market/`).
**Purpose:** Evidence base for the strategic pivot from "backbone of all hospital data" → **audit-grade oncology data abstraction, India-first for validation, pharma/CRO for revenue.**

> All figures are analyst/market-report estimates. Definitions vary widely between reports (especially "RWE" and "healthcare analytics"), so ranges are given and the source metric is named. Treat single-source numbers as directional, not precise.

---

## 1. The zone to AVOID — Ambient clinical documentation (scribes)

- Market ~**$1.2B (2025) → ~$15B (2034–35)**, ~28.8% CAGR. Note generation = 53% of the market; hospitals/health systems = 55%; **North America = 50–76%** of activity/capital.
- **Clinical documentation is 44% of all healthcare-AI deal activity and 60% of the dollars** — the single most crowded, best-funded category.
- Funding is brutally concentrated: 25 disclosed scribe deals / **$1.54B over 4 years**; top 3 deals = 51% of capital.
- **Abridge:** ~$700M+ raised across 2024–25, **$5.3B valuation** (doubled in 4 months), **$100M+ ARR**, Best in KLAS 2025 & 2026. Ambience ($243M Series C), Nabla ($120M total), Suki, Freed (Sequoia) all entrenched.
- **Verdict:** A new US scribe entrant cannot win. Do not compete here.

## 2. The occupied zone — "Unified longitudinal record / data backbone"

- **Innovaccer** explicitly sells "unified longitudinal patient record + agentic AI data layer." **Health Catalyst** sits on 100M+ patient records.
- Healthcare analytics market ~**$55B (2025) → ~$166B (2030)**, ~24.6% CAGR (broad definition).
- In India, **ABDM (Ayushman Bharat Digital Mission) IS the backbone** — govt-owned, **1B+ (104 crore) linked health records**, ABHA IDs, Unified Health Interface. **Eka Care** owns the consumer rail: 110M+ records, 50M+ users — but raised only ~$20M (low-ARPU consumer economics).
- **Verdict:** "Be the backbone" pits a seed startup against incumbents, the EHR, and a government. Trap. Plug into ABDM; don't rebuild it.

## 3. The TARGET zone — Oncology data / RWE / abstraction

- **Oncology RWE solutions market: $974.1M (2026) → $3,088.1M (2036).** (Broader RWE solutions: ~$20–22B in 2025–26; scope-dependent, some reports $2.8B–$24.6B.)
- **Cancer registry software: ~$108M (2026) → $285M (2034)**, 12.85% CAGR. Small but the purest "abstraction" analog.
- **ROI anchor:** "a single chart abstraction for tumor registry reporting requires **~1 hour of certified specialist time**." Manual, labor-bound, audit-heavy — the exact task to automate.
- **RECIST 1.1** = imaging gold standard for 40 years; trials use **Blind Independent Central Review (BICR)** — double reads + adjudication, expensive, high inter-reader variability. Clear automation opportunity, and FindingFrame already computes RECIST deterministically.
- **Direct competitors to watch:** **Carta Healthcare** (oncology registry abstraction, "hybrid intelligence," July 2026) and **John Snow Labs** ("regulatory-grade AI for cancer registries, full traceability") — note they are *already* using the traceability angle. **Flatiron Health** (closest strategic analog).

## 4. Comparables (exit / valuation evidence)

| Company | What | Milestone |
|---|---|---|
| **Flatiron Health** | Oncology EMR data + RWE | Acquired by Roche **$1.9B (2018)**, ~$2.1B w/ earnouts; had raised $314M. Roche reportedly weighing a sale at **$10–15B (2026)**. |
| **Tempus AI** (public) | Oncology data + diagnostics | Revenue $532M (2023) → ~$690M (2025); Q1 2026 rev $348M. "Nvidia of healthcare" framing (also a short-seller target). |
| **ConcertAI** | Oncology RWD/RWE | $70M Series C at ~**$630M** valuation. |

**Takeaway:** Oncology data abstraction is a proven multi-billion-dollar category with a $10B+ potential exit comp (Flatiron). This is where FindingFrame's real strength lives.

## 5. India — the validation beachhead

- **National Cancer Grid (NCG):** 244–380+ centers; treats **~860,000 new cancer patients/year = 60–70% of all Indian cancer cases.** Tata Memorial anchors it (~43,000–70,000 new patients/yr).
- **India clinical trials market:** ~$2.1–3.1B (2025) → ~$4.6–6.6B (2034), ~8.6% CAGR. **India CRO market:** ~$6.74B (2025) → $12B (2035). Global clinical trials ~$89B (2025) → $158B (2033).
- India = less crowded, multilingual moat (Sarvam stack), NABH accreditation as a hospital wedge, one flagship (TMC) unlocks NCG distribution + clinician-validated gold data at scale.
- **Monetization caution:** Indian hospital SaaS ACVs are ~$10–30K/yr — validation partner, not the primary payer. **Payer = pharma/CRO running trials & RWE studies in India, billed in USD.**

## 6. Why-now (regulation as tailwind)

- **FDA/EMA** published joint guiding principles for AI in drug development (Jan 2026). **India's CDSCO** going digital (DDRS) and tightening AI-medical-device rules. A 2025 **HHS rule** requires AI tools to be part of formal risk-analysis; **>70% of orgs cite governance/compliance as the deployment gate** — "procurement now depends on governance, not feature lists."
- **80%+ of physicians now use AI professionally** (2026 AMA survey) — market is warm.
- **Implication:** Provenance/auditability/reproducibility is shifting from "nice research property" to **procurement and regulatory requirement**. This is a headwind for fuzzy end-to-end LLM extraction and a tailwind for FindingFrame's architecture.

## 7. One-line synthesis

The paper's #1 blocker (clinician κ validation) is also the startup's #1 fundability unlock; the narrowest technical strength (auditable oncology RECIST tracking) is the sharpest wedge. Everything points to: **go deep on oncology abstraction at Tata Memorial, sell provenance to pharma/CRO, don't go wide on hospital data.**
