"""
FindingFrame graph adapter.

This is the schema-transition layer for the frame path. It deliberately emits a
new graph shape with `tracks`, not legacy free-form `entities`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from extraction.finding_frame_schema import FINDING_FRAME_SCHEMA_VERSION, FindingFrame
from fact_graph.frame_linker import FRAME_LINKER_SCHEMA_VERSION, link_frame_events


FRAME_FACT_GRAPH_SCHEMA_VERSION = "finding_frame_graph_v1"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _event_hash(*parts: Any) -> str:
    joined = "|".join(_safe_str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _frame_from_any(frame: FindingFrame | dict[str, Any]) -> FindingFrame:
    if isinstance(frame, FindingFrame):
        return frame
    allowed = set(FindingFrame.model_fields)
    return FindingFrame.model_validate(
        {key: value for key, value in frame.items() if key in allowed}
    )


def finding_frame_to_event(
    frame: FindingFrame | dict[str, Any],
    *,
    report_date: str | None = None,
    study_type: str | None = None,
    frame_index: int = 1,
    source_kind: str = "checklist",
) -> dict[str, Any]:
    """Convert one FindingFrame into an append-only frame event."""
    source_payload = frame if isinstance(frame, dict) else frame.model_dump(mode="json")
    parsed = _frame_from_any(frame)
    frame_payload = parsed.model_dump(mode="json")
    date = report_date or _safe_str(source_payload.get("report_date")) or "Unknown"
    modality = study_type or _safe_str(source_payload.get("study_type")) or "Unknown"
    raw_track_key = parsed.track_key()
    track_key = _safe_str(source_payload.get("track_key")) or raw_track_key
    event_id = "frame_event_" + _event_hash(
        parsed.source_report_id,
        track_key,
        frame_index,
        parsed.evidence_text,
    )
    return {
        "event_id": event_id,
        "track_key": track_key,
        "original_track_key": _safe_str(source_payload.get("original_track_key"))
        or raw_track_key,
        "finding_type": parsed.finding_type,
        "finding_surface": parsed.finding_surface,
        "assertion": parsed.assertion,
        "anatomy": parsed.anatomy,
        "laterality": parsed.laterality,
        "uncertainty": parsed.uncertainty,
        "temporal_change": parsed.temporal_change,
        "measurement": (
            parsed.measurement.model_dump(mode="json") if parsed.measurement else None
        ),
        "clinical_importance": parsed.clinical_importance,
        "source_report_id": parsed.source_report_id,
        "report_date": date,
        "study_type": modality,
        "evidence_text": parsed.evidence_text,
        "evidence_span_start": parsed.evidence_span_start,
        "evidence_span_end": parsed.evidence_span_end,
        "lesion_key": parsed.lesion_key,
        "review_only": parsed.review_only,
        "source_kind": source_kind,
        "frame_index": frame_index,
        "frame_schema_version": FINDING_FRAME_SCHEMA_VERSION,
    }


def events_to_tracks(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Link frame events into Phase 9 tracks and derive latest status."""
    return link_frame_events(events)["tracks"]


def frames_to_frame_fact_graph(
    *,
    subject_id: str,
    frames: list[FindingFrame | dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standalone FindingFrame fact graph artifact."""
    events: list[dict[str, Any]] = []
    for index, frame in enumerate(frames, start=1):
        source = frame if isinstance(frame, dict) else frame.model_dump(mode="json")
        events.append(
            finding_frame_to_event(
                frame,
                report_date=source.get("report_date"),
                study_type=source.get("study_type"),
                frame_index=int(source.get("frame_index", index) or index),
                source_kind=str(source.get("source_kind", "checklist")),
            )
        )
    link_result = link_frame_events(events)
    return {
        "schema_version": FRAME_FACT_GRAPH_SCHEMA_VERSION,
        "frame_schema_version": FINDING_FRAME_SCHEMA_VERSION,
        "linker_schema_version": FRAME_LINKER_SCHEMA_VERSION,
        "graph_type": "finding_frame",
        "subject_id": str(subject_id),
        "created_at": datetime.now().isoformat(),
        "metadata": dict(metadata or {}),
        "events": link_result["events"],
        "tracks": link_result["tracks"],
        "unresolved_link_queue": link_result["unresolved_link_queue"],
        "false_split_candidates": link_result["false_split_candidates"],
        "link_summary": link_result["summary"],
    }


def write_frame_fact_graph(graph: dict[str, Any], path: str | Path) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(destination)
