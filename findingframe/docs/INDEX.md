# FindingFrame docs index

All paths relative to `findingframe/`. Status words are deliberate:
**live** = built and verified; **proposal** = not built.

| Doc | Status in one line |
|---|---|
| `docs/BUILD_SPEC.md` | **Live contract** — R6 vertical-slice API + worker + data model (incremental endpoints appended post-R6; connectivity § still assumes the old superuser DSN — production runs least-privilege `ff_app`). |
| `docs/RUNBOOK.md` | **Live ops** — local dev, migrations, seeds, compose (local + tyrone), demo walkthrough. |
| `docs/DEMO_MONEY_PATIENT.md` | **Live demo script** — flagship synthetic `DEMO-NSCLC-01` (naive PD → human-confirmed PR); artifact frozen at engine `e04d3c6`. |
| `docs/HANDOFF_INCREMENTAL_DEMO.md` | **Live build handoff** — incremental runs + carry-forward ("dynamicity" demo, `DEMO-NSCLC-LONG-01`); ⚠ §0-vs-tail status contradiction unresolved per NOTE 2026-09-03, tail authoritative. |
| `docs/DEMO_INCREMENTAL.md` | **Proposal only, partly superseded** — pre-build design; three claims voided by §3 of the handoff above (no tmc changes, re-run-the-fold, trigger wording). |
| `docs/IRR_PROTOCOL.md` | **Live protocol, unexecuted pilot** — blinded 2-reader Cohen's-κ design + `compute_kappa.py` verified end-to-end; `ff.annotation_tasks` has 0 rows. |

Product status: `HANDOFF.md`. Working conventions: `AGENTS.md`.
Repo-level context: `pre/README.md`, `pre/docs/README.md`, `pre/PRE_UPDATE_PLAN_2026-07-30.md`.
