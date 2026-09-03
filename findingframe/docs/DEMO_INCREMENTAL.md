# The incremental demo — proposal

Status: proposal, nothing built yet. Written 2026-08-01.

The current flagship demo (`DEMO_MONEY_PATIENT.md`) shows one thing very well: a human link
decision flips a wrong PD to a correct PR. It is a *static* story. Four reports go in, one
answer comes out.

This proposal adds the story we cannot currently tell: **what happens on the day the next scan
lands.** A patient already carries ten reviewed and signed reports. The eleventh arrives. The
system reads one report, folds it into the record it already has, and every downstream answer —
tracks, RECIST, the digest — moves. The clinician is asked to look at what changed, not at
everything again.

---

## 1. The two acts

**Act one — the built record.** Patient with ten longitudinal CT reports. Frames extracted,
tracks linked, and then a full clinician pass: every track confirmed or merged, the quarantine
queue cleared, target lesions chosen, RECIST computed, the whole thing signed. This is the
"before" state, and it has to be real work, not a seeded fiction — the point of act two is that
this work is *not repeated*.

**Act two — the eleventh report.** One report is uploaded. Then:

| What | Cost |
|---|---|
| LLM extraction | 1 report read, not 11 |
| Linking | 1 report's frames folded into carried state |
| Human review | only genuinely new or changed items |
| RECIST + digest | recomputed from stored tracks; no report text involved |

The screen to build is a **"what changed"** view: N tracks carried forward untouched, M tracks
that gained an event, K new tracks needing a decision, and the response category before and
after.

### What report 11 should say

Make it a real clinical event, not a footnote. After a sustained partial response, the eleventh
scan shows regrowth that crosses the +20%-over-nadir threshold, so the call becomes progressive
disease.

This is the right choice for a specific technical reason: **the nadir lives in the carried
state.** It was set at an earlier timepoint. A demo where report 11 only extends a shrinking
series would not prove the incremental state is complete. A demo where the correct answer depends
on a value computed six reports ago does prove it.

---

## 2. What happens today

Adding a report today re-runs everything.

`create_run` (`backend/app/services/runs.py:44`) collects **every** current report version for the
patient, hashes a manifest over all of them, and queues a run. The worker calls `process_patient`
(`backend/app/engine/adapter.py`), which hands the engine all eleven reports and links from
scratch. Frames, tracks and track events are written as fresh rows under a new `run_id`.

The extraction cache spares the LLM cost on reports one to ten, but that is a side effect of a
text-keyed cache, not a designed property, and every track gets a new row and a new identity.
Worse, the reviewer's ten reports of work sits on the *old* run. `PRE_UPDATE_PLAN_2026-07-30.md`
already flags this as P0-4: a new successful run silently replaces a reviewer's signed-off view.

So the demo does not exist yet. But the architecture is unusually ready for it.

---

## 3. Why incremental here is exact, not approximate

This matters more than it might seem. An audit-grade product cannot ship a fast path that gives
*nearly* the same answer as the slow path. The claim has to be identity.

Two facts make it identity.

**The linker is already a fold.** `link_frame_events` (`tmc/fact_graph/frame_linker.py:371`)
sorts events by `(report_date, source_report_id, frame_index)` and folds them one at a time into
two accumulators, `track_events` and `track_states`. The matching function
`_compatible_track_keys` (`:252`) reads only `track_states` — no lookahead, no second pass. What
is computed at the end (`tracks`, `false_split_candidates`, the summary counters) is a pure
function of the accumulated state.

Seed that fold with the state after report ten, feed it only report eleven's events, and the
output is byte-identical to folding all eleven, because a later report sorts strictly after
everything already folded in.

`tmc/tests/test_linker_determinism.py` already establishes the surrounding property — the linker
is idempotent and order-insensitive, with one documented sort-key tie that the real pipeline
cannot produce. An equivalence test for the incremental path belongs beside it.

**Extraction is already per-report.** `FindingFramePatientProcessor.process_patient`
(`tmc/pipeline/finding_frame_processor.py:212`) is a loop calling `self.extractor.extract` once
per report with no cross-report state (`:307`), followed by exactly one call to
`frames_to_frame_fact_graph` over the accumulated frames (`:469`). Nothing between the two stages
is stateful.

**And the human layer is keyed on stable strings.** Link decisions reference `track_key`
(`finding_type|anatomy|laterality`), and RECIST target selections reference
`confirmed_track_key` (`backend/app/services/linking.py:94`, `recist.py:96`). These strings are
stable across runs, so a reviewer's decisions can be replayed onto new state by key rather than
by row identity. This is the fact that makes carry-forward possible at all.

**Downstream is already stateless.** `compute_recist` (`recist.py:211`) and `build_digest`
(`digest.py:40`) read tracks and events from the database, not report text. Once the new track
events land, they need no change.

---

## 4. Changes needed in tmc

Small and additive. Every new parameter defaults to the current behaviour, so nothing existing
moves.

**`fact_graph/frame_linker.py`** — the substantive change.

- `link_frame_events(events, prior_state=None)`. When `prior_state` is given, seed `track_events`,
  `track_states`, `unresolved_queue` and the `decisions` counter from it instead of starting
  empty.
- Return the carried state in the result (call it `linker_state`) so a caller can persist it.
- The state must serialise to plain JSON. `track_states` already is; `track_events` holds the
  full event dicts, which is what a resumed fold needs for `_track_from_events` and
  `_false_split_candidates`.
- One piece of bookkeeping to get right: `queue_id` in the unresolved queue is numbered
  `unresolved_{n}` off queue length, and `original_track_count` counts distinct incoming
  `track_key`s. Both need to continue from the carried values rather than restart, or the
  incremental output will differ from the batch output in those two fields only.

**`fact_graph/frame_adapter.py`** — thread it through. `frames_to_frame_fact_graph` gains a
`prior_state` argument and returns `linker_state` in the artifact.

**`pipeline/finding_frame_processor.py`** — `process_patient` gains `prior_state` and passes it
down. Optionally accept a reports frame containing only the new reports.

**Tests** — one equivalence test next to `test_linker_determinism.py`: for a multi-report event
set, folding all at once and folding incrementally report by report produce identical results,
over the existing fixtures. This is the test that lets us say "identical" on stage.

Nothing in the research pipeline, evaluation harness or paper artifacts changes.

---

## 5. Changes needed in findingframe

**Schema (new migration).**

- `extraction_runs.parent_run_id uuid references ff.extraction_runs(id)`
- `extraction_runs.run_kind text` — `full` or `incremental`
- `extraction_runs.delta_manifest jsonb` — the reports actually read this run
- The existing `checkpoint jsonb` column (`0001_init.sql:198`, documented as "per-report resume
  state", currently near-unused) is the natural home for the serialised linker state.

**Provenance must not weaken.** `report_manifest` on an incremental run still describes all
eleven reports, so the run remains independently reproducible from its manifest alone.
`delta_manifest` records what was newly read. An auditor can still recompute the whole thing;
they simply also learn what the fast path did. Say this plainly in the demo — the objection
"you cut a corner on the audit trail" is the one a pharma reviewer will raise.

**Run creation.** `create_run` grows an incremental path: given a patient with a succeeded run
whose manifest is a prefix of the current report set, create a child run over the delta.

**Worker.** For an incremental run: load the parent's linker state and extract only the delta
reports, then fold. Materialise the result by copying the parent's frames, tracks and track
events forward and inserting the new rows, so every existing query (digest, confirmed tracks,
RECIST, audit packet) works unchanged. The row copy is cheap; the LLM call and the relink are the
real costs and those are what shrink.

**Carry-forward.** Replay the parent run's link decisions, target selections and reviews onto the
child by `track_key`, recording provenance back to the parent decision. A decision must be marked
as carried, not forged as new — the signature chain has to show a human decided it once, and
when. Anything whose key no longer exists, or whose track gained an event that changes its
character, goes back to the reviewer.

**A diff endpoint.** `GET /runs/{id}/delta` returning: carried tracks, tracks that gained events,
new tracks, new gate-failed frames, and the RECIST before/after. This is what act two renders.

---

## 6. Changes needed in web

The UI is in better shape for this than expected.

- **A delta view** on the review workbench: the "what changed" screen above. New component.
- **Wire the live update.** `createLinkDecision` invalidates `["link-decisions"]` and
  `["confirmed-tracks"]` but **not** `["recist-contrast", runId]`
  (`components/LinkConfirmation.tsx:41-45`). Confirming a merge therefore does not refresh the
  contrast card today. The demo depends on watching the call change, so this wire has to be added.
- **Quarantine actions.** `QuarantineZone` is display-only — there is no verify or reject action
  on a quarantined frame. Act one requires clearing the queue, so this needs wiring.
- **`WorkflowStepper`** already models Upload → Extract → Review → Confirm links → RECIST →
  Sign-off but is only mounted on the patient page. Act two is exactly a second pass through that
  stepper, so put it on the review and RECIST pages too.
- `RecistChart` already draws the PR and PD threshold lines, so the nadir-crossing moment renders
  with no new chart work.

**Mock mode carries the demo.** `lib/mock.ts` (606 lines) already implements every endpoint the
UI uses against an in-memory store in `sessionStorage`, with a real deterministic RECIST
computation. Building the incremental flow in mock mode first gives a shareable, offline,
data-safe demo and pins the API shape before any backend work starts.

---

## 7. The data

Build it synthetic. The real MIMIC subjects are available (`10511269` has 15 reports, `10000935`
has 37, under `tmc/outputs/paired_v1/`), but the PhysioNet DUA already restricts the deployment to
screen-share only, and an eleven-report clinician walkthrough is precisely the thing worth handing
someone a link to.

Follow the existing pattern in `infra/scripts/money_patient_reports.py`: hand-authored reports,
labelled synthetic in the text itself, extracted with the real engine, frozen to
`infra/seed_data/` so re-seeding needs no LLM key.

Eleven timepoints, two or three measurable targets, a sustained partial response, a nadir set
around timepoint six, and regrowth at timepoint eleven crossing +20% over that nadir. Plus the
usual realism: routine negatives, one genuinely gate-uncertain finding, and at least one new
finding at timepoint eleven that needs a fresh human decision.

---

## 8. Order of work

1. Author the eleven synthetic reports and verify the intended RECIST path with the real engine
   and the real `classify`, as `build_money_patient.py` does today.
2. The tmc linker change plus its equivalence test. This is the load-bearing claim; prove it
   before building anything on top.
3. Mock-mode incremental flow in the web app — the full demo, offline, to settle the API shape.
4. Backend: migration, incremental run creation, worker fold, carry-forward, delta endpoint.
5. Point the web app at live and run act one for real, including the clinician pass.

Steps 1 and 2 are independent and can run together.

---

## 9. The claim to make on stage

Not "we cached it". The claim is:

> One report in. One report read. The record it joins was already reviewed and signed, and that
> review stands — we did not ask the clinician to do it again. The response call changed, and it
> changed because of a nadir measured six scans ago that the system still holds. The answer is
> identical to reprocessing all eleven reports, and there is a test that proves it.
