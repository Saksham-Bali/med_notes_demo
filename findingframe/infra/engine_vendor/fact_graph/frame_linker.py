"""Deterministic longitudinal linker for FindingFrame events.

Phase 9 links single-report frame events into longitudinal tracks without
paired-report LLM extraction. The linker is conservative: compatible anatomy
and laterality can merge frames, but ambiguous matches are sent to an explicit
review queue instead of being forced into an existing track.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from extraction.frame_slot_normalizer import normalize_anatomy_for_linking


FRAME_LINKER_SCHEMA_VERSION = "finding_frame_linker_v1"

_UNKNOWN_ANATOMY = {"", "unknown", "not_stated", "not_applicable", "none"}
_UNKNOWN_LATERALITY = {"", "unknown", "none", "not_applicable", "na", "n_a"}
_BILATERAL_LATERALITY = {"bilateral", "both"}

_ANATOMY_PARENTS: dict[str, set[str]] = {
    "pleural_space": {"thorax"},
    "heart": {"thorax"},
    "lung": {"thorax"},
    "thorax": set(),
    "rib": {"bone", "thorax"},
    "sternum": {"bone", "thorax"},
    "spine": {"bone"},
    "lateral_malleolus": {"bone", "extremity"},
    "femoral_region": {"extremity"},
    "bone": set(),
    "intracranial": {"head_neck"},
    "liver": {"abdomen"},
    "kidney": {"abdomen"},
    "renal_collecting_system": {"kidney", "abdomen"},
    "peritoneum": {"abdomen"},
    "aorta": {"abdomen"},
    "abdomen": set(),
    "pelvis": set(),
    "deep_vein": {"extremity"},
}

_DEFAULT_ANATOMY_BY_TYPE: dict[str, str] = {
    "ascites": "peritoneum",
    "cardiomegaly": "heart",
    "hepatomegaly": "liver",
    "hydronephrosis": "kidney",
    "liver_metastasis": "liver",
    "lung_metastasis": "thorax",
    "brain_metastasis": "intracranial",
    "pleural_effusion": "pleural_space",
    "pneumothorax": "pleural_space",
    "pulmonary_embolism": "thorax",
}

_SIDELESS_TYPES = {
    "ascites",
    "cardiomegaly",
    "hepatomegaly",
}

_GLOBAL_ABSENT_TYPES = {
    "bone_metastasis",
    "fracture",
    "hemorrhage",
    "hydronephrosis",
    "lymph_node_metastasis",
    "pneumothorax",
    "pulmonary_embolism",
}


def _is_catch_all_or_review_only(event: dict[str, Any]) -> bool:
    return (
        _normalize_token(event.get("finding_type")) == "other_important_finding"
        or _normalize_token(event.get("source_kind")) == "catch_all"
        or bool(event.get("review_only"))
    )


def _link_family_for_event(event: dict[str, Any]) -> str:
    """Return an optional sub-identity family for broad classes."""
    finding_type = _normalize_token(event.get("finding_type"))
    text = " ".join(
        [
            _normalize_token(event.get("finding_surface")),
            _normalize_token(event.get("evidence_text")),
            _normalize_token(event.get("anatomy")),
        ]
    )
    if finding_type == "device_or_line":
        if "ekg" in text or "ecg" in text:
            return "ekg_leads"
        if "sternal" in text or "sternotomy" in text:
            return "sternal_wires"
        if "foley" in text or "urinary_bladder" in text:
            return "foley_catheter"
        if "jugular" in text or "central_line" in text or "svc" in text:
            return "central_line"
        if (
            "graft" in text
            or "stent" in text
            or "bypass" in text
            or "aorta" in text
            or "femoral" in text
        ):
            return "vascular_graft"
    return ""


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_token(value: Any) -> str:
    text = _safe_str(value).strip().lower()
    return "_".join(text.replace("-", " ").split())


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str, int]:
    return (
        _safe_str(event.get("report_date")),
        _safe_str(event.get("source_report_id")),
        int(event.get("frame_index", 0) or 0),
    )


def _latest_status(assertion: str, had_prior_present: bool) -> str:
    if assertion == "present":
        return "active"
    if assertion == "absent":
        return "resolved" if had_prior_present else "absent"
    if assertion == "uncertain":
        return "uncertain"
    return "not_mentioned"


def _ancestor_set(anatomy: str) -> set[str]:
    ancestors: set[str] = set()
    queue = list(_ANATOMY_PARENTS.get(anatomy, set()))
    while queue:
        parent = queue.pop()
        if parent in ancestors:
            continue
        ancestors.add(parent)
        queue.extend(_ANATOMY_PARENTS.get(parent, set()))
    return ancestors


def link_anatomy_for_event(event: dict[str, Any]) -> str:
    """Return the normalized anatomy used for longitudinal compatibility."""
    finding_type = _normalize_token(event.get("finding_type"))
    raw = _normalize_token(event.get("anatomy"))
    if raw in _UNKNOWN_ANATOMY:
        return "unknown"

    canonical = normalize_anatomy_for_linking(
        finding_type=finding_type,
        anatomy=raw,
        assertion=event.get("assertion") or "",
        evidence_text=event.get("evidence_text") or "",
        finding_surface=event.get("finding_surface") or "",
    )
    default = _DEFAULT_ANATOMY_BY_TYPE.get(finding_type)
    if default and canonical in {"thorax", "abdomen", "pelvis", "unknown"}:
        return default
    if finding_type in {"pleural_effusion", "pneumothorax"} and (
        "pleura" in raw or canonical == "thorax"
    ):
        return "pleural_space"
    if finding_type == "hydronephrosis" and canonical in {
        "kidney",
        "renal_collecting_system",
    }:
        return "kidney"
    return canonical


def link_laterality_for_event(event: dict[str, Any]) -> str:
    """Return the normalized laterality used for longitudinal compatibility."""
    finding_type = _normalize_token(event.get("finding_type"))
    assertion = _normalize_token(event.get("assertion"))
    laterality = _normalize_token(event.get("laterality"))
    if laterality in {"na", "n_a", "none"}:
        laterality = "not_applicable"
    if finding_type in _SIDELESS_TYPES:
        return "not_applicable"
    if (
        assertion == "absent"
        and finding_type in _GLOBAL_ABSENT_TYPES
        and laterality in _UNKNOWN_LATERALITY | _BILATERAL_LATERALITY
    ):
        return "not_applicable"
    return laterality or "unknown"


def _anatomy_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    if left in _UNKNOWN_ANATOMY or right in _UNKNOWN_ANATOMY:
        return False
    return left in _ancestor_set(right) or right in _ancestor_set(left)


def _laterality_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    if left in _UNKNOWN_LATERALITY or right in _UNKNOWN_LATERALITY:
        return True
    return False


def _explicit_lesion_key(event: dict[str, Any]) -> str:
    lesion_key = _normalize_token(event.get("lesion_key"))
    if lesion_key in {"", "none", "null", "unknown", "unresolved_link"}:
        return ""
    return lesion_key


def _event_base_track_key(event: dict[str, Any]) -> str:
    parts = [
        _normalize_token(event.get("finding_type")) or "unknown",
        link_anatomy_for_event(event),
        link_laterality_for_event(event),
    ]
    lesion_key = _explicit_lesion_key(event)
    if lesion_key:
        parts.append(lesion_key)
    else:
        link_family = _link_family_for_event(event)
        if link_family:
            parts.append(link_family)
    if not lesion_key and _is_catch_all_or_review_only(event):
        parts.extend(["review_only", _event_identity(event)])
    return "|".join(parts)


def _event_identity(event: dict[str, Any]) -> str:
    return "|".join(
        [
            _safe_str(event.get("source_report_id")),
            _safe_str(event.get("source_kind")),
            _safe_str(event.get("frame_index")),
        ]
    )


def _compatible_track_keys(
    event: dict[str, Any],
    track_states: dict[str, dict[str, Any]],
) -> list[str]:
    finding_type = _normalize_token(event.get("finding_type"))
    anatomy = link_anatomy_for_event(event)
    laterality = link_laterality_for_event(event)
    lesion_key = _explicit_lesion_key(event)
    event_link_family = _link_family_for_event(event)

    if _is_catch_all_or_review_only(event) and not lesion_key:
        return []

    candidates: list[str] = []
    for track_key, state in track_states.items():
        if state.get("unresolved_link"):
            continue
        if state["finding_type"] != finding_type:
            continue
        track_lesion = _safe_str(state.get("lesion_key"))
        if lesion_key or track_lesion:
            if lesion_key != track_lesion:
                continue
        track_link_family = _safe_str(state.get("link_family"))
        if event_link_family or track_link_family:
            if event_link_family != track_link_family:
                continue
        if state.get("review_only_seed") and not lesion_key:
            continue
        if not _anatomy_compatible(anatomy, state["link_anatomy"]):
            continue
        if not _laterality_compatible(laterality, state["link_laterality"]):
            continue
        candidates.append(track_key)
    return sorted(candidates)


def _track_from_events(track_key: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_events = sorted(events, key=_event_sort_key)
    latest = sorted_events[-1]
    prior = sorted_events[:-1]
    had_prior_present = any(event.get("assertion") == "present" for event in prior)
    latest_status = _latest_status(
        _safe_str(latest.get("assertion")),
        had_prior_present=had_prior_present,
    )
    link_decisions = Counter(_safe_str(event.get("link_decision")) for event in sorted_events)
    original_track_keys = sorted(
        {
            _safe_str(event.get("original_track_key") or event.get("track_key"))
            for event in sorted_events
            if _safe_str(event.get("original_track_key") or event.get("track_key"))
        }
    )
    unresolved = any(event.get("link_status") == "unresolved_link" for event in sorted_events)
    latest_lesion = latest.get("lesion_key")
    return {
        "track_key": track_key,
        "finding_type": latest.get("finding_type"),
        "anatomy": latest.get("anatomy"),
        "laterality": latest.get("laterality"),
        "link_anatomy": latest.get("link_anatomy"),
        "link_laterality": latest.get("link_laterality"),
        "link_family": latest.get("link_family"),
        "lesion_key": latest_lesion,
        "event_count": len(sorted_events),
        "latest_report_id": latest.get("source_report_id"),
        "latest_report_date": latest.get("report_date"),
        "latest_assertion": latest.get("assertion"),
        "latest_status": latest_status,
        "unresolved_link": unresolved,
        "review_required": unresolved,
        "original_track_keys": original_track_keys,
        "link_decision_counts": dict(sorted(link_decisions.items())),
        "contains_compatible_merges": len(original_track_keys) > 1,
        "events": sorted_events,
    }


def _false_split_candidates(tracks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    items = sorted(tracks.items())
    for index, (left_key, left) in enumerate(items):
        if left.get("unresolved_link"):
            continue
        if _normalize_token(left.get("finding_type")) == "other_important_finding":
            continue
        if any(event.get("review_only") for event in left.get("events") or []):
            continue
        for right_key, right in items[index + 1 :]:
            if right.get("unresolved_link"):
                continue
            if _normalize_token(right.get("finding_type")) == "other_important_finding":
                continue
            if any(event.get("review_only") for event in right.get("events") or []):
                continue
            if left.get("finding_type") != right.get("finding_type"):
                continue
            if not _anatomy_compatible(
                _safe_str(left.get("link_anatomy")),
                _safe_str(right.get("link_anatomy")),
            ):
                continue
            if not _laterality_compatible(
                _safe_str(left.get("link_laterality")),
                _safe_str(right.get("link_laterality")),
            ):
                continue
            candidates.append(
                {
                    "left_track_key": left_key,
                    "right_track_key": right_key,
                    "finding_type": left.get("finding_type"),
                    "reason": "same_type_compatible_anatomy_laterality",
                }
            )
    return candidates


def link_frame_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Link frame events into longitudinal tracks and unresolved review items."""
    indexed_events = [
        (index, dict(event))
        for index, event in enumerate(events)
    ]
    original_track_count = len(
        {
            _safe_str(event.get("track_key"))
            for _, event in indexed_events
            if _safe_str(event.get("track_key"))
        }
    )

    track_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    track_states: dict[str, dict[str, Any]] = {}
    unresolved_queue: list[dict[str, Any]] = []
    decisions: Counter[str] = Counter()
    linked_by_original_index: dict[int, dict[str, Any]] = {}

    for original_index, event in sorted(indexed_events, key=lambda item: _event_sort_key(item[1])):
        original_track_key = _safe_str(event.get("track_key")) or _event_base_track_key(event)
        event["original_track_key"] = original_track_key
        event["linker_schema_version"] = FRAME_LINKER_SCHEMA_VERSION
        event["link_anatomy"] = link_anatomy_for_event(event)
        event["link_laterality"] = link_laterality_for_event(event)
        event["link_family"] = _link_family_for_event(event)
        base_track_key = _event_base_track_key(event)
        explicit_unresolved = _normalize_token(event.get("lesion_key")) == "unresolved_link"

        if explicit_unresolved:
            candidates = _compatible_track_keys(event, track_states)
            track_key = f"{base_track_key}|unresolved_link|{_event_identity(event)}"
            event["track_key"] = track_key
            event["link_status"] = "unresolved_link"
            event["link_decision"] = "explicit_unresolved_link"
            event["link_reason"] = "source frame marked lesion_key=unresolved_link"
            event["link_candidate_track_keys"] = candidates
            event["link_review_required"] = True
        else:
            candidates = _compatible_track_keys(event, track_states)
            exact_candidates = [
                key for key in candidates if key in {base_track_key, original_track_key}
            ]
            if len(candidates) == 0:
                track_key = base_track_key
                event["track_key"] = track_key
                event["link_status"] = "new_track"
                event["link_decision"] = "new_track"
                event["link_reason"] = "no compatible prior track"
                event["link_candidate_track_keys"] = []
                event["link_review_required"] = False
            elif len(exact_candidates) == 1:
                track_key = exact_candidates[0]
                event["track_key"] = track_key
                event["link_status"] = "linked"
                event["link_decision"] = "exact_key"
                event["link_reason"] = "matched existing exact track key"
                event["link_candidate_track_keys"] = candidates
                event["link_review_required"] = False
            elif len(candidates) == 1:
                track_key = candidates[0]
                event["track_key"] = track_key
                event["link_status"] = "linked"
                event["link_decision"] = "compatible_merge"
                event["link_reason"] = "single compatible prior track"
                event["link_candidate_track_keys"] = candidates
                event["link_review_required"] = False
            else:
                track_key = f"{base_track_key}|unresolved_link|{_event_identity(event)}"
                event["track_key"] = track_key
                event["link_status"] = "unresolved_link"
                event["link_decision"] = "ambiguous_compatible_tracks"
                event["link_reason"] = "multiple compatible prior tracks; review required"
                event["link_candidate_track_keys"] = candidates
                event["link_review_required"] = True

        decisions[_safe_str(event["link_decision"])] += 1
        track_events[event["track_key"]].append(event)
        track_states[event["track_key"]] = {
            "finding_type": _normalize_token(event.get("finding_type")),
            "link_anatomy": event["link_anatomy"],
            "link_laterality": event["link_laterality"],
            "link_family": event["link_family"],
            "lesion_key": _explicit_lesion_key(event),
            "unresolved_link": event["link_status"] == "unresolved_link",
            "review_only_seed": _is_catch_all_or_review_only(event),
        }
        if event["link_status"] == "unresolved_link":
            queue_item = {
                "queue_id": f"unresolved_{len(unresolved_queue) + 1}",
                "track_key": event["track_key"],
                "source_report_id": event.get("source_report_id"),
                "frame_index": event.get("frame_index"),
                "finding_type": event.get("finding_type"),
                "finding_surface": event.get("finding_surface"),
                "anatomy": event.get("anatomy"),
                "laterality": event.get("laterality"),
                "assertion": event.get("assertion"),
                "evidence_text": event.get("evidence_text"),
                "candidate_track_keys": list(event.get("link_candidate_track_keys") or []),
                "reason": event.get("link_reason"),
            }
            unresolved_queue.append(queue_item)
        linked_by_original_index[original_index] = event

    linked_events = [linked_by_original_index[index] for index, _ in indexed_events]
    tracks = {
        track_key: _track_from_events(track_key, events_for_track)
        for track_key, events_for_track in sorted(track_events.items())
    }
    false_split_candidates = _false_split_candidates(tracks)
    summary = {
        "linker_schema_version": FRAME_LINKER_SCHEMA_VERSION,
        "input_event_count": len(events),
        "original_track_count": original_track_count,
        "track_count": len(tracks),
        "review_queue_count": len(unresolved_queue),
        "unresolved_link_count": len(unresolved_queue),
        "link_decision_counts": dict(sorted(decisions.items())),
        "compatible_merge_count": decisions.get("compatible_merge", 0),
        "exact_link_count": decisions.get("exact_key", 0),
        "new_track_count": decisions.get("new_track", 0),
        "false_split_candidate_count": len(false_split_candidates),
    }
    return {
        "schema_version": FRAME_LINKER_SCHEMA_VERSION,
        "events": linked_events,
        "tracks": tracks,
        "unresolved_link_queue": unresolved_queue,
        "false_split_candidates": false_split_candidates,
        "summary": summary,
    }
