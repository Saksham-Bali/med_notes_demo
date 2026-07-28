"""
Tests for the radiology-extractor FastAPI service.

Uses a mock RadiologyExtractor so the full ML pipeline is never loaded
during the test run.  Tests cover:
  - /health endpoint
  - /api/v1/extract happy path (single finding)
  - /api/v1/extract with multiple findings
  - /api/v1/extract with empty report text (validation error)
  - /api/v1/extract when extractor raises (internal error)
  - ClinicalFact shape validation
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path so `app` package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Build a TestClient with the extractor mocked out at import time so that
# the lifespan never tries to load HybridExtractor / EntityGrounder.
# ---------------------------------------------------------------------------
_MOCK_EXTRACTOR = MagicMock()

# Default: return one sample grounded finding
_SAMPLE_FINDING: dict = {
    "entity": "lung nodule",
    "canonical_name": "finding_lung_nodule",
    "radlex_id": "RID50149",
    "snomed_id": None,
    "is_negated": False,
    "certainty": "probable",
    "confidence_score": 0.88,
    "evidence_text": "2.3cm left lower lobe nodule",
    "measurement": {"value": 2.3, "unit": "cm", "normalized_mm": 23.0},
    "measurement_normalized": {
        "current_value": 2.3,
        "current_unit": "cm",
        "current_mm": 23.0,
        "prior_value": None,
        "prior_unit": None,
        "prior_mm": None,
    },
    "modality": "CT",
    "body_region": "chest",
    "temporal_change": "NEW",
    "anatomical_location": "left lower lobe",
    "grounding_method": "exact_match",
    "grounding_confidence": 0.99,
}

_MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]


def _make_client() -> TestClient:
    """Create a TestClient with the extractor pre-patched on app.state."""
    with patch(
        "app.extractor.RadiologyExtractor", return_value=_MOCK_EXTRACTOR
    ):
        from app.main import app

        client = TestClient(app)
        # Ensure app.state.extractor is the mock (lifespan sets it on startup)
        app.state.extractor = _MOCK_EXTRACTOR
        return client


_CLIENT = _make_client()

_EXTRACT_PAYLOAD: dict = {
    "patient_id": "P001",
    "report_text": "CT chest: 2.3cm left lower lobe nodule is noted.",
    "prior_report_text": None,
    "report_id": "R-20260401",
    "report_date": "2026-04-01",
    "modality": "CT",
    "body_region": "chest",
    "hadm_id": "",
}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_returns_200(self):
        response = _CLIENT.get("/health")
        assert response.status_code == 200

    def test_health_body(self):
        response = _CLIENT.get("/health")
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "radiology-extractor"


# ---------------------------------------------------------------------------
# Extract endpoint — happy path
# ---------------------------------------------------------------------------
class TestExtract:
    def test_extract_returns_200(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        assert response.status_code == 200

    def test_extract_result_shape(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        body = response.json()
        assert "result" in body
        result = body["result"]
        assert "clinical_facts" in result
        assert "entity_count" in result
        assert "extraction_source" in result
        assert "processing_time_ms" in result

    def test_extract_entity_count_matches_facts(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        result = response.json()["result"]
        assert result["entity_count"] == len(result["clinical_facts"])
        assert result["entity_count"] == 1

    def test_extract_clinical_fact_fields(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        required_fields = [
            "fact_id", "patient_id", "entity_name", "certainty",
            "certainty_label", "is_negated", "modality", "source_type",
            "source_report_id", "date", "hadm_id",
        ]
        for field in required_fields:
            assert field in fact, f"Missing field: {field}"

    def test_extract_patient_id_propagated(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        assert fact["patient_id"] == "P001"

    def test_extract_modality_propagated(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        assert fact["modality"] == "CT"

    def test_extract_source_type_is_radiology(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        assert fact["source_type"] == "radiology"

    def test_extract_extraction_source_hybrid(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        result = response.json()["result"]
        assert result["extraction_source"] == "hybrid"

    def test_extract_multiple_findings(self):
        second_finding = dict(_SAMPLE_FINDING, entity="pleural effusion",
                              canonical_name="finding_pleural_effusion",
                              radlex_id="RID34539")
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING, second_finding]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        result = response.json()["result"]
        assert result["entity_count"] == 2
        assert len(result["clinical_facts"]) == 2

    def test_extract_empty_findings(self):
        _MOCK_EXTRACTOR.extract.return_value = []
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        result = response.json()["result"]
        assert result["entity_count"] == 0
        assert result["clinical_facts"] == []

    def test_extract_fact_id_is_uuid(self):
        import uuid
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        # Should not raise
        uuid.UUID(fact["fact_id"])

    def test_extract_measurement_present(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        assert fact["measurement"] is not None
        assert fact["measurement"]["value"] == pytest.approx(2.3, abs=0.01)
        assert fact["measurement"]["normalized_mm"] == pytest.approx(23.0, abs=0.1)

    def test_extract_temporal_change(self):
        _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]
        response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
        fact = response.json()["result"]["clinical_facts"][0]
        assert fact["temporal_change"] == "NEW"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------
class TestValidation:
    def test_empty_report_text_returns_422(self):
        payload = dict(_EXTRACT_PAYLOAD, report_text="")
        response = _CLIENT.post("/api/v1/extract", json=payload)
        assert response.status_code == 422

    def test_whitespace_report_text_returns_422(self):
        payload = dict(_EXTRACT_PAYLOAD, report_text="   \n  ")
        response = _CLIENT.post("/api/v1/extract", json=payload)
        assert response.status_code == 422

    def test_missing_patient_id_returns_422(self):
        payload = {k: v for k, v in _EXTRACT_PAYLOAD.items() if k != "patient_id"}
        response = _CLIENT.post("/api/v1/extract", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Extractor exception handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    def test_extractor_exception_returns_500(self):
        _MOCK_EXTRACTOR.extract.side_effect = RuntimeError("LLM timeout")
        try:
            response = _CLIENT.post("/api/v1/extract", json=_EXTRACT_PAYLOAD)
            assert response.status_code == 500
        finally:
            # Reset side effect so other tests are not affected
            _MOCK_EXTRACTOR.extract.side_effect = None
            _MOCK_EXTRACTOR.extract.return_value = [_SAMPLE_FINDING]


# ---------------------------------------------------------------------------
# CFS adapter unit tests (no HTTP)
# ---------------------------------------------------------------------------
class TestCfsAdapter:
    def test_basic_conversion(self):
        from app.cfs_adapter import grounded_finding_to_cfs
        fact = grounded_finding_to_cfs(
            finding=_SAMPLE_FINDING,
            patient_id="P001",
            report_id="R-001",
            report_date="2026-04-01",
            modality="CT",
            hadm_id="",
        )
        assert fact["patient_id"] == "P001"
        assert fact["source_report_id"] == "R-001"
        assert fact["source_type"] == "radiology"
        assert fact["modality"] == "CT"
        assert fact["is_negated"] is False
        assert fact["entity_name"] == "finding_lung_nodule"
        assert fact["radlex_id"] == "RID50149"

    def test_negated_finding(self):
        from app.cfs_adapter import grounded_finding_to_cfs
        neg_finding = dict(_SAMPLE_FINDING, is_negated=True,
                           certainty="confirmed", confidence_score=0.95)
        fact = grounded_finding_to_cfs(
            finding=neg_finding,
            patient_id="P001",
            report_id="R-001",
            report_date="2026-04-01",
            modality="CT",
            hadm_id="",
        )
        assert fact["is_negated"] is True

    def test_measurement_normalisation(self):
        from app.cfs_adapter import grounded_finding_to_cfs
        fact = grounded_finding_to_cfs(
            finding=_SAMPLE_FINDING,
            patient_id="P001",
            report_id="R-001",
            report_date="2026-04-01",
            modality="CT",
            hadm_id="",
        )
        assert fact["measurement"] is not None
        assert "normalized_mm" in fact["measurement"]

    def test_certainty_label_from_score(self):
        from app.cfs_adapter import _certainty_label
        finding_high = {"confidence_score": 0.95}
        assert _certainty_label(finding_high) == "confirmed"

        finding_mid = {"confidence_score": 0.75}
        assert _certainty_label(finding_mid) == "probable"

        finding_low = {"confidence_score": 0.55}
        assert _certainty_label(finding_low) == "suspected"

    def test_certainty_label_from_string(self):
        from app.cfs_adapter import _certainty_label
        assert _certainty_label({"certainty": "definite"}) == "confirmed"
        assert _certainty_label({"certainty": "probable"}) == "probable"
        assert _certainty_label({"certainty": "possible"}) == "suspected"
        assert _certainty_label({"certainty": "indeterminate"}) == "indeterminate"
