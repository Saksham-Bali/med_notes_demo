# FindingFrame — Clinical Validation Protocol: Inter-Rater Reliability (Cohen's κ)

**Status:** protocol + tooling ready; pilot not yet executed (0 rows in `ff.annotation_tasks`
as of this writing — verified live, see §7).
**Scope of this document:** the blinded clinician IRR pilot only. It does not cover the
200-patient TMC engagement's regulatory/consent process, which is a separate workstream.
**Companion script:** `infra/scripts/compute_kappa.py` (Deliverable 2 of this same work item).
**Aligns with:** `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` (research team's
stratified IRR pilot design) and `pre/strategy/PRODUCT_AND_MARKET.md` §7 (this pilot is
simultaneously the FindingFrame paper's IRR requirement and the startup's #1 fundability
unlock — one body of work serves both).

---

## 1. Purpose

FindingFrame's current validation story is **engineering gold**: 30 MIMIC-IV patients,
labels curated by the engineering team against source reports, no board-certified clinician
has adjudicated any label
(`pre/tmc/new_plan/verified_specs/phase_c_clinician_validation.md` §2.1 calls this
`engineering_curated_not_clinician_adjudicated`). `pre/strategy/PRODUCT_AND_MARKET.md` is explicit
that this is a diligence liability: *"No clinical-validation claims yet ... say
'architecturally validated; clinical validation underway.'"* This protocol is how that
changes to a real number: a blinded, double-read, chance-corrected inter-rater agreement
statistic, computed the way JAMIA/npj/Radiology:AI reviewers expect it.

### 1.1 The distinction that makes or breaks this claim

Fable's review flagged the single most important thing to get right, and the schema
(`infra/supabase/migrations/0001_init.sql`) already has the columns to enforce it. There
are two structurally different things a clinician can do in this product, and only one of
them is IRR:

| | **Production review** | **Blinded IRR read** |
|---|---|---|
| What the clinician sees | The model's extraction, digest, tracks — full context | Only the raw item (evidence sentence / frame / candidate slots), **model output hidden** |
| Purpose | Approve/correct facts before sign-off (the product's normal workflow) | Measure whether two independent readers agree with each other, independent of the model |
| Number of readers | 1 (whoever is reviewing that patient) | ≥2, working **independently**, no communication |
| Statistically valid IRR? | **No** — anchoring bias. Seeing the model's answer measurably shifts a reviewer toward it (well-documented in annotation literature); a 95% "agreement" rate here tells you readers rubber-stamp, not that the extraction is correct. | **Yes**, if and only if the read was truly blinded and independent |
| Schema marker | `ff.reviews.model_output_visible = true` (the column's own default) | `ff.reviews.model_output_visible = false` **and** an `assignment_id` linking it to a blinded `ff.annotation_assignments` row — **or**, the mechanism this pilot actually uses, a row in `ff.annotation_records` under an assignment with `model_output_visible = false` |
| Pairing / independence | N/A — one reviewer, no pairing | `ff.annotation_assignments.independence_group` — two assignments sharing a group are the pair a κ is computed over. Two assignments **without** a shared `independence_group` cannot be scored as an agreement pair; `compute_kappa.py` refuses to (prints a warning, skips them) |

**Why this matters concretely:** every reviewer-facing screen in the built product
(`RUNBOOK.md` §6, `BUILD_SPEC.md`'s `POST /runs/{id}/reviews`) is a **production review** —
the clinician sees the digest, the verbatim evidence, the model's slot values, and marks
`link_correct` / `type_correct` / etc. against what they were shown. That is the correct
UX for the *product* (a human must approve every fact before sign-off) and it is worthless
as an IRR measurement, because the two things being "compared" (reader vs. reader) were never
independent — both readers, if there were two, would have been anchored on the same model
output. **`ff.reviews` rows can never be pooled into a κ calculation and called IRR.** The
schema's `model_output_visible` flag on `ff.reviews` exists specifically so this mistake is
detectable and preventable, not to imply reviews are a source of κ.

The blinded pilot this document specifies uses a **separate capture path** —
`ff.annotation_tasks` / `ff.annotation_assignments` / `ff.annotation_records` — built for
exactly this, with no other purpose. `compute_kappa.py` reads only from this path.

---

## 2. Study design

### 2.1 Readers

- **≥ 2 board-certified radiologists** (or oncology fellows), reading **independently** —
  no joint sessions, no shared screen, no discussion until after both have submitted.
- Each reader is one `ff.annotation_assignments` row, `annotator_id` = their `auth.users.id`,
  `model_output_visible = false`.
- The two (or more, for a Fleiss-style extension — see §6) assignments that form one blinded
  pair share one `ff.annotation_assignments.independence_group` value (e.g. `"pilot_pair_1"`).
  This string is the *entire* mechanism that tells `compute_kappa.py` "these two rows are a
  genuine independent pair" — get it wrong (leave it null, or give three readers the same
  group) and the script will warn and refuse to score them (verified — see §7).

### 2.2 Sample: stratified, 150–200 frames

Aligned with `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` §3.1 and its verified refinement in
`pre/tmc/new_plan/verified_specs/phase_c_clinician_validation.md` §3.1. Recommended stratification for the
FindingFrame platform pilot:

| Stratum | % of sample | Source in `ff.*` | Rationale |
|---|---|---|---|
| Standard / representative | 50% | Random `ff.frames` across confirmed runs | Unbiased estimate of overall agreement |
| Unresolved-link / false-split candidates | 25% | `ff.tracks.unresolved_link = true` OR `ff.tracks.false_split_candidate = true` → their member frames | Over-samples the hardest linking cases — this is where the 0.382 strict-Jaccard track-F1 weakness lives, and where clinician judgment is most valuable |
| Low-confidence / gate-adjacent | 25% | `ff.frames.evidence_verified = false` (gate-failed, already force-routed to review) or `ff.frames.uncertainty is not null` | Validates the evidence-gate's own false-positive/false-negative rate — directly tests the source-linking guarantee ("100% source-linked; gate-failed facts quarantined") at its edges |
| *(optional, track-level slice)* Track-level adjudication set | separate, ~30–50 tracks | Tracks touched by any `ff.link_decisions` in the demo/pilot data, oversampled for `unresolved_link`/`false_split_candidate` | Feeds the track-linking κ (see §3) — pick tracks, not individual frames, since track identity is what's being judged |

Example selection query (illustrative — run once to build the sample, not part of
`compute_kappa.py`):

```sql
-- stratum 2: frames belonging to unresolved/false-split tracks
select f.id, f.run_id, f.track_key
from ff.frames f
join ff.tracks t on t.run_id = f.run_id and t.track_key = f.track_key
where t.unresolved_link or t.false_split_candidate;

-- stratum 3: gate-failed or uncertain frames
select id, run_id, track_key from ff.frames
where evidence_verified = false or uncertainty is not null;
```

`item_ref` in `ff.annotation_records` should be the frame's `ff.frames.id` (as text) for
frame/slot-level items — this is what lets `compute_kappa.py`'s correction-rate feature
(§3.4) join back to the model's original value. For the track-level set, `item_ref` should
be `ff.tracks.id` (as text).

### 2.3 Units of agreement

`ff.annotation_tasks.unit_of_agreement` is a first-class enum (`'slot' | 'frame' | 'track'`)
for exactly this reason — each level answers a different question and gets its own κ:

| Unit | What's being judged | `item_ref` | κ computed by `compute_kappa.py` as |
|---|---|---|---|
| **Slot** | Is this one field (`finding_type`, `anatomy`, `laterality`, `assertion`, `temporal_change`, `measurement`) correct? | `ff.frames.id` | One κ per slot key present in both readers' `labels` jsonb |
| **Frame** | Do the two readers agree on the *entire* frame (all slots at once)? | `ff.frames.id` | Per-slot κ, **plus** a composite `full_frame (all slots)` row — the concatenation of all canonical slots into one category, any single-slot mismatch = disagreement on the composite |
| **Track** | Do the two readers agree this frame/pair belongs to the same longitudinal finding (link/split)? | `ff.tracks.id`, or a frame-pair key | κ over the binary/categorical linking judgment (whatever key the reader recorded, e.g. `belongs_to_same_track` or `linked`) |

A single pilot task is recommended at `unit_of_agreement = 'frame'` with `labels` holding
all six core slots per frame (richer than `pre/tmc/new_plan/phase_c_clinician_validation_spec.md`'s original per-slot binary
"is `X` correct?" design — see box below), plus a **second, separate** task at
`unit_of_agreement = 'track'` for the track-linking judgment, since its `item_ref`
namespace (tracks) is different from the frame task's (frames).

> **Design note — why raw category labels beat binary correctness flags.**
> `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` §3.2 and the original `pre/tmc/scripts/compute_kappa.py`
> record a *binary* judgment per slot (`finding_type_correct: true/false`) rather than the
> reader's actual chosen label. That is a legitimate design but it is *not* what
> `ff.annotation_records.labels` stores here, and the difference matters statistically:
> binary correct/incorrect kappa is vulnerable to *prevalence paradox* — if the model is
> right 95% of the time, both readers will say "correct" 95% of the time regardless of
> whether they're actually agreeing about anything, which can produce a **misleadingly
> high** kappa on a skewed marginal, or occasionally the reverse (low kappa despite high
> raw agreement) — the well-known kappa paradox. Recording each reader's **actual chosen
> category** (`labels = {"finding_type": "liver_metastasis", ...}`, independently, without
> seeing what the other reader chose or what the model said) and computing kappa on the
> raw categorical agreement is the more defensible statistic and is what `compute_kappa.py`
> implements. It also gives you the *correction* for free (§3.4) — you already have the
> reader's intended label, no separate "what should it have been" free-text field needed.

### 2.4 Blinding checklist (must hold for every assignment scored as IRR)

- [ ] `ff.annotation_assignments.model_output_visible = false` for **both** assignments in
      the pair.
- [ ] `independence_group` set and shared by exactly the two paired assignments (not 1, not 3+).
- [ ] The two readers did not communicate before both had submitted (procedural, not
      schema-enforced — document it in the pilot's session log).
- [ ] `annotator_id` values differ (two different `auth.users` — trivially true with real
      readers, but worth asserting since nothing in the schema prevents the same user id
      from annotating "both" sides, which would make the exercise circular).
      `compute_kappa.py` does not currently assert this — see §5 gap list.

---

## 3. Metrics

### 3.1 Cohen's κ

$$\kappa = \frac{p_o - p_e}{1 - p_e}$$

- $p_o$ = observed agreement = trace of the confusion matrix / N.
- $p_e$ = chance agreement = $\sum_k \left(\frac{\text{row}_k}{N}\cdot\frac{\text{col}_k}{N}\right)$
  over categories $k$ (row/column marginals of the confusion matrix).

Implemented directly with numpy in `compute_kappa.py::cohens_kappa()` (no scikit-learn
dependency) — confusion matrix via `np.zeros` + index bumps, `po = trace/n`,
`pe = row_marginals · col_marginals`. Verified by hand in `--demo` (see §7): a textbook
50-item, 2×2 confusion matrix (20/5/10/15) gives $p_o=0.70$, $p_e=0.50$, $\kappa=0.400$
exactly — matches the standard textbook worked example bit-for-bit.

Computed per:
- Each core slot: `finding_type`, `anatomy`, `laterality`, `assertion`, `temporal_change`,
  `measurement` (whichever are present in both readers' records for a given task).
- Track-linking judgment (binary or categorical, per §2.3).
- A `full_frame (all slots)` composite when `unit_of_agreement = 'frame'`.

### 3.2 95% confidence interval

Percentile bootstrap (2,000 resamples by default, seeded for reproducibility): resample
items with replacement, recompute κ each time, take the 2.5th/97.5th percentiles.
Non-parametric — makes no assumption about κ's sampling distribution, appropriate at the
pilot's planned N≈150–200 (and correctly reports very wide intervals at small N, which is
itself an honest signal — see the N=2/N=8 examples in §7).

### 3.3 Interpretation bands (Landis & Koch, 1977)

| κ range | Interpretation |
|---|---|
| < 0.00 | Poor |
| 0.00 – 0.20 | Slight |
| 0.20 – 0.40 | Fair |
| 0.40 – 0.60 | Moderate |
| 0.60 – 0.80 | Substantial |
| 0.80 – 1.00 | Almost perfect |

`pre/tmc/docs/ANNOTATION_GUIDELINES.md` Appendix A already targets **inter-rater agreement > 0.70**
("substantial") as the paper's headline bar, and `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` §7
treats ≥0.60 as the adjudication trigger (see §4).

### 3.4 Correction rate (ties to the ROI claim)

`compute_kappa.py::compute_correction_rate()` joins each blinded reader's recorded label
back to the model's **original** stored value in `ff.frames` for the same `item_ref` — a
comparison the reader could not have made themselves, since they never saw the model
output. For each of `finding_type`, `anatomy`, `laterality`, `assertion`, `temporal_change`:
correction rate = fraction of items where the reader's independent label differs from the
model's. (`measurement` is deliberately excluded — the reader's free-text/derived
measurement representation and the model's normalized `jsonb` aren't directly comparable
without a units-aware equality check this script doesn't implement; flagged as a gap in §5.)

This is the number that feeds `pre/strategy/PRODUCT_AND_MARKET.md`'s ROI claim ("~1 hour → ~20
minutes per patient") with an actual per-slot correction frequency instead of an anecdote —
and, because it's computed independently for each of the two blinded readers, a large gap
between reader A's and reader B's correction rate against the same model output is itself
a useful QC signal (one reader may be systematically stricter/looser than the other).

### 3.5 Time-per-read

**Known schema gap, documented rather than hidden.** `ff.review_sessions` gives production
review real `active_seconds`/`tracks_reviewed` instrumentation. There is no equivalent
table for blinded annotation sessions — `ff.annotation_assignments`/`annotation_records`
only carry `created_at`. Until a future migration adds
`started_at`/`ended_at`/`active_seconds` to `ff.annotation_assignments` (mirroring
`ff.review_sessions` — out of scope for this doc, which may not touch migrations), the
pragmatic proxy is:

```sql
select assignment_id, max(created_at) - min(created_at) as wall_clock_span, count(*) as n_items
from ff.annotation_records group by assignment_id;
```

divided by item count for a rough seconds-per-item figure. This is a **coarse proxy** (it
doesn't exclude breaks/interruptions between records) — adequate to sanity-check the pilot
didn't take an implausible amount of time, not precise enough to cite as the ROI number
itself. `pre/tmc/docs/ANNOTATION_GUIDELINES.md` §5 separately targets 10–15 min/patient for the
*production* review workflow, which does have real instrumentation via `review_sessions`.

---

## 4. Adjudication — the review → gold loop

```
ff.annotation_assignments (rad1, blinded)  ─┐
ff.annotation_assignments (rad2, blinded)  ─┼─► ff.annotation_records (both) ─► compute_kappa.py
                                             │        │
                                             │        ▼ (disagreement found)
                                             │  ff.adjudications
                                             │    - item_ref
                                             │    - resolves_assignment_ids = [rad1_assignment_id, rad2_assignment_id]
                                             │    - consensus (jsonb — the resolved label)
                                             │    - adjudicator_id (third, senior reader)
                                             │        │
                                             │        ▼
                                             └─► ff.gold_candidates
                                                   - item_ref
                                                   - gold = consensus
                                                   - contamination_model_visible = false  ◄── because it descends from a blinded read
                                                   - source = 'adjudication'
```

Procedure (matches `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` §8 "Open Question: Adjudication"):

1. Run `compute_kappa.py --task-id <id>` after both readers submit. For every `item_ref`
   where the two readers' labels disagree on any slot, that item is a candidate for
   adjudication.
2. A **third, senior clinical reader** — who did not participate in the blinded pair —
   reviews the disagreement (seeing both readers' labels and the evidence, but this is now
   a *consensus-building* step, not another blinded IRR read; it never itself contributes to
   the κ calculation) and records a `ff.adjudications` row: `resolves_assignment_ids` lists
   the two `ff.annotation_assignments.id`s being reconciled, `consensus` holds the resolved
   label set.
3. **If κ ≥ 0.60** (substantial-or-better, per the `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` recommendation): promote
   adjudicated items into `ff.gold_candidates` with `source = 'adjudication'` and
   `contamination_model_visible = false`. This is the first row of *genuinely
   clinician-validated* gold FindingFrame will have.
   **If κ < 0.60**: still adjudicate (produces useful ambiguity data — see §6), but do not
   yet claim a validated gold set; report the low κ as a finding about task difficulty
   (`pre/tmc/new_plan/phase_c_clinician_validation_spec.md` §8 explicitly anticipates this: *"a publishable finding ... reframes the 0.338
   track F1 as approaching the ceiling of human agreement rather than systematic failure"*).
4. Items where the two blinded readers **agreed** don't strictly need adjudication (no
   disagreement to resolve) — they may be promoted directly to `gold_candidates` with
   `source = 'adjudication'`, `contamination_model_visible = false`, and `gold` set to
   either reader's (identical) label, since two independent blinded reads agreeing is
   itself the validation.

---

## 5. Governance and integrity

This section exists because the single easiest way to destroy this pilot's credibility in
diligence is to blur the line between what was actually validated and what wasn't — and the
research repo (`pre/tmc`) already contains an artifact that does exactly the wrong thing, so
it is named explicitly:

> **`pre/tmc/scripts/simulate_annotations.py`** generates two **entirely synthetic**
> "rad1"/"rad2" annotation files using `random.seed()`-driven coin flips at
> hand-picked agreement rates (0.90–0.98) — it does not involve a real clinician at any
> point. `pre/tmc/scripts/compute_kappa.py` then computes a κ table over this fabricated
> data and writes it to `outputs/finding_frame_runs/clinician_irr_summary.json`, labeled
> "INTER-RATER RELIABILITY (IRR) PILOT RESULTS." **This file, and any number derived from
> it, must never be presented as clinician-validated IRR, must never be cited in the paper,
> the pitch deck, or any diligence material, and must never be confused with the real
> pilot this document specifies.** `infra/scripts/vendor_engine.sh` already excludes
> `scripts/` and self-verifies no `*simulate*` files ship into the deployed engine
> (`RUNBOOK.md` §2 — *"no simulated/fabricated IRR material ships"*) — that control is
> about the shipped *product*; this document is the corresponding control for the
> *validation claim*: **the standalone kappa tool for this platform's real pilot is
> `findingframe/infra/scripts/compute_kappa.py`, a from-scratch implementation against
> `ff.annotation_records`, sharing no code, no data, and no output file with the tmc
> repo's simulated version.** Anyone citing an IRR number for FindingFrame should be able
> to point to a `ff.annotation_tasks` row, its `ff.annotation_assignments` (both
> `model_output_visible=false`), and the `compute_kappa.py --task-id <id>` output that
> scored them — if they can't, the number is not real IRR.

### 5.1 Rules

1. **Engineering-curated gold is never presented as clinician-validated.** Any
   `ff.gold_candidates` row with `source = 'engineering'` must carry
   `contamination_model_visible = true` (the column's own default) — that flag is the
   permanent, queryable record that this label was curated with the model's output
   visible, i.e. it is not blind and cannot be cited as inter-rater-validated. A
   `gold_candidates` row can only legitimately have `contamination_model_visible = false`
   if it descends from the adjudication loop in §4 (`source = 'adjudication'`, tracing back
   through `resolves_assignment_ids` to two assignments that were actually
   `model_output_visible = false`). Treat any row that has `contamination_model_visible =
   false` but `source != 'adjudication'`, or whose lineage doesn't trace to blinded
   assignments, as a data-integrity bug to be investigated before it's used anywhere.
2. **The simulated-IRR artifacts named above must never surface** in the FindingFrame
   product, its docs, its pitch materials, or its paper. They may remain in the `tmc`
   research repo as engineering scaffolding/dry-run material for the *statistics code*,
   clearly labeled as synthetic, but treated as radioactive outside that context.
3. **Every step below maps to an append-only or otherwise auditable table** — nothing
   about the pilot's result can be quietly edited after the fact:

   | Protocol step | `ff.*` table(s) | Mutability |
   |---|---|---|
   | Define the pilot (protocol, stratification, unit of agreement) | `annotation_tasks` | Mutable (metadata only; not a source of truth for results) |
   | Assign blinded readers to an independence group | `annotation_assignments` | Mutable (`status` progresses `assigned → completed`); `model_output_visible`/`independence_group` are the integrity-critical fields, worth a one-time review before the pilot starts |
   | Each reader's independent judgment | `annotation_records` | **Append-only** (`0003_integrity.sql` — no UPDATE/DELETE, enforced by trigger for every role including the superuser backend DSN) |
   | κ computation | *(not stored — computed on read by `compute_kappa.py`)* | N/A; re-run anytime, always reproducible from `annotation_records` |
   | Disagreement resolution | `adjudications` | **Append-only** |
   | Validated label | `gold_candidates` | **Append-only**; `contamination_model_visible` + `source` are the provenance flags (rule 1 above) |
   | Anything a clinician does in the *production* review UI (not this pilot) | `reviews` | **Append-only**; `model_output_visible` defaults `true` — this is how a stray production review can never accidentally be pooled into a κ read |

4. **Provenance flagging is universal, not pilot-specific.** Every table in this pipeline
   that could conceivably be mistaken for validated ground truth carries an explicit
   boolean or enum saying how it was produced (`model_output_visible`,
   `contamination_model_visible`, `source`). The rule for anyone consuming these tables:
   *if a query doesn't select and check the provenance column, the query is wrong.*

### 5.2 Known gaps (surfaced, not hidden)

- No REST API exists yet for creating `annotation_tasks`/`assignments`/`records`
  (`BUILD_SPEC.md`'s API contract has no `/annotation-*` routes). The pilot is run via
  direct SQL against the DB (§7), the same way `seed_demo.py`/`verify_chain.py` connect —
  adequate for a one-time N≈150–200 pilot, not something to scale to continuous annotation
  without building the missing endpoints + a blinded annotation UI (backend/web work,
  explicitly out of scope for this document).
- `compute_kappa.py` does not assert that the two `annotator_id`s in an independence_group
  are actually different users (§2.4 checklist) — worth a manual spot-check before trusting
  a pilot's results, or a follow-up assertion in the script.
- Correction rate (§3.4) skips `measurement` — no units-aware equality check implemented.
- Time-per-read (§3.5) has no dedicated instrumentation table yet; the proxy is coarse.
- Track-level κ (§2.3) needs the pilot's item_ref convention pinned down (`ff.tracks.id`
  vs. a frame-pair key) before sampling — recommend `tracks.id` for simplicity, revisit if
  the design needs pairwise judgments instead of whole-track judgments.

---

## 6. What we can claim after N readers (honesty table)

| Pilot state | Statistically meaningful? | What we **can** say | What we **cannot** say | Relevance |
|---|---|---|---|---|
| **Today: 0 blinded readers** | — | *"Clinical validation protocol and tooling are built and verified end-to-end (schema, sampling design, kappa computation); the pilot itself has not yet been run."* | Any κ number; "clinician-validated"; "IRR-tested" | Shows diligence the team distinguishes infrastructure-readiness from validation — itself a credibility signal |
| **2 readers, small pilot batch (N < 50)** | κ point estimate only; bootstrap CI will be wide | *"Preliminary pilot κ = X (wide 95% CI, N=Y) — directional, not conclusive"* | "Validated"; any journal-citable IRR; any product marketing claim | Internal go/no-go signal for whether to scale the pilot to full N |
| **2 readers, full N≈150–200 (the planned pilot)** | Per-slot κ with a reasonably tight 95% CI, plus track-linking κ | *"Blinded double-read inter-rater agreement (κ=X, 95% CI [.,.]) on a stratified N=150–200 pilot"* — the exact claim `pre/strategy/PRODUCT_AND_MARKET.md` §7 needs, and the bar `pre/tmc/new_plan/phase_c_clinician_validation_spec.md` §7 sets for JBI/AIM-tier submission | Population-level accuracy; "prospectively validated"; regulatory-grade claims; anything about sites other than the one(s) the readers came from | **This is the fundability unlock** — converts "engineering-curated gold, no κ" (current `pre/tmc/docs/AUDIT_AND_UPGRADE_ROADMAP_2026-07.md` framing) into a real number; also the FindingFrame paper's single highest-impact addition per `pre/tmc/docs/LITERATURE_REVIEW_2022_2026.md` |
| **≥3 readers / multiple independence groups (Fleiss' κ extension)** | Multi-rater reliability; adjudicated majority-vote gold | *"Reproducible across N≥3 independent readers"* — a stronger claim than pairwise κ alone | Still not a prospective or multi-site trial | Strengthens a JAMIA-tier submission; not required for the immediate fundability unlock |
| **200-patient TMC engagement, clinician-adjudicated at scale** | Full validated benchmark, per `PRODUCT_AND_MARKET.md` §7 item 1 | *"200-patient clinician-adjudicated validation at Tata Memorial"* — the full claim | "FDA-cleared"; "regulatory-cleared" (never — see `PRODUCT_AND_MARKET.md` §5) | Unlocks pharma/CRO pilot conversations and the registry-licensing revenue line |

---

## 7. Operational runbook

Everything below was run against the live Supabase project during verification of this
document (region `ap-southeast-1`, same DB `seed_demo.py`/`verify_chain.py` use). As of
today, `ff.annotation_tasks` has **zero rows** — the commands below are the exact path from
that empty state to a scored pilot.

### 7.1 Confirm the tooling works before you have data

```bash
cd pre/findingframe
backend/.venv/bin/python infra/scripts/compute_kappa.py --demo
```

Computes κ on an in-memory synthetic example (a textbook 2×2 confusion matrix, a
perfect-agreement case, and a chance-agreement case) and asserts the arithmetic — proves
the math without touching the DB. All three cases passed when verified for this document
(κ = 0.400 / 1.000 / ≈0.000 exactly as expected).

```bash
backend/.venv/bin/python infra/scripts/compute_kappa.py --list-tasks
backend/.venv/bin/python infra/scripts/compute_kappa.py
```

Both exit 0 and print `No annotation_tasks found ... — no annotations yet.` against the
live, currently-empty DB — verified. This is intentional: the script is safe to run at any
point in the project's life, before or after the pilot.

### 7.2 Create the pilot task

No REST endpoint exists for this yet (§5.2) — create directly via SQL (`psql`, using the
same `FF_DATABASE_URL` as `infra/scripts/migrate.sh`, or via any `psycopg` session):

```sql
insert into ff.annotation_tasks (org_id, protocol_id, name, unit_of_agreement, description)
values (
  '<org_id>',
  'irr_pilot_v1',
  'IRR Pilot v1 — stratified 150-200 frame sample',
  'frame',
  'Blinded double-read pilot; see docs/IRR_PROTOCOL.md'
)
returning id;
```

Repeat with `unit_of_agreement = 'track'` for the separate track-linking judgment set
(§2.3), if running both in the same pilot wave.

### 7.3 Assign blinded readers

```sql
insert into ff.annotation_assignments
  (task_id, org_id, annotator_id, model_output_visible, independence_group, status)
values
  ('<task_id>', '<org_id>', '<rad1_user_id>', false, 'pair_1', 'assigned'),
  ('<task_id>', '<org_id>', '<rad2_user_id>', false, 'pair_1', 'assigned')
returning id, annotator_id;
```

`model_output_visible = false` and a shared `independence_group` are the two fields that
make this a valid blinded pair — see the §2.4 checklist before proceeding.

### 7.4 Collect annotations

Each reader works through their stratified item list (§2.2) blind to the model's output and
to the other reader, and records one `ff.annotation_records` row per item:

```sql
insert into ff.annotation_records (assignment_id, org_id, item_ref, labels)
values (
  '<rad1_assignment_id>', '<org_id>', '<frame_id>',
  '{"finding_type":"liver_metastasis","anatomy":"liver","laterality":"right","assertion":"present","temporal_change":"stable"}'::jsonb
);
```

(In production this would come from a blinded annotation UI — out of scope for this
document, which does not touch `backend/`/`web/`. For a one-time pilot at this scale,
direct SQL insertion from a reviewer's structured export — e.g. a spreadsheet with one row
per item — is an adequate, auditable substitute; the append-only trigger on
`annotation_records` protects it identically either way.)

### 7.5 Score it

```bash
backend/.venv/bin/python infra/scripts/compute_kappa.py --task-id <task_id>
```

Prints, per `independence_group`: reader record counts, a coverage warning for any items
only one reader annotated, per-slot κ (+ 95% CI + Landis-Koch interpretation), the
`full_frame` composite κ, and each reader's correction rate against the model's original
`ff.frames` values (§3.4) — verified end-to-end against the live DB with a synthetic 8-item
pair inserted and scored inside an uncommitted transaction, then rolled back (so the
verification left **zero** rows behind in this append-only table): observed 87.5%
finding_type agreement (κ=0.840), 100% anatomy/laterality agreement (κ=1.000), 87.5%
assertion agreement (κ=0.742), 75% full-frame composite agreement (κ=0.709) — and,
separately, a real-`ff.frames`-backed check confirmed the correction-rate join
(one synthetic "reader correction" of a real frame's `assertion` value was detected
correctly as 1/2 = 50%).

### 7.6 Adjudicate and promote to gold

For each `item_ref` the printed table shows disagreement on (or, at κ≥0.60, for every
item — §4): a third senior reader records `ff.adjudications`, then eligible items are
promoted to `ff.gold_candidates` with `source='adjudication'`,
`contamination_model_visible=false`. Re-run `compute_kappa.py --task-id <task_id>` any time
— it is idempotent and read-only, safe to re-run as more records arrive mid-pilot.

### 7.7 Report

Feed the printed κ + CI table directly into: the paper's IAA subsection (matches
`pre/tmc/docs/ANNOTATION_GUIDELINES.md` Appendix A's Table 3 shape), the diligence data room (§6's
honesty table sets the exact claim boundary), and `pre/strategy/PRODUCT_AND_MARKET.md`'s
critical-path item 1.
