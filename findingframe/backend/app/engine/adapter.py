"""The ONLY place that imports FindingFrame engine internals (Fable's isolation point).

Exposes a stable, product-facing surface:
  - manifest_base()          reproducibility metadata (engine sha, model, prompt/schema versions)
  - extract_report(...)      one report  -> ReportExtraction
  - process_patient(...)     many reports -> PatientArtifact (frames + deterministic tracks + graph)

The engine lives at settings.engine_path (../../tmc). We keep the engine research-intact and
depend on it as a versioned dependency; product code never edits it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

_MEAS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm)\b", re.IGNORECASE)


def _normalize_measurement(m: Any) -> Any:
    """Populate normalized_mm/values (in mm) from a measurement's raw/text when the
    engine/LLM leaves them null — RECIST needs numeric mm. Deterministic; mm as-is, cm*10.
    Kept in the adapter (data-prep at the engine boundary) so the engine stays untouched."""
    if not isinstance(m, dict):
        return m
    if m.get("normalized_mm") is not None:
        return m
    src = m.get("raw") or m.get("text") or ""
    vals_mm: list[float] = []
    for num, unit in _MEAS_RE.findall(str(src)):
        try:
            v = float(num)
        except ValueError:
            continue
        vals_mm.append(v * 10.0 if unit.lower() == "cm" else v)
    if not vals_mm:
        return m
    m = dict(m)
    m["values"] = vals_mm
    m["normalized_mm"] = max(vals_mm)   # longest diameter; recist.py picks short axis for nodes
    m["value"] = max(vals_mm)
    m["unit"] = "mm"
    return m


def _normalize_artifact_measurements(artifact: dict) -> None:
    """In-place: normalize measurements on frames and any track events that carry them."""
    for f in artifact.get("frames", []) or []:
        if isinstance(f, dict) and "measurement" in f:
            f["measurement"] = _normalize_measurement(f.get("measurement"))
    tracks = artifact.get("tracks", {})
    track_iter = tracks.values() if isinstance(tracks, dict) else (tracks or [])
    for t in track_iter:
        for ev in (t.get("events", []) if isinstance(t, dict) else []) or []:
            if isinstance(ev, dict) and "measurement" in ev:
                ev["measurement"] = _normalize_measurement(ev.get("measurement"))

from app.core.config import settings
from app.engine.types import (
    ExtractionManifest,
    PatientArtifact,
    ReportExtraction,
    ReportInput,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EngineAdapter:
    """Thin, process-local wrapper around the FindingFrame engine."""

    def __init__(self) -> None:
        self._prepared = False
        self._git_sha = ""
        self._prompt_version = ""
        self._schema_version = ""

    # -- setup ---------------------------------------------------------------
    def _prepare(self) -> None:
        if self._prepared:
            return
        engine_path = str(Path(settings.engine_path).resolve())
        if engine_path not in sys.path:
            sys.path.insert(0, engine_path)

        # Feed the engine's LLM client via env (it reads env before config files),
        # so behavior is independent of process cwd.
        os.environ.setdefault("LLM_PROVIDER", settings.llm_provider)
        if settings.openrouter_api_key:
            os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
        if settings.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
        if settings.llm_provider == "openrouter":
            os.environ.setdefault("OPENROUTER_MODEL", settings.llm_model)
            os.environ.setdefault("OPENROUTER_REASONING_EFFORT", settings.llm_reasoning_effort)
        else:
            os.environ.setdefault("OPENAI_MODEL", settings.llm_model)

        self._git_sha = settings.engine_git_sha or self._resolve_git_sha(engine_path)
        # Versions are cheap module constants; import lazily.
        try:
            from extraction.finding_frame_extractor import _PROMPT_VERSION  # type: ignore
            self._prompt_version = _PROMPT_VERSION
        except Exception:
            self._prompt_version = "unknown"
        try:
            from extraction.finding_frame_schema import SCHEMA_VERSION  # type: ignore
            self._schema_version = SCHEMA_VERSION
        except Exception:
            self._schema_version = "unknown"
        self._prepared = True

    @staticmethod
    def _resolve_git_sha(engine_path: str) -> str:
        try:
            out = subprocess.run(
                ["git", "-C", engine_path, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                return ""
            sha = out.stdout.strip()
            # rev-parse alone claims the engine is exactly HEAD even when the checkout
            # carries uncommitted changes. Report "<sha>+dirty" for those so manifests,
            # health, exports and signoff never mistake a patched tree for a clean one.
            status = subprocess.run(
                ["git", "-C", engine_path, "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            )
            if status.returncode == 0 and status.stdout.strip():
                return f"{sha}+dirty"
            return sha
        except Exception:
            return ""

    # -- manifest ------------------------------------------------------------
    def manifest_base(self) -> ExtractionManifest:
        self._prepare()
        return ExtractionManifest(
            engine_git_sha=self._git_sha,
            model_provider=settings.llm_provider,
            model_id=settings.llm_model,
            prompt_version=self._prompt_version,
            schema_version=self._schema_version,
            temperature=settings.llm_temperature,
            reasoning_effort=settings.llm_reasoning_effort,
        )

    def build_manifest(self, reports: list[ReportInput]) -> ExtractionManifest:
        """Deterministic manifest hash over ordered report hashes + model params."""
        m = self.manifest_base()
        report_manifest: list[dict[str, Any]] = []
        for r in sorted(reports, key=lambda x: (x.chart_date, x.source_report_id)):
            h = r.text_sha256 or _sha256(r.text)
            report_manifest.append({
                "source_report_id": r.source_report_id,
                "report_version_id": r.report_version_id,
                "text_sha256": h,
                "chart_date": r.chart_date.isoformat(),
            })
        m.report_manifest = report_manifest
        payload = json.dumps({
            "engine_git_sha": m.engine_git_sha,
            "model_provider": m.model_provider,
            "model_id": m.model_id,
            "prompt_version": m.prompt_version,
            "schema_version": m.schema_version,
            "temperature": m.temperature,
            "reasoning_effort": m.reasoning_effort,
            "reports": report_manifest,
        }, sort_keys=True)
        m.manifest_hash = _sha256(payload)
        return m

    # -- extraction ----------------------------------------------------------
    def extract_report(self, report: ReportInput, *, domain: str = "radiology") -> ReportExtraction:
        self._prepare()
        from extraction.finding_frame_extractor import FindingFrameExtractor  # type: ignore

        cache_dir = Path(tempfile.gettempdir()) / "ff_engine_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        extractor = FindingFrameExtractor(
            domain=domain, use_cache=True, cache_path=str(cache_dir / "extract_cache.json"),
        )
        res = extractor.extract(
            report.text,
            chart_date=report.chart_date.strftime("%Y-%m-%d"),
            study_type=report.study_type,
            source_report_id=report.source_report_id,
        )
        d = res.to_dict() if hasattr(res, "to_dict") else {}
        return ReportExtraction(
            source_report_id=report.source_report_id,
            frames=d.get("frames", []),
            other_important_findings=d.get("other_important_findings", []),
            overall_confidence=d.get("overall_confidence", 0.0),
            critical_ambiguities=d.get("critical_ambiguities", []),
            diagnostics=d.get("diagnostics", {}),
        )

    def process_patient(
        self, subject_code: str, reports: list[ReportInput], *, domain: str = "radiology",
        run_id: str | None = None,
    ) -> PatientArtifact:
        """Full multi-report pipeline: extraction -> deterministic linking -> track graph.

        Reliable path: FindingFramePatientProcessor writes subject_{id}_frame_pipeline.json;
        we run it into a temp dir and read that artifact back.
        """
        self._prepare()
        from pipeline.finding_frame_processor import FindingFramePatientProcessor  # type: ignore

        # The engine filters reports by int(subject_id) (finding_frame_processor.py), so a
        # non-numeric product subject_code would drop every row. Use a stable integer
        # surrogate for the engine call; the product subject_code is restored on return.
        subj_int = int.from_bytes(hashlib.sha1(subject_code.encode()).digest()[:6], "big")
        rows = []
        for r in reports:
            rows.append({
                "subject_id": subj_int,
                "charttime": r.chart_date,
                "note_id": r.note_id or r.source_report_id,
                "note_type": r.study_type,
                "text": r.text,
            })
        reports_df = pd.DataFrame(rows).sort_values("charttime").reset_index(drop=True)

        with tempfile.TemporaryDirectory(prefix="ff_run_") as tmp:
            proc = FindingFramePatientProcessor(output_dir=tmp, save_artifacts=True)
            proc.process_patient(str(subj_int), reports_df, run_id=run_id)
            artifact_path = Path(tmp) / f"subject_{subj_int}_frame_pipeline.json"
            if not artifact_path.exists():
                # fall back to any *_frame_pipeline.json produced
                candidates = list(Path(tmp).glob("*_frame_pipeline.json"))
                if not candidates:
                    raise RuntimeError("engine did not produce a frame pipeline artifact")
                artifact_path = candidates[0]
            artifact = json.loads(artifact_path.read_text())

        _normalize_artifact_measurements(artifact)
        manifest = self.build_manifest(reports)
        return PatientArtifact(
            subject_id=subject_code,
            frames=artifact.get("frames", []),
            frame_events=artifact.get("frame_events", []),
            tracks=artifact.get("tracks", {}),
            track_graph=artifact.get("track_graph", {}),
            unresolved_link_queue=artifact.get("unresolved_link_queue", []),
            false_split_candidates=artifact.get("false_split_candidates", []),
            link_summary=artifact.get("link_summary", {}),
            metrics=artifact.get("metrics", {}),
            manifest=manifest,
            raw=artifact,
        )


_adapter: EngineAdapter | None = None


def get_engine() -> EngineAdapter:
    global _adapter
    if _adapter is None:
        _adapter = EngineAdapter()
    return _adapter
