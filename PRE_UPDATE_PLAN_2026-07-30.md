# Updating `pre` after the tmc audit — plan and working ledger

Written 2026-07-30. Ledger: each item gets notes as it lands. Items get added and removed as
the work teaches us things.

## Correction, first

Yesterday I told you the deployed product carries the negation bug, and that "not enlarged"
could be recorded as increased for a patient. **That was wrong.** I checked that the *function*
differed between the two engine copies and did not check whether the function is on the
product's path. It is not. Evidence in §1.4.

The engine copies really are stale, and the update really is needed — but for a different
reason, and the top item is a silent cache, not a clinical defect.

---

## 1. Verified state

### 1.1 There are four live copies of the engine, not two

| # | Copy | Pinned at | Role |
|---|------|-----------|------|
| 1 | `~/project/tmc` | `5edaa99`, clean, pushed | source of truth |
| 2 | `pre/tmc` | `e04d3c6` + dirty | local-dev engine (`settings.engine_path`) |
| 3 | `pre/findingframe/infra/engine_vendor/` | `VENDOR_SHA=e04d3c6d9c…` | **what Docker ships** |
| 4 | `tyrone:~/findingframe/` | `VENDOR_SHA=e04d3c6d9c…` | **what users hit** |

Plus `pre/findingframe_deploy_snapshot/` (17 Jul, carries secrets, gitignored) — out of scope,
but it exists and it is stale too.

### 1.2 The deployed path is not `../../tmc`

I said the backend "executes code from `pre/tmc` at runtime". True for local dev only.
`infra/docker/Dockerfile.backend:28` and `Dockerfile.worker:30` both `COPY infra/engine_vendor
./engine`, and `docker-compose.yml:26,38` set `FF_ENGINE_PATH=/app/engine`.
`config.py:56`'s `PRE_DIR / "tmc"` is the local default that the container overrides.

So the propagation tool is `infra/scripts/vendor_engine.sh`, not `git pull`.

### 1.3 `pre/tmc` sits on an abandoned history line

`e04d3c6` is **not an ancestor of `origin/main`**. It is reachable from branch `Frames` and
`remotes/origin/SIRS`. Its main-line twin is `cc03519`, and `git diff e04d3c6 cc03519` is
**empty** — the rewrite preserved content exactly. Counts: 26 behind, 13 ahead.

The dirty tree is stale, not unique work:

- `CLAUDE.md`, `finding_frame_extractor.py`, `finding_frame_schema.py` — byte-identical to upstream.
- `finding_type_taxonomy.py` — 0 lines only in pre; upstream is a strict superset.
- `AGENTS.md` — 9 unique lines, all superseded numbers (0.634, 0.605, the old dev-8 table).
- All 5 untracked paths already exist upstream.

So a hard reset to `origin/main` loses nothing. A `git pull` would try to merge two lines of
duplicated history and make a mess.

### 1.4 The negation bug is dead code in the product

- `_is_negated_term` is called only inside `normalize_temporal_change_for_scoring`
  (`frame_slot_normalizer.py:547,549,552`). The one other mention, line 662, is the
  `RULE_LOGIC_FUNCTIONS` provenance registry — a list to hash, not a call.
- That function has exactly two callers: `extraction/temporal_change_module.py:167` and
  `evaluation/frame_metrics.py:262` — the scorer.
- `grep` across `backend/` and `worker/` for `normalize_temporal_change_for_scoring`,
  `temporal_change_module`, `_is_negated_term`: **no hits**.
- `evaluation/` is excluded from the vendor by design. `temporal_change_module.py` is vendored
  but nothing vendored imports it — the vendor script's own docstring already says it degrades
  to dead code.
- `fact_graph/frame_linker.py` imports only `normalize_anatomy_for_linking`, which does not
  touch negation.

The product takes `temporal_change` as the raw slot from the extractor. The fix was a scorer
fix. It belongs in the paper, and it did.

**Independently reviewed and upheld** (Fable, 2026-07-30), with two findings stronger than mine:

- The product's RECIST (`backend/app/services/recist.py`) classifies from measurement mm values
  only. `temporal_change` never feeds classification at all.
- `_coerce_choice` (`finding_frame_schema.py:131-157`) coerces the raw slot into a closed enum by
  exact match, so "not enlarged" falls to the default `not_stated` — never `increased`. Downstream
  consumers (`worker/persist.py:59`, `track_graph.py:237-262`) use exact set membership on that
  enum, not substring matching.

So there is no negation-vulnerable path on the product side, and no second instance of the bug
hiding behind the raw slot. The reviewer also confirmed the product's only subprocess calls are
`git rev-parse` / `git status` (`adapter.py:126,136`) — it never shells out to engine scripts.

### 1.5 What genuinely changed on the shipped surface

`git diff --stat e04d3c6 5edaa99` restricted to the eleven vendored dirs:

```
extraction/finding_type_taxonomy.py   | 790 ++++++   <- biggest, changes what gets extracted
extraction/finding_frame_extractor.py | 173 ++
extraction/rule_layer_provenance.py   | 152 ++       <- new file
extraction/frame_slot_normalizer.py   |  94 ++
extraction/temporal_change_module.py  |  85 ++       <- dead code in the product
extraction/finding_frame_schema.py    |  41 ++
pipeline/finding_frame_processor.py   |   9 +
fact_graph/frame_adapter.py           |   6 +
8 files changed, 1325 insertions(+), 25 deletions(-)
```

**Correction, later on 2026-07-30.** I wrote that "+790 taxonomy lines change what the extractor
recognises". Wrong — and it is the third time I inferred behaviour from diff size. Measured rather
than read, the oncology pipeline is very nearly untouched:

| Change | Effect on `domain="radiology"` |
|--------|-------------------------------|
| taxonomy +790 | **none.** A new CXR domain plus provenance registries. Loaded both versions side by side: `taxonomy_prompt_block()` — the literal text that goes into the LLM prompt — and `all_finding_types()` identical; `TAXONOMY_ALIASES`, `ANATOMY_ALIASES`, `EVIDENCE_SUPPORT_TERMS_BY_TYPE` identical; all 20 type definitions field-wise identical. Only 2 lines were removed from the entire file, both in echo helpers. |
| extractor +173 | **none.** A hydropneumothorax de-duplicator. `hydropneumothorax` is not an oncology type, so `hydro_keys` is empty and it early-returns. |
| rule_layer_provenance +152 (new) | **additive metadata.** Adds a `rule_layer_provenance` fingerprint to the artifact. Changes no extraction or linking output, and is a real gain for an audit-grade product: a reader can now tell which rule-layer version produced the tracks. |
| normalizer +94 | **none.** The negation fix, scorer-only (§1.4). `normalize_anatomy_for_linking` and `normalize_anatomy_for_scoring` are byte-identical across the two SHAs. |
| temporal_change_module +85 | **none.** Dead code in the product. |
| schema +41 | **the only real change.** `_ABSENT_ASSERTION_SUPPORT_TERMS_BY_TYPE["cardiomegaly"]` went 7 → 10 terms, a strict superset adding three "within normal limits" phrasings. A `cardiomegaly` frame asserted **absent** on evidence like "cardiomediastinal silhouette is within normal limits" now counts as properly supported. One finding type, one assertion value, three phrasings. |
| processor +9, frame_adapter +6 | wiring the provenance field through. |

So the engine *content* update is close to a no-op for oncology output. What this pass actually
delivered was the provenance fix, the cache fix, the vendor guard and the docs. It also strengthens
the "do not re-extract" call: re-running would produce near-identical frames.

### 1.6 The cache will not notice any of it

`FindingFrameExtractor` cache key (`finding_frame_extractor.py:307-313`):

```
CACHE_VERSION : namespace : sha256(report_text)[:16] : chart_date : study_type : source_report_id
CACHE_VERSION = f"{FINDING_FRAME_SCHEMA_VERSION}:{_PROMPT_VERSION}"
```

Across `e04d3c6` and `5edaa99` both constants are **unchanged**:
`finding_frame_v1` and `finding_frame_prompt_v7_generalization_contract`.

No engine SHA participates. So every already-cached report keeps returning the old engine's
output after the update. Existing caches: `pre/findingframe/outputs/cache/
finding_frame_extraction_cache.json` and `/tmp/ff_engine_cache/` (adapter.py:190-193).

**Left alone, this update is a silent no-op for every report already processed.**

---

## 2. Problems

| ID | Problem | Severity |
|----|---------|----------|
| P0-1 | Cache keys ignore the engine version, so the update is a no-op for cached reports (§1.6) | P0 |
| P0-2 | Recorded provenance is `e04d3c6+dirty` — a SHA unreachable from `main`. An audit-grade product cannot resolve its own engine version (§1.3) | P0 |
| P0-3 | The +1325-line shipped delta has never been reviewed for product effect. It was written for the paper (§1.5) | P0 |
| P1-1 | Tyrone is file-copied, not a checkout, and no script pushes an update to it (§1.1) | P1 |
| P1-2 | Stale and mislabelled figures in hand-written docs — see §2.1, larger than the four I first found | P1 |
| P1-3 | "Audit-grade" guarantees do not say the anatomy criterion cannot penalise wrong anatomy on 41.1% of frames | P1 |
| P0-4 | A new successful run silently replaces what a reviewer already signed off (§2.2) | P0 |
| P0-5 | Patient 10000935's stored manifest misdescribes its own provenance (§2.3) | P0 |
| P1-4 | `vendor_engine.sh:165` pins `VENDOR_SHA` with bare `git rev-parse HEAD` — no dirty check, so the vendoring path is less honest than the live adapter, which does append `+dirty` | P1 |
| P2-1 | Nothing checks that `VENDOR_SHA` is an ancestor of `origin/main` and clean | P2 |

### 2.2 P0-4: the engine update can quietly move ground under a reviewer

`web/app/(app)/patients/[id]/signoff/page.tsx:38-39` resolves the run to display as
`runs.data?.find(r => r.status === "succeeded")` — always the latest succeeded run. Link decisions,
target-lesion picks and signoffs are scoped to a `run_id` (`routers/runs.py:86-114,118-139`) and do
not carry forward.

`runs.create_run` dedupes on `manifest_hash` (`services/runs.py:69`), and `manifest_hash` includes
`engine_git_sha` (`adapter.py:172-181`). So the moment the engine SHA changes, any create-run call
**cannot** hit the idempotent path and must enqueue a genuinely new run. When it succeeds, the UI
switches to it, and a reviewer who had confirmed tracks for that patient reopens it to unreviewed
data from a different engine, with nothing saying anything changed. `HANDOFF.md:112` confirms
multiple runs per environment already exist, so this is not hypothetical.

This is the most user-visible risk in the whole update, and neither my plan nor my earlier answer
named it.

### 2.3 P0-5: the flagship demo patient's manifest is not true

`infra/scripts/seed_demo.py:61-62,451-453` hardcodes `model_provider="openrouter"` and
`model_id="openai/gpt-5.5"` into 10000935's `extraction_runs` row, but those frames came from a
precomputed tmc evaluation packet, not a live call (`seed_demo.py:29-31,142-144`, which says the
point was to be demoable without an LLM key). So the one run this patient has carries a manifest
describing a call that never happened. Anything treating `manifest_hash` / `engine_git_sha` as
ground truth is trusting a fabricated field — in the product whose selling point is provenance.

Withdrawn: the negation claim (§1.4). Kept in this ledger as a record, not deleted.

### 2.0 P0-2 is worse than written above

Provenance is not merely stale — it is **decoupled from the shipped code**:

- `infra/engine_vendor/VENDOR_SHA` is written by the vendor script and **read by nothing**. No hit
  for `VENDOR_SHA` anywhere in `backend/` or `worker/`.
- `adapter.py:109` takes `settings.engine_git_sha or self._resolve_git_sha(engine_path)`. In the
  container `engine_path=/app/engine`, which is not a git repo, so `_resolve_git_sha` returns "".
- So production provenance comes from the env var — and on tyrone
  `infra/docker-compose.tyrone.yml:30,45` **hardcodes** `FF_ENGINE_GIT_SHA:
  e04d3c6d9c7938b32b0b3be1b9a37f9869d024c2`.

Consequences. Someone can update the vendored engine and the product will keep reporting the old
SHA, with every manifest, export and signoff carrying it. The recent "verified live: correct engine
SHA" check passed because it compared a hardcoded constant against the stale value it was expected
to have — it validated a constant against itself.

Worse: **`docker-compose.tyrone.yml` is not in the repo.** It is not gitignored, just never
committed. The production deployment config exists only on the server.

### 2.1 Figure inventory (independent pass)

Confirmed stale: `PRODUCT_AND_MARKET.md:29` Full-Frame 0.634 → **0.639**; `:32` backend spread
0.027 → **0.030**; `:33`, `:89`, `:101` track-linking 0.34 → **0.382**;
`PRODUCT_BUILD_PLAN.md:30` 0.338 → **0.382**.

Mislabelled, which is worse than stale because the number was never measured:

- `PRODUCT_AND_MARKET.md:29` "~92% per-slot accuracy" — derived as `0.598^(1/6) = 0.918`, which
  assumes six independent slot draws. Full-Frame F1 is a joint match on one frame and makes no such
  assumption. Presented under a "Validated capability" header as if measured. The directly measured
  per-slot figures (~0.962 dev-8, ~0.924 ext-20) are not quoted.
- `PRODUCT_AND_MARKET.md:30` "Evidence-anchoring ~97%" — that is the **chest-X-ray external
  transfer** figure (96.3–96.6%), not a property of the 30-patient cohort, and it sits next to a
  mention of the 208-question QA benchmark whose own grounding rate is a third number, 0.952.
  Three distinct figures collapsed into one.
- `PRODUCT_BUILD_PLAN.md:17` "LLM call at T=0" — the product runs `openrouter` /
  `openai/gpt-5.5`, and `OpenRouterLLMClient` (`utils/llm.py:260-283`) sets
  `payload["temperature"]` unconditionally, with no guard like the OpenAI client's
  (`:176-178`). Whether that endpoint honours, ignores or rejects it is established by no artifact.
  Same claim shape tmc had to withdraw, on a different code path. Unverified, not yet false.

Also found, and it is a defect in **tmc**, not pre: `tmc/AGENTS.md:38-40` says "over the 21 finding
types the Type F1 is 0.816", but 0.816 is the **20-class** average with the catch-all excluded; the
21-class figure is 0.777. The doc written to warn about that trap mislabels it. The paper itself
(`main.tex:72`, `table_per_class_support.tex`) gets it right.

My earlier claim that `findingframe/docs/IRR_PROTOCOL.md:277` quotes 0.338 was not reproduced by
the independent pass, which found only correctly-disclosed synthetic κ at `:469-478`. Recheck
before editing.

One caution for whoever reads that pass: it also concluded the deployed engine was "running the
exact bug tmc withdrew" and would misread "not enlarged" as growth. It verified the code diff, which
is real, and then inferred user impact from it — the same one-level-too-shallow error I made. §1.4
stands.

---

## 3. Plan

Ordered by dependency. Each item states its gate — how we know it worked.

| # | Item | Gate |
|---|------|------|
| 1 | Correct the memory file and the record on the negation claim | memory file says scorer-only, with the grep evidence |
| 2 | Back up `pre/tmc`'s abandoned line + dirty tree to a local branch, then `reset --hard origin/main` | `git rev-parse HEAD` = `5edaa99`; backup branch resolves; `git status` clean |
| 3 | Review the +1325-line shipped delta and classify every change: affects the product / scorer-only / inert | written classification, per file, with the call path for each "affects" |
| 4 | Re-vendor: `infra/scripts/vendor_engine.sh`, then `--verify-only` | `VENDOR_SHA` = `5edaa99…`; vendored normalizer md5 = upstream's |
| 5 | Run the product's own tests against the new engine | backend tests pass; any live extraction check uses **`DEMO-NSCLC-01`**, never 10000935 |
| 6 | Fix P0-1: make the engine version part of the cache key, or bump `CACHE_VERSION` | a cached report re-extracts after the engine changes; test proves it |
| 7 | Fix P0-2: make provenance refuse to report a SHA that is not an ancestor of `origin/main` | adapter flags unreachable SHAs; test covers it |
| 8 | Fix the four stale figures (P1-2) and add the anatomy-criterion disclosure (P1-3) | numbers match the current canonical set; disclosure names the 41.1% |
| 9 | Add the P2-1 guard | check fails on a dirty or non-ancestor vendor |
| 10 | **Stop.** Present the tyrone deploy for your go-ahead | not started without you |

Item 10 is deliberate. Rebuilding and restarting the live stack is outward-facing and I am not
doing it on my own judgement. Everything before it is local and reversible.

---

## 4. Progress log

**Item 1 — done.** Memory file `project-pre-engine-staleness` rewritten: the negation claim is
withdrawn and recorded as a correction rather than deleted, since the mistake is the reusable
lesson ("the code differs between copies" is not "the behaviour differs for users" — trace the call
path before assigning severity). Index line in `MEMORY.md` updated too, because its old hook
asserted the withdrawn claim. §1.4 above now carries the independent review.

**Item 2 — backups done, reset not yet run.** Non-destructive, working tree untouched:
- branch `pre-tmc-abandoned-2026-07-30` → `e04d3c6` (the abandoned line)
- tag `pre-tmc-dirty-2026-07-30` → `ac3ed24` (the dirty tree, captured via `git stash create`)

**Item 2 — reset done.** `pre/tmc` now at `5edaa99`, fully clean (the 901 previously-untracked
files are tracked at this commit, so the adapter reports a bare SHA with no `+dirty`).

Before the reset I compared every untracked file against upstream: 901 files, 899 byte-identical,
**2 differing** — `external_validation.html` and `paper/tables/table_external_validation.tex`, both
cases where upstream is the *better* version (the `.tex` gained its HAND-MAINTAINED header and the
expanded disclosure caption; the html still carried the stale Full-Frame 0.634). Both copied to
the scratchpad at `pre_tmc_untracked_backup/` anyway. Nothing unique was lost.

Two corrections to my own §1.3 wording, from the independent review:
- I wrote that the modified files were "identical to upstream or strict subsets". True for the five
  I checked; **not** true for `AGENTS.md` and the `paper/*` files, which differ in both directions.
  The reviewer read them line by line and confirmed every difference is superseded material (an old
  paper title, pre-correction baseline numbers, a `references.bib` duplicate upstream removed). No
  work lost, but my phrasing overreached.
- I called `pre/tmc` the "local-dev engine". It is also the **default `ENGINE_SRC` for
  `vendor_engine.sh`** (`:51-52`) and is imported by `seed_demo.py:51,142-144`. It is the source of
  what Docker ships, not a convenience checkout.

**Item 4 — done.** Re-vendored. `VENDOR_SHA` now `5edaa997…`, verified **reachable from
`origin/main`** (checked inside the engine repo — a tmc SHA does not resolve inside `pre`, which
made my first attempt at this check fail spuriously). Vendored `frame_slot_normalizer.py`,
`finding_type_taxonomy.py` and `finding_frame_extractor.py` all md5-match upstream. Vendor script's
own checks pass: no irr/simulate files, no `.env`, no excluded dirs, import smoke test clean.

**Item 5 — test half done.** `71 passed, 1 skipped`. The gate's other half was **rewritten**: it
said "a real extraction on demo patient 10000935", and 10000935 is **real MIMIC, 37 reports,
DUA-restricted** (`HANDOFF.md:122`) — only `DEMO-NSCLC-01` is synthetic (`:123`). Because
`manifest_hash` includes `engine_git_sha`, a create-run for that patient after an engine change
cannot dedupe and *must* enqueue a live run, sending all 37 real reports to OpenRouter
(`backend/.env:16-17`, currently `deepseek/deepseek-v4-pro`). I ran only the test suite, so nothing
was sent. Any live check uses the synthetic patient.

**Item 8 — done.** Four docs edited. Every replacement traced to a tmc artifact, not copied from
another doc. Spot-checked the key figures myself against `paper/sections/results.tex`: all-30
full-frame 0.639 ✓, QA hallucination 0.000 / grounding 0.952 ✓, and both per-slot means reproduce
exactly (dev-8 0.9624, ext-20 0.9240).

Corrected values: Full-Frame 0.634 → **0.639**; backend spread 0.027 → **0.030**; track-linking
0.34 / 0.338 → **0.382**, now with the regime named at every site and the permissive 0.741 stated
beside it as non-interchangeable. Two mislabels rewritten: the `0.598^(1/6)` "per-slot accuracy"
replaced with a real mean of measured accuracies, and "evidence-anchoring ~97%" split back into the
QA benchmark's own 95.2% and the separate chest-X-ray transfer figure. "LLM call at T=0" now says
what is configured and marks the effect unverified. The §2.1 disclosure landed as a
"Reading these figures" note naming patient-macro aggregation and the 41.1% anatomy collapse.

Two things I fixed on top, both instances of the house failure mode the pass did not catch:
the per-slot bullet led with **dev-8 0.962** — the cohort prompts and rules were tuned on, which the
paper itself says "should be read as a measure of fit" — and that average folds in a temporal-change
accuracy of 1.000 that the paper attributes to the deterministic normaliser re-reading evidence at
scoring time, not to the model. The held-out 0.924 now leads, with both caveats stated.

Resolved: `IRR_PROTOCOL.md:277` is a verbatim quotation of a source file inside `pre/tmc`, not an
assertion the doc makes, so it was correctly left alone — my original claim about that line was
wrong. `PRODUCT_AND_MARKET.md:101` is a forward-looking target, not a stale measurement. One extra
stale figure found and fixed at `IRR_PROTOCOL.md:83`.

Still open, and it is a **tmc** defect: `tmc/AGENTS.md:38-40` says "over the 21 finding types the
Type F1 is 0.816", but 0.816 is the 20-class average with the catch-all excluded; 21-class is 0.777.
The doc written to warn about that trap gets it wrong. The paper is correct.

**Ordering changed on review.** The original sequence re-vendored and tested (4, 5) before fixing
provenance and the cache (6, 7) — which opens exactly the window where the database can hold two
inconsistent "current" views of a patient. Since no run has been created, the window is still shut.
Items 6, 7 and 9 are in flight now, and **no run gets created until they land.**

**Items 6, 7, 9 — done.** `82 passed, 1 skipped` (was 71/1).

The cache diagnosis in §1.6 was right about the bug and wrong about its location.
`extract_report()` has **no production caller** — only tests. The worker's real path is
`worker/main.py:131` → `process_patient()`, which built `FindingFramePatientProcessor` with no
`extractor=` override, so the engine's own default took over: `./outputs/cache/…`, cwd-relative and
never touching the temp dir at all. Both call sites now share `_build_extractor()`, cached under
`ff_engine_cache/<sha>/`. An unresolved SHA disables caching rather than sharing an "unknown"
bucket, which would recreate the bug between two engine states we cannot distinguish.

Provenance precedence was **inverted** — resolve from shipped code first, env var last. Without
that, tyrone's hardcoded `FF_ENGINE_GIT_SHA` would have won forever and the whole update would have
stayed invisible. `VENDOR_SHA` is validated against `^[0-9a-f]{7,40}$` so an empty file, or the
literal `unknown` the vendor script writes on its own failure, cannot pass as resolved.

The vendor guard rejects a dirty source or a SHA unreachable from the source repo's `origin/main`,
with `--allow-untraceable` for deliberate exceptions. Verified adversarially in a scratch repo,
including a simulated history rewrite reproducing the real `e04d3c6`/`Frames` case.

One defect I found in the guard's own verification: the import smoke test writes `__pycache__` back
into the vendored tree *after* rsync excluded it — 9 dirs, 46 `.pyc` files. Docker `COPY`s the
directory wholesale, so the image shipped macOS bytecode and the tree stopped being byte-reproducible
from its `VENDOR_SHA`, the one property it exists to provide. The script now cleans up after itself.

**Item 10 — deployed, with your go-ahead.** Live and verified:

- `https://deep.taile0f78b.ts.net/api/v1/health` → `engine_sha: 5edaa997…`, `db: ok` (was `e04d3c6d9c…`)
- in-container: `VENDOR_SHA` = 5edaa997…, normalizer 665 lines, `rule_layer_provenance.py` present
- in-container adapter after `_prepare()`: sha resolves, cache root
  `/tmp/ff_engine_cache/5edaa997…/`
- `process_patient` calls `_prepare()` before `_build_extractor`, so production is not silently
  running with caching disabled
- backend and worker rebuilt and healthy; caddy and web untouched
- tyrone's compose file backed up to `~/docker-compose.tyrone.yml.bak-2026-07-30`, then brought into
  the repo — it had never been committed

**No run was created**, so P0-4 (a new run silently replacing a reviewer's signed-off view) has not
been triggered. It remains unfixed and is now the top open item.

## 5. Open after this pass

| Item | Why it matters |
|------|----------------|
| P0-4 | A new successful run still silently replaces a reviewer's signed-off view. Needs an explicit "engine changed" state, not a silent swap. Do this before any re-extraction. |
| P0-5 | 10000935's manifest still describes an LLM call that never happened. |
| ~~Re-extracting existing patients~~ | **Not required.** The engine update is forward-looking: new reports get the new engine, and both existing runs correctly record `engine_git_sha: e04d3c6d9c…`, the engine that produced them. Nothing claims to be newer than it is. Re-extraction would only refresh *displayed* demo data, and it risks the PD→PR moment — that discrepancy is computed from stored tracks, and +790 taxonomy lines can change which findings are extracted, hence the classification. For 10000935 it would also send 37 real MIMIC reports to a third-party API. If it is ever done, fix P0-4 first. |
| `build_money_patient.py` | Still uses the unscoped cache path; same staleness risk, off the serving path. |
| `seed_demo.py:113-135` | Duplicate `resolve_git_sha` that never exercises the VENDOR_SHA branch. Hygiene. |
| `findingframe_deploy_snapshot/` | 17 Jul, carries live secrets, no owner. |
| `tmc/AGENTS.md:38-40` | Calls 0.816 the 21-class average; it is the 20-class one. A tmc fix. |
| Shell-script tests | The vendor guard has no automated test; verified by hand only. |
