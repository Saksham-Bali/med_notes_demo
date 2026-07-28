"""Deterministic verifiers for telemetry emitted by pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pipeline_telemetry import PipelineTelemetry, TelemetryEvent


REQUIRED_EVENT_KEYS = {
    "event_id",
    "run_id",
    "sequence",
    "stage",
    "step",
    "status",
    "started_at",
    "ended_at",
    "duration_ms",
    "inputs",
    "outputs",
    "metrics",
    "checks",
    "warnings",
}

DEFAULT_REQUIRED_REPORT_STEPS = (
    ("report", "load"),
    ("report", "clean"),
    ("frame", "extract"),
    ("frame", "evidence_gate"),
    ("frame", "catch_all_review"),
)


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    message: str
    severity: str = "error"
    event_id: str | None = None
    report_id: str | None = None


@dataclass
class VerificationReport:
    issues: list[VerificationIssue] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def add(
        self,
        code: str,
        message: str,
        *,
        severity: str = "error",
        event_id: str | None = None,
        report_id: str | None = None,
    ) -> None:
        self.issues.append(
            VerificationIssue(
                code=code,
                message=message,
                severity=severity,
                event_id=event_id,
                report_id=report_id,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [issue.__dict__ for issue in self.issues],
            "summary": self.summary,
        }


def _coerce_events(events_or_path: Any) -> list[dict[str, Any]]:
    if isinstance(events_or_path, (str, Path)):
        return PipelineTelemetry.load_jsonl(events_or_path)
    events: list[dict[str, Any]] = []
    for event in events_or_path or []:
        if isinstance(event, TelemetryEvent):
            events.append(event.to_dict())
        elif isinstance(event, dict):
            events.append(event)
        else:
            events.append({"invalid_event": str(event)})
    return events


def verify_telemetry_events(
    events_or_path: Any,
    *,
    expected_report_ids: set[str] | None = None,
    required_report_steps: tuple[tuple[str, str], ...] = DEFAULT_REQUIRED_REPORT_STEPS,
) -> VerificationReport:
    """
    Verify telemetry completeness and internal consistency.

    This is not a clinical-quality verifier. It is a pipeline observability
    verifier: missing stages, broken counters, failed steps, and evidence-gate
    inconsistencies become explicit feedback before metric runs.
    """
    events = _coerce_events(events_or_path)
    report = VerificationReport(summary={"event_count": len(events)})
    if not events:
        report.add("telemetry.empty", "No telemetry events were emitted")
        return report

    sequences: list[int] = []
    report_ids_seen: set[str] = set()
    steps_by_report: dict[str, set[tuple[str, str]]] = {}
    step_counts: dict[str, int] = {}
    emitted_warning_count = 0

    for event in events:
        missing = REQUIRED_EVENT_KEYS - set(event)
        event_id = str(event.get("event_id", ""))
        report_id = event.get("report_id")
        emitted_warning_count += len(event.get("warnings") or [])
        if missing:
            report.add(
                "telemetry.missing_keys",
                f"Event is missing keys: {sorted(missing)}",
                event_id=event_id or None,
                report_id=str(report_id) if report_id else None,
            )
            continue

        try:
            sequences.append(int(event["sequence"]))
        except Exception:
            report.add("telemetry.bad_sequence", "Event sequence is not an integer", event_id=event_id)

        if event.get("status") not in {"completed", "failed"}:
            report.add("telemetry.bad_status", f"Bad event status: {event.get('status')}", event_id=event_id)

        duration = event.get("duration_ms")
        if duration is None or float(duration) < 0:
            report.add("telemetry.bad_duration", "Event duration must be non-negative", event_id=event_id)

        if event.get("status") == "failed" and not event.get("error"):
            report.add("telemetry.failed_without_error", "Failed event has no error payload", event_id=event_id)

        stage = str(event.get("stage"))
        step = str(event.get("step"))
        step_key = f"{stage}.{step}"
        step_counts[step_key] = step_counts.get(step_key, 0) + 1

        if report_id:
            report_id_str = str(report_id)
            report_ids_seen.add(report_id_str)
            steps_by_report.setdefault(report_id_str, set()).add((stage, step))

        if (stage, step) == ("frame", "evidence_gate"):
            _verify_evidence_gate_event(report, event)
        if (stage, step) == ("track", "build"):
            _verify_track_build_event(report, event)

    if sequences and sequences != sorted(sequences):
        report.add("telemetry.sequence_order", "Telemetry event sequences are not monotonic")
    if len(sequences) != len(set(sequences)):
        report.add("telemetry.sequence_duplicate", "Telemetry event sequences contain duplicates")

    required_pipeline_steps = {("pipeline", "start"), ("pipeline", "summary")}
    emitted_steps = {(str(e.get("stage")), str(e.get("step"))) for e in events}
    for stage_step in required_pipeline_steps:
        if stage_step not in emitted_steps:
            report.add(
                "telemetry.missing_pipeline_step",
                f"Missing pipeline step {stage_step[0]}.{stage_step[1]}",
            )

    expected = expected_report_ids or report_ids_seen
    for report_id in expected:
        emitted = steps_by_report.get(report_id, set())
        for required in required_report_steps:
            if required not in emitted:
                report.add(
                    "telemetry.missing_report_step",
                    f"Missing report step {required[0]}.{required[1]}",
                    report_id=report_id,
                )

    report.summary.update(
        {
            "reports_seen": sorted(report_ids_seen),
            "step_counts": step_counts,
            "error_count": sum(1 for issue in report.issues if issue.severity == "error"),
            "verifier_warning_count": sum(
                1 for issue in report.issues if issue.severity == "warning"
            ),
            "emitted_warning_count": emitted_warning_count,
            "warning_count": emitted_warning_count
            + sum(1 for issue in report.issues if issue.severity == "warning"),
        }
    )
    return report


REQUIRED_FRAME_KEYS = {
    "finding_type",
    "finding_surface",
    "assertion",
    "evidence_text",
    "anatomy",
    "laterality",
    "uncertainty",
    "temporal_change",
    "clinical_importance",
    "source_report_id",
    "track_key",
    "report_date",
    "source_kind",
}


def verify_frame_pipeline_artifact(artifact: dict[str, Any]) -> VerificationReport:
    """Verify the frame-to-track artifact emitted by FindingFramePatientProcessor."""
    report = VerificationReport(summary={})
    if not isinstance(artifact, dict):
        report.add("artifact.not_object", "Pipeline artifact is not an object")
        return report

    if "entities" in artifact:
        report.add(
            "artifact.legacy_entities_present",
            "Frame pipeline artifact must not contain legacy free-form entities",
        )

    for key in ("schema_version", "subject_id", "reports", "frames", "tracks", "metrics"):
        if key not in artifact:
            report.add("artifact.missing_key", f"Missing artifact key: {key}")

    reports = artifact.get("reports") or []
    frames = artifact.get("frames") or []
    tracks = artifact.get("tracks") or {}
    metrics = artifact.get("metrics") or {}
    if not isinstance(reports, list):
        report.add("artifact.bad_reports", "reports must be a list")
        reports = []
    if not isinstance(frames, list):
        report.add("artifact.bad_frames", "frames must be a list")
        frames = []
    if not isinstance(tracks, dict):
        report.add("artifact.bad_tracks", "tracks must be an object")
        tracks = {}

    attempted = int(artifact.get("reports_attempted") or 0)
    succeeded = int(artifact.get("reports_succeeded") or 0)
    failed = int(artifact.get("reports_failed") or 0)
    if attempted and succeeded + failed != attempted:
        report.add(
            "artifact.report_count_mismatch",
            "reports_succeeded + reports_failed must equal reports_attempted",
        )

    for report_payload in reports:
        if not isinstance(report_payload, dict):
            continue
        critical_ambiguities = [
            str(item) for item in report_payload.get("critical_ambiguities") or []
        ]
        if any("FindingFrame extraction failed" in item for item in critical_ambiguities):
            report.add(
                "artifact.report_extraction_failed",
                "Report extraction failure was recorded in a succeeded report",
                report_id=str(report_payload.get("report_id") or "") or None,
            )

    if int(metrics.get("frame_count") or 0) != len(frames):
        report.add("artifact.frame_count_mismatch", "metrics.frame_count does not match frames length")
    if int(metrics.get("track_count") or 0) != len(tracks):
        report.add("artifact.track_count_mismatch", "metrics.track_count does not match tracks length")

    frame_counts_by_track: dict[str, int] = {}
    for index, frame in enumerate(frames, start=1):
        if not isinstance(frame, dict):
            report.add("frame.not_object", f"Frame {index} is not an object")
            continue
        missing = REQUIRED_FRAME_KEYS - set(frame)
        track_key = str(frame.get("track_key", ""))
        if missing:
            report.add(
                "frame.missing_keys",
                f"Frame missing keys: {sorted(missing)}",
                report_id=str(frame.get("source_report_id") or "") or None,
            )
        if not track_key:
            report.add("frame.missing_track_key", "Frame has no track_key")
        else:
            frame_counts_by_track[track_key] = frame_counts_by_track.get(track_key, 0) + 1
            if track_key not in tracks:
                report.add(
                    "frame.track_missing",
                    f"Frame track_key is not present in tracks: {track_key}",
                    report_id=str(frame.get("source_report_id") or "") or None,
                )

        start = int(frame.get("evidence_span_start", -1) or -1)
        end = int(frame.get("evidence_span_end", -1) or -1)
        if (start >= 0 or end >= 0) and end <= start:
            report.add(
                "frame.bad_evidence_span",
                "Frame evidence span end must be greater than start",
                report_id=str(frame.get("source_report_id") or "") or None,
            )

        if frame.get("source_kind") == "catch_all" and not frame.get("review_only"):
            report.add(
                "frame.catch_all_not_review_only",
                "Catch-all frames must be review_only",
                report_id=str(frame.get("source_report_id") or "") or None,
            )

    for track_key, track in tracks.items():
        if not isinstance(track, dict):
            report.add("track.not_object", f"Track is not an object: {track_key}")
            continue
        events = track.get("events") or []
        if not isinstance(events, list):
            report.add("track.bad_events", f"Track events must be a list: {track_key}")
            continue
        if int(track.get("event_count") or 0) != len(events):
            report.add("track.event_count_mismatch", f"event_count mismatch for {track_key}")
        if frame_counts_by_track.get(str(track_key), 0) != len(events):
            report.add(
                "track.frame_count_mismatch",
                f"Track event count does not match frames for {track_key}",
            )
        if not events:
            continue
        events_sorted = sorted(
            events,
            key=lambda item: (
                str(item.get("report_date", "")),
                str(item.get("source_report_id", "")),
                int(item.get("frame_index", 0) or 0),
            ),
        )
        latest = events_sorted[-1]
        prior = events_sorted[:-1]
        expected_status = _expected_latest_status(
            str(latest.get("assertion", "uncertain")),
            had_prior_present=any(item.get("assertion") == "present" for item in prior),
        )
        if track.get("latest_assertion") != latest.get("assertion"):
            report.add(
                "track.latest_assertion_mismatch",
                f"Latest assertion mismatch for {track_key}",
            )
        if track.get("latest_status") != expected_status:
            report.add(
                "track.latest_status_mismatch",
                f"Latest status mismatch for {track_key}: expected {expected_status}",
            )

    report.summary.update(
        {
            "reports": len(reports),
            "frames": len(frames),
            "tracks": len(tracks),
            "error_count": sum(1 for issue in report.issues if issue.severity == "error"),
            "warning_count": sum(1 for issue in report.issues if issue.severity == "warning"),
        }
    )
    return report


def _expected_latest_status(assertion: str, had_prior_present: bool) -> str:
    if assertion == "present":
        return "active"
    if assertion == "absent":
        return "resolved" if had_prior_present else "absent"
    if assertion == "uncertain":
        return "uncertain"
    return "not_mentioned"


def _verify_evidence_gate_event(report: VerificationReport, event: dict[str, Any]) -> None:
    outputs = event.get("outputs") or {}
    checks = event.get("checks") or {}
    event_id = str(event.get("event_id", ""))
    report_id = str(event.get("report_id", ""))

    required = {"frames_total", "source_verifiable_count", "invalid_evidence_count"}
    missing = required - set(outputs)
    if missing:
        report.add(
            "evidence_gate.missing_counts",
            f"Evidence gate missing counts: {sorted(missing)}",
            event_id=event_id,
            report_id=report_id,
        )
        return

    total = int(outputs.get("frames_total") or 0)
    source_verifiable = int(outputs.get("source_verifiable_count") or 0)
    invalid = int(outputs.get("invalid_evidence_count") or 0)
    if source_verifiable > total:
        report.add(
            "evidence_gate.count_overflow",
            "Source-verifiable count exceeds total frames",
            event_id=event_id,
            report_id=report_id,
        )
    if invalid > total:
        report.add(
            "evidence_gate.invalid_overflow",
            "Invalid evidence count exceeds total frames",
            event_id=event_id,
            report_id=report_id,
        )
    frame_checks = checks.get("frames")
    if frame_checks is not None and len(frame_checks) != total:
        report.add(
            "evidence_gate.frame_check_mismatch",
            "Per-frame evidence checks do not match frames_total",
            event_id=event_id,
            report_id=report_id,
        )


def _verify_track_build_event(report: VerificationReport, event: dict[str, Any]) -> None:
    outputs = event.get("outputs") or {}
    event_id = str(event.get("event_id", ""))
    required = {"frame_count", "track_count", "latest_status_counts"}
    missing = required - set(outputs)
    if missing:
        report.add(
            "track_build.missing_counts",
            f"Track build missing counts: {sorted(missing)}",
            event_id=event_id,
        )
        return
    if int(outputs.get("track_count") or 0) > int(outputs.get("frame_count") or 0):
        report.add(
            "track_build.count_overflow",
            "Track count cannot exceed frame count",
            event_id=event_id,
        )
