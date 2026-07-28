"""Offline unit tests for the IRR / Cohen's kappa pilot (no DB, no LLM).

Covers (a) the kappa arithmetic on known records, and (b) the load-bearing BLINDING invariant:
the items a blinded reader is shown must never carry the model's slot values.
See docs/IRR_PROTOCOL.md.
"""
from __future__ import annotations

import math

from app.services import irr
from app.services.kappa import (
    CANONICAL_SLOT_ORDER,
    cohens_kappa,
    interpret_kappa,
    score_pair,
    to_category,
)


# --- kappa arithmetic (hand-checkable) --------------------------------------
def test_kappa_textbook_2x2_is_exactly_0_400():
    # classic 20/5/10/15 confusion matrix (N=50) -> po=0.70, pe=0.50, kappa=0.400
    a = ["present"] * 20 + ["present"] * 5 + ["absent"] * 10 + ["absent"] * 15
    b = ["present"] * 20 + ["absent"] * 5 + ["present"] * 10 + ["absent"] * 15
    r = cohens_kappa(a, b)
    assert abs(r["po"] - 0.70) < 1e-9
    assert abs(r["pe"] - 0.50) < 1e-9
    assert abs(r["kappa"] - 0.400) < 1e-9


def test_kappa_perfect_agreement_is_one():
    cats = ["liver", "lung", "bone"] * 8
    assert abs(cohens_kappa(cats, cats)["kappa"] - 1.0) < 1e-9


def test_interpret_kappa_bands():
    assert interpret_kappa(-0.1) == "poor"
    assert interpret_kappa(0.1) == "slight"
    assert interpret_kappa(0.3) == "fair"
    assert interpret_kappa(0.5) == "moderate"
    assert interpret_kappa(0.7) == "substantial"
    assert interpret_kappa(0.9) == "almost perfect"
    assert interpret_kappa(float("nan")) == "n/a"


def test_to_category_canonicalizes_structures_and_null():
    assert to_category({"b": 1, "a": 2}) == to_category({"a": 2, "b": 1})
    assert to_category(None) == to_category(None)
    assert to_category(None) != to_category("present")


# --- score_pair over known records ------------------------------------------
def _records(slot: str, labels_a: list, labels_b: list) -> tuple[dict, dict]:
    ra = {str(i): {slot: v} for i, v in enumerate(labels_a)}
    rb = {str(i): {slot: v} for i, v in enumerate(labels_b)}
    return ra, rb


def test_score_pair_reproduces_textbook_kappa_on_a_slot():
    a = ["present"] * 20 + ["present"] * 5 + ["absent"] * 10 + ["absent"] * 15
    b = ["present"] * 20 + ["absent"] * 5 + ["present"] * 10 + ["absent"] * 15
    ra, rb = _records("assertion", a, b)
    rows = {r["slot"]: r for r in score_pair(ra, rb, with_ci=False)}
    assert "assertion" in rows
    assert rows["assertion"]["n"] == 50
    assert abs(rows["assertion"]["kappa"] - 0.400) < 1e-9
    # 0.400 sits exactly on the Landis-Koch fair/moderate boundary (float-representation
    # dependent), so accept either side of it rather than asserting a knife-edge.
    assert rows["assertion"]["band"] in ("fair", "moderate")


def test_score_pair_perfect_slot_agreement():
    labels = (["liver_metastasis", "lung_nodule"] * 5)
    ra, rb = _records("finding_type", labels, labels)
    rows = {r["slot"]: r for r in score_pair(ra, rb, with_ci=False)}
    assert abs(rows["finding_type"]["kappa"] - 1.0) < 1e-9
    assert abs(rows["finding_type"]["po"] - 1.0) < 1e-9


def test_score_pair_emits_full_frame_composite_when_multi_slot():
    ra = {
        "0": {"finding_type": "liver_metastasis", "assertion": "present"},
        "1": {"finding_type": "lung_nodule", "assertion": "present"},
        "2": {"finding_type": "liver_metastasis", "assertion": "absent"},
        "3": {"finding_type": "lung_nodule", "assertion": "absent"},
    }
    rb = {
        "0": {"finding_type": "liver_metastasis", "assertion": "present"},
        "1": {"finding_type": "lung_nodule", "assertion": "absent"},   # disagree on assertion
        "2": {"finding_type": "liver_metastasis", "assertion": "absent"},
        "3": {"finding_type": "lung_nodule", "assertion": "absent"},
    }
    slots = {r["slot"] for r in score_pair(ra, rb, with_ci=False)}
    assert "finding_type" in slots
    assert "assertion" in slots
    assert "full_frame (all slots)" in slots


def test_score_pair_scores_track_linking_key():
    ra = {str(i): {"belongs_to_same_track": v} for i, v in enumerate([True, True, False, False])}
    rb = {str(i): {"belongs_to_same_track": v} for i, v in enumerate([True, False, False, False])}
    slots = {r["slot"] for r in score_pair(ra, rb, with_ci=False)}
    assert "belongs_to_same_track" in slots


def test_score_pair_only_scores_overlapping_items_and_slots():
    ra = {"0": {"finding_type": "liver_metastasis"}, "1": {"finding_type": "lung_nodule"}}
    rb = {"1": {"finding_type": "lung_nodule"}, "2": {"finding_type": "bone_lesion"}}
    rows = {r["slot"]: r for r in score_pair(ra, rb, with_ci=False)}
    # only item "1" overlaps -> n == 1 for finding_type
    assert rows["finding_type"]["n"] == 1


# --- BLINDING: the items a blinded reader sees must not leak model slot values -----
def test_blinded_frame_item_strips_all_model_slots():
    # a frame row exactly as ff.frames would return it, with model output populated
    frame_row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "source_report_id": "report_3",
        "evidence_text": "There is a new 2.1 cm lesion in the right hepatic lobe.",
        "evidence_span_start": 10,
        "evidence_span_end": 60,
        "report_version_id": "22222222-2222-2222-2222-222222222222",
        # --- model output that must NEVER reach a blinded reader ---
        "finding_type": "liver_metastasis",
        "finding_surface": "hepatic lesion",
        "anatomy": "liver",
        "laterality": "right",
        "assertion": "present",
        "temporal_change": "new",
        "measurement": {"values": [21], "unit": "mm"},
        "clinical_importance": "high",
        "severity": "high",
        "uncertainty": None,
    }
    item = irr.blinded_frame_item(frame_row, full_text="FULL REPORT TEXT")

    # not one model slot leaked
    leaked = set(item.keys()) & irr.MODEL_SLOT_COLUMNS
    assert leaked == set(), f"blinded item leaked model slots: {leaked}"
    for slot in CANONICAL_SLOT_ORDER:
        assert slot not in item

    # but the source-only fields the reader legitimately needs ARE present
    assert item["item_ref"] == frame_row["id"]
    assert item["evidence_text"] == frame_row["evidence_text"]
    assert item["full_text"] == "FULL REPORT TEXT"
    assert item["source_report_id"] == "report_3"

    # and no model value appears anywhere in the serialized item
    import json
    blob = json.dumps(item)
    for forbidden in ("liver_metastasis", "hepatic lesion", "high"):
        assert forbidden not in blob


def test_blinded_frame_slot_fields_are_empty_prompts_not_values():
    # the reader is told WHICH fields to fill, never their model values
    assert irr.FRAME_SLOT_FIELDS == CANONICAL_SLOT_ORDER
    assert "belongs_to_same_track" in irr.TRACK_SLOT_FIELDS


# --- task description round-trip (item-set persistence) ---------------------
def test_description_payload_round_trip():
    import uuid as _uuid
    run = _uuid.uuid4()
    enc = irr._encode_description("human note", run, "frame", {"seed": 1}, ["a", "b", "c"])
    dec = irr._decode_description(enc)
    assert dec["text"] == "human note"
    assert dec["run_id"] == str(run)
    assert dec["item_refs"] == ["a", "b", "c"]
    assert dec["sampling"] == {"seed": 1}


def test_decode_description_tolerates_plain_human_text():
    dec = irr._decode_description("just a hand-written description")
    assert dec["text"] == "just a hand-written description"
    assert dec["item_refs"] == []


def _unused_math_guard():
    # keep `math` import meaningful for linters if assertions above change
    assert math.isnan(float("nan"))
