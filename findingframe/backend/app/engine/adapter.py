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

# A git commit SHA is lowercase hex, 7 (abbreviated) to 40 (full) characters. Used to
# reject anything read from VENDOR_SHA that isn't actually a SHA -- e.g. the literal
# string "unknown" that infra/scripts/vendor_engine.sh writes when its own git
# rev-parse failed at vendor time, or a truncated/corrupted file. Without this check
# such a value would silently be treated as a confidently-resolved engine identity.
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


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

        # Resolution order: derive from the shipped code first (git checkout, else the
        # vendor script's pin -- see _resolve_git_sha), and only fall back to the env
        # var if the engine directory itself carries no verifiable identity at all.
        # This is the inverse of the old order (env var first). The env var is a
        # hand-set constant with no tie to what is actually on disk; on tyrone it is
        # hardcoded in infra/docker-compose.tyrone.yml to a SHA that does not track
        # engine updates (PRE_UPDATE_PLAN_2026-07-30.md §2.0). Preferring it would keep
        # rewarding that hardcode. Auto-resolution is now the source of truth; the env
        # var survives only as a last resort for environments where neither a .git
        # checkout nor a VENDOR_SHA file is present (e.g. an ad hoc test harness).
        self._git_sha = self._resolve_git_sha(engine_path) or settings.engine_git_sha
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
        """Best-effort engine identity, in order:

        1. A real git checkout (dev default: settings.engine_path -> ../../tmc).
           rev-parse HEAD, "+dirty" suffix if the tree carries uncommitted changes.
        2. VENDOR_SHA (production: Dockerfile.backend/.worker COPY infra/engine_vendor/
           to /app/engine, a plain directory with no .git -- rev-parse can't work there
           at all. infra/scripts/vendor_engine.sh pins the source commit into this file
           at vendor time; §2.0 of PRE_UPDATE_PLAN_2026-07-30.md is the reason this
           fallback exists -- without it, production provenance had no path back to the
           shipped code and depended entirely on a hand-set env var.)

        Returns "" ("unresolved") rather than pass through a value we cannot stand
        behind: an empty, truncated or corrupted VENDOR_SHA file -- or the literal
        "unknown" the vendor script writes when ITS OWN git rev-parse failed -- must
        never be mistaken by a caller (`sha or "unknown"`) for a confidently-resolved
        SHA just because it happens to be a non-empty string.
        """
        try:
            out = subprocess.run(
                ["git", "-C", engine_path, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode == 0:
                sha = out.stdout.strip()
                # rev-parse alone claims the engine is exactly HEAD even when the
                # checkout carries uncommitted changes. Report "<sha>+dirty" for those
                # so manifests, health, exports and signoff never mistake a patched
                # tree for a clean one.
                status = subprocess.run(
                    ["git", "-C", engine_path, "status", "--porcelain"],
                    capture_output=True, text=True, timeout=10,
                )
                if status.returncode == 0 and status.stdout.strip():
                    return f"{sha}+dirty"
                return sha
        except Exception:
            pass

        # Not a git checkout (or git itself unusable here) -- try the vendor pin.
        try:
            vendor_sha = (Path(engine_path) / "VENDOR_SHA").read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return vendor_sha if _SHA_RE.match(vendor_sha) else ""

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
    def _cache_root(self) -> Path | None:
        """Directory partition for this resolved engine version's extraction cache.

        None ("caching disabled") when self._git_sha could not be confidently resolved
        (see _resolve_git_sha) -- deliberately, not a shared "unknown" bucket. A cache
        keyed by report text alone survives an engine change silently: the +1325-line
        taxonomy update that shipped 5edaa99 changed what gets extracted, but
        CACHE_VERSION (schema+prompt version) was unchanged and no engine SHA
        participated in the key, so every already-cached report kept returning the OLD
        engine's output after the update (PRE_UPDATE_PLAN_2026-07-30.md §1.6). Scoping
        the cache directory by SHA fixes that for any resolved SHA; falling back to a
        shared bucket for the unresolved case would just recreate the same bug between
        any two engine states we can't tell apart. Refusing to cache is the safe choice
        -- slower/costlier, never silently wrong.
        """
        if not self._git_sha:
            return None
        # Make the SHA filesystem-safe. Note "+dirty" is a meaningful partition, not
        # noise: a patched checkout must not share a cache with the clean commit it was
        # edited from.
        safe_sha = re.sub(r"[^A-Za-z0-9+_.-]", "_", self._git_sha)
        root = Path(tempfile.gettempdir()) / "ff_engine_cache" / safe_sha
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _build_extractor(self, domain: str):
        """Construct a FindingFrameExtractor whose disk cache is partitioned by engine
        SHA (see _cache_root). Shared by extract_report() and process_patient() -- the
        latter passes this into FindingFramePatientProcessor(extractor=...) instead of
        letting it build its own default extractor, which used an unversioned,
        cwd-relative cache path (./outputs/cache/finding_frame_extraction_cache.json)
        that bypassed SHA scoping entirely; see the comment on that call site.
        Import is lazy: must only run after _prepare() has put the engine on sys.path.

        NOTE on outputs/cache/finding_frame_extraction_cache.json (committed in this
        repo): that path is exactly FindingFrameExtractor()'s own default cache_path --
        what gets used when something builds a FindingFramePatientProcessor without an
        extractor= override and runs with cwd == the findingframe/ repo root, the gap
        process_patient() used to have. Its keys (report_1..report_4, chart dates
        matching infra/scripts/money_patient_reports.py, model=deepseek/deepseek-v4-pro)
        match infra/scripts/build_money_patient.py, a one-off script that calls
        FindingFramePatientProcessor directly (bypassing this adapter) and is re-run
        often enough during development that the cache is almost certainly there on
        purpose, to avoid re-paying for real LLM calls on every re-run -- not an
        accident. It is LIVE for that script, not vestigial, so it is left in place
        rather than deleted here. It is NOT written or read by backend/ or worker/ any
        more now that both adapter call sites pass an explicit, SHA-scoped extractor.
        It carries the same staleness risk this fix addresses (no SHA in its key
        either) if build_money_patient.py is ever run against a different engine
        version without clearing it -- out of scope here since that script is not part
        of the serving path, but worth the same treatment later.
        """
        from extraction.finding_frame_extractor import FindingFrameExtractor  # type: ignore

        cache_root = self._cache_root()
        return FindingFrameExtractor(
            domain=domain,
            use_cache=cache_root is not None,
            cache_path=str((cache_root or Path(tempfile.gettempdir())) / "extract_cache.json"),
        )

    def extract_report(self, report: ReportInput, *, domain: str = "radiology") -> ReportExtraction:
        self._prepare()
        extractor = self._build_extractor(domain)
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
            # extractor=... matters: left default, FindingFramePatientProcessor builds its
            # own FindingFrameExtractor() (pipeline/finding_frame_processor.py), which in
            # turn defaults to cache_path="./outputs/cache/finding_frame_extraction_cache.json"
            # -- relative to the *process's* cwd, not scoped by engine SHA at all. This is
            # the worker's actual call path (worker/main.py -> process_patient), so it is
            # the one that matters most: passing our own SHA-scoped extractor here is what
            # makes an engine update actually invalidate cached patients being re-run.
            proc = FindingFramePatientProcessor(
                output_dir=tmp, save_artifacts=True, extractor=self._build_extractor(domain),
            )
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
