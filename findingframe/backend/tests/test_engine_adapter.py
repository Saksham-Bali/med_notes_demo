"""Engine-adapter contract tests. No network: the LLM extractor is monkeypatched.

Covers:
  * manifest_hash determinism (order-independent, text-sensitive),
  * extract_report maps a mocked extractor result into the ReportExtraction DTO.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine.adapter import get_engine
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
