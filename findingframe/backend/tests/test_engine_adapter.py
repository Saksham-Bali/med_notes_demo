"""Engine-adapter contract tests. No network: the LLM extractor is monkeypatched.

Covers:
  * manifest_hash determinism (order-independent, text-sensitive),
  * extract_report maps a mocked extractor result into the ReportExtraction DTO,
  * engine provenance: _resolve_git_sha marks dirty worktrees "<sha>+dirty",
    falls back to VENDOR_SHA for a non-git engine directory, and rejects a
    marker/malformed VENDOR_SHA rather than presenting it as resolved,
  * engine provenance precedence: auto-resolution beats the FF_ENGINE_GIT_SHA env
    var, which survives only as a last resort (PRE_UPDATE_PLAN_2026-07-30.md §2.0),
  * extraction cache: partitioned by engine SHA, disabled (not shared-unversioned)
    when the SHA is unresolved, and wired into both extract_report() and
    process_patient() (PRE_UPDATE_PLAN_2026-07-30.md §1.6).
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile as tempfile_mod
from pathlib import Path

import pytest

from app.core.config import settings
from app.engine.adapter import EngineAdapter, get_engine
from app.engine.types import ReportInput


def _report(rid: str, text: str, day: int) -> ReportInput:
    return ReportInput(
        source_report_id=rid,
        text=text,
        chart_date=dt.datetime(2024, 1, day, tzinfo=dt.timezone.utc),
        report_version_id=f"ver-{rid}",
    )


def test_manifest_hash_is_deterministic_and_order_independent():
    engine = get_engine()
    a = _report("report_1", "Liver lesion measures 20 mm.", 1)
    b = _report("report_2", "Interval increase to 30 mm.", 8)

    m1 = engine.build_manifest([a, b])
    m2 = engine.build_manifest([b, a])  # reversed input order

    assert m1.manifest_hash
    assert m1.manifest_hash == m2.manifest_hash  # sorted internally -> stable
    assert len(m1.report_manifest) == 2


def test_manifest_hash_changes_with_text():
    engine = get_engine()
    base = [_report("report_1", "Stable disease.", 1)]
    changed = [_report("report_1", "Progressive disease.", 1)]
    assert engine.build_manifest(base).manifest_hash != engine.build_manifest(changed).manifest_hash


class _FakeResult:
    def to_dict(self):
        return {
            "frames": [
                {
                    "finding_type": "mass",
                    "anatomy": "liver",
                    "laterality": "unknown",
                    "assertion": "present",
                    "evidence_text": "A 20 mm hepatic mass is present.",
                    "evidence_span_start": 0,
                    "evidence_span_end": 30,
                }
            ],
            "other_important_findings": [],
            "overall_confidence": 0.9,
            "critical_ambiguities": [],
            "diagnostics": {"prompt_version": "test"},
        }


class _FakeExtractor:
    def __init__(self, *a, **k):
        pass

    def extract(self, text, **kwargs):
        return _FakeResult()


def test_extract_report_maps_mocked_extractor(monkeypatch):
    engine = get_engine()
    engine._prepare()  # ensures the engine path is importable

    import extraction.finding_frame_extractor as ffe  # type: ignore

    monkeypatch.setattr(ffe, "FindingFrameExtractor", _FakeExtractor)

    result = engine.extract_report(_report("report_1", "A 20 mm hepatic mass is present.", 1))
    assert result.source_report_id == "report_1"
    assert len(result.frames) == 1
    assert result.frames[0]["finding_type"] == "mass"
    assert result.overall_confidence == pytest.approx(0.9)


def _git(repo, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def test_resolve_git_sha_marks_dirty_worktree(tmp_path):
    """A manifest sha must never claim a clean HEAD for a patched engine tree."""
    repo = tmp_path / "engine"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "engine.py").write_text("x = 1\n")
    _git(repo, "add", "engine.py")
    _git(repo, "commit", "-qm", "init")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert EngineAdapter._resolve_git_sha(str(repo)) == head

    # Uncommitted modification to a tracked file taints provenance.
    (repo / "engine.py").write_text("x = 2\n")
    assert EngineAdapter._resolve_git_sha(str(repo)) == f"{head}+dirty"

    # So does an untracked, non-ignored file (an importable module not in any commit).
    _git(repo, "checkout", "-q", "--", "engine.py")
    assert EngineAdapter._resolve_git_sha(str(repo)) == head
    (repo / "new_module.py").write_text("y = 3\n")
    assert EngineAdapter._resolve_git_sha(str(repo)) == f"{head}+dirty"


def test_resolve_git_sha_non_repo_returns_empty(tmp_path):
    assert EngineAdapter._resolve_git_sha(str(tmp_path / "nope")) == ""


# -- FIX 2: VENDOR_SHA fallback + unresolved-vs-confident distinction ---------------

def test_resolve_git_sha_falls_back_to_vendor_sha_file(tmp_path):
    """Production's case: /app/engine is a plain COPY (Dockerfile.backend/.worker),
    not a git checkout, so rev-parse can't work at all. infra/scripts/vendor_engine.sh
    pins the source commit into VENDOR_SHA at vendor time -- this must be honoured."""
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    sha = "5edaa9975eedbdfe380c2169e996173695798615"
    (engine_dir / "VENDOR_SHA").write_text(f"{sha}\n")
    assert EngineAdapter._resolve_git_sha(str(engine_dir)) == sha


def test_resolve_git_sha_rejects_unknown_vendor_sha_marker(tmp_path):
    """vendor_engine.sh itself writes the literal "unknown" when ITS git rev-parse
    failed at vendor time. That must not be presented as a confidently-resolved SHA
    just because the file is non-empty."""
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "VENDOR_SHA").write_text("unknown\n")
    assert EngineAdapter._resolve_git_sha(str(engine_dir)) == ""


def test_resolve_git_sha_rejects_malformed_vendor_sha_file(tmp_path):
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()

    (engine_dir / "VENDOR_SHA").write_text("")
    assert EngineAdapter._resolve_git_sha(str(engine_dir)) == ""

    (engine_dir / "VENDOR_SHA").write_text("not-a-real-sha!!\n")
    assert EngineAdapter._resolve_git_sha(str(engine_dir)) == ""


def test_git_sha_precedence_prefers_auto_resolution_over_env_var(monkeypatch):
    """§2.0: infra/docker-compose.tyrone.yml hardcodes FF_ENGINE_GIT_SHA to a stale
    SHA. Auto-resolution (git checkout or VENDOR_SHA -- code actually shipped) must
    win over that hand-set constant whenever it resolves to anything at all."""
    monkeypatch.setattr(settings, "engine_git_sha", "e04d3c6d9c7938b32b0b3be1b9a37f9869d024c2")
    monkeypatch.setattr(
        EngineAdapter, "_resolve_git_sha",
        staticmethod(lambda engine_path: "5edaa9975eedbdfe380c2169e996173695798615"),
    )

    engine = EngineAdapter()
    engine._prepare()
    assert engine._git_sha == "5edaa9975eedbdfe380c2169e996173695798615"


def test_git_sha_falls_back_to_env_var_when_unresolvable(monkeypatch):
    """The env var still matters, but only as a last resort -- when the engine
    directory carries no verifiable identity at all (no .git, no VENDOR_SHA)."""
    monkeypatch.setattr(settings, "engine_git_sha", "manually-pinned-sha")
    monkeypatch.setattr(EngineAdapter, "_resolve_git_sha", staticmethod(lambda engine_path: ""))

    engine = EngineAdapter()
    engine._prepare()
    assert engine._git_sha == "manually-pinned-sha"


# -- FIX 1: extraction cache partitioned by engine SHA ------------------------------

def test_cache_root_none_when_sha_unresolved():
    """No shared "unknown" bucket: an engine whose SHA we can't confidently resolve
    gets no cache at all, rather than risk mixing output across engine versions."""
    engine = EngineAdapter()
    engine._git_sha = ""
    assert engine._cache_root() is None


def test_cache_root_scoped_by_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile_mod, "gettempdir", lambda: str(tmp_path))

    engine_old = EngineAdapter()
    engine_old._git_sha = "e04d3c6d9c7938b32b0b3be1b9a37f9869d024c2"
    root_old = engine_old._cache_root()

    engine_new = EngineAdapter()
    engine_new._git_sha = "5edaa9975eedbdfe380c2169e996173695798615"
    root_new = engine_new._cache_root()

    assert root_old is not None and root_new is not None
    assert root_old != root_new  # different engine SHAs never share a cache partition
    assert root_old.is_dir() and root_new.is_dir()
    assert "e04d3c6d9c7938b32b0b3be1b9a37f9869d024c2" in str(root_old)
    assert "5edaa9975eedbdfe380c2169e996173695798615" in str(root_new)


def test_cache_root_partitions_dirty_checkouts_separately():
    """A patched (+dirty) tree must not share a cache with the clean commit it was
    edited from -- the +dirty suffix is a meaningful partition, not noise to strip."""
    clean = EngineAdapter()
    clean._git_sha = "5edaa9975eedbdfe380c2169e996173695798615"
    dirty = EngineAdapter()
    dirty._git_sha = "5edaa9975eedbdfe380c2169e996173695798615+dirty"
    assert clean._cache_root() != dirty._cache_root()


def test_build_extractor_disables_cache_when_sha_unresolved(monkeypatch):
    engine = EngineAdapter()
    engine._prepare()
    engine._git_sha = ""  # simulate an unresolvable engine version

    import extraction.finding_frame_extractor as ffe  # type: ignore

    captured: dict = {}

    class _CapturingExtractor:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(ffe, "FindingFrameExtractor", _CapturingExtractor)
    engine._build_extractor(domain="radiology")

    assert captured["use_cache"] is False


def test_build_extractor_scopes_cache_path_by_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile_mod, "gettempdir", lambda: str(tmp_path))

    engine = EngineAdapter()
    engine._prepare()
    engine._git_sha = "cccccccccccccccccccccccccccccccccccccccc"

    import extraction.finding_frame_extractor as ffe  # type: ignore

    captured: dict = {}

    class _CapturingExtractor:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(ffe, "FindingFrameExtractor", _CapturingExtractor)
    engine._build_extractor(domain="radiology")

    assert captured["use_cache"] is True
    assert "cccccccccccccccccccccccccccccccccccccccc" in captured["cache_path"]
    assert str(tmp_path) in captured["cache_path"]


def test_process_patient_wires_sha_scoped_extractor_into_processor(monkeypatch):
    """The worker's real call path (worker/main.py -> process_patient) must not fall
    through to FindingFramePatientProcessor's own default extractor -- that default
    uses an unversioned, cwd-relative cache path that bypasses SHA scoping entirely."""
    engine = EngineAdapter()
    engine._prepare()

    sentinel = object()
    monkeypatch.setattr(engine, "_build_extractor", lambda domain: sentinel)

    import pipeline.finding_frame_processor as ffp  # type: ignore

    captured: dict = {}

    class _FakeProcessor:
        def __init__(self, output_dir, extractor=None, save_artifacts=True):
            captured["extractor"] = extractor
            self._output_dir = Path(output_dir)

        def process_patient(self, subject_id, reports_df, *, run_id=None):
            artifact = {
                "frames": [], "frame_events": [], "tracks": {}, "track_graph": {},
                "unresolved_link_queue": [], "false_split_candidates": [],
                "link_summary": {}, "metrics": {},
            }
            (self._output_dir / f"subject_{subject_id}_frame_pipeline.json").write_text(
                json.dumps(artifact)
            )

    monkeypatch.setattr(ffp, "FindingFramePatientProcessor", _FakeProcessor)

    result = engine.process_patient("patient-x", [_report("report_1", "Stable disease.", 1)])

    assert captured["extractor"] is sentinel
    assert result.subject_id == "patient-x"
