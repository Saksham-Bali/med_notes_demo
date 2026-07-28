"""
Structured telemetry for FindingFrame pipeline runs.

The telemetry contract is intentionally JSON-first: every step emits a compact
event with counts, checks, artifacts, warnings, and errors. The JSONL stream is
append-only so long patient runs still leave inspectable partial state.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal


TelemetryStatus = Literal["completed", "failed"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        return str(value)


@dataclass
class TelemetryEvent:
    """One completed or failed pipeline step."""

    event_id: str
    run_id: str
    sequence: int
    stage: str
    step: str
    subject_id: str | None = None
    report_id: str | None = None
    status: TelemetryStatus = "completed"
    started_at: str = field(default_factory=_utc_now)
    ended_at: str | None = None
    duration_ms: float | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def finish(self, start_monotonic: float, status: TelemetryStatus = "completed") -> None:
        self.status = status
        self.ended_at = _utc_now()
        self.duration_ms = round((time.monotonic() - start_monotonic) * 1000, 3)

    def fail(self, start_monotonic: float, exc: BaseException) -> None:
        self.finish(start_monotonic, status="failed")
        self.error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "stage": self.stage,
            "step": self.step,
            "subject_id": self.subject_id,
            "report_id": self.report_id,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "inputs": _json_safe(self.inputs),
            "outputs": _json_safe(self.outputs),
            "metrics": _json_safe(self.metrics),
            "checks": _json_safe(self.checks),
            "artifacts": _json_safe(self.artifacts),
            "warnings": _json_safe(self.warnings),
            "error": _json_safe(self.error),
            "metadata": _json_safe(self.metadata),
        }


class PipelineTelemetry:
    """Append-only telemetry stream for a single pipeline run."""

    def __init__(
        self,
        subject_id: str | None = None,
        run_id: str | None = None,
        output_dir: str | Path | None = None,
        jsonl_path: str | Path | None = None,
        summary_path: str | Path | None = None,
        reset: bool = True,
    ):
        self.subject_id = str(subject_id) if subject_id is not None else None
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        self.events: list[TelemetryEvent] = []
        self._sequence = 0

        out_dir = Path(output_dir) if output_dir is not None else None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)

        self.jsonl_path = Path(jsonl_path) if jsonl_path is not None else None
        self.summary_path = Path(summary_path) if summary_path is not None else None
        if self.jsonl_path is None and out_dir is not None:
            self.jsonl_path = out_dir / f"{self.run_id}_telemetry.jsonl"
        if self.summary_path is None and out_dir is not None:
            self.summary_path = out_dir / f"{self.run_id}_telemetry_summary.json"

        if reset:
            for path in (self.jsonl_path, self.summary_path):
                if path is not None and path.exists():
                    path.unlink()

    @contextmanager
    def span(
        self,
        stage: str,
        step: str,
        *,
        report_id: str | None = None,
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[TelemetryEvent]:
        self._sequence += 1
        start_monotonic = time.monotonic()
        event = TelemetryEvent(
            event_id=f"{self.run_id}:{self._sequence}",
            run_id=self.run_id,
            sequence=self._sequence,
            subject_id=self.subject_id,
            report_id=str(report_id) if report_id is not None else None,
            stage=stage,
            step=step,
            inputs=dict(inputs or {}),
            metadata=dict(metadata or {}),
        )
        try:
            yield event
            event.finish(start_monotonic, status="completed")
        except Exception as exc:
            event.fail(start_monotonic, exc)
            self._record(event)
            raise
        self._record(event)

    def record_event(
        self,
        stage: str,
        step: str,
        *,
        report_id: str | None = None,
        outputs: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        checks: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        with self.span(stage, step, report_id=report_id, metadata=metadata) as event:
            event.outputs.update(outputs or {})
            event.metrics.update(metrics or {})
            event.checks.update(checks or {})
            event.warnings.extend(warnings or [])
        return self.events[-1]

    def _record(self, event: TelemetryEvent) -> None:
        self.events.append(event)
        if self.jsonl_path is None:
            return
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        stage_counts: dict[str, int] = {}
        step_counts: dict[str, int] = {}
        warning_count = 0
        failed_events: list[dict[str, Any]] = []

        for event in self.events:
            status_counts[event.status] = status_counts.get(event.status, 0) + 1
            stage_counts[event.stage] = stage_counts.get(event.stage, 0) + 1
            key = f"{event.stage}.{event.step}"
            step_counts[key] = step_counts.get(key, 0) + 1
            warning_count += len(event.warnings)
            if event.status == "failed":
                failed_events.append(event.to_dict())

        report_ids = sorted({event.report_id for event in self.events if event.report_id})
        return {
            "run_id": self.run_id,
            "subject_id": self.subject_id,
            "event_count": len(self.events),
            "status_counts": status_counts,
            "stage_counts": stage_counts,
            "step_counts": step_counts,
            "reports_seen": report_ids,
            "warning_count": warning_count,
            "failed_event_count": len(failed_events),
            "failed_events": failed_events,
            "jsonl_path": str(self.jsonl_path) if self.jsonl_path else None,
        }

    def write_summary(self) -> dict[str, Any]:
        summary = self.summary()
        if self.summary_path is not None:
            self.summary_path.parent.mkdir(parents=True, exist_ok=True)
            self.summary_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return summary

    @staticmethod
    def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events
