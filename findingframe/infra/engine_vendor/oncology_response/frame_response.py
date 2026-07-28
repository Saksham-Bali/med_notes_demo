"""RECIST-like oncology response review aid over FindingFrame tracks.

This module does not implement formal RECIST. It produces cited, review-needed
labels from text-extracted longitudinal findings.
"""

from __future__ import annotations

from typing import Any

from extraction.measurement_normalizer import measurement_max_mm


MALIGNANT_FINDING_TYPES = {
    "primary_tumor",
    "liver_metastasis",
    "lung_metastasis",
    "bone_metastasis",
    "brain_metastasis",
    "lymph_node_metastasis",
}


def _safe_assertion(event: dict[str, Any]) -> str:
    return str(event.get("assertion") or "uncertain").lower()


def _measurement(event: dict[str, Any], finding_type: str) -> float | None:
    return measurement_max_mm(event.get("measurement"), finding_type=finding_type)


def _event_evidence(event: dict[str, Any]) -> dict[str, str]:
    return {
        "source_report_id": str(event.get("source_report_id") or ""),
        "report_date": str(event.get("report_date") or "")[:10],
        "evidence_text": str(event.get("evidence_text") or ""),
    }


def _track_citation(track: dict[str, Any]) -> dict[str, Any]:
    events = track.get("events") or []
    cited = [_event_evidence(event) for event in events if str(event.get("evidence_text") or "").strip()]
    return {
        "track_key": str(track.get("track_key") or ""),
        "finding_type": str(track.get("finding_type") or ""),
        "evidence": cited[:3],
    }


def classify_track(track: dict[str, Any]) -> dict[str, Any]:
    finding_type = str(track.get("finding_type") or "")
    events = sorted(
        track.get("events") or [],
        key=lambda event: (str(event.get("report_date") or ""), str(event.get("source_report_id") or "")),
    )
    measurements = [
        (_measurement(event, finding_type), event)
        for event in events
        if _safe_assertion(event) == "present"
    ]
    measurable = [(value, event) for value, event in measurements if value is not None]
    progression = str(track.get("progression") or track.get("latest_status") or "").lower()
    temporal_changes = {str(event.get("temporal_change") or "") for event in events}

    if finding_type in MALIGNANT_FINDING_TYPES and measurable:
        classification = "target_candidate"
    elif finding_type in MALIGNANT_FINDING_TYPES:
        classification = "non_target_disease"
    elif finding_type in {"pleural_effusion", "ascites", "pneumonia_or_infection"}:
        classification = "supporting_non_response"
    else:
        classification = "excluded"

    present_after_absent = False
    saw_absent = False
    for event in events:
        assertion = _safe_assertion(event)
        if assertion == "absent":
            saw_absent = True
        if assertion == "present" and saw_absent:
            present_after_absent = True

    new_lesion = finding_type in MALIGNANT_FINDING_TYPES and (
        "new" in temporal_changes or "new" in progression or present_after_absent
    )
    if new_lesion:
        classification = "new_lesion_candidate"

    baseline = measurable[0][0] if measurable else None
    latest = measurable[-1][0] if measurable else None
    nadir = min((value for value, _ in measurable), default=None)
    pct_from_baseline = None
    pct_from_nadir = None
    if baseline not in (None, 0) and latest is not None:
        pct_from_baseline = round(((latest - baseline) / baseline) * 100.0, 2)
    if nadir not in (None, 0) and latest is not None:
        pct_from_nadir = round(((latest - nadir) / nadir) * 100.0, 2)

    measurement_conflicts = []
    if len(measurable) >= 2:
        first_value = measurable[0][0]
        latest_value = measurable[-1][0]
        if "increased" in temporal_changes and latest_value < first_value:
            measurement_conflicts.append("temporal_increased_but_size_decreased")
        if "decreased" in temporal_changes and latest_value > first_value:
            measurement_conflicts.append("temporal_decreased_but_size_increased")
    if track.get("progression_detail") and "discordant" in str(track.get("progression_detail")).lower():
        measurement_conflicts.append("summary_marked_measurement_temporal_discordance")

    return {
        "track_key": str(track.get("track_key") or ""),
        "finding_type": finding_type,
        "classification": classification,
        "baseline_candidate_measurement_mm": baseline,
        "latest_candidate_measurement_mm": latest,
        "nadir_candidate_measurement_mm": nadir,
        "percent_change_from_baseline": pct_from_baseline,
        "percent_change_from_nadir": pct_from_nadir,
        "new_lesion_candidate": new_lesion,
        "non_target_qualitative_progression": finding_type in MALIGNANT_FINDING_TYPES
        and "increased" in temporal_changes
        and not measurable,
        "measurement_conflicts": sorted(set(measurement_conflicts)),
        "citation": _track_citation(track),
    }


def build_response_review(tracks: list[dict[str, Any]], subject_id: str) -> dict[str, Any]:
    classified = [classify_track(track) for track in tracks]
    cited = [item for item in classified if item["citation"]["evidence"]]
    conflicts = [item for item in cited if item["measurement_conflicts"]]
    new_lesions = [item for item in cited if item["new_lesion_candidate"]]
    non_target_pd = [item for item in cited if item["non_target_qualitative_progression"]]

    target_candidates = [item for item in cited if item["classification"] == "target_candidate"]
    measurable_progression = [
        item
        for item in target_candidates
        if item["percent_change_from_nadir"] is not None and item["percent_change_from_nadir"] >= 20.0
    ]
    measurable_improvement = [
        item
        for item in target_candidates
        if item["percent_change_from_baseline"] is not None and item["percent_change_from_baseline"] <= -30.0
    ]

    labels = []
    if conflicts or not cited:
        labels.append(
            {
                "label": "response_review_needed",
                "reason": "Measurement conflicts or missing cited evidence require review.",
                "citations": [item["citation"] for item in conflicts] or [],
            }
        )
    if new_lesions or non_target_pd or measurable_progression:
        labels.append(
            {
                "label": "possible_progression",
                "reason": "New malignant lesion candidate, non-target progression, or measurable increase surfaced.",
                "citations": [item["citation"] for item in (new_lesions + non_target_pd + measurable_progression)],
            }
        )
    elif measurable_improvement:
        labels.append(
            {
                "label": "possible_improvement",
                "reason": "Target-candidate measurements decreased from baseline.",
                "citations": [item["citation"] for item in measurable_improvement],
            }
        )
    elif cited:
        labels.append(
            {
                "label": "possible_stable_disease",
                "reason": "No new-lesion, qualitative progression, or target-candidate threshold change was detected.",
                "citations": [item["citation"] for item in cited[:5]],
            }
        )

    return {
        "schema_version": "recist_like_review_aid_v1",
        "label": "RECIST-like review aid",
        "formal_recist": False,
        "subject_id": str(subject_id),
        "track_count": len(tracks),
        "classified_tracks": classified,
        "response_labels": labels,
    }
