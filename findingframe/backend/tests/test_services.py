"""Offline service unit tests (no DB, no LLM): RECIST caps + classification, digest section
grouping, worker clinical-section derivation, and the audit/crypto hash chain."""
from __future__ import annotations

import pytest

from app.core.crypto import canonical_json, chain_hash, sha256_hex
from app.core.errors import UnprocessableEntity
from app.services import recist
from app.services.digest import normalize_section
from worker.persist import derive_section


# --- RECIST caps ------------------------------------------------------------
def test_recist_accepts_five_targets_two_per_organ():
    sel = [
        {"confirmed_track_key": "t1", "organ": "liver", "baseline_mm": 20},
        {"confirmed_track_key": "t2", "organ": "liver", "baseline_mm": 15},
        {"confirmed_track_key": "t3", "organ": "lung", "baseline_mm": 12},
        {"confirmed_track_key": "t4", "organ": "lung", "baseline_mm": 11},
        {"confirmed_track_key": "t5", "organ": "node", "baseline_mm": 18},
    ]
    recist.validate_selection_caps(sel)  # no raise


def test_recist_rejects_more_than_five_targets():
    sel = [{"confirmed_track_key": f"t{i}", "organ": f"o{i}", "baseline_mm": 10} for i in range(6)]
    with pytest.raises(UnprocessableEntity) as e:
        recist.validate_selection_caps(sel)
    assert e.value.code == "too_many_targets"


def test_recist_rejects_more_than_two_per_organ():
    sel = [
        {"confirmed_track_key": "t1", "organ": "liver", "baseline_mm": 20},
        {"confirmed_track_key": "t2", "organ": "liver", "baseline_mm": 15},
        {"confirmed_track_key": "t3", "organ": "liver", "baseline_mm": 12},
    ]
    with pytest.raises(UnprocessableEntity) as e:
        recist.validate_selection_caps(sel)
    assert e.value.code == "too_many_per_organ"


def test_recist_rejects_empty():
    with pytest.raises(UnprocessableEntity):
        recist.validate_selection_caps([])


# --- RECIST classification --------------------------------------------------
def test_recist_classify_new_lesion_is_pd():
    assert recist.classify(sld=50, baseline_sld=50, nadir_sld=50, new_lesion=True) == "PD"


def test_recist_classify_complete_response():
    assert recist.classify(sld=0, baseline_sld=40, nadir_sld=0, new_lesion=False) == "CR"


def test_recist_classify_partial_response():
    # 40 -> 25 = -37.5% from baseline
    assert recist.classify(sld=25, baseline_sld=40, nadir_sld=25, new_lesion=False) == "PR"


def test_recist_classify_progressive_from_nadir():
    # nadir 20 -> 26 = +30% and +6mm absolute
    assert recist.classify(sld=26, baseline_sld=40, nadir_sld=20, new_lesion=False) == "PD"


def test_recist_classify_stable():
    assert recist.classify(sld=38, baseline_sld=40, nadir_sld=38, new_lesion=False) == "SD"


# --- RECIST 1.1 nodal vs non-nodal axis selection (bug fix a) ---------------
def test_mm_non_nodal_uses_longest_diameter():
    # non-nodal lesion: LONGEST of a bi-dimensional measurement
    assert recist._mm({"values": [22, 14]}, nodal=False) == 22.0
    assert recist._mm({"values": [14, 22]}, nodal=False) == 22.0


def test_mm_nodal_uses_short_axis():
    # lymph node: SHORT axis = the smaller value
    assert recist._mm({"values": [22, 14]}, nodal=True) == 14.0
    assert recist._mm({"values": [14, 22]}, nodal=True) == 14.0


def test_mm_scalar_taken_as_is_for_both():
    assert recist._mm({"normalized_mm": 18}, nodal=True) == 18.0
    assert recist._mm({"value": 18}, nodal=False) == 18.0


def test_is_nodal_detects_lymph_nodes_not_nodules():
    assert recist._is_nodal(finding_type="lymph_node_metastasis") is True
    assert recist._is_nodal(anatomy="mediastinal lymph node") is True
    assert recist._is_nodal(organ="node") is True
    # a pulmonary "nodule" must NOT be treated as nodal
    assert recist._is_nodal(finding_type="pulmonary_nodule", anatomy="lung") is False
    assert recist._is_nodal(finding_type="liver_metastasis", organ="liver") is False


# --- RECIST 1.1 Complete Response reachable with a node target (bug fix b) ---
def test_recist_classify_cr_reachable_with_node_target():
    # node regressed to 8mm short axis, all non-nodal targets gone -> CR even though
    # the SLD (=8mm) is > 0. Under the old sld==0 rule this was unreachable.
    assert (
        recist.classify(sld=8, baseline_sld=40, nadir_sld=8, new_lesion=False, cr_eligible=True)
        == "CR"
    )


def test_recist_not_cr_when_node_still_pathological():
    # node still 12mm short axis (>=10) -> not CR; -70% from baseline -> PR
    assert (
        recist.classify(sld=12, baseline_sld=40, nadir_sld=12, new_lesion=False, cr_eligible=False)
        == "PR"
    )


def test_recist_classify_scalar_fallback_still_cr_at_zero():
    # no per-target signal supplied -> falls back to sld==0 meaning CR (nodeless case)
    assert recist.classify(sld=0, baseline_sld=40, nadir_sld=0, new_lesion=False) == "CR"


# --- RECIST 1.1 PR / PD / SD boundaries -------------------------------------
def test_recist_pr_boundary_exactly_minus_30_pct():
    # 40 -> 28 = exactly -30% from baseline -> PR
    assert recist.classify(sld=28, baseline_sld=40, nadir_sld=28, new_lesion=False) == "PR"


def test_recist_pd_boundary_20pct_and_5mm_from_nadir():
    # nadir 25 -> 30 = +20% AND +5mm absolute -> PD
    assert recist.classify(sld=30, baseline_sld=40, nadir_sld=25, new_lesion=False) == "PD"


def test_recist_no_pd_when_absolute_increase_below_5mm():
    # nadir 20 -> 24 = +20% but only +4mm absolute -> PD guard fails; -40% baseline -> PR
    assert recist.classify(sld=24, baseline_sld=40, nadir_sld=20, new_lesion=False) == "PR"


def test_recist_sd_just_under_pr_threshold():
    # 40 -> 30 = -25% (not <= -30) and no growth -> SD
    assert recist.classify(sld=30, baseline_sld=40, nadir_sld=30, new_lesion=False) == "SD"


def test_recist_new_lesion_forces_pd_even_when_shrinking():
    # shrinking SLD but a new lesion appeared -> PD
    assert recist.classify(sld=10, baseline_sld=40, nadir_sld=10, new_lesion=True) == "PD"


# --- RECIST 1.1 target eligibility (measurability) --------------------------
def test_recist_rejects_undersized_non_nodal_target():
    with pytest.raises(UnprocessableEntity) as e:
        recist.validate_selection_caps(
            [{"confirmed_track_key": "t1", "organ": "liver", "baseline_mm": 8}]
        )
    assert e.value.code == "target_too_small"


def test_recist_rejects_undersized_node_target():
    # a 12mm short-axis node is NOT an eligible target (needs >=15mm)
    with pytest.raises(UnprocessableEntity) as e:
        recist.validate_selection_caps(
            [{"confirmed_track_key": "t1", "organ": "node", "baseline_mm": 12}]
        )
    assert e.value.code == "node_target_too_small"


def test_recist_accepts_eligible_node_and_lesion():
    recist.validate_selection_caps(
        [
            {"confirmed_track_key": "t1", "organ": "liver", "baseline_mm": 10},  # >=10 ok
            {"confirmed_track_key": "t2", "organ": "node", "baseline_mm": 15},   # >=15 ok
        ]
    )  # no raise


# --- digest / worker section grouping ---------------------------------------
def test_normalize_section_maps_labels():
    assert normalize_section("needs_attention") == "needs_attention"
    assert normalize_section("NEEDS ATTENTION") == "needs_attention"
    assert normalize_section("routine negatives") == "routine_negatives"
    assert normalize_section(None) == "uncertain"


def test_derive_section_needs_attention_on_worsening():
    track = {"latest_status": "active", "events": [{"temporal_change": "increased"}]}
    assert derive_section(track) == "needs_attention"


def test_derive_section_unresolved_is_uncertain():
    track = {"latest_status": "active", "unresolved_link": True, "events": []}
    assert derive_section(track) == "uncertain"


def test_derive_section_absent_is_routine_negative():
    assert derive_section({"latest_status": "absent", "events": []}) == "routine_negatives"


def test_derive_section_resolved():
    assert derive_section({"latest_status": "resolved", "events": []}) == "resolved"


# --- audit hash chain -------------------------------------------------------
def test_canonical_json_is_stable_regardless_of_key_order():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_chain_hash_links_previous():
    h1 = chain_hash(None, {"action": "a"})
    h2 = chain_hash(h1, {"action": "b"})
    # tamper-evident: changing the prev hash changes the row hash
    assert h2 != chain_hash("tampered", {"action": "b"})
    assert h1 == sha256_hex(canonical_json({"action": "a"}))
