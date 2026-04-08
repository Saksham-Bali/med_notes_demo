"""
Tests for fact-graph-service API.

Uses TestClient (sync) with a temporary data directory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Patch the settings data_dir before importing main so the app uses a temp dir.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture(scope="module")
def client(tmp_data_dir: Path):
    import app.config as cfg_module

    # Monkey-patch from_env to return a temp-dir-backed Settings.
    original_from_env = cfg_module.Settings.from_env

    @classmethod  # type: ignore[misc]
    def patched_from_env(cls):
        return cfg_module.Settings(data_dir=tmp_data_dir)

    cfg_module.Settings.from_env = patched_from_env  # type: ignore[method-assign]

    from app.main import app as fastapi_app

    with TestClient(fastapi_app) as c:
        yield c

    cfg_module.Settings.from_env = original_from_env  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Fixtures: sample payloads
# ---------------------------------------------------------------------------

PATIENT_ID = "test-patient-001"

SAMPLE_FACT = {
    "patient_id": PATIENT_ID,
    "date": "2024-03-15",
    "source_type": "radiology",
    "source_report_id": "RPT-001",
    "hadm_id": "HAD-001",
    "entity_name": "pleural_effusion",
    "radlex_id": "RID34539",
    "certainty": 0.8,
    "certainty_label": "suspected",
    "is_negated": False,
    "modality": "CT",
    "evidence_text": "Small left-sided pleural effusion is identified.",
    "body_region": "chest",
    "measurement": {
        "value": 15.0,
        "unit": "mm",
        "normalized_mm": 15.0,
        "raw_text": "15 mm",
    },
}

SAMPLE_INGEST_REQUEST = {
    "patient_id": PATIENT_ID,
    "facts": [SAMPLE_FACT],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ingest_returns_200(client: TestClient):
    resp = client.post("/api/v1/ingest", json=SAMPLE_INGEST_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_id"] == PATIENT_ID
    assert body["facts_ingested"] == 1
    # At minimum one entity should have been created.
    assert body["entities_created"] >= 1


def test_ingest_creates_entity(client: TestClient):
    """A second ingest with the same entity updates rather than creates."""
    second_fact = dict(SAMPLE_FACT)
    second_fact["date"] = "2024-04-01"
    second_fact["source_report_id"] = "RPT-002"
    resp = client.post(
        "/api/v1/ingest",
        json={"patient_id": PATIENT_ID, "facts": [second_fact]},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Entity already existed; should be 0 new + 1 updated.
    assert body["entities_created"] == 0
    assert body["entities_updated"] >= 1


def test_ingest_mismatched_patient_id_rejected(client: TestClient):
    bad_fact = dict(SAMPLE_FACT)
    bad_fact["patient_id"] = "some-other-patient"
    resp = client.post(
        "/api/v1/ingest",
        json={"patient_id": PATIENT_ID, "facts": [bad_fact]},
    )
    assert resp.status_code == 422


def test_get_state_after_ingest(client: TestClient):
    resp = client.get(f"/api/v1/patient/{PATIENT_ID}/state")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_id"] == PATIENT_ID
    assert body["entity_count"] >= 1
    assert len(body["entities"]) == body["entity_count"]
    entity_names = [e["canonical_name"] for e in body["entities"]]
    assert "pleural_effusion" in entity_names


def test_get_timeline_after_ingest(client: TestClient):
    resp = client.get(f"/api/v1/patient/{PATIENT_ID}/timeline")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_id"] == PATIENT_ID
    assert body["event_count"] >= 1
    events = body["events"]
    assert len(events) == body["event_count"]
    # Events should be sorted by date.
    dates = [e["date"] for e in events]
    assert dates == sorted(dates)


def test_get_entity_history(client: TestClient):
    # First find the entity_id from state.
    state = client.get(f"/api/v1/patient/{PATIENT_ID}/state").json()
    entity_id = state["entities"][0]["entity_id"]

    resp = client.get(f"/api/v1/patient/{PATIENT_ID}/entity/{entity_id}/history")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_id"] == entity_id
    assert body["patient_id"] == PATIENT_ID
    assert body["event_count"] >= 1
    assert len(body["events"]) == body["event_count"]


def test_get_entity_history_not_found(client: TestClient):
    resp = client.get(f"/api/v1/patient/{PATIENT_ID}/entity/nonexistent_entity/history")
    assert resp.status_code == 404


def test_check_conflicts_no_conflict(client: TestClient):
    """A new fact for a new entity should report no conflicts."""
    new_fact = dict(SAMPLE_FACT)
    new_fact["entity_name"] = "brand_new_finding_xyz"
    new_fact["radlex_id"] = None
    resp = client.post(
        f"/api/v1/patient/{PATIENT_ID}/check-conflicts",
        json=[new_fact],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict_count"] == 0


def test_check_conflicts_detects_conflict(client: TestClient):
    """Asserting presence of a finding for an entity that is currently 'absent'
    (all events negated) should be detected as a conflict."""
    # Use a fresh patient so the entity has no prior non-negated events.
    conflict_patient = "conflict-test-patient"
    negated_fact = dict(SAMPLE_FACT)
    negated_fact["patient_id"] = conflict_patient
    negated_fact["entity_name"] = "pericardial_effusion"
    negated_fact["date"] = "2024-05-01"
    negated_fact["source_report_id"] = "RPT-CONFLICT-01"
    negated_fact["certainty_label"] = "confirmed"
    negated_fact["is_negated"] = True

    # Ingest one fully-negated fact so the entity status becomes "absent".
    ingest_resp = client.post(
        "/api/v1/ingest",
        json={"patient_id": conflict_patient, "facts": [negated_fact]},
    )
    assert ingest_resp.status_code == 200

    # Verify entity is absent.
    state = client.get(f"/api/v1/patient/{conflict_patient}/state").json()
    entity = next(
        (e for e in state["entities"] if e["canonical_name"] == "pericardial_effusion"),
        None,
    )
    assert entity is not None
    assert entity["status"] == "absent"

    # Now check conflict: a new confirmed non-negated fact for the absent entity.
    conflict_fact = dict(SAMPLE_FACT)
    conflict_fact["patient_id"] = conflict_patient
    conflict_fact["entity_name"] = "pericardial_effusion"
    conflict_fact["date"] = "2024-06-01"
    conflict_fact["certainty_label"] = "confirmed"
    conflict_fact["is_negated"] = False
    resp = client.post(
        f"/api/v1/patient/{conflict_patient}/check-conflicts",
        json=[conflict_fact],
    )
    assert resp.status_code == 200
    body = resp.json()
    # Entity is absent but new fact asserts presence → conflict.
    assert body["conflict_count"] >= 1


def test_ingest_negated_finding(client: TestClient):
    """Negated findings should be ingested cleanly."""
    neg_fact = dict(SAMPLE_FACT)
    neg_fact["patient_id"] = "neg-patient-001"
    neg_fact["is_negated"] = True
    neg_fact["certainty_label"] = "confirmed"
    neg_fact["entity_name"] = "pneumothorax"
    resp = client.post(
        "/api/v1/ingest",
        json={"patient_id": "neg-patient-001", "facts": [neg_fact]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["facts_ingested"] == 1

    state = client.get("/api/v1/patient/neg-patient-001/state").json()
    entity = next(e for e in state["entities"] if e["canonical_name"] == "pneumothorax")
    # All events are negated → status should be "absent"
    assert entity["status"] == "absent"


def test_ingest_multiple_facts(client: TestClient):
    """Multiple facts for different entities in one request."""
    facts = [
        {**SAMPLE_FACT, "patient_id": "multi-001", "entity_name": "atelectasis", "source_report_id": "RPT-M1"},
        {**SAMPLE_FACT, "patient_id": "multi-001", "entity_name": "consolidation", "source_report_id": "RPT-M1"},
        {**SAMPLE_FACT, "patient_id": "multi-001", "entity_name": "ground_glass_opacity", "source_report_id": "RPT-M1"},
    ]
    resp = client.post(
        "/api/v1/ingest",
        json={"patient_id": "multi-001", "facts": facts},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["facts_ingested"] == 3
    assert body["entities_created"] == 3

    state = client.get("/api/v1/patient/multi-001/state").json()
    assert state["entity_count"] == 3
