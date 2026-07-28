# IndigoEdge — One-Page Pitch

> **"Flatiron built a $1.9B business on human abstractors. We built the abstractor that shows its work."**

---

**Problem.**
Oncology runs on unstructured radiology reports. Turning them into trial-grade or registry-grade data costs **~1 hour of certified-specialist time per chart**, and pivotal trials still pay for **Blind Independent Central Review** — double reads plus adjudication — to compute RECIST 1.1 tumor response. Generic LLMs can't fix this: pharma and regulators reject data they cannot trace. Hallucination here isn't an accuracy problem, it's an **admissibility problem**.

**Insight.**
The unlock isn't a better model — it's an architecture where the model *cannot* invent data. Split the job: **LLMs read language; deterministic code owns identity, linking, and scoring.**

**Product.**
**FindingFrame** extracts structured oncology finding frames (type, anatomy, laterality, measurement, temporal change, assertion), each anchored to a **mandatory verbatim source sentence verified by a gate** — zero fabricated facts by construction. Deterministic composite-key linking builds longitudinal lesion tracks and computes **RECIST 1.1 progression**. It runs on four LLM backends with no retraining, every fact is clinician-approved, and it reads Indian-language reports via Sarvam.

**Why now.**
FDA/EMA real-world-evidence and AI guidances (2026) now demand **documented provenance for every data element**; India's CDSCO is tightening AI-device rules; >70% of healthcare orgs say governance — not features — gates procurement. Black-box extraction has become a liability precisely as LLMs got good enough to read radiology. Only an audit-grade wrapper makes that usable. India's clinical-trials market is growing to **~$4.6–6.6B by 2034**, and DPDP data-localization favors a model-agnostic, on-prem-deployable stack.

**Wedge.**
**India-first validation, global-pharma revenue.** Tata Memorial (~43–70K new patients/yr) and the **National Cancer Grid (~860K patients/yr, 60–70% of all Indian cancer cases)** give us clinical validation and registry deployment at unmatched cost — and a provenance-complete oncology data asset no US player can reach. Dollar revenue comes from **pharma/CRO oncology trials**: audit-grade abstraction and RECIST pre-reads, priced per patient at 50–70% below manual central review.

**Ask.**
Seed funding to deliver the evidence pack that converts architecture into contracts:
1. A **200-patient clinician-adjudicated validation** at Tata Memorial (inter-rater κ; track-linking F1 → >0.7).
2. **2 National Cancer Grid registry deployments.**
3. **2 paid pharma/CRO pilots** (abstraction + RECIST pre-read).

**The bet.** The services revenue is the on-ramp; the re-rating asset is the **860K-patients/yr provenance-complete oncology dataset** flowing through the pipeline — exactly the curated-data moat that took Flatiron from a $1.9B acquisition to a reported $10–15B asset.
