"""Offline unit tests (no DB, no LLM) for the carry-forward gate.

The gate decides, when a new report arrives, which of a clinician's previous
confirmations still stand. Getting it wrong is expensive in both directions: too strict
and the reviewer re-does settled work at every scan, too lax and a confirmation is
carried past evidence the clinician never saw.
"""
from __future__ import annotations

from app.services.carry_forward import (
    ACKNOWLEDGE,
    CARRY,
    NEW,
    REOPEN,
    plan_identities,
)

CLEAN = (False, False)          # (unresolved_link, false_split_candidate)
AMBIGUOUS = (True, False)
SPLIT_FLAGGED = (False, True)

LUNG = "primary_tumor|thorax|left"
LIVER = "liver_metastasis|liver|right"


def _one(key=LUNG, members=None):
    return [{"confirmed_track_key": key, "member_track_keys": members or [key]}]


def _plan(**kw):
    base = dict(
        parent_confirmed=_one(),
        parent_flags={LUNG: CLEAN},
        new_flags={LUNG: CLEAN},
        parent_event_dates={LUNG: {"2024-02-05"}},
        new_event_dates={LUNG: {"2024-02-05"}},
        category_moved=False,
        target_keys={LUNG},
    )
    base.update(kw)
    return plan_identities(**base)


# --- the identity claim survives new evidence -------------------------------
def test_unchanged_identity_with_no_new_evidence_carries():
    (p,) = _plan()
    assert p.status == CARRY


def test_new_measurement_alone_does_not_reopen_identity():
    """A track exists so identity is settled once and measurements accumulate. Re-asking
    at every scan would make longitudinal tracking self-defeating."""
    (p,) = _plan(new_event_dates={LUNG: {"2024-02-05", "2025-08-18"}})
    assert p.status == ACKNOWLEDGE
    assert p.gained_event_dates == ["2025-08-18"]


# --- but a changed identity picture does ------------------------------------
def test_new_ambiguous_link_candidate_reopens():
    (p,) = _plan(new_flags={LUNG: AMBIGUOUS})
    assert p.status == REOPEN
    assert "ambiguous" in p.reason


def test_new_false_split_flag_reopens():
    (p,) = _plan(new_flags={LUNG: SPLIT_FLAGGED})
    assert p.status == REOPEN
    assert "false-split" in p.reason


def test_ambiguity_already_present_on_the_parent_does_not_reopen():
    """Only a *newly* raised flag disturbs the claim — the clinician already saw and
    resolved the old one when they confirmed."""
    (p,) = _plan(parent_flags={LUNG: AMBIGUOUS}, new_flags={LUNG: AMBIGUOUS})
    assert p.status == CARRY


def test_missing_member_track_reopens():
    (p,) = _plan(new_flags={LIVER: CLEAN}, new_event_dates={LIVER: set()})
    assert p.status == REOPEN
    assert "no longer present" in p.reason


# --- the size-blind-linker trigger ------------------------------------------
def test_measurement_that_moves_the_recist_category_reopens():
    """The linker matches on type/anatomy/laterality and nothing about size, so a lesion
    going 12mm -> 44mm links silently with no ambiguity and no split flag. Escalate on
    decision impact instead: re-attest identity exactly when the new evidence is what
    changes the answer."""
    (p,) = _plan(
        new_event_dates={LUNG: {"2024-02-05", "2025-08-18"}},
        category_moved=True,
    )
    assert p.status == REOPEN
    assert "RECIST category" in p.reason


def test_category_move_does_not_reopen_a_non_target_track():
    """The escalation is about target lesions driving the call; a non-target that merely
    gained evidence still only needs acknowledgement."""
    (p,) = _plan(
        new_event_dates={LUNG: {"2024-02-05", "2025-08-18"}},
        category_moved=True,
        target_keys=set(),
    )
    assert p.status == ACKNOWLEDGE


def test_category_move_without_new_evidence_still_carries():
    (p,) = _plan(category_moved=True)
    assert p.status == CARRY


# --- merged identities ------------------------------------------------------
def test_merged_identity_reopens_when_either_member_becomes_ambiguous():
    merged = _one("confirmed_liver", [LIVER, LUNG])
    (p,) = plan_identities(
        parent_confirmed=merged,
        parent_flags={LIVER: CLEAN, LUNG: CLEAN},
        new_flags={LIVER: CLEAN, LUNG: AMBIGUOUS},
        parent_event_dates={LIVER: {"2024-02-05"}, LUNG: {"2024-02-05"}},
        new_event_dates={LIVER: {"2024-02-05"}, LUNG: {"2024-02-05"}},
        category_moved=False,
        target_keys=set(),
    )
    assert p.status == REOPEN


def test_merged_identity_gains_events_from_any_member():
    merged = _one("confirmed_liver", [LIVER, LUNG])
    (p,) = plan_identities(
        parent_confirmed=merged,
        parent_flags={LIVER: CLEAN, LUNG: CLEAN},
        new_flags={LIVER: CLEAN, LUNG: CLEAN},
        parent_event_dates={LIVER: {"2024-02-05"}, LUNG: {"2024-02-05"}},
        new_event_dates={LIVER: {"2024-02-05", "2025-08-18"}, LUNG: {"2024-02-05"}},
        category_moved=False,
        target_keys=set(),
    )
    assert p.status == ACKNOWLEDGE
    assert p.gained_event_dates == ["2025-08-18"]


# --- the eleven-report demo shape -------------------------------------------
def test_demo_shape_three_targets_reopen_and_the_rest_carry():
    """Report 11 moves the call from PR to PD. The three target lesions that drove it are
    re-attested; the routine negatives that did not change are not re-litigated."""
    targets = [LUNG, LIVER, "adrenal_metastasis|adrenal|left"]
    negatives = [f"routine_negative_{i}|thorax|none" for i in range(6)]
    confirmed = [{"confirmed_track_key": k, "member_track_keys": [k]} for k in targets + negatives]
    flags = {k: CLEAN for k in targets + negatives}
    before = {k: {"2024-02-05"} for k in targets + negatives}
    after = {k: ({"2024-02-05", "2025-08-18"} if k in targets else {"2024-02-05"})
             for k in targets + negatives}

    plans = plan_identities(
        confirmed, flags, flags, before, after,
        category_moved=True, target_keys=set(targets),
    )
    by_status = {}
    for p in plans:
        by_status.setdefault(p.status, []).append(p.confirmed_track_key)

    assert sorted(by_status[REOPEN]) == sorted(targets)
    assert sorted(by_status[CARRY]) == sorted(negatives)
    assert ACKNOWLEDGE not in by_status
    assert NEW not in by_status
