#!/usr/bin/env python3
"""FindingFrame — Cohen's kappa for the blinded clinician IRR pilot.

Run with the backend venv:
    backend/.venv/bin/python infra/scripts/compute_kappa.py --demo
    backend/.venv/bin/python infra/scripts/compute_kappa.py --list-tasks
    backend/.venv/bin/python infra/scripts/compute_kappa.py --task-id <uuid>

See docs/IRR_PROTOCOL.md for the full study design this script implements the
statistics for. Short version of what this does:

  1. Given an `ff.annotation_tasks.id`, find its `ff.annotation_assignments`
     grouped by `independence_group` (this column is what makes two rows a
     genuine *blinded, independent* reader pair rather than two arbitrary
     reviews).
  2. For each independence_group with exactly two assignments, pull
     `ff.annotation_records` for both, align them by `item_ref` (the item both
     readers were shown — a frame_id, track_key, or link-pair key depending on
     `unit_of_agreement`).
  3. For every slot key present in both readers' `labels` jsonb (finding_type,
     anatomy, laterality, assertion, temporal_change, measurement, plus a
     track-linking key if this is a track-level task), compute Cohen's kappa,
     observed agreement, n, and a bootstrap 95% CI.
  4. Print one table per independence_group.

Cohen's kappa is implemented directly with numpy (confusion-matrix trace /
marginals) — this script does NOT import scikit-learn. `--demo` proves the
math against a hand-checkable textbook confusion matrix (kappa = 0.400) plus
a perfect-agreement and a chance-agreement case, so the arithmetic can be
verified without a database.

Governance note (see docs/IRR_PROTOCOL.md §6): this script only ever reads
`ff.annotation_records` for assignments with `model_output_visible=false`
(blinded reads). If it finds `model_output_visible=true` in a pair it is
asked to score, it computes the number anyway but prints a loud warning —
that number is a production-review agreement statistic, not IRR, and must
never be cited as clinician-validated kappa.

Exits 0 whether or not any annotations exist yet (prints "no annotations
yet" and returns cleanly) — this script is meant to be runnable today,
before the pilot has collected a single record, and again after.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np

# --- repo layout (mirrors seed_demo.py / verify_chain.py) --------------------
SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_ENV = FF_ROOT / "backend" / ".env"

# Canonical slot ordering for display; anything else found in `labels` is
# appended afterwards (sorted) so the script never silently drops a slot.
CANONICAL_SLOT_ORDER = [
    "finding_type",
    "anatomy",
    "laterality",
    "assertion",
    "temporal_change",
    "measurement",
]
TRACK_KEY_ALIASES = ["track_link", "linked", "same_track", "belongs_to_same_track", "decision"]

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("psycopg not found; installing psycopg[binary] into this interpreter's venv ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg[binary]"], check=True)
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore


# --- env + DSN (copied from seed_demo.py / verify_chain.py) ------------------
def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def build_pg_dsn(database_url: str) -> str:
    scheme, _, rest = database_url.partition("://")
    if "+" in scheme:
        scheme = "postgresql"
    u = urlsplit(f"{scheme}://{rest}")
    dbname = (u.path or "/postgres").lstrip("/") or "postgres"
    from psycopg.conninfo import make_conninfo

    return make_conninfo(
        host=u.hostname or "",
        port=u.port or 5432,
        user=unquote(u.username or "postgres"),
        password=unquote(u.password or ""),
        dbname=dbname,
        sslmode="require",
    )


def connect():
    env = load_env_file(BACKEND_ENV)
    database_url = env.get("FF_DATABASE_URL", "")
    if not database_url:
        print(f"ERROR: FF_DATABASE_URL missing from {BACKEND_ENV}", file=sys.stderr)
        sys.exit(1)
    return psycopg.connect(build_pg_dsn(database_url), autocommit=True, row_factory=dict_row)


# --- Cohen's kappa, implemented directly (no sklearn) ------------------------
def to_category(value) -> str:
    """Coerce a jsonb label value to a hashable, sortable category string.

    Structured values (measurement objects, lists) are canonicalized via
    sorted-key JSON so two readers who extracted the identical structure
    agree, and any difference in the structure counts as disagreement.
    """
    if value is None:
        return "∅null"  # sorts after normal strings' ASCII range is irrelevant; just a stable sentinel
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def confusion_matrix(labels_a: list[str], labels_b: list[str]) -> tuple[np.ndarray, list[str]]:
    categories = sorted(set(labels_a) | set(labels_b))
    idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    mat = np.zeros((k, k), dtype=float)
    for a, b in zip(labels_a, labels_b):
        mat[idx[a], idx[b]] += 1.0
    return mat, categories


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> dict:
    """Cohen's kappa for two raters' categorical judgments over the same n items.

    kappa = (p_o - p_e) / (1 - p_e)
      p_o = observed agreement = trace(confusion matrix) / n
      p_e = chance agreement   = sum_k( row_marginal_k * col_marginal_k )
    """
    n = len(labels_a)
    assert n == len(labels_b)
    if n == 0:
        return {"n": 0, "po": float("nan"), "pe": float("nan"), "kappa": float("nan")}
    mat, categories = confusion_matrix(labels_a, labels_b)
    po = float(np.trace(mat) / n)
    row_marg = mat.sum(axis=1) / n
    col_marg = mat.sum(axis=0) / n
    pe = float(np.dot(row_marg, col_marg))
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 1e-12 else float("nan")
    return {"n": n, "po": po, "pe": pe, "kappa": kappa, "n_categories": len(categories)}


def bootstrap_kappa_ci(
    labels_a: list[str], labels_b: list[str], n_boot: int = 2000, alpha: float = 0.05, seed: int = 42
) -> tuple[float, float]:
    """Percentile bootstrap CI: resample items (with replacement) as pairs,
    recompute kappa each time. Non-parametric — makes no distributional
    assumption about kappa's sampling distribution, appropriate for the
    n~150-200-item pilot sizes here.
    """
    n = len(labels_a)
    if n == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    la = np.array(labels_a, dtype=object)
    lb = np.array(labels_b, dtype=object)
    boots: list[float] = []
    for _ in range(n_boot):
        sample_idx = rng.integers(0, n, size=n)
        result = cohens_kappa(list(la[sample_idx]), list(lb[sample_idx]))
        k = result["kappa"]
        if not np.isnan(k):
            boots.append(k)
    if not boots:
        return (float("nan"), float("nan"))
    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    return lo, hi


def interpret_kappa(kappa: float) -> str:
    """Landis & Koch (1977) bands."""
    if np.isnan(kappa):
        return "n/a"
    if kappa < 0:
        return "poor"
    if kappa < 0.20:
        return "slight"
    if kappa < 0.40:
        return "fair"
    if kappa < 0.60:
        return "moderate"
    if kappa < 0.80:
        return "substantial"
    return "almost perfect"


# --- table printing -----------------------------------------------------------
def print_kappa_table(title: str, rows: list[dict]) -> None:
    print(f"\n--- {title} ---")
    if not rows:
        print("  (nothing to score)")
        return
    header = f"{'slot / unit':<22} | {'n':>5} | {'agree %':>8} | {'kappa':>7} | {'95% CI':>17} | interpretation"
    print(header)
    print("-" * len(header))
    for r in rows:
        n = r["n"]
        po = r["po"]
        kappa = r["kappa"]
        lo, hi = r.get("ci", (float("nan"), float("nan")))
        agree_str = f"{po:.1%}" if not np.isnan(po) else "n/a"
        kappa_str = f"{kappa:.3f}" if not np.isnan(kappa) else "n/a"
        ci_str = f"[{lo:.3f}, {hi:.3f}]" if not np.isnan(lo) else "n/a"
        print(
            f"{r['slot']:<22} | {n:>5d} | {agree_str:>8} | {kappa_str:>7} | {ci_str:>17} | {interpret_kappa(kappa)}"
        )


def score_pair(item_labels_a: dict[str, dict], item_labels_b: dict[str, dict]) -> list[dict]:
    """Given item_ref -> labels(jsonb-as-dict) for two readers, return one
    kappa-table row per slot key common to both readers."""
    common_items = sorted(set(item_labels_a) & set(item_labels_b))
    if not common_items:
        return []

    all_keys: set[str] = set()
    for item in common_items:
        all_keys |= set((item_labels_a[item] or {}).keys())
        all_keys |= set((item_labels_b[item] or {}).keys())

    ordered_keys = [k for k in CANONICAL_SLOT_ORDER if k in all_keys]
    ordered_keys += [k for k in TRACK_KEY_ALIASES if k in all_keys and k not in ordered_keys]
    ordered_keys += sorted(k for k in all_keys if k not in ordered_keys)

    rows: list[dict] = []
    for key in ordered_keys:
        la: list[str] = []
        lb: list[str] = []
        for item in common_items:
            da = item_labels_a[item] or {}
            db = item_labels_b[item] or {}
            if key in da and key in db:
                la.append(to_category(da[key]))
                lb.append(to_category(db[key]))
        if not la:
            continue
        result = cohens_kappa(la, lb)
        ci = bootstrap_kappa_ci(la, lb)
        rows.append({"slot": key, **result, "ci": ci})

    # Frame-level composite: concatenate the canonical slots present into a
    # single per-item category, so "do the two readers agree on the WHOLE
    # frame" is its own kappa row (matches ff.annotation_tasks.unit_of_agreement
    # = 'frame' — see docs/IRR_PROTOCOL.md).
    frame_slots = [k for k in CANONICAL_SLOT_ORDER if k in all_keys]
    if len(frame_slots) > 1:
        la, lb = [], []
        for item in common_items:
            da = item_labels_a[item] or {}
            db = item_labels_b[item] or {}
            if all(k in da for k in frame_slots) and all(k in db for k in frame_slots):
                la.append(to_category({k: da[k] for k in frame_slots}))
                lb.append(to_category({k: db[k] for k in frame_slots}))
        if la:
            result = cohens_kappa(la, lb)
            ci = bootstrap_kappa_ci(la, lb)
            rows.append({"slot": "full_frame (all slots)", **result, "ci": ci})

    return rows


# Prefer the factored backend implementation so this pilot script and the REST API
# (app.services.irr) compute the identical statistic from identical code
# (docs/IRR_PROTOCOL.md §5, "shares ... code"). The local definitions above are the
# authoritative fallback and are byte-identical, so the script stays standalone if the
# backend package isn't importable.
try:  # noqa: SIM105
    _BACKEND_DIR = FF_ROOT / "backend"
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    from app.services.kappa import (  # type: ignore  # noqa: E402
        bootstrap_kappa_ci,
        cohens_kappa,
        confusion_matrix,
        interpret_kappa,
        score_pair,
        to_category,
    )
except Exception:  # pragma: no cover - keep the standalone local implementations
    pass


# --- correction rate: blinded reader's label vs the model's ORIGINAL ff.frames
# value for the same item. The reader never saw this value (model_output_visible
# should be false for these assignments) — this is a post-hoc analysis join done
# by this script, not something exposed to the annotator. Ties to the ROI claim
# ("how often would a reviewer actually need to correct the model").
CORRECTION_RATE_SLOTS = ["finding_type", "anatomy", "laterality", "assertion", "temporal_change"]


def compute_correction_rate(cur, item_labels: dict[str, dict]) -> list[dict] | None:
    """Returns None if item_refs in this task aren't ff.frames UUIDs (e.g. a
    track-level task, or a synthetic/test item_ref scheme) — correction rate
    vs the model is only meaningful for frame/slot-level tasks whose item_ref
    is a real ff.frames.id.
    """
    item_refs = list(item_labels.keys())
    for ref in item_refs:
        try:
            uuid.UUID(str(ref))
        except (ValueError, AttributeError, TypeError):
            return None

    cur.execute(
        """
        select id::text as item_ref, finding_type, anatomy, laterality,
               assertion::text as assertion, temporal_change
        from ff.frames where id::text = any(%s)
        """,
        (item_refs,),
    )
    frame_rows = {r["item_ref"]: r for r in cur.fetchall()}
    if not frame_rows:
        return None  # these UUIDs aren't ff.frames ids in this DB

    results = []
    for slot in CORRECTION_RATE_SLOTS:
        n = 0
        corrected = 0
        for ref, labels in item_labels.items():
            frame = frame_rows.get(ref)
            if frame is None or not labels or slot not in labels or labels[slot] is None:
                continue
            n += 1
            if to_category(frame[slot]) != to_category(labels[slot]):
                corrected += 1
        if n:
            results.append({"slot": slot, "n": n, "corrected": corrected, "rate": corrected / n})
    return results


def print_correction_rate_table(label: str, rows: list[dict] | None) -> None:
    if rows is None:
        print(f"  (correction rate vs model skipped for {label}: item_refs are not ff.frames ids)")
        return
    if not rows:
        print(f"  (correction rate vs model: no comparable slots for {label})")
        return
    print(f"  correction rate vs model output ({label} — blinded, reader never saw these values):")
    for r in rows:
        print(f"    {r['slot']:<18} corrected {r['corrected']:>4}/{r['n']:<4} ({r['rate']:.1%})")


# --- demo mode: hand-checkable synthetic example ------------------------------
def run_demo() -> int:
    print("=== compute_kappa.py --demo ===")
    print("Synthetic in-memory example — no database connection. Proves the kappa")
    print("arithmetic against a hand-checkable textbook confusion matrix.\n")

    # --- Case 1: classic textbook 2x2, kappa should come out to exactly 0.400 ---
    # Confusion matrix (rows = rater A, cols = rater B), N=50:
    #            B=present   B=absent
    # A=present     20           5
    # A=absent      10          15
    # po = (20+15)/50 = 0.70
    # row marginals: A=present 25/50=0.5, A=absent 25/50=0.5
    # col marginals: B=present 30/50=0.6, B=absent 20/50=0.4
    # pe = 0.5*0.6 + 0.5*0.4 = 0.30 + 0.20 = 0.50
    # kappa = (0.70 - 0.50) / (1 - 0.50) = 0.20 / 0.50 = 0.400  (Landis-Koch: fair/moderate boundary)
    rater_a = (
        ["present"] * 20 + ["present"] * 5 + ["absent"] * 10 + ["absent"] * 15
    )
    rater_b = (
        ["present"] * 20 + ["absent"] * 5 + ["present"] * 10 + ["absent"] * 15
    )
    result1 = cohens_kappa(rater_a, rater_b)
    ci1 = bootstrap_kappa_ci(rater_a, rater_b)
    expected_kappa = 0.400
    print(f"Case 1 — textbook 2x2 confusion matrix (N=50):")
    print(f"  observed agreement (p_o) = {result1['po']:.4f}  (expect 0.7000)")
    print(f"  chance agreement   (p_e) = {result1['pe']:.4f}  (expect 0.5000)")
    print(f"  kappa                    = {result1['kappa']:.4f}  (expect {expected_kappa:.4f})")
    print(f"  95% CI (bootstrap)       = [{ci1[0]:.4f}, {ci1[1]:.4f}]")
    assert abs(result1["po"] - 0.70) < 1e-9, "p_o mismatch"
    assert abs(result1["pe"] - 0.50) < 1e-9, "p_e mismatch"
    assert abs(result1["kappa"] - expected_kappa) < 1e-9, "kappa mismatch — arithmetic is WRONG"
    print("  PASS: matches hand-computed values exactly.\n")

    # --- Case 2: perfect agreement, 3 categories -> kappa should be exactly 1.0 ---
    cats = ["liver", "lung", "bone"] * 8
    result2 = cohens_kappa(cats, cats)
    print(f"Case 2 — perfect agreement, 3 categories (N={result2['n']}):")
    print(f"  kappa = {result2['kappa']:.4f}  (expect 1.0000)")
    assert abs(result2["kappa"] - 1.0) < 1e-9
    print("  PASS.\n")

    # --- Case 3: independent random labels at the true marginal rates -> kappa ~ 0 ---
    rng = np.random.default_rng(7)
    n3 = 4000
    a3 = rng.choice(["present", "absent"], size=n3, p=[0.5, 0.5])
    b3 = rng.choice(["present", "absent"], size=n3, p=[0.5, 0.5])
    result3 = cohens_kappa(list(a3), list(b3))
    print(f"Case 3 — two independent 50/50 coin-flip raters (N={n3}):")
    print(f"  kappa = {result3['kappa']:.4f}  (expect ~0, since ratings are statistically independent)")
    assert abs(result3["kappa"]) < 0.05, "independent raters should show ~chance agreement"
    print("  PASS.\n")

    # --- Assemble as a per-slot table the way a real pilot run would print ---
    # (a small hand-mixed 6-item slice — 2 agree-present, 2 disagree, 1 disagree, 1 agree-absent —
    # so both categories appear on both sides and kappa is well-defined, unlike a
    # same-category-only slice which would divide by zero chance-agreement variance.)
    small_a = [rater_a[18], rater_a[19], rater_a[20], rater_a[21], rater_a[34], rater_a[35]]
    small_b = [rater_b[18], rater_b[19], rater_b[20], rater_b[21], rater_b[34], rater_b[35]]
    print_kappa_table(
        "Demo pilot — independence_group 'demo_pair' (synthetic, 6 items, 2 slots)",
        [
            {**cohens_kappa(small_a, small_b), "slot": "assertion", "ci": bootstrap_kappa_ci(small_a, small_b)},
            {**result2, "slot": "finding_type", "ci": bootstrap_kappa_ci(cats, cats)},
        ],
    )
    print("\nAll --demo assertions passed: the kappa implementation is arithmetically correct.")
    return 0


# --- live DB mode --------------------------------------------------------------
def list_tasks(cur) -> int:
    cur.execute(
        """
        select t.id, t.protocol_id, t.name, t.unit_of_agreement, t.created_at,
               count(a.id) as n_assignments,
               count(distinct a.independence_group) as n_independence_groups
        from ff.annotation_tasks t
        left join ff.annotation_assignments a on a.task_id = t.id
        group by t.id, t.protocol_id, t.name, t.unit_of_agreement, t.created_at
        order by t.created_at desc
        """
    )
    rows = cur.fetchall()
    if not rows:
        print("No annotation_tasks found in ff.annotation_tasks — no annotations yet.")
        print("See docs/IRR_PROTOCOL.md §Runbook to create one.")
        return 0
    print(f"{'task_id':<38} | {'unit':<6} | {'assignments':>11} | {'groups':>6} | name")
    print("-" * 100)
    for r in rows:
        print(
            f"{str(r['id']):<38} | {r['unit_of_agreement']:<6} | {r['n_assignments']:>11} | "
            f"{r['n_independence_groups']:>6} | {r['name']}"
        )
    return 0


def resolve_task(cur, task_id: str | None) -> dict | None:
    if task_id:
        cur.execute(
            "select id, protocol_id, name, unit_of_agreement, description from ff.annotation_tasks where id = %s",
            (task_id,),
        )
        return cur.fetchone()
    # no task-id given: fall back to the most recently created task, if any.
    cur.execute(
        "select id, protocol_id, name, unit_of_agreement, description from ff.annotation_tasks "
        "order by created_at desc limit 1"
    )
    return cur.fetchone()


def score_task(cur, task: dict) -> int:
    """Given a resolved ff.annotation_tasks row, pull its assignments/records
    from the DB (via `cur`) and print one kappa table per independence_group.
    Split out from run_live() so it can be exercised directly (e.g. against an
    uncommitted transaction in a test) without going through a fresh connection.
    """
    task_id = str(task["id"])
    print(f"Task: {task['name']!r}  (id={task_id}, protocol={task['protocol_id']}, "
          f"unit_of_agreement={task['unit_of_agreement']})")
    if task.get("description"):
        print(f"  {task['description']}")

    cur.execute(
        """
        select id, annotator_id, independence_group, model_output_visible, status
        from ff.annotation_assignments
        where task_id = %s
        order by independence_group nulls last, created_at
        """,
        (task_id,),
    )
    assignments = cur.fetchall()
    if not assignments:
        print("  No annotation_assignments for this task yet — no annotations yet.")
        return 0

    groups: dict[str | None, list[dict]] = {}
    for a in assignments:
        groups.setdefault(a["independence_group"], []).append(a)

    any_scored = False
    for group_key, group_assignments in groups.items():
        group_label = group_key if group_key is not None else "(no independence_group set)"
        print(f"\n=== independence_group: {group_label} ===")
        if group_key is None:
            print("  WARNING: these assignments have no independence_group — cannot pair them into")
            print("  an IRR read. Set independence_group when creating assignments (see IRR_PROTOCOL.md).")
            continue
        if len(group_assignments) != 2:
            print(f"  WARNING: expected exactly 2 assignments in this independence_group for a "
                  f"pairwise Cohen's kappa read, found {len(group_assignments)}. Skipping.")
            continue

        a1, a2 = group_assignments
        for a in (a1, a2):
            if a["model_output_visible"]:
                print(f"  WARNING: assignment {a['id']} has model_output_visible=true — this is a "
                      f"PRODUCTION REVIEW read, not a blinded IRR read. Any kappa computed below is "
                      f"anchored and must NOT be reported as clinician-validated IRR.")

        cur.execute(
            "select assignment_id, item_ref, labels from ff.annotation_records where assignment_id = %s",
            (a1["id"],),
        )
        records_a = {r["item_ref"]: r["labels"] for r in cur.fetchall()}
        cur.execute(
            "select assignment_id, item_ref, labels from ff.annotation_records where assignment_id = %s",
            (a2["id"],),
        )
        records_b = {r["item_ref"]: r["labels"] for r in cur.fetchall()}

        print(f"  reader A: annotator_id={a1['annotator_id']}  n_records={len(records_a)}")
        print(f"  reader B: annotator_id={a2['annotator_id']}  n_records={len(records_b)}")

        if not records_a or not records_b:
            print("  no annotations yet for this pair.")
            continue

        print_correction_rate_table("reader A", compute_correction_rate(cur, records_a))
        print_correction_rate_table("reader B", compute_correction_rate(cur, records_b))

        only_a = set(records_a) - set(records_b)
        only_b = set(records_b) - set(records_a)
        if only_a or only_b:
            print(f"  (coverage) {len(only_a)} item(s) only annotated by reader A, "
                  f"{len(only_b)} only by reader B — excluded from paired kappa.")

        rows = score_pair(records_a, records_b)
        if not rows:
            print("  no overlapping item_refs / slot keys between the two readers yet.")
            continue
        any_scored = True
        print_kappa_table(f"Cohen's kappa — {task['name']} / group {group_label}", rows)

    if not any_scored:
        print("\nNo scoreable reader pairs yet — no annotations yet.")
    return 0


def run_live(args: argparse.Namespace) -> int:
    print("=== compute_kappa.py — live DB ===")
    with connect() as conn:
        with conn.cursor() as cur:
            if args.list_tasks:
                return list_tasks(cur)

            task = resolve_task(cur, args.task_id)
            if task is None:
                if args.task_id:
                    print(f"Task {args.task_id} not found — no annotations yet.")
                else:
                    print("No annotation_tasks found in ff.annotation_tasks — no annotations yet.")
                print("See docs/IRR_PROTOCOL.md §Runbook to create one and assign blinded readers.")
                return 0
            return score_task(cur, task)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cohen's kappa for the FindingFrame blinded clinician IRR pilot "
                    "(see docs/IRR_PROTOCOL.md)."
    )
    ap.add_argument("--task-id", help="ff.annotation_tasks.id (uuid). Omit to use the most recent task.")
    ap.add_argument("--list-tasks", action="store_true", help="List annotation_tasks and exit.")
    ap.add_argument("--demo", action="store_true",
                     help="Compute kappa on a tiny synthetic in-memory example (no DB) to prove the math.")
    args = ap.parse_args()

    if args.demo:
        return run_demo()
    return run_live(args)


if __name__ == "__main__":
    raise SystemExit(main())
