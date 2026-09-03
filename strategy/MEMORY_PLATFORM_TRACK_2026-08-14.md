# Memory Platform Track — Phases 5–7 (split from the near-term plan)

**Date:** 2026-08-14 · **Status:** moved verbatim from `MEMORY_LAYER_IMPLEMENTATION_PLAN_2026-08-13.md` (B9, critique C13)
**Why split:** these phases answer a *developer-memory* demand hypothesis ("developers will pay for verifiable agent memory") that GATE 0 does not test — GATE 0 validates the legal vertical only. Keeping them in the near-term plan inflated the week count and blurred the kill gates. The legal vertical is killable without killing this track, and vice versa.
**Entry condition:** none of this starts before the Phase 3 revenue gate (paying customer at geography-appropriate published rates). Phase 6 (RL) additionally requires its own pre-registered gates below.

---

### Phase 5 — Substrate generalization, condensed (6–8 wks) [DeepSeek #5: views, not stores]
- Episodic/semantic/procedural as *views* over existing frames + tracks, not a rebuild (2 wks, not 3–4).
- Forgetting: Zep-style `valid_at`/`invalid_at` — invalidated never deleted — **plus the erasure path**: key-shard deletion/redaction with the hash chain proving what was removed and when; access/export/erasure ops on the user-centric store with tests [Claude #1, #2].
- Compression with deterministic span-coverage checks first; FactScore on outputs.
- Split multi-agent work: 5a subjects/ownership, 5b routing/isolation/conflict matrices (4–6 wks total, not 2–3) [Gemini #1].
- Context-fill stress ladder: run the store at 10%/50%/90% context occupancy, publish the retrieval-degradation curve [Kimi's only-add].

### Phase 6 — RL, staged and gated [refined with RL-research findings]
- **Gate A (data, split by RL mode):** *Imitation/SFT* on human review decisions is gated on **≥10K labeled decisions** (hundreds of labels overfit — DeepSeek critique stands). But *outcome-driven RL* does not need human labels at all: **Memory-R1** (arXiv 2508.19828) trained its ADD/UPDATE/DELETE/NOOP policy on just **152 QA pairs for eval** with a frozen Answer Agent as reward and gained +48% F1 / +37% judge over Mem0, zero-shot transferring to MSC/LongMemEval. So: **outcome-driven RL is gated by Memory Gym readiness + the pre-committed delta below, not by label count.**
- **Gate B: pre-committed expected delta** — write the expected F1 gain before training; **<5 points = don't train**.
- v0 baseline: DPO on review decisions (cheap preference pairs) → v1 SFT on Memory Gym traces (small-data SFT transfers: PI's 4.4K traces lifted BFCL 18.9→52.3) → v2 GRPO.
- v2 Memory Gym: per PI spec — synthesizer/solver, 5 difficulty tiers per memory ability (extraction → temporal → update/refresh → contradiction → abstention), **deterministic verifiers only** (our frame_metrics philosophy; no LLM judge on any reward's critical path — Mem-α's Qwen3-32B content-judge reward is the explicit anti-pattern), every task gold-replay + no-op + flakiness validated.
- v3 RL targets, in order: (1) **working-memory curation** (MemAct: keep/drop/merge as actions; sparse terminal reward + context-overflow penalty; 4B policy beat a 235B model at 59.1% — the strongest first target), (2) write-policy proposals (verifier-gated), (3) forgetting/retention (MEM1 shows it **emerges** from task reward + budget constraint — do not reward compression directly), then Tier 2.5 runtime utilities (MemRL).
- **Reward spec (all components deterministic or rule-verified):** r_outcome (frozen, version-pinned evaluator) + r_evidence (span-substring gate as reward) + r_human_agreement (+1/−1 vs logged review decisions; DPO first) + r_abstention (NOOP is the *correct* action on decoys — Abstain-R1 pattern; never a competing flat component) + r_budget (token-count penalty, applied only after correctness stops saturating — PI: a saturating visible reward lets hidden hacks absorb the gradient).
- **Anti-hacking monitors (PI playbook):** catch-all `other_important_finding` distribution spillover; over-retrieval ("maximize accuracy by retrieving everything"); evidence-span keyword-stuffing; never train with "do not write X" prompts.
- **Kill criteria pre-registered**: cancel if Δ < 5 pts or cost > budget below.
- World-modeling option: SFT-as-RL constant-positive-advantage on deterministic tool responses (linker/retriever outputs) — PI's ECHO/PaW technique, zero added cost, helps most in domains the model hasn't memorized (exactly memory-policy behavior).
- Cost reality: Memory-R1 recipe (8B) ≈ **$300–1,500/run** (single 8×H100, hours–1 day); Mem-α recipe (4B, 205 steps) ≈ **$5–7K/run**; PI Sprints free for 1B-scale validation; hosted campaign $15–60K only if sprint-scale runs prove out.
- Governance: MemArchitect (2603.18330) / SSGM (2603.11768) as the policy-governance references — every learned write under Tier-2 verifier disposal (§2 of the implementation plan).

### Phase 7 — Ecosystem (2–3 wks)
- Full MCP server (write/sign tools) with the Phase-1 threat model enforced; A2A memory-sharing spec; skill provenance on the hash chain [Gemini #2, #5].
- Local-first deployment story modeled on Supermemory (MIT; embedded graph engine + local embeddings — the OSS UX benchmark, not a competitor on audit-grade).
- Open Memory Gym on PI's Environments Hub (leaderboard + Sprints as distribution and partnership on-ramp); production memory store stays proprietary.
- Open memory-exchange format (export/import across agent platforms) — portability as moat [Gemini's only-add].
- Red-team drill: poisoned documents + forged sign-offs for one week; prove the chain catches each; publish [GPT-5's only-add].

**Platform-track total: 8–11 person-weeks (Phases 5, 7) + RL (cost-priced separately, gated).**
