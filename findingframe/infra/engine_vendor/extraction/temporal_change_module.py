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
   evidence span via ``normalize_temporal_change_for_scoring``.
3. Measurement differences - within the same longitudinal track, the current
   measurement is compared to the previous measurement. A relative change
   greater than 10% yields ``increased`` / ``decreased``; within +/-10%
   yields ``stable``.
4. Assertion transitions - absent -> present yields ``new``, present ->
   absent yields ``resolved``, present throughout yields ``stable`` (unless a
   measurement delta already determined otherwise).

Important invariants:

* The first occurrence of a finding is NEVER automatically labelled ``new``.
  ``new`` is only assigned through explicit "new" language or an
  absent -> present assertion transition.
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
    """Use the shared scoring normalizer to read explicit comparison cues."""
    label = normalize_temporal_change_for_scoring(
        temporal_change=frame.get("temporal_change") or "not_stated",
        evidence_text=frame.get("evidence_text") or "",
        finding_surface=frame.get("finding_surface") or "",
        assertion=frame.get("assertion") or "present",
        finding_type=frame.get("finding_type") or "",
        source_report_id=frame.get("source_report_id") or "",
        anatomy=frame.get("anatomy") or "unknown",
    )
    return label if label != "not_stated" else None


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
    """Determine a temporal label from assertion state changes."""
    prior = str(previous.get("assertion") or "present").lower()
    now = str(current.get("assertion") or "present").lower()
    if prior == "absent" and now == "present":
        return "new", f"{prior}->{now}"
    if prior == "present" and now == "absent":
        return "resolved", f"{prior}->{now}"
    if prior == "present" and now == "present":
        return "stable", f"{prior}->{now} (present throughout)"
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