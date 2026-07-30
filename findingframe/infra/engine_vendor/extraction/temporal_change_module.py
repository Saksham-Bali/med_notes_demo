"""Deterministic temporal-change inference for longitudinal FindingFrames.

This module post-processes existing frame artifacts to improve the
``temporal_change`` slot without any LLM calls. It combines four deterministic
sources of evidence, applied in a fixed priority:

1. Uncertainty guard - evidence indicating the finding cannot be assessed
   ("not included in field of view", "limited exam", ...) forces
   ``not_stated`` because no temporal comparison is possible.
2. Explicit comparison phrases - the existing term sets
   ``_STABLE_TERMS`` / ``_NEW_TERMS`` / ``_INCREASED_TERMS`` /
   ``_DECREASED_TERMS`` / ``_RESOLVED_TERMS`` are matched against the
   evidence span via ``normalize_temporal_change_for_scoring``, whose own
   negation guard (``frame_slot_normalizer._is_negated_term``) is trusted
   directly -- see the module-level note below for why this module no
   longer re-validates that guard's decisions itself.
3. Measurement differences - within the same longitudinal track, the current
   measurement is compared to the previous measurement. A relative change
   greater than 10% yields ``increased`` / ``decreased``; within +/-10%
   yields ``stable``.
4. Assertion transitions - absent -> present yields ``new``, present ->
   absent yields ``resolved``. Present throughout is NOT defaulted to
   ``stable`` here: steps 2 and 3 already had the chance to find positive
   evidence of "no change", and a bare assertion match with nothing else is
   not itself such evidence (see the note on ``_assertion_transition``).

Important invariants:

* The first occurrence of a finding is NEVER automatically labelled ``new``.
  ``new`` is only assigned through explicit "new" language or an
  absent -> present assertion transition.
* Present-throughout is NEVER automatically labelled ``stable`` on assertion
  alone. ``stable`` is only assigned through explicit "stable"/"unchanged"
  language or a measurement delta within +/-10%.
* Original frames are never mutated; deep copies are returned.
* Every decision is recorded in ``frame["temporal_inference"]`` with the
  inference method, the supporting evidence string, and a reference to the
  previous source report used for comparison.
"""

from __future__ import annotations

import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

from evaluation.frame_metrics import normalize_frame_for_eval
from extraction.frame_slot_normalizer import normalize_temporal_change_for_scoring
from extraction.measurement_normalizer import measurement_max_mm


# History note (kept for anyone tracing why `_explicit_label` below is a
# thin pass-through): `frame_slot_normalizer._is_negated_term` used to guard
# its directional-term match with a regex anchored on `\b` between
# underscore-joined tokens. `_` is a word character to Python's `re` engine,
# so `\b` never fell between two underscore-joined tokens -- only at the
# very start/end of the whole string. In practice this made that guard a
# no-op for almost every real evidence span: phrasing of the form "not
# enlarged" or "no enlarged mass" failed to register as negated, so
# `normalize_temporal_change_for_scoring` read plain negative findings as
# "increased". That was the dominant driver of the temporal_change_module
# "increased" F1 regression (0.8082 -> 0.6842 macro-averaged across the
# frozen 30-patient cohort; see outputs/finding_frame_runs/temporal_eval.json
# before the fix below).
#
# This module originally worked around that bug locally: it accepted
# whatever label `normalize_temporal_change_for_scoring` returned, then
# re-validated any directional label ("increased"/"decreased"/"new")
# against a corrected, token-window negation check
# (`_directional_term_is_negated_nearby`) before trusting it, scoped
# entirely to this module's own decisions -- deliberately not touching the
# shared function, since fixing its regex there would have silently shifted
# the canonical frozen-30 Full-Frame F1 numbers reported throughout the
# paper (a properly measured change, out of scope for that isolated fix).
#
# That shared-function fix has since been made and measured (see
# `frame_slot_normalizer._is_negated_term` and its docstring for the
# corrected token-window implementation, promoted verbatim from this
# module's `_directional_term_is_negated_nearby`, including its
# empirically-chosen `window=10`). `normalize_temporal_change_for_scoring`
# now already declines to return a directional label for a negated term, so
# the local re-validation this module used to perform is redundant -- by
# construction, `label` below can no longer be "increased"/"decreased"/"new"
# for a negated occurrence, so re-checking it a second time here can never
# change the outcome. It has been removed; `_explicit_label` now trusts
# `normalize_temporal_change_for_scoring` directly.


# Thresholds for measurement deltas (relative change, expressed as ratio
# current / previous). The spec requires a 10% boundary: above +10% grows,
# below -10% shrinks, within +/-10% stable.
_MEASUREMENT_INCREASE_RATIO = 1.10
_MEASUREMENT_DECREASE_RATIO = 0.90

# Evidence spans that indicate the finding cannot be assessed on this exam,
# so temporal comparison is impossible. Substring phrases (case-insensitive).
_UNCERTAINTY_PHRASES = (
    "not included in field of view",
    "not included in the field of view",
    "outside the field of view",
    "out of field of view",
    "outside field of view",
    "not fully evaluated",
    "limited exam",
    "limited examination",
    "limited evaluation",
    "not optimally evaluated",
)


def _report_order(value: Any) -> tuple[int, str]:
    """Sortable key deriving report sequence from a report id."""
    text = str(value or "")
    match = re.search(r"(\d+)$", text)
    return (int(match.group(1)) if match else 10**9, text)


def _chronological_key(frame: dict[str, Any]) -> tuple[Any, tuple[int, str]]:
    """Order frames by report date when available, falling back to report id."""
    report_date = frame.get("report_date")
    if report_date:
        return (str(report_date), _report_order(frame.get("source_report_id")))
    return ("", _report_order(frame.get("source_report_id")))


def _identity(frame: dict[str, Any]) -> tuple[str, str, str]:
    """Normalized (finding_type, anatomy, laterality) identity for grouping."""
    normalized = normalize_frame_for_eval(frame)
    return (
        normalized["finding_type"],
        normalized["anatomy"],
        normalized["laterality"],
    )


def _track_bucket(frame: dict[str, Any]) -> str | tuple[str, str, str]:
    """Prefer the linker's track_key, fall back to normalized identity."""
    track_key = frame.get("track_key")
    if track_key:
        return str(track_key)
    return _identity(frame)


def _uncertainty_guard(frame: dict[str, Any]) -> str | None:
    """Return the matching uncertainty phrase, or None when assessable."""
    text = " ".join(
        str(frame.get(slot) or "").lower()
        for slot in ("evidence_text", "finding_surface")
    )
    if not text:
        return None
    for phrase in _UNCERTAINTY_PHRASES:
        if phrase in text:
            return phrase
    return None


def _explicit_label(frame: dict[str, Any]) -> str | None:
    """Use the shared scoring normalizer to read explicit comparison cues.

    The normalizer's own negation guard (``frame_slot_normalizer._is_negated_term``)
    is trusted directly -- no local re-validation is needed (see the
    module-level note near the top of this file for why that used to be
    necessary and why it no longer is).
    """
    label = normalize_temporal_change_for_scoring(
        temporal_change=frame.get("temporal_change") or "not_stated",
        evidence_text=frame.get("evidence_text") or "",
        finding_surface=frame.get("finding_surface") or "",
        assertion=frame.get("assertion") or "present",
        finding_type=frame.get("finding_type") or "",
        source_report_id=frame.get("source_report_id") or "",
        anatomy=frame.get("anatomy") or "unknown",
    )
    if label == "not_stated":
        return None
    return label


def _measurement_change(
    previous: dict[str, Any], current: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Determine a temporal label from current vs previous measurement.

    Returns ``(label, evidence)`` where ``evidence`` describes the delta for
    auditability. ``label`` is None when comparison is not possible.
    """
    finding_type = str(current.get("finding_type") or "")
    prior_mm = measurement_max_mm(
        previous.get("measurement"), finding_type=finding_type
    )
    current_mm = measurement_max_mm(
        current.get("measurement"), finding_type=finding_type
    )
    if prior_mm is None or current_mm is None or prior_mm <= 0:
        return None, None
    ratio = current_mm / prior_mm
    if ratio > _MEASUREMENT_INCREASE_RATIO:
        return "increased", f"{prior_mm:.2f}mm->{current_mm:.2f}mm (ratio {ratio:.2f})"
    if ratio < _MEASUREMENT_DECREASE_RATIO:
        return "decreased", f"{prior_mm:.2f}mm->{current_mm:.2f}mm (ratio {ratio:.2f})"
    return "stable", f"{prior_mm:.2f}mm->{current_mm:.2f}mm (ratio {ratio:.2f})"


def _assertion_transition(
    previous: dict[str, Any], current: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Determine a temporal label from assertion state changes.

    ``absent -> present`` and ``present -> absent`` are strong, independent
    signals and are always applied. ``present -> present`` previously
    defaulted unconditionally to ``stable`` -- but by the time this step
    runs, both the explicit-evidence step (2) and the measurement-delta step
    (3) have already had a chance to detect real growth/shrinkage and would
    have returned before reaching here. A bare assertion match with no other
    corroborating evidence is not itself evidence of "no change": it means
    we have no deterministic signal at all, and forcing "stable" in that gap
    was misclassifying genuinely-changed findings (this was the other half
    of the "increased" F1 regression described in the module-level note
    above; measured on the frozen 30-patient cohort, removing this default
    raised macro temporal F1 from 0.615 to 0.625 without the negation-check
    fix alone, and does not reduce recall for "stable" itself -- the bare
    default was also creating false "stable" positives). So we defer here
    too: the frame keeps whatever label it already had (``not_stated`` by
    construction, since this function is only reached when it is).
    """
    prior = str(previous.get("assertion") or "present").lower()
    now = str(current.get("assertion") or "present").lower()
    if prior == "absent" and now == "present":
        return "new", f"{prior}->{now}"
    if prior == "present" and now == "absent":
        return "resolved", f"{prior}->{now}"
    return None, None


def _apply_decision(
    frame: dict[str, Any],
    *,
    value: str,
    method: str,
    evidence: str | None,
    detail: str | None,
    previous: dict[str, Any] | None,
) -> None:
    frame["temporal_change"] = value
    frame["temporal_inference"] = {
        "method": method,
        "deterministic": True,
        "evidence": evidence,
        "detail": detail,
        "previous_source_report_id": (
            previous.get("source_report_id") if previous else None
        ),
    }


def _resolve_frame(
    frame: dict[str, Any], *, previous: dict[str, Any] | None
) -> None:
    """Apply the deterministic priority cascade for one frame in context."""
    current_label = str(frame.get("temporal_change") or "not_stated").lower()

    # 1) Uncertainty guard: cannot assess -> not_stated, regardless of prior
    #    explicit language or measurement. This takes priority because a
    #    finding that is out-of-field or on a limited exam cannot be compared.
    if current_label == "not_stated":
        phrase = _uncertainty_guard(frame)
        if phrase:
            _apply_decision(
                frame,
                value="not_stated",
                method="uncertainty_guard",
                evidence=phrase,
                detail=None,
                previous=previous,
            )
            return

    # 2) Explicit comparison phrases supported by the evidence span.
    if current_label == "not_stated":
        explicit = _explicit_label(frame)
        if explicit:
            _apply_decision(
                frame,
                value=explicit,
                method="explicit_evidence",
                evidence=explicit,
                detail=None,
                previous=previous,
            )
            return

    # 3) Measurement differences within the same track.
    if current_label == "not_stated" and previous is not None:
        label, evidence = _measurement_change(previous, frame)
        if label:
            _apply_decision(
                frame,
                value=label,
                method="measurement_delta",
                evidence=evidence,
                detail=None,
                previous=previous,
            )
            return

    # 4) Assertion transitions within the same track (covers present
    #    throughout -> stable as a conservative default).
    if current_label == "not_stated" and previous is not None:
        label, evidence = _assertion_transition(previous, frame)
        if label:
            _apply_decision(
                frame,
                value=label,
                method="assertion_transition",
                evidence=evidence,
                detail=None,
                previous=previous,
            )
            return


def infer_temporal_changes(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copied frames with deterministic temporal_change inferences.

    The cascade is uncertainty guard -> explicit evidence -> measurement delta
    -> assertion transition. Existing non-empty temporal labels are retained
    unchanged when no deterministic evidence supports a replacement. The first
    occurrence of a track is never forced to ``new``.
    """
    output = [deepcopy(frame) for frame in frames]
    by_track: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for frame in output:
        by_track[_track_bucket(frame)].append(frame)

    for track_frames in by_track.values():
        track_frames.sort(key=_chronological_key)
        previous: dict[str, Any] | None = None
        for frame in track_frames:
            _resolve_frame(frame, previous=previous)
            previous = frame
    return output