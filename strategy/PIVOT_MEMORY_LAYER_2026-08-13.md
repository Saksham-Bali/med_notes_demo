# IndigoEdge — Pivot Strategy: Evidence-Anchored Document Memory Layer

**Version:** 2026-08-13 v2 (post-critic-pass) · **Status:** Strategy draft, v2 · **Companion docs:** `PITCH.md`, `MARKET_RESEARCH.md`, `PRODUCT_AND_MARKET.md`, `PRODUCT_BUILD_PLAN.md` (oncology-first, still live for the deployed product until a go/no-go decision is made)

> **What this document is:** the pivot case, evidence, and plan for generalizing FindingFrame from an oncology product into a domain-agnostic *evidence-anchored document memory layer*, with legal as the first vertical. It supersedes the India-first-pharma strategy on the *strategic* layer; the existing docs remain the reference for the deployed oncology product, which is not being shut down.
>
> **Number discipline (same rules as `PRODUCT_AND_MARKET.md`, plus the team's documented failure modes from `tmc/AGENTS.md`):** market figures are analyst estimates with named sources and ranges where sources disagree; our own estimates are flagged; single-point figures from incompatible scopes are never compared directly; no accuracy claim may transfer from one domain to another without stating the caveats (patient-macro vs type-macro, the 41.1% anatomy criterion, dev-cohort vs held-out).
>
> **Critic pass:** v1 was reviewed adversarially. Ten must-fix findings were accepted and are incorporated inline (marked **[C#]** where the fix changes a claim); the record is in §11. Corrections are kept visible, not silently deleted.

---

## 1. The pivot decision

### 1.1 Why now

Healthcare-specific products carry a structural tax that the last three months of this project demonstrated firsthand:

- **HIPAA/DPDP friction.** Every artifact is DUA-restricted (MIMIC text cannot even be demoed via a circulating link — `HANDOFF.md:5-8`), every deployment needs a BAA posture, and the flagship demo patient's *manifest* ended up describing an LLM call that never happened (`PRE_UPDATE_PLAN_2026-07-30.md` P0-5) because real data could not move freely.
- **Clinical validation is the gating function.** The remaining blocker on the research track was a second human annotator — a people problem, not an engineering problem. Every figure needs clinician adjudication before it counts. That is correct for a medical product; it is also why the engine's *economics* are stuck behind a validation bottleneck that software cannot fix.
- **The engine's actual moat is not oncology.** The defensible core — slot-typed fact extraction, verbatim evidence anchoring, deterministic composite-key identity, longitudinal tracks, human sign-off, hash-chained audit, slot-level evaluation — is domain-agnostic by construction. Oncology is the first domain it was *tuned* for, not the only domain it can *serve*.

**Honesty note [C#1]:** the oncology product has **zero paid pilots** — `HANDOFF.md` §11 is literally titled "stop building, start converting." This pivot therefore does not abandon a revenue engine; there is none to abandon. But it also means the foundational premise — that attestation/provenance is a purchasable category, not a feature — **has never been validated by money**. Demand validation is therefore GATE 0 of this plan (§5.2), before any build commitment.

### 1.2 The hypothesis

**A horizontal "evidence-anchored memory layer" — every claim carries its verbatim source, every fact has a timeline, everything is human-signable and hash-verifiable — with per-domain adapters, sold first into legal.** If the whitespace analysis below holds, the same engine that extracts tumor frames becomes a legal-case memory engine by swapping one adapter layer.

The honest version of the whitespace claim: it is currently **supply-side** (four research agents + competitor documentation, zero customer interviews). "Nobody combines X+Y+Z" is indistinguishable from "nobody pays for it" until a buyer says otherwise. This doc plans for that uncertainty instead of pretending it away.

### 1.3 What does NOT change

The architectural invariants from `PRODUCT_BUILD_PLAN.md` §2 transfer verbatim, because they are domain-free:

1. **Hybrid split** — LLMs do language understanding; identity, linking, normalization, verification are deterministic.
2. **Composite-key linking** — no fuzzy LLM entity matching (with one scoped exception for legal party resolution, §4.2 — which is the main event, not an edge case; see §7).
3. **Evidence anchoring** — every fact carries a gate-checked verbatim source sentence.
4. **Model-agnosticism** — backend selectable; no vendor lock-in.
5. **Reproducibility** — SHA manifests, versioned prompts/gold, frozen benchmarks.
6. **Human-in-the-loop by design** — nothing enters the signed record without sign-off.
7. **Audit-grade provenance** — append-only, hash-chained, independently re-verifiable.

What changes: the *slots*, the *taxonomy*, the *linker key spec*, and the *downstream task module* (RECIST). Everything else is the platform.

---

## 2. Evidence base: the whitespace is real

Research method: four parallel research agents (market landscape, legal domain, technical feasibility, GTM) plus firecrawl-verified scrapes. Raw results: `pre/.firecrawl/pivot-legal-memory/`. Key sources cited inline.

### 2.1 The "memory layer" category exists — and is price-crushed

The three most-starred open-source agent-memory projects make three incompatible bets ([digitalapplied comparison](https://www.digitalapplied.com/blog/open-source-agent-memory-mem0-letta-zep-compared)):

| System | Architecture | Pricing (hosted) | What it lacks vs us |
|---|---|---|---|
| **Mem0** | Passive fact extraction from message pairs; vector-first; graph tier gated to Pro (~$0.00038–0.0005/memory-add) | $19/mo Starter | No verbatim anchors, no evidence gate, no human sign-off, LLM silently rewrites facts |
| **Letta** | Agent runtime; memory tiers the agent edits via tool calls | ~$20/mo + usage | Agent-authored memory — inherently non-verifiable |
| **Zep/Graphiti** | Temporal knowledge graph; facts carry `valid_at`/`invalid_at`; contradicted facts invalidated, not deleted ([arXiv:2501.13956](https://arxiv.org/abs/2501.13956)) | $104/mo Flex → $312/mo Flex Plus; SOC 2 + HIPAA BAA gated above entry tier | Temporal tracking ✓ but facts are LLM-inferred *conversation* triples — no source-span verification, no attestation, no slot-level evaluation |

Adjacent categories: vector DBs (storage, no facts), RAG frameworks (retrieval, no fact model — and LangGraph checkpointer shipped 3 RCE-class CVEs in Nov 2025, a governance argument in our favor), GraphRAG (batch-built static graphs, no incremental tracks, no anchors), document parsers (Unstructured/LlamaParse — upstream suppliers, no memory), enterprise search (Glean: $200M ARR Dec 2025, $7.2B valuation, but cites *documents* not facts, no longitudinal entity tracks), enterprise ontologies (Palantir AIP: governed lineage + human review gates — the closest "audit-grade" incumbent, but structured-data-centric, platform-bound, priced at enterprise scale), evals/governance tools (Vectara/Galileo/Patronus: score outputs, don't store attested facts).

**Conclusion:** every adjacent player has acquired *pieces* — Mem0 added graphs, Letta added archival memory, Zep added temporal validity, Glean sells "trusted answers" — but as of Aug 2026 **nobody combines slot-typed extraction + verbatim evidence gate + deterministic cross-document entity tracks + human sign-off workbench + hash-chained re-verifiable audit**. E-discovery (Relativity/Everlaw) proves WTP for audit but is matter-bound with no longitudinal model.

**Counter-position, stated honestly [C#1]:** the same evidence supports a different reading — provenance is *absorbed into platform purchases* (Palantir, Relativity), not bought standalone, and an incumbent (Harvey at $15.5B, with UniCourt/Recap data partnerships one integration away) could bolt longitudinal docket memory onto their product in a quarter if a customer asks. Our answer cannot be "they won't bother" — it must be speed, focus, and the parts that are genuinely hard to bolt on: the human sign-off workflow, the hash-chained audit machinery, and the slot-level evaluation methodology (all already built and shipped in oncology). This stays an open risk until demand validation (§5.2 GATE 0).

### 2.2 The biggest threat is also the reason this works

Model providers shipped chat memory across the board in 2025–26 (Claude chat memory, OpenAI, Gemini, Copilot — all "No" on audit/version-control per [MemoryLake comparison](https://www.memorylake.ai/en/blogs/ai-memory-compared-2026)). But provider memory is summary-based, ungrounded to source documents, and cannot attest. Regulated buyers cannot put sign-off records in a model provider's blob. Native memory kills the *low-end* "remember across documents" layer — and creates the *high-end* demand for verifiable memory. Our moat is the attestation layer and the evaluation methodology, not the storage.

### 2.3 Legal: the two halves of our product never appear together

Verified competitor sweep across legal tech 2026:

- **Litigation analytics** (Lex Machina 45M docs/10M+ cases, Westlaw Litigation Analytics, Trellis, UniCourt, Docket Alarm, Premonition): longitudinal *docket metadata* (dates, judges, outcomes) — **no content-level links** between a remand order and the appeal that follows it, no span anchoring to judgment text.
- **AI assistants** (Harvey: $190M ARR Jan 2026, $11B valuation Mar 2026 ([CNBC](https://www.cnbc.com/2026/03/25/legal-ai-startup-harvey-raises-200-million-at-11-billion-valuation.html)), reportedly raising at $15.5B; CoCounsel; Luminance; Spellbook; Robin AI; EvenUp; Eve; Legora $5.6B Apr 2026): stateless per-prompt Q&A and drafting. Citations yes, span-anchored typed-slot data models no.
- **Case-law research** (Casetext→Thomson Reuters $650M 2023, vLex, Judicata): retrieval + citators. Citator networks are weakly longitudinal; no case-history tracks.
- **Contract extraction** (Kira, Luminance, Ontra; CUAD benchmark): span-level clause extraction — the closest analog to our evidence anchoring — **zero longitudinal dimension**.
- **E-discovery** (Relativity ~$75–150/GB/matter, Everlaw $95–150/seat/mo, DISCO): audit trails + citation validation, but per-matter, no cross-matter memory.

**The whitespace:** nobody parses a long judgment PDF into structured procedural history (parties, claims, rulings, citations, dates, remand/affirm/reverse relationships) and links it across documents. Academic SOTA is sparse and old (Jackson's History Assistant 2003; "Events Matter" 2020; Vacek 2019). No commercial product does multi-trial longitudinal case memory with per-fact evidence. Our Type/Identity/Full-Frame slot-level evaluation methodology would itself be a contribution — nobody publishes slot-level F1 for procedural-history extraction.

**Engine-quality transfer, with the mandatory caveats [C#3]:** the oncology numbers (Type F1 0.855 all-30) do **not** transfer to legal. They are patient-macro averages under a scorer whose anatomy criterion does not penalize wrong anatomy on 41.1% of gold frames, on clean text with a tuned taxonomy, with full-frame F1 0.639 (i.e., ~36% of frames have a wrong slot on radiology). Legal starts *worse*: messy OCR'd PDFs, an unbounded entity space, and no tuned taxonomy. Expected legal performance is explicitly §4.7: we do not publish a legal number until we have measured one on held-out gold.

### 2.4 The regulatory tailwind (why legal, why now)

- **India, July 2026:** the Supreme Court ruled in *Pooja Ramesh Singh v. J&K Bank* (2026 INSC 668) that **unverified AI citations are professional misconduct**; the Bombay HC imposed ₹50,000 costs in Jan 2026 for a filing built on an untraceable AI-cited judgment; draft Regulations for Use of AI in Courts, 2026 add AI-disclosure duties ([Judicio 2026 field guide](https://judicio.ai/blogs/best-legal-ai-tools-india-2026)). Verified-citation tooling went from "productivity nicety" to **survival purchase** for India's 2M enrolled advocates.
- **US, 2025:** 12+ AI-sanctions cases in one year — $31K Ellis George/K&L Gates sanctions, a Florida 2-year suspension, a California Bar 1-year recommendation over 21 fabricated quotes ([Law.com 2026-04-06](https://www.law.com/2026/04/06/figuring-out-how-to-deal-with-this-how-are-courts-grappling-with-disciplining-aihallucinations/)). The sanctions record — not any vendor's benchmark — is the demand evidence.
- **On competitor hallucination claims [C#2]:** v1 cited "Harvey hallucinates 1-in-6 queries." Withdrawn: the underlying Medium analysis attributes that figure to **Lexis+ AI**, and Harvey publishes its own benchmark claiming 0.2% on BigLaw Bench. Neither is neutral. The honest formulation: **hallucination rates in legal AI are contested, vendor-reported, and not independently audited — which is itself the argument** for span-anchored, gate-verified extraction whose verification the customer can run independently. (Stanford HAI's 58–82% hallucination findings concern general chatbots, not legal products; not cited here as legal evidence.)
- **EU:** the AI Act Annex III classifies "administration of justice" AI as high-risk (core obligations from Aug 2, 2026) — a compliance cost for us in EU/UK deployment of outcome-prediction features, and a moat against unverifiable competitors in the same breath. Judgment-parsing + chronology, scoped away from "applying law to concrete facts," sits outside it; do not ship prediction tools in the EU until assessed (§7).
- **Regulatory comparison vs healthcare (the whole point of the pivot):** court judgments are public records — no HIPAA analog, no covered-entity/BAA chain, no breach-notification regime, no DUA. The real burden is professional-conduct (ABA Formal Op. 512 mapping Model Rules 1.1/1.6/5.1–5.3 onto AI use, flowing to vendors *contractually*: SOC 2, zero-retention, no-training clauses) and attorney-client privilege **the moment we ingest client/matter data** (judgment-only products avoid privilege entirely). India's DPDP applies to party names in judgments but sits in a far simpler regime than health data. **Verdict: materially lighter on statutory data regulation; the friction is commercial (contracts), not statutory.**
- **The honest remainder [C#10]:** "public records" is the *start* of the privacy analysis, not the end — DPDP (fines to ₹250 crore, enforcement phasing through May 2027) and GDPR still govern processing of party names for commercial analytics, and Indian Kanoon's ToS restrict bulk scraping. Data licensing and privacy posture are priced workstreams (§6.3) and a standing risk (§7).

---

## 3. Positioning

### 3.1 Category verdict

**Do not call it a "memory layer."** Infra memory is commoditized ($25/mo Zep, provider-native memory free). **Do not call it generic "document intelligence"** (Luminance/DocuSign/Adobe own that phrase at enterprise prices).

**Positioning: "Attributable Longitudinal Document Intelligence."** The one-line frame:

> *Every claim carries its verbatim source. Every fact has a timeline. Everything is human-signable and hash-verifiable.*

> **Canonical provenance claim (added 2026-08-14, B8 — supersedes all looser phrasings in every doc):** *100% source-linked: every fact carries a verbatim source span; spans that fail verification are quarantined for mandatory human review, not silently passed. On degraded scans, the link certifies the anchor to the extracted text as-is, and OCR confidence travels with the span.* Never claim "0% hallucination by construction" (retracted 2026-07-17, `PRODUCT_BUILD_PLAN.md` R5).

Buyers in legal already speak this language: "citation-verified," "court-ready," "pin-cited." The three differentiators map 1:1 from the engine: evidence anchoring (vs RAG's lossy chunks), deterministic longitudinal identity resolution (vs Zep's chat focus), hash-chained audit (vs everyone). We are the **trust layer between the document and the decision**.

### 3.2 Who we are not

- Not Harvey/CoCounsel (we don't draft; we are the grounded substrate *under* drafting tools — an MCP server they can plug into).
- Not Lex Machina (we extract from *text*, not docket metadata; our rulings are span-anchored).
- Not Zep/Mem0 (we sell attestation and evaluation, not conversation memory).
- Not Palantir (we are a focused document-intelligence layer, not a platform; self-serve entry).
- **Precision fix [C#5]:** v1 said Indian incumbents "don't verify" — wrong. SCC Online and Manupatra *do* verify citations against their 60-year editorial corpora; that is their core competency. What they don't do: span-anchored extraction of judgment *content* into longitudinal cross-document tracks, with human sign-off and an independently re-verifiable audit chain. The differentiator is content-level provenance, not citation checking.

---

## 4. Legal vertical: the first adapter

### 4.1 Frame schema (draft v2)

One claim per evidence span. Proposed slots:

| Slot | Meaning | Notes |
|---|---|---|
| `case_id` | Court-issued identifier | Stable anchor across documents |
| `court` | Forum + level | Normalized hierarchy |
| `party` + `role` | Named party, procedural role | Roles: plaintiff/defendant/appellant/appellee/petitioner/respondent |
| `speaker` | Who is speaking **[C#7]** | court_majority / court_dissent / party_argument / lower_court_finding / procedural_recital. Judgments are polyvocal; "who said what, sourced" is unimplementable without this slot. |
| `issue` | Legal claim/doctrine | Taxonomy size is an open design question (§4.6), not asserted |
| `procedural_event_type` | The event the frame describes **[C#7]** | filing, hearing, motion, order, ruling, remand, continuance. The event *generates* frames; the slot holds its type, the frame holds claims about it |
| `holding` | Outcome + direction | granted/denied/dismissed/remanded/vacated/affirmed/reversed/reversed_in_part. "The court *declined to* reverse" is a **holding value** (a decision not to act), not an assertion stance — the negation problem in legal is scoped here, not in `assertion` |
| `citation` | Cited authority | For precedent tracks |
| `event_date` | When it happened | Replaces `charttime`; the temporal axis |
| `assertion` | Stance of the statement itself | Present/absent/uncertain — with dicta-vs-holding and majority-vs-dissent scoping as *known hard cases*, not ignored |
| `evidence_text` + span | Verbatim sentence | The non-negotiable invariant |

### 4.2 Linking design

- **Case tracks:** composite key `case_id | issue | party_role` — the remand order links to the trial order links to the post-remand ruling.
- **Precedent tracks:** `citation | issue` across cases — treatment status (followed/distinguished/overruled) is the "assertion-state" of a citation.
- **Parallel proceedings:** a `proceeding_id` slot in the key + multi-parent graph edges (the TrackGraph's COEVOLUTION edge type was built for exactly this shape; under-tested, reusable).
- **The deterministic-identity exception, stated at full size [C#7]:** parties, firms, and judges are unbounded open sets — anatomy's fixed hierarchy has no legal analog. Deterministic keys hold where identifiers exist (case numbers, citations). For entity resolution, the design is LLM-assisted alias resolution with **mandatory human confirm** — and this is not an edge case, it is *most of the interesting legal identity work*. The invariant becomes: **the machine never auto-merges people it cannot prove identical; ambiguity always routes to the human queue** (`unresolved_link_queue`, `false_split_candidates` already exist). The product story: the machine does what is provable, the human does what is judgment, and the audit chain records which was which.

### 4.3 The three hardest problems (identified by code-level analysis)

1. **Segmentation.** `report_cleaner.py` assumes ~5 short sections; 100+ page judgments with star pagination, footnotes, and cross-page evidence spans need chunked extraction with offset arithmetic. The word-boundary span locator transfers; the section model does not. **This is a priced subsystem (§6.3), not an adapter detail.**
2. **Entity resolution.** Covered in §4.2 — the open-vocabulary identity problem.
3. **Track semantics with parallel proceedings.** The composite-key model assumes linear tracks. Consolidated MDLs, parallel state/federal actions, and remands that bifurcate need multi-parent graphs. Design constraint: never auto-merge; ambiguity goes to the human queue.
4. **Messy ingestion [C#6].** PACER scans, OCR'd text, and tables. Note the gate's guarantee is only as strong as the text: on corrupted OCR, `source_verifiable` means "anchored to this mangled string," not "fact is supported." The product must surface OCR confidence alongside every evidence span.

### 4.4 Data and evaluation

- **Data (ranked by accessibility):** CourtListener/RECAP (9M+ opinions, 2,000+ courts; APIs now in *membership tiers* — free tier exists, full API access is paid [C#5]; RECAP archives hundreds of millions of PACER entries); Indian Kanoon (30M+ judgments; **bulk-scraping-restricted ToS** — check before using at scale [C#10]); eCourts (660 crore pages digitized, 1.07 crore cases e-filed under ₹7,210-crore Phase III); UK National Archives Find Case Law API (clean JSON); Harvard case.law (6.5M-opinion corpus migrated to CourtListener). **Commercial-use terms for every source are a GATE-0 due-diligence item, not a detail.**
- **Benchmarks:** CUAD is the closest existing span-level extraction task (and its documented annotation pathologies are a blueprint for better legal gold); LegalBench "dicta vs holding" tasks are near-proxies for the assertion slot; CaseHOLD for rulings-as-typed-facts; ILDC/Nyay-LLM for India. **Nothing exists for longitudinal track-linking** — our track metrics (Jaccard-track F1, purity, split/merge) would be a research contribution, and gold tracks can be built from appeal-chain data.
- **Gold discipline (transferred from tmc):** engineering-curated gold first, explicit labels, no silent rewrites, frozen manifests. **The 3-case pilot gold is US-based (CourtListener) from day 1 [C#4]** — India provides volume and iteration; India-tuned extraction validates nothing about US docket behavior (SLPs, curative petitions, in-limine dismissals have no US analog), so the *pilot gold that gates the product* must be the market we intend to sell first.
- **Annotation reality [C#10]:** a law-trained annotation study is the κ-equivalent gate. The team has failed to produce one second human annotator in 18 months on the clinical side. The legal κ study stays **descoped to feasibility** until a named legal advisor/annotator exists (§10, D7).

### 4.5 Downstream task modules (the RECIST equivalents)

1. **Procedural-history reconstruction** — event chronology per case, every event pin-cited.
2. **Cross-document contradiction detection** — same claim, conflicting versions, both sentences side by side (the deterministic linker's superpower).
3. **Precedent treatment tracking** — citation graph with followed/distinguished/overruled status.
4. (Later, and not in the EU without an AI-Act assessment) **Outcome analytics** — judge/motion statistics computed over span-anchored rulings, not docket metadata. Every statistic clickable to its source.

### 4.6 Open design questions (to resolve in the spike, not assert)

- **Issue taxonomy size:** "~25 issues" was a v1 guess. Westlaw's key-number system runs six figures; the right grain for a v0 adapter is unknown and is a spike output. The issue slot is also where the LLM is weakest — putting the least-reliable slot at the center of the composite key is a design risk to pressure-test, not a decision made.
- **Event vs frame modeling:** whether procedural events are best modeled as frame types or as a separate event layer with frames attached.
- **Chunking economics:** chunk size × LLM cost × span-offset arithmetic for 100+ page documents (feeds §5.3's cost model).

### 4.7 Expected accuracy, honestly [C#3]

We publish **no legal accuracy number until one is measured on held-out gold**. The honest prior, derived from oncology: full-frame F1 0.639 on clean text with a tuned taxonomy and a 6-slot schema (and that scorer's anatomy criterion forgave wrong anatomy on 41.1% of frames). Legal starts from a worse position on every axis — messy text, open vocabularies, harder semantics (dicta vs holding, "reversed in part," polyvocality). A reasonable planning prior is **full-frame 0.4–0.6 on first gold**, improving with taxonomy iteration — and the internal gate for the adapter is **diagnostic** (per-slot error decomposition tells us where to fix), **not** a marketing number. The pitch to buyers is never "we're accurate" — it is "you can check every fact against its source in one click, and the audit chain proves nothing changed since sign-off."

### 4.8 Money moments (the PD→PR analog)

The oncology demo worked because PD→PR is a single-number longitudinal verdict that flips a treatment decision. Legal equivalents:

1. **"Procedural history in 60 seconds"** — drop a 3,000-page multi-year docket; get a verified, pin-cited chronology. The gasp: a junior associate's 40-hour task done, fully sourced.
2. **"Contradiction detector"** — "The warranty in Schedule 3 contradicts the 10-Q disclosure; here are both sentences." Cross-document identity resolution — nobody else does this.
3. **"Funder's pre-filing screen"** — drop opposing counsel's past 50 filings: "This judge grants summary judgment in 72% of contract cases after 2+ continuances," every statistic clickable to sources. Litigation funders buy this as underwriting.

---

## 5. Market entry

### 5.1 The geography fork

Two independently researched positions with real evidence. **This is the one decision the founding team must make consciously; both are defensible.**

| | India-first | US-first |
|---|---|---|
| Data | Free at scale (subject to ToS due diligence, §4.4) | CourtListener free tier; full API in membership tiers; PACER paywalled ($0.10/page) |
| Demand pull | SCI zero-tolerance ruling (Jul 2026) → compliance need; 2M advocates | 12+ sanctions cases (2025) → liability need; funders/insurers pay for defensibility |
| WTP (published) | SCC Online AI Pro ₹51.5–67.5K/yr; Manupatra AI Search ₹6K/yr + timelines 8 credits/page; Jhana ₹3.3–5K/mo; Judicio ₹10K/mo | Harvey $1.2–2.4K/seat/mo (20–50-seat floors, $288–360K annual minimums); CoCounsel $200–500/seat/mo; EvenUp $300–800/case; Lucio $149/seat/mo |
| Market size | ~$2.64B (Mordor Intelligence) — **other analysts put India legal services ~10x higher; scope mismatch, do not lean on the low figure alone [C#8]** | ~$400B US legal services; legal AI software $1.5–3.1B at ~28% CAGR, NA 42% share |
| Competition | Incumbents verify *citations*; nobody does content-level longitudinal tracks | Crowded: Lex Machina/Trellis on analytics; Harvey/CoCounsel on drafting |
| Validation transfer | **Weak [C#4]**: India terminology (SLP, curative petition) does not transfer to US dockets | Direct: gold built on the market we sell into |
| Regulation | DPDP phased in through May 2027, fines to ₹250 crore; judgments public but party-name processing unlitigated | Ethics rules flow to vendors contractually; UPL is a marketing risk only |

**Recommended (v2): hybrid sequencing — India corpus for iteration, US gold and revenue from day 1.** The correction from v1: India's role is *volume and machinery validation* (pipeline, review workflow, audit chain, evaluation harness), not extraction-taxonomy validation. The US-based 3-case pilot gold (§4.4) is built in parallel from M0, and the revenue gates are anchored on US willingness-to-pay with India priced at its own published market rates. First design partners: **2 Indian litigation teams (volume/iteration) + 1 US litigation funder (gold + revenue proof)**.

> Alternative view (from the GTM research agent, recorded, not adopted): US-first entirely — the Indian wallet is too small to matter and DPDP buys less regulatory freedom than expected. Legitimate disagreement; see §10, D1.

### 5.2 Twelve-month GTM sequence (stage-gated, v2)

- **GATE 0 (M0, before any build commit) [C#1] — demand validation.** One named lawyer, funder, or insurer who has said, in writing, they would pay for span-anchored procedural history/contradiction detection. Also: data-licensing due diligence on CourtListener/Indian Kanoon ToS (§4.4). **If no demand signal exists in 4 weeks, the pivot stops and oncology continues.**
- **M0–3 — Spike + design partners + legal adapter v0.** Run the 2-day KeySpec spike (§6.3 note) **before** committing the 4–6 week core estimate [C#9]. Ship procedural-history extraction on real dockets to the 3 design partners. Gate: 2 partners using weekly; adapter passes internal gold eval (diagnostic target, §4.7 — not a marketing number).
- **M3–6 — Money-moment product.** Procedural timeline + contradiction detector, pin-cited throughout. **Gate: paying customers at published-market rates for their geography — US: ≥$2K/mo from the funder; India: ₹10K+/mo — or the equivalent in one paid pilot at §5.3 pricing. NPS ≥ 8.** (v1's "2 paying ≥$2K/mo" gate was unreachable by construction against India's published ₹3.3–10K/mo prices; fixed [C#5].)
- **M6–9 — MCP server launch.** Ship the memory layer as an MCP server (10K+ public servers; 97M monthly SDK downloads; stateless 2026-07-28 spec — [adoption stats](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)). Position: the *grounded memory* lawyers plug into Claude/ChatGPT/Harvey — Trojan horse for developers, lead-gen for enterprise. **Security story is mandatory, not optional [C#10]:** tool-poisoning/prompt-injection guardrails, explicit data-exfiltration posture, client-scoped permissions — the doc that cites LangGraph RCE CVEs cannot ship an MCP server without one. Gate: 100+ server installs, 3 enterprise inbound leads.
- **M9–12 — Expand + validate.** Plaintiff PI firms, appellate practices, insurers. κ-style validation study **scoped to feasibility** until a named legal annotator exists [C#10]. Gate: **$100–150K ARR, 5–8 accounts, 1 funder logo.**
- **M12+ — Second adapter** (financial filings) only after the ARR gate. The adapter architecture stays; the *selling* stays legal-only until then.

### 5.3 Business model and unit economics [C#4]

**Per-matter/per-document vertical SaaS. Not per-seat. Not developer API.**

- Per-seat compresses (Glean $30/seat); infra pricing collapses (Zep $25/mo); audit-grade is a *professional-liability* purchase — price like insurance and legal research, not SaaS.
- Anchors: EvenUp $300–800/demand; e-discovery AI review <5¢/doc vs $0.50–1.00 human; Manupatra timeline 8 credits/page proves per-document WTP in India.

**Cost model (our estimates, flagged; refine in spike §4.6):** a 100-page judgment is ~60K tokens of text. Chunked extraction at 8–12K tokens/chunk with per-chunk calls plus a synthesis pass is ~$0.30–1.50 per judgment at mid-2026 frontier-model prices (per-chunk × chunks), before OCR. A 3,000-page docket is ~$10–50 in LLM spend. Therefore:

- **Funder screens at $10–50 per docket are below marginal cost for large dockets — withdrawn [C#4].** Correct pricing: **$100–500 per docket** for funder screens (value-based: a funder is underwriting a case, not buying tokens), or per-matter $2–5K/mo for ongoing litigation timelines.
- The oncology rate limiter (~5 calls/min) is insufficient for docket-scale ingestion; bulk processing needs a job-queue throughput plan, priced in §6.3.

### 5.4 Data licensing posture [C#10]

CourtListener membership tiers for full API access; Indian Kanoon ToS restrict bulk scraping; PACER via RECAP; UK National Archives API is the cleanest. Every source's commercial-use terms get a written verdict in the GATE-0 due-diligence note. Party-name privacy posture (DPDP/GDPR) is a documented product decision before the first non-judgment dataset is ingested — do not discover this in diligence.

---

## 6. Technical plan

### 6.1 Component audit (from code-level analysis of `tmc/` + `pre/findingframe/`)

| Module | Domain coupling (verified) | Generalization | Effort |
|---|---|---|---|
| `finding_frame_schema.py` | 6 fixed radiology slots; clinical enums; cardiomegaly hardcodes | Schema becomes adapter-defined; evidence/span/track-key contract is the core invariant | M |
| `finding_type_taxonomy.py` | 20-class oncology + echo/CXR taxonomies embedded in one 1,885-line file | Split into per-domain registry behind `DomainAdapter.get_taxonomy()` | M |
| `finding_frame_extractor.py` | Already has `domain=` param, domain-gated rescues and prompt blocks — good seam | Convert `if domain==` branches to strategy injection | M |
| `frame_slot_normalizer.py` | ~127 anatomy rules; temporal patterns | Adapter supplies normalizer callables | M |
| `measurement_normalizer.py` | mm/cm, area/volume | Adapter-defined units | S |
| `report_cleaner.py` | ~48 radiology section regexes | Adapter supplies section patterns. **Legal segmentation is the hard version — a subsystem, not a plugin** [C#6] | L |
| `frame_linker.py` | Composite key hardcoded to type\|anatomy\|laterality; anatomy parent hierarchy; no domain param | Extract `KeySpec` (ordered slots + parent map + compat predicates) and `LinkingPolicy`; cascade algorithm is domain-neutral | M |
| `track_graph.py` / `frame_adapter.py` | Clinical edge types | Edge-type set adapter-defined | S |
| `finding_frame_processor.py` | MIMIC column names, int-cast subject | Column mapping + coercion hooks | S–M |
| `frame_metrics.py` | `_identity_key` fixed to type/anatomy/laterality | Key-fns from adapter; matching/PRF/bootstrap machinery transfers | M |
| `track_metrics.py` | Reads track dicts | Transfers | S |
| Product backend | `recist.py`, `irr.py` slot lists, `export.py` PDF, DB `finding_type/anatomy` columns, review UI labels | RECIST/IRR/export → task-module plugins; DB gains domain-schema JSONB; ~80% of backend (EngineAdapter, manifests, audit chain, jobs) transfers as-is | M–L |

**Echo precedent reality-check:** the "45 lines of domain config" claim was taxonomy *tables* added to one file (plus ~280 lines of aliases/terms and domain-gated branches in 4 files) — it worked because echo *shares the radiology slot semantics*. Legal does not. The honest claim for legal is: **zero changes to core architecture; adapter scale measured in thousands of lines, not 45** — and that claim is stated everywhere, including the pitch. **Stated as the open question (added 2026-08-14, critique C5):** the engine's domain-agnosticism is currently evidenced only by a within-slot-semantics transfer (echo). The legal adapter is the first real test of the pivot's central technical bet; until its diagnostic eval exists on held-out gold, "domain-agnostic architecture" is a hypothesis with one supporting anecdote, not a demonstrated property.

### 6.2 The DomainAdapter interface (minimal)

1. `schema: BaseModel` (adapter-defined slots + enums, same frozen-versioning discipline)
2. `taxonomy` + `taxonomy_prompt_block()` + `concept_terms()`
3. `section_patterns` + `keep_sections`
4. `slot_normalizers: dict[slot, Callable]`
5. `key_spec: KeySpec` (ordered key slots, parent hierarchy, compat predicates, sideless/global-absent policies)
6. `linking_policy` (cascade thresholds, review-queue predicates, edge-type set)
7. `rescue_rules` (deterministic post-LLM fixes)
8. `evidence_gate_hooks` (negation/uncertainty regexes, per-type support terms)
9. `task_modules: [TaskModule]` (RECIST analog)
10. `metric_key_fns` (type/identity/full key builders)

### 6.3 Effort estimate (person-weeks, our estimates, flagged; v2 includes the omitted subsystems [C#6])

| Workstream | Wks |
|---|---|
| **GATE 0: demand validation + data-licensing due diligence** (not engineering, but it gates everything) | 2–4 |
| KeySpec spike (2 days, before the estimate below is committed [C#9]) | 0.5 |
| Core refactor to adapter architecture (KeySpec extraction, schema factory, domain param through linker/processor/metrics, radiology tables → `radiology` adapter, test parity at 488 tests) | 4–6 |
| Legal adapter v0 (schema + issue taxonomy at spike-determined grain, section regexes, normalizers, key spec, linking policy, prompt blocks, chunked extraction with cross-page spans, 3-case US pilot gold, evals) | 6–8 |
| **Messy-PDF ingestion subsystem: PACER scans, OCR, tables, OCR-confidence surfacing** [C#6] | 3–5 |
| **Pin-cite / Bluebook / citation parsing** [C#6] | 2–3 |
| Bulk job-queue throughput plan (rate limiter is ~5 calls/min; dockets need parallelism) [C#4] | 1–2 |
| Docket/proceeding-ID parser + normalizer — canonicalizes the `proceeding_id` key slot across OCR/format variants; corpus-scale track mining over 43K SC headers [added 2026-08-14, critique C9a/C14] | 1–2 |
| Productize (domain-agnostic review UI labels, task-module registry, seed data, IRR slot lists, DB JSONB migration) | 3–5 |
| **Total to legal v0 demo (excluding GATE 0)** | **20–31** (was 19–29; +1–2 docket parser, 2026-08-14) |

### 6.4 What to reuse from the existing product (from code-level review)

**~70% unchanged:** extraction engine + evidence anchoring + quality checks; deterministic linker core; normalizer architecture; hash-chained audit trail (→ legal evidence integrity, near-literal fit); FastAPI + Next.js review workbench (→ attorney sign-off UI); evaluation harness (slot-level metrics machinery); manifest-frozen reproducibility (→ defensible methodology).

**~30% rebuild, with the caveat that the IRR/κ "apparatus" transfers as *software* only:** legal taxonomy and slot schema; date normalization; messy-PDF ingestion; pin-cite parsing; task modules. The κ *methodology* transfers; the κ *people* do not — oncology has been blocked 18 months on a second annotator, and legal needs law-trained annotators who do not exist in the org chart yet (§5.2, §10).

---

## 7. Risks (with evidence)

| # | Risk | Assessment |
|---|---|---|
| 1 | **The category doesn't exist as a standalone purchase** [C#1] | The deepest risk: provenance may be a feature absorbed into platforms (Palantir, Relativity), not a product. GATE 0 exists to test this with money, not research. |
| 2 | **LLM-native memory commoditizes the layer** | Real, but chat-scoped, ungrounded, non-verifiable. Kills the low-end; *creates* demand for attestation. Defense: sell outcomes (defensibility, underwriting), not storage. |
| 3 | **Incumbents bolt on longitudinal docket memory** | Harvey/CoCounsel have data partnerships and $15.5B-scale budgets. Defense: speed, focus, and the parts that are genuinely hard to bolt on (sign-off workflow, hash-chained audit, evaluation methodology — already built). Not a permanent moat; a head start. |
| 4 | **GraphRAG is "good enough"** | Costs collapsed ~1000x; ungrounded-legal-query hallucination rates are documented as high but sources are contested (a GraphRAG vendor's marketing blog claims ROI; independent numbers are scarce). We do not cite vendor claims as neutral evidence. Moat holds only if we sell outcomes, not retrieval. |
| 5 | **Lawyers won't pay for provenance** | Partly true for drafting; decisively false at liability points: $31K sanctions, Florida suspension, California recommendation. Sell to funders, insurers, e-discovery defensibility — the people whose money dies on a bad citation. |
| 6 | **Legal sales cycles (6–18 months)** | Real for enterprise. Mitigation: per-matter pricing with self-serve ingestion; funders and PI firms buy faster than Am Law. |
| 7 | **Horizontal dilution** | Glean needed $100M ARR before horizontal spread. Mitigation: adapter architecture stays; *sell* only legal until the ARR gate. |
| 8 | **Entity resolution breaks the deterministic-identity claim** | The one architectural sacrifice in legal, at full size (§4.2): most interesting identity work needs human-confirmed resolution. The invariant becomes "never auto-merge what we cannot prove," and the audit chain records machine vs human decisions. |
| 9 | **Evaluation credibility + annotator bottleneck** | Engineering-curated gold was tmc's permanent caveat; the team has never produced a second human annotator in 18 months. Legal κ stays descoped to feasibility until a named legal advisor exists. |
| 10 | **EU AI Act high-risk classification** | Only for EU/UK deployment of outcome-prediction features. Judgment-parsing + chronology sits outside "applying law to concrete facts" if scoped carefully. Monitor; no prediction tools in the EU until assessed. |
| 11 | **MCP security** [C#10] | Shipping an MCP server exposes case documents to third-party clients: tool poisoning, prompt injection, data exfiltration. A mandatory security story precedes any MCP launch (§5.2). |
| 12 | **Unit economics on large dockets** [C#4] | LLM cost per docket ($10–50 at 3,000 pages) plus OCR forces value-based pricing ($100–500/docket), not cost-plus. Modeled in §5.3; refine in spike. |
| 13 | **Process risk — the team's failure signature** | This team's documented failure mode is presenting measurement artifacts as validated results (post-hoc conventions, fabricated manifest, stale engines across 4 copies). Legal buyers are professional skeptics. Countermeasures, in this doc by construction: named sources with ranges, no cross-domain accuracy transfer (§4.7), corrections recorded not deleted (§11), and the existing product's P0s fixed before the vertical ships (§8). |

---

## 8. What this means for the existing assets

- **The oncology product stays live and supported** (`pre/findingframe/` deployed at `5edaa997`, verified). It becomes the reference customer for "audit-grade in a regulated domain" — its existence *is* the pitch.
- **The research repo (`tmc/`) remains the engine source of truth.** The adapter refactor lands *upstream* there; the product vendors it (the `vendor_engine.sh` mechanism already handles this).
- **The paper track is frozen, not unaffected (amended 2026-08-14, B3/critique C7):** the paper's one remaining `\PENDING` is B2 (clinician IRR) — the same second-annotator search this pivot redirects to legal, and one founder cannot run both searches. The paper stays at 55 pp with the B2 marker pending until the legal advisor search resolves (a found advisor may make a legal κ feasible first) or GATE 0 kills the pivot (the oncology annotation search resumes). The frozen paper still serves double duty: the slot-level evaluation methodology is the credibility artifact for the legal vertical's κ-study claim.
- **Strategy docs:** this document supersedes `PRODUCT_AND_MARKET.md`'s India-first-pharma revenue plan on the strategic layer; `PRODUCT_BUILD_PLAN.md` stays valid for the oncology product. A go/no-go update to `PITCH.md` and `MARKET_RESEARCH.md` follows a decision on §10.
- **Open P0s from the pre audit remain open and transfer:** P0-4 (a new run silently replaces a reviewer's signed-off view) matters *more* in legal — fix before any re-extraction; P0-5 (demo patient's fabricated manifest) is a brand risk for an audit-grade product and must be fixed or the patient replaced. Both are now explicit blockers on any new vertical shipping on the same review/audit machinery.
- **Capacity reality [C#10]:** there is one founder. The plan above is ~19–29 person-weeks of engineering plus design-partner selling plus GATE-0 validation. The honest sequencing: GATE 0 is cheap and founder-runnable; the engine refactor is not parallelizable with partner-selling without a second hire. The ARR gates assume either a hire or a slowed engine timeline — stated here, not hidden.

---

## 9. Immediate next actions (pre-decision)

1. **Run GATE 0 — demand validation** (§5.2): one written willingness-to-pay signal + data-licensing due-diligence note. **This precedes everything.**
2. **Decide the geography fork (§5.1)** — v2 recommends India-corpus/US-gold-and-revenue.
3. **Decide the build sequence** — legal adapter v0 ahead of the MCP server, or MCP-first with legal as the flagship adapter (v2 recommendation: legal first).
4. **Run the 2-day KeySpec spike** — before committing the 4–6 week core estimate [C#9].
5. **Build the 3-case US pilot gold** (CourtListener, 3 multi-year cases) — the legal equivalent of the first 8-patient gold set; US-based, not India-based [C#4].
6. **Fix P0-4 and P0-5** in the product before any new vertical ships on the same review/audit machinery.
7. **Find one legal advisor** (name in the org chart) before M3; without one, the κ gate at M9–12 is redefined as feasibility-only [C#10].

---

## 10. Open decisions (owner: founder)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Geography | India-corpus/US-gold-and-revenue / US-first / India-only | India-corpus/US-gold-and-revenue (v2) |
| D2 | Category name | "Attributable Longitudinal Document Intelligence" / "audit-grade document memory" / other | ALDI working title; test in design-partner conversations |
| D3 | First adapter confirmation | Legal judgments / financial filings / insurance claims | Legal judgments |
| D4 | Platform strategy | Vertical SaaS first / MCP developer-first / both in parallel | Vertical SaaS first, MCP at M6–9 with security story |
| D5 | What happens to oncology | Keep selling / freeze / fold into legal infra | Keep (reference customer); revisit at legal's ARR gate |
| D6 | MVP downstream task | Procedural history / contradiction detector / funder screen | Procedural history + contradiction detector |
| D7 | Legal advisor / annotators [C#10] | Hire part-time advisor now / advisor by M3 / none, κ stays feasibility | Named advisor by M3; κ feasibility-only until then |
| D8 | Founder capacity [C#10] | Second hire at M3 / solo with slowed timeline / contractor for OCR+adapter | Decide at GATE-0 exit, with the §8 capacity reality on the table |

---

## 11. Critic pass record (v1 → v2)

An adversarial review of v1 produced ten must-fix findings. All accepted; corrections are inline, marked **[C#n]**, and summarized here — kept visible per the team's convention (corrections recorded, not deleted):

| # | Finding | Resolution |
|---|---|---|
| C#1 | Whitespace case is supply-side; zero demand signals; oncology has zero paid pilots | Added GATE 0 demand validation (written WTP signal) before any build; added §1.1 honesty note; added risk #1 |
| C#2 | "Harvey hallucinates 1-in-6" misattributes a Lexis+ figure and contradicts the doc's own valuation figures | Claim withdrawn; replaced with the sanctions record as demand evidence; valuation figures made consistent ($11B Mar 2026, reportedly raising at $15.5B); §2.4 states the meta-point (contested vendor benchmarks are themselves the argument for independent verification) |
| C#3 | No expected legal accuracy stated; "Type F1 ≥ 0.80 on self-curated gold" is the dev-cohort overfit trap | New §4.7: no legal number until measured on held-out gold; planning prior full-frame 0.4–0.6; internal gates are diagnostic, not marketing numbers |
| C#4 | Economics missing; $10–50 funder screen likely below marginal cost; India validation doesn't transfer to US; rate limiter ignored | §5.3 cost model added ($0.30–1.50/judgment, $10–50/3,000-page docket); funder screens re-priced $100–500; pilot gold made US-based; throughput workstream priced in §6.3 |
| C#5 | M3–6 gate ("2 paying ≥$2K/mo") unreachable against India's published ₹3.3–10K/mo; "no incumbents verify" contradicted by SCC/Manupatra; CourtListener labeled "Free"; Lucio misrow | Gate redefined by geography-appropriate published rates; incumbent claim corrected to content-vs-citation distinction; CourtListener membership tiers noted; Lucio moved to the US WTP row |
| C#6 | OCR and pin-cite/Bluebook called part of the rebuild but absent from effort rows; report_cleaner rated "S (plugin)" while prose says "the hard version" | Two new workstream rows (3–5 wks, 2–3 wks); cleaner re-rated L; totals revised 13–19 → 19–29 person-weeks |
| C#7 | Schema has no speaker/attribution slot; `procedural_event` conflates event with claims; "declined to reverse" is a holding value not assertion stance; "~25-issue taxonomy" asserted without basis; deterministic-identity "exception" is actually the main event | Speaker slot added; slot renamed `procedural_event_type`; holding-vs-assertion scoping fixed; taxonomy size moved to §4.6 open questions; §4.2 rewritten to state the exception at full size and redefine the invariant (never auto-merge; audit chain records machine vs human) |
| C#8 | India $2.64B vs US $400B compares single-point figures from incompatible scopes (the team's documented RWE-trap failure mode) | Table cell now flags the ~10x analyst spread and warns against leaning on the low figure; conclusion no longer rests on the comparison alone |
| C#9 | The 4–6 week core estimate gates the whole plan and is a guess (the doc's own next-action admits it) | KeySpec spike promoted to GATE-0-adjacent: run before committing the estimate; §6.3 marks the estimate as spike-gated |
| C#10 | No legal advisor/annotator named; κ study scheduled despite the team's 18-month annotator failure; MCP security story missing; DPDP/GDPR party-name analysis unfinished; data ToS unexamined; founder capacity unaddressed | κ descoped to feasibility (D7); MCP security mandatory before launch (§5.2, risk #11); privacy/data posture moved to §5.4 + GATE 0; capacity reality stated in §8 (D8) |

**Open after v2:** the demand-validation gate (§5.2 GATE 0) is the next action, and everything downstream is conditional on it. The geography fork (D1) remains a founder decision; v2's recommendation stands on the US-gold correction.
