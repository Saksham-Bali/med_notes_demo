"""
Patient-level FindingFrame pipeline with structured telemetry.

This is the GOAL.md-oriented path:

single report -> evidence-backed FindingFrame -> deterministic track_key
-> longitudinal track timeline -> verifier-friendly artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from extraction.finding_frame_extractor import FindingFrameExtractor
from extraction.finding_frame_schema import FindingFrame, check_evidence_quality
from extraction.finding_type_taxonomy import evidence_terms_for_type, is_taxonomy_finding_type
from extraction.report_cleaner import clean_report
from fact_graph.frame_adapter import (
    FRAME_FACT_GRAPH_SCHEMA_VERSION,
    frames_to_frame_fact_graph,
)


def _OPTIONAL_TRACK_GRAPH_FN(tracks: dict) -> dict[str, Any]:
    """Lazily build a TrackGraph if the module is available."""
    try:
        from fact_graph.track_graph import build_track_graph  # noqa: PLC0415
    except ImportError:
        return {}
    return build_track_graph(tracks)
from telemetry import PipelineTelemetry
from telemetry.verifiers import (
    VerificationReport,
    verify_frame_pipeline_artifact,
    verify_telemetry_events,
)


FRAME_PIPELINE_SCHEMA_VERSION = "finding_frame_pipeline_v1"


@dataclass
class FramePipelineResult:
    subject_id: str
    output_path: str | None
    telemetry_jsonl_path: str | None
    telemetry_summary_path: str | None
    verifier_report_path: str | None
    artifact: dict[str, Any]
    telemetry_summary: dict[str, Any]
    verifier_report: VerificationReport


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _stable_report_id(index: int) -> str:
    return f"report_{index}"


def _sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"created_at", "manifest_hash"}
    }
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iter_patient_reports(subject_id: str, reports_df: pd.DataFrame) -> Iterable[tuple[int, pd.Series]]:
    reports = reports_df
    if "subject_id" in reports.columns:
        reports = reports[reports["subject_id"] == int(subject_id)]
    sort_columns = [column for column in ("charttime", "note_id") if column in reports.columns]
    if sort_columns:
        reports = reports.sort_values(sort_columns)
    return enumerate((row for _, row in reports.iterrows()), start=1)


def _build_report_manifest(
    subject_id: str,
    patient_reports: list[tuple[int, pd.Series]],
    *,
    selection_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for sequence_idx, report in patient_reports:
        report_text = _safe_str(report.get("text"))
        digest = _sha256(report_text)
        reports.append(
            {
                "report_id": _stable_report_id(sequence_idx),
                "note_id": _safe_str(report.get("note_id")),
                "charttime": _safe_str(report.get("charttime")),
                "note_type": _safe_str(report.get("note_type")),
                "text_chars": len(report_text),
                "text_sha256": digest,
                "text_sha256_16": digest[:16],
            }
        )

    payload: dict[str, Any] = {
        "schema_version": "finding_frame_report_manifest_v1",
        "created_at": datetime.now().isoformat(),
        "subject_id": str(subject_id),
        "selection_policy": selection_policy
        or {"source": "processor_input", "sort": "charttime asc, note_id asc"},
        "report_count": len(reports),
        "reports": reports,
    }
    payload["manifest_hash"] = _manifest_hash(payload)
    return payload


def latest_status_from_assertion(assertion: str, had_prior_present: bool = False) -> str:
    """Derive review status from latest frame assertion."""
    if assertion == "present":
        return "active"
    if assertion == "absent":
        return "resolved" if had_prior_present else "absent"
    if assertion == "uncertain":
        return "uncertain"
    return "not_mentioned"


def build_frame_tracks(frames: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build Phase 9 FindingFrame tracks from frame dictionaries."""
    graph = frames_to_frame_fact_graph(
        subject_id="unknown",
        frames=frames,
        metadata={"source": "build_frame_tracks"},
    )
    return graph["tracks"]


def _sync_frame_link_fields(
    frames: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    """Copy linker metadata back onto artifact frames for verifier consistency."""
    for frame, event in zip(frames, events):
        for key in (
            "track_key",
            "original_track_key",
            "linker_schema_version",
            "link_anatomy",
            "link_laterality",
            "link_family",
            "link_status",
            "link_decision",
            "link_reason",
            "link_candidate_track_keys",
            "link_review_required",
        ):
            if key in event:
                frame[key] = event[key]


def _frame_dict(
    frame: FindingFrame,
    *,
    report_date: str,
    study_type: str,
    frame_index: int,
    source_kind: str,
) -> dict[str, Any]:
    data = frame.model_dump(mode="json")
    data["track_key"] = frame.track_key()
    data["report_date"] = report_date
    data["study_type"] = study_type
    data["frame_index"] = frame_index
    data["source_kind"] = source_kind
    return data


class FindingFramePatientProcessor:
    """Run the new frame pipeline for one patient and emit verifier-ready artifacts."""

    def __init__(
        self,
        output_dir: str = "./outputs/finding_frame_runs",
        extractor: FindingFrameExtractor | None = None,
        save_artifacts: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.extractor = extractor or FindingFrameExtractor()
        self.save_artifacts = save_artifacts

    def process_patient(
        self,
        subject_id: str,
        reports_df: pd.DataFrame,
        *,
        telemetry: PipelineTelemetry | None = None,
        run_id: str | None = None,
    ) -> FramePipelineResult:
        started = time.time()
        subject_id = str(subject_id)
        run_id = run_id or f"frame_{subject_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        artifact_path = self.output_dir / f"subject_{subject_id}_frame_pipeline.json"
        telemetry_jsonl = self.output_dir / f"subject_{subject_id}_frame_telemetry.jsonl"
        telemetry_summary_path = (
            self.output_dir / f"subject_{subject_id}_frame_telemetry_summary.json"
        )
        verifier_path = self.output_dir / f"subject_{subject_id}_frame_verifier_report.json"

        telemetry = telemetry or PipelineTelemetry(
            subject_id=subject_id,
            run_id=run_id,
            jsonl_path=telemetry_jsonl,
            summary_path=telemetry_summary_path,
        )

        patient_reports = list(_iter_patient_reports(subject_id, reports_df))
        report_manifest = dict(reports_df.attrs.get("report_manifest") or {})
        if not report_manifest:
            report_manifest = _build_report_manifest(
                subject_id,
                patient_reports,
                selection_policy=reports_df.attrs.get("report_selection_policy"),
            )
        report_manifest_hash = str(report_manifest.get("manifest_hash") or "")
        all_frames: list[dict[str, Any]] = []
        reports_payload: list[dict[str, Any]] = []
        report_errors: list[dict[str, Any]] = []

        with telemetry.span(
            "pipeline",
            "start",
            inputs={
                "subject_id": subject_id,
                "reports_attempted": len(patient_reports),
                "schema_version": FRAME_PIPELINE_SCHEMA_VERSION,
            },
        ) as event:
            event.outputs["output_dir"] = str(self.output_dir)

        for sequence_idx, report in patient_reports:
            report_id = _stable_report_id(sequence_idx)
            report_date = _safe_str(report.get("charttime") or report.get("date") or "Unknown")
            study_type = _safe_str(report.get("note_type") or report.get("category") or "RR")
            report_text = _safe_str(report.get("text"))
            report_digest = _sha256(report_text)

            with telemetry.span(
                "report",
                "load",
                report_id=report_id,
                inputs={"sequence_index": sequence_idx},
            ) as event:
                event.outputs.update(
                    {
                        "report_id": report_id,
                        "report_date": report_date,
                        "study_type": study_type,
                        "text_chars": len(report_text),
                        "text_sha256_16": report_digest[:16],
                    }
                )
                if not report_text.strip():
                    event.warnings.append("empty_report_text")

            try:
                cleaned = None
                with telemetry.span("report", "clean", report_id=report_id) as event:
                    cleaned = clean_report(report_text)
                    event.outputs.update(
                        {
                            "extraction_text_chars": len(cleaned.extraction_text),
                            "indication_chars": len(cleaned.indication),
                            "sections_found": list(cleaned.sections_found),
                            "used_full_text_fallback": cleaned.extraction_text.strip()
                            == report_text.strip(),
                        }
                    )

                with telemetry.span(
                    "frame",
                    "extract",
                    report_id=report_id,
                    metadata={"extractor": type(self.extractor).__name__},
                ) as event:
                    extraction = self.extractor.extract(
                        report_text=report_text,
                        chart_date=report_date,
                        study_type=study_type,
                        source_report_id=report_id,
                    )
                    event.outputs.update(
                        {
                            "checklist_frame_count": len(extraction.frames),
                            "catch_all_frame_count": len(extraction.other_important_findings),
                            "overall_confidence": extraction.overall_confidence,
                            "critical_ambiguity_count": len(extraction.critical_ambiguities),
                        }
                    )
                    event.metrics.update(extraction.diagnostics)
                    event.warnings.extend(extraction.critical_ambiguities)

                report_frames: list[dict[str, Any]] = []
                for frame_index, frame in enumerate(extraction.frames, start=1):
                    report_frames.append(
                        _frame_dict(
                            frame,
                            report_date=report_date,
                            study_type=study_type,
                            frame_index=frame_index,
                            source_kind="checklist",
                        )
                    )
                catch_all_start = len(report_frames) + 1
                for offset, frame in enumerate(
                    extraction.other_important_findings,
                    start=catch_all_start,
                ):
                    report_frames.append(
                        _frame_dict(
                            frame,
                            report_date=report_date,
                            study_type=study_type,
                            frame_index=offset,
                            source_kind="catch_all",
                        )
                    )

                with telemetry.span("frame", "evidence_gate", report_id=report_id) as event:
                    frame_checks = []
                    issue_counter: Counter[str] = Counter()
                    source_verifiable_count = 0
                    invalid_evidence_count = 0
                    for frame_payload in report_frames:
                        frame = FindingFrame.model_validate(
                            {
                                key: value
                                for key, value in frame_payload.items()
                                if key
                                in {
                                    "finding_type",
                                    "finding_surface",
                                    "assertion",
                                    "evidence_text",
                                    "anatomy",
                                    "laterality",
                                    "uncertainty",
                                    "temporal_change",
                                    "measurement",
                                    "clinical_importance",
                                    "source_report_id",
                                    "evidence_span_start",
                                    "evidence_span_end",
                                    "lesion_key",
                                    "review_only",
                                }
                            }
                        )
                        concept_terms = (
                            evidence_terms_for_type(frame.finding_type)
                            if is_taxonomy_finding_type(frame.finding_type)
                            else ()
                        )
                        check = check_evidence_quality(frame, report_text, concept_terms)
                        if check.source_verifiable:
                            source_verifiable_count += 1
                        if check.issues:
                            invalid_evidence_count += 1
                            issue_counter.update(check.issues)
                        frame_checks.append(
                            {
                                "track_key": frame_payload["track_key"],
                                "finding_type": frame.finding_type,
                                "assertion": frame.assertion,
                                "source_kind": frame_payload["source_kind"],
                                "source_verifiable": check.source_verifiable,
                                "readable_span": check.readable_span,
                                "concept_supported": check.concept_supported,
                                "assertion_supported": check.assertion_supported,
                                "issues": list(check.issues),
                                "span_start": check.span_start,
                                "span_end": check.span_end,
                            }
                        )
                    event.outputs.update(
                        {
                            "frames_total": len(report_frames),
                            "source_verifiable_count": source_verifiable_count,
                            "invalid_evidence_count": invalid_evidence_count,
                            "issues_by_type": dict(issue_counter),
                        }
                    )
                    event.checks["frames"] = frame_checks

                with telemetry.span("frame", "catch_all_review", report_id=report_id) as event:
                    catch_all_frames = [
                        frame for frame in report_frames if frame["source_kind"] == "catch_all"
                    ]
                    event.outputs.update(
                        {
                            "catch_all_total": len(catch_all_frames),
                            "review_only_count": sum(
                                1 for frame in catch_all_frames if frame.get("review_only")
                            ),
                            "trusted_frame_count": sum(
                                1 for frame in report_frames if frame["source_kind"] == "checklist"
                            ),
                        }
                    )
                    non_review = [
                        frame["track_key"]
                        for frame in catch_all_frames
                        if not frame.get("review_only")
                    ]
                    if non_review:
                        event.warnings.append(
                            f"catch_all_without_review_only:{','.join(non_review)}"
                        )

                all_frames.extend(report_frames)
                reports_payload.append(
                    {
                        "report_id": report_id,
                        "note_id": _safe_str(report.get("note_id")),
                        "report_date": report_date,
                        "study_type": study_type,
                        "text_sha256": report_digest,
                        "text_sha256_16": report_digest[:16],
                        "frame_count": len(report_frames),
                        "checklist_frame_count": len(extraction.frames),
                        "catch_all_frame_count": len(extraction.other_important_findings),
                        "critical_ambiguities": list(extraction.critical_ambiguities),
                        "raw_response": extraction.raw_response,
                        "extraction_diagnostics": dict(extraction.diagnostics),
                    }
                )
            except Exception as exc:
                report_errors.append(
                    {
                        "report_id": report_id,
                        "report_date": report_date,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        with telemetry.span("track", "build") as event:
            frame_graph = frames_to_frame_fact_graph(
                subject_id=subject_id,
                frames=all_frames,
                metadata={"run_id": telemetry.run_id},
            )
            _sync_frame_link_fields(all_frames, frame_graph["events"])
            tracks = frame_graph["tracks"]
            link_summary = frame_graph.get("link_summary") or {}
            latest_status_counts = Counter(
                track["latest_status"] for track in tracks.values()
            )
            event.outputs.update(
                {
                    "frame_count": len(all_frames),
                    "track_count": len(tracks),
                    "latest_status_counts": dict(latest_status_counts),
                    "unresolved_link_count": sum(
                        1 for track in tracks.values() if track.get("unresolved_link")
                    ),
                    "review_queue_count": len(
                        frame_graph.get("unresolved_link_queue") or []
                    ),
                    "original_track_count": link_summary.get("original_track_count", 0),
                    "compatible_merge_count": link_summary.get(
                        "compatible_merge_count", 0
                    ),
                    "false_split_candidate_count": link_summary.get(
                        "false_split_candidate_count", 0
                    ),
                }
            )
            event.metrics.update(link_summary)
            event.checks["track_keys"] = sorted(tracks)

        duration = time.time() - started
        artifact = {
            "schema_version": FRAME_PIPELINE_SCHEMA_VERSION,
            "frame_graph_schema_version": FRAME_FACT_GRAPH_SCHEMA_VERSION,
            "subject_id": subject_id,
            "processed_at": datetime.now().isoformat(),
            "run_id": telemetry.run_id,
            "extraction_provenance": {
                "provider": str(os.getenv("LLM_PROVIDER") or "openrouter"),
                "model": str(
                    getattr(getattr(self.extractor, "llm_client", None), "model", "unknown")
                ),
                "reasoning_effort": str(
                    os.getenv("OPENAI_REASONING_EFFORT")
                    or os.getenv("OPENROUTER_REASONING_EFFORT")
                    or "automatic"
                ),
                "prompt_versions": sorted({
                    str(report.get("extraction_diagnostics", {}).get("prompt_version"))
                    for report in reports_payload
                    if report.get("extraction_diagnostics", {}).get("prompt_version")
                }),
                "raw_responses_retained": all(
                    bool(str(report.get("raw_response") or "").strip())
                    for report in reports_payload
                ),
            },
            "report_manifest_hash": report_manifest_hash,
            "report_manifest": report_manifest,
            "reports_attempted": len(patient_reports),
            "reports_succeeded": len(reports_payload),
            "reports_failed": len(report_errors),
            "report_errors": report_errors,
            "reports": reports_payload,
            "frames": all_frames,
            "frame_events": frame_graph["events"],
            "tracks": tracks,
            "track_graph": _OPTIONAL_TRACK_GRAPH_FN(tracks),
            "unresolved_link_queue": frame_graph.get("unresolved_link_queue") or [],
            "false_split_candidates": frame_graph.get("false_split_candidates") or [],
            "link_summary": frame_graph.get("link_summary") or {},
            "metrics": {
                "frame_count": len(all_frames),
                "track_count": len(tracks),
                "original_track_count": (
                    frame_graph.get("link_summary") or {}
                ).get("original_track_count", len(tracks)),
                "unresolved_link_count": len(
                    frame_graph.get("unresolved_link_queue") or []
                ),
                "compatible_merge_count": (
                    frame_graph.get("link_summary") or {}
                ).get("compatible_merge_count", 0),
                "false_split_candidate_count": len(
                    frame_graph.get("false_split_candidates") or []
                ),
                "catch_all_count": sum(
                    1 for frame in all_frames if frame.get("source_kind") == "catch_all"
                ),
                "run_duration_seconds": round(duration, 3),
            },
        }

        with telemetry.span("pipeline", "summary") as event:
            event.outputs.update(
                {
                    "reports_attempted": artifact["reports_attempted"],
                    "reports_succeeded": artifact["reports_succeeded"],
                    "reports_failed": artifact["reports_failed"],
                    "frame_count": artifact["metrics"]["frame_count"],
                    "track_count": artifact["metrics"]["track_count"],
                    "original_track_count": artifact["metrics"]["original_track_count"],
                    "unresolved_link_count": artifact["metrics"]["unresolved_link_count"],
                    "compatible_merge_count": artifact["metrics"]["compatible_merge_count"],
                    "false_split_candidate_count": artifact["metrics"][
                        "false_split_candidate_count"
                    ],
                    "catch_all_count": artifact["metrics"]["catch_all_count"],
                    "run_duration_seconds": artifact["metrics"]["run_duration_seconds"],
                }
            )
            if self.save_artifacts:
                event.artifacts["frame_pipeline"] = str(artifact_path)
                event.artifacts["telemetry_jsonl"] = str(telemetry_jsonl)
                event.artifacts["telemetry_summary"] = str(telemetry_summary_path)
                event.artifacts["verifier_report"] = str(verifier_path)

        telemetry_summary = telemetry.write_summary()
        telemetry_verifier = verify_telemetry_events(
            telemetry.events,
            expected_report_ids={_stable_report_id(idx) for idx, _ in patient_reports},
        )
        artifact_verifier = verify_frame_pipeline_artifact(artifact)
        verifier_report = VerificationReport(
            issues=[*telemetry_verifier.issues, *artifact_verifier.issues],
            summary={
                "telemetry": telemetry_verifier.summary,
                "artifact": artifact_verifier.summary,
            },
        )
        artifact["telemetry_summary"] = telemetry_summary
        artifact["verifier_report"] = verifier_report.to_dict()

        if self.save_artifacts:
            artifact_path.write_text(
                json.dumps(artifact, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            verifier_path.write_text(
                json.dumps(verifier_report.to_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )

        return FramePipelineResult(
            subject_id=subject_id,
            output_path=str(artifact_path) if self.save_artifacts else None,
            telemetry_jsonl_path=str(telemetry_jsonl) if self.save_artifacts else None,
            telemetry_summary_path=str(telemetry_summary_path)
            if self.save_artifacts
            else None,
            verifier_report_path=str(verifier_path) if self.save_artifacts else None,
            artifact=artifact,
            telemetry_summary=telemetry_summary,
            verifier_report=verifier_report,
        )
