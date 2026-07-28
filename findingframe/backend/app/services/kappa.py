"""Cohen's kappa — the chance-corrected inter-rater agreement math for the blinded IRR
pilot (docs/IRR_PROTOCOL.md §3).

This is the factored core of ``infra/scripts/compute_kappa.py`` — the arithmetic is byte-for-byte
the same numpy implementation (confusion-matrix trace / marginals; percentile bootstrap CI;
Landis & Koch bands). It lives here so the REST API (``app.services.irr``) and the standalone
pilot script compute the *identical* number from the *identical* code, and so it can be unit
tested offline with no database (see ``tests/test_irr.py`` and ``compute_kappa.py --demo``).

Pure functions only — no DB, no I/O. Governance note (§6): kappa is only ever IRR when the
records scored come from assignments with ``model_output_visible = false`` (blinded). This
module computes the statistic; the caller is responsible for only feeding it blinded reads.
"""
from __future__ import annotations

import json

import numpy as np

# Canonical slot ordering for display; anything else found in `labels` is appended
# afterwards (sorted) so a kappa run never silently drops a slot.
CANONICAL_SLOT_ORDER = [
    "finding_type",
    "anatomy",
    "laterality",
    "assertion",
    "temporal_change",
    "measurement",
]
# Keys a track-linking judgment might be recorded under (unit_of_agreement='track').
TRACK_KEY_ALIASES = ["track_link", "linked", "same_track", "belongs_to_same_track", "decision"]


def to_category(value) -> str:
    """Coerce a jsonb label value to a hashable, sortable category string.

    Structured values (measurement objects, lists) are canonicalized via sorted-key JSON so
    two readers who extracted the identical structure agree, and any difference in the
    structure counts as disagreement.
    """
    if value is None:
        return "∅null"  # stable sentinel for "reader left this slot blank"
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
    """Percentile bootstrap CI: resample items (with replacement) as pairs, recompute kappa
    each time. Non-parametric — makes no distributional assumption about kappa's sampling
    distribution, appropriate for the n~150-200-item pilot sizes here (and correctly reports
    very wide intervals at small n, which is itself an honest signal)."""
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
    if kappa is None or np.isnan(kappa):
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


def score_pair(
    item_labels_a: dict[str, dict], item_labels_b: dict[str, dict], *, with_ci: bool = True
) -> list[dict]:
    """Given ``item_ref -> labels`` for two readers, return one kappa-table row per slot key
    common to both readers, plus a ``full_frame (all slots)`` composite row when >1 canonical
    slot is present. Each row: {slot, n, po, pe, kappa, ci:(lo,hi), band}."""
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

    def _row(slot: str, la: list[str], lb: list[str]) -> dict:
        result = cohens_kappa(la, lb)
        ci = bootstrap_kappa_ci(la, lb) if with_ci else (float("nan"), float("nan"))
        return {**result, "slot": slot, "ci": ci, "band": interpret_kappa(result["kappa"])}

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
        rows.append(_row(key, la, lb))

    # Frame-level composite: concatenate the canonical slots present into one per-item
    # category, so "do the two readers agree on the WHOLE frame" is its own kappa row.
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
            rows.append(_row("full_frame (all slots)", la, lb))

    return rows
