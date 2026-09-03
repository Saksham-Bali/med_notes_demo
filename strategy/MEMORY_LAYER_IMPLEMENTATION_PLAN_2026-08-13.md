# Unified Build Plan v2 — Evidence-Anchored Memory Layer

**Date:** 2026-08-13 · **Status:** v2 — synthesis of survey (arXiv 2602.06052v4), RL research, Prime Intellect playbook, OSS memory systems (incl. Supermemory), four plan variants, and a five-model critique panel (Kimi K3 / DeepSeek V4 / GPT-5 / Claude Opus / Gemini 3)
**Supersedes:** v1 of this doc; `PIVOT_MEMORY_LAYER_2026-08-13.md` §5–§6 sequencing details
**Research artifacts:** `.firecrawl/memory-survey/` (PI research, model critiques, RL scrapes, OSS scrapes); survey text `/tmp/agent_memory_survey.txt`

---

## 1. The decision (best of four plans + five critiques)

The plan-variants pass produced four plans; the recommendation and the critique panel converge on the same shape:

> **D-gated hybrid: demand-validated vertical (legal) first, benchmark authority as the ecosystem play, substrate generalization funded by the vertical, RL last and gated.** Killable at every stage.

Every plan that builds 16+ weeks of substrate before asking whether anyone pays was rejected by the panel (GPT-5: "GATE 0 says stop in 4 weeks; this plan spends 6 before learning anything"). Every plan that leads with RL was rejected on team reality (DeepSeek: "RL/SFT on a few hundred labels is theater"; the review queue has hundreds of decisions, not tens of thousands). The benchmark-first plan survives as a *phase*, not a plan — publication is cheap and the machinery already exists.

## 2. The core design insight: three-tier actor model (resolves determinism-vs-RL)

The audit-grade claim decomposes into four properties; RL only threatens one of them:

| Property | Threat from learned policies | Resolution |
|---|---|---|
| Decisions recorded (append-only, hash-chained) | none | unchanged |
| Every accepted fact verifiable against evidence (span gate) | none | unchanged |
| Identity/linking deterministic (composite keys) | **yes — learned merges break it** | Tier 1: never learned |
| Same inputs → same outputs | **yes — stochastic policies** | reframed: *re-verifiability, not uniqueness* |

**Tier 1 — deterministic core (never learned):** evidence gate, span verification, composite-key computation, normalization, hash chain, audit. The "physics" of the system.

**Tier 2 — policy decisions (learnable, verifier-gated):** what to write, when to update, what to retrieve, what to compress, what to forget. A learned policy *proposes*; the deterministic verifier *disposes* (span-exact, no contradiction, no auto-merge). **Every proposal→accept/reject event commits the policy's model + prompt + seed + weights manifest to the hash chain** (Claude critique #4) — learned writes remain auditable.

**Tier 2.5 — runtime utility learning, data-space only (MemRL pattern):** the literature resolves the determinism tension decisively — **no surveyed system mutates policy weights at runtime**. MemRL (arXiv 2601.03192) instead learns Q-values over (intent, experience, utility) triplets on *memory entries*: retrieval ranked by learned utility, not similarity; weights frozen; theoretical convergence guarantees; utilities inspectable and revertible. This is self-evolution that never breaks reproducibility: the policy is a frozen artifact; only per-frame utility scores drift, and every drift is an append-only audit-chain event. Our version: utility = f(evidence-verifiability, retrieval hit rate, human-confirm rate), updated Monte-Carlo style, fully on the chain.

**Tier 3 — human adjudication:** ambiguous deletes, merges, conflicts. The review queue becomes the product, not a fallback.

Reproducibility reframed honestly: the system guarantees *any state can be recomputed and re-audited*, not that two runs agree — exactly like two human abstractors. "Deterministic where identity is at stake, human-gated where judgment is at stake, recorded always." This is the line for the paper, the pitch, and the audit story.

## 3. Phase plan (each phase has a kill gate)

### Phase −1 — P0 remediation (1–2 wks) [GPT-5, Claude]
Fix `pre/findingframe` P0-4 (new run silently replaces a reviewer's signed-off view → explicit "engine changed" state) and P0-5 (10000935's fabricated manifest). **A memory product cannot ship on machinery that once described an LLM call that never happened.** Gate: P0s closed with tests.

### Phase 0 — GATE 0 demand validation (2–4 wks) [the pivot's C#1]
One written willingness-to-pay signal (lawyer/funder/insurer) for span-anchored procedural history or contradiction detection + data-licensing verdicts (CourtListener membership tiers, Indian Kanoon ToS, DPDP/GDPR party-name posture). **Amended 2026-08-14 (B2, critique C3/C6):** pre-GATE-0 work is Phase −1, this phase, **plus ≤3 person-days of bounded technical feasibility work** (gold pilots, extraction probes, KeySpec spike) — recorded because the v0 gold build (2026-08-14) predated GATE 0 without authorization; the cap makes the gate enforceable instead of decorative. **The WTP question is strengthened: the signal must state standalone-purchase intent at a stated price — "would you pay $X/mo for this as a separate tool" — not general usefulness**; a "yes, useful" answer does not retire risk #1 (platform absorption). **Kill-switch: return to the oncology paper track, 4 weeks lost.**

### Phase 1 — Spike + adapter + probes + read-only MCP (4–6 wks)
- KeySpec spike (2 days) **before** committing any estimate; reconcile the two unreconciled numbers (16–22 vs 19–29) into one ±10% by end of this phase [Kimi #1].
- `DomainAdapter` extraction; radiology regression-free on frozen_30 (488 tests).
- **Probe harness now, not Phase 5** [Kimi #5]: HaluMem-style MI/FMR probes + FactScore over stored frames, pre-commit thresholds **MI ≥ 0.85, FMR ≤ 0.03, FactScore ≥ 0.90** [Kimi #4].
- **Read-only MCP server** (read-tracks/query-frames), 1 week not 2–3 [DeepSeek #6]; threat model doc lands here, not with the full server [GPT-5 #4].
- Token budgets as hard caps from week 1: **≤4K injected span tokens/query, ≤8K working context**, logged per query [Kimi #2].

### Phase 2 — Legal adapter v0 (8–12 wks, cheap-model-first)
- **Benchmark one-shot full-context extraction vs chunked on the 3-case US pilot gold before building any chunking subsystem** — a 100-page judgment ≈ 60K tokens fits one 1M-token call; chunking may be sunk cost [Kimi #3].
- Cheap-model-first routing: run pilot gold through cheap models + a 7B fine-tune, publish per-slot deltas, escalate to frontier on gate failures only [DeepSeek #4]. Judge chain: deterministic span checks → 7B judge → frontier judge on riskiest 10% [DeepSeek #3].
- Schema v2 with `speaker` slot (polyvocality), `procedural_event_type`, holding-vs-assertion scoping (pivot §4.1); multimodal anchors: page/bbox coordinates for non-text evidence (exhibits, tables) [Gemini #3].
- **Cost-per-memory-op ledger from day 1**: price every ADD/UPDATE/RETRIEVE/COMPRESS in $/1K frames/model tier; route to minimize [DeepSeek's only-add].
- Abstention ships as **default behavior with a threshold**, not an eval artifact — under the SCI "unverified citations = misconduct" regime, confabulation is a liability vector [Claude #5].
- Design partners: 2 India (volume/iteration) + 1 US funder (gold + revenue). Gate: partners using weekly; diagnostic eval on held-out gold; **no legal accuracy number published until measured**.

### Phase 3 — Money moment + data capture + consent (4–8 wks)
- Procedural history + contradiction detector, pin-cited throughout.
- Instrument every review decision as RL preference data **with documented label provenance; unconsented decisions excluded from training** [Claude #3]. Reviewer confirmation-rate stats as an ops metric [Claude #6].
- Failure paths specified: per-operation rollback, queue SLAs, `review_only` retention policy [GPT-5 #2, #6].
- Gate: paying customer at geography-appropriate published rates (pivot §5.2); NPS ≥ 8.

### Phase 4 — Benchmark publication (3–4 wks, parallel with Phase 3 where possible)
- Publish the existing frozen evaluation + track-linking metrics as a public benchmark package (the machinery exists; this is packaging + docs).
- Pre-register the eval protocol in writing: LoCoMo/LongMemEval/HaluMem scores are **membership checks, never in the same table as frozen-benchmark scores** [GPT-5 #5].
- Named venue for publication; the benchmark harness ships as a reusable package [Gemini #6].
- This doubles as the demand-generation machine for Phase 2/3 design partners. Gate: ≥3 external submissions in 90 days, or downgrade to marketing collateral.

### Phases 5–7 — MOVED 2026-08-14 (B9, critique C13)
Substrate generalization, RL, and ecosystem now live in `MEMORY_PLATFORM_TRACK_2026-08-14.md`. They answer a developer-memory demand hypothesis that GATE 0 does not test; entry condition is the Phase 3 revenue gate. Content moved verbatim, not deleted.

**Total, near-term (Phases −1..4): ~22–36 person-weeks** with kill gates after 4 (GATE 0) and ~18 (paying customer). Phases 5–7 (8–11 wks + gated RL) moved to `MEMORY_PLATFORM_TRACK_2026-08-14.md` on 2026-08-14. All estimates reconciled in Phase 1.

## 4. Economics ledger (running)

| Operation | Model tier | Cost anchor |
|---|---|---|
| Extraction per judgment (one-shot) | cheap-first → frontier escalation | ~$0.05–0.50 one-shot vs $0.30–1.50 chunked; measured in Phase 2 |
| Judgment per 3,000-page docket | mixed | $10–50 LLM spend; priced $100–500 value-based (pivot §5.3) |
| RL training 3–8B policy | own GPUs / PI Sprints | $300–1.5K/run (Memory-R1 recipe) to $5–7K/run (Mem-α recipe); $0 for outcome-driven RL until Memory Gym ready |
| Memory ops (ADD/RETRIEVE/COMPRESS) | per-op ledger | telemetry from Phase 2 |

## 5. What remains open

| # | Decision | Owner | Deadline |
|---|---|---|---|
| D1 | Geography fork final (India-corpus/US-gold-and-revenue vs US-first) | founder | GATE 0 exit |
| D2 | Legal advisor named in org chart | founder | Phase 2 start |
| D3 | Second engineer (Phase 2 OCR/adapter) or contractor | founder | Phase 1 exit |
| D4 | Publication venue for the benchmark | founder + advisor | Phase 4 start |
| D5 | PI partnership conversation (Sprints/Environments Hub) | founder | Phase 6 Gate A |

## 6. Failure modes this plan is designed to survive

1. **No demand** → killed at GATE 0 (4 wks, zero build beyond P0 remediation).
2. **Paying customer never converts** → killed at Phase 3 gate; benchmark (Phase 4) already running as the authority play; oncology intact.
3. **RL doesn't help** → pre-registered kill criteria; the product never needed it (Tier 1 + Tier 3 alone is the current system, already shipped).
4. **Measurement failure mode (the team's history)** → pre-committed thresholds (MI/FMR/FactScore), pre-registered eval protocol, benchmark conventions declared before any system runs on them, no standard-score mixing with frozen scores, corrections recorded not deleted.
5. **Legal erasure/privacy collision** → Phase 5 erasure path + consent instrumentation in Phase 3, both before any client-matter data is ever ingested.
