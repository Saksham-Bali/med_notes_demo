from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings(tmp_path):
    return Settings(
        data_dir=tmp_path,
        enable_fact_graph=False,
        enable_summary_generator=False,
    )


def test_counselling_workflow_creates_review_session(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/transcribe":
            return httpx.Response(
                200,
                json={
                    "agent_id": "voice-transcription",
                    "patient_id": "PAT-001",
                    "result": {
                        "transcript_original": {
                            "language": "hi",
                            "segments": [{"speaker": "patient", "start_time": 0.0, "end_time": 2.0, "text": "dar lag raha hai"}],
                        },
                        "transcript_english": {
                            "language": "en",
                            "segments": [{"speaker": "patient", "start_time": 0.0, "end_time": 2.0, "text": "I am afraid"}],
                        },
                        "full_text_english": "Patient: I am afraid",
                    },
                },
            )
        if request.url.path == "/api/v1/summarize":
            return httpx.Response(
                200,
                json={
                    "agent_id": "counselling-summarizer",
                    "patient_id": "PAT-001",
                    "result": {
                        "counselling_facts": [
                            {
                                "fact": "Patient expressed fear",
                                "category": "CONCERN",
                                "certainty": 0.92,
                                "evidence_text": "I am afraid",
                                "speaker": "patient",
                                "selectable": True,
                            }
                        ],
                        "clinical_facts": [
                            {
                                "entity": "fear about treatment",
                                "entity_type": "PRIMARY",
                                "certainty": 0.92,
                                "evidence": "I am afraid",
                                "source_type": "COUNSELLING",
                            }
                        ],
                        "session_summary": "Patient discussed fear.",
                        "stats": {"facts_extracted": 1},
                    },
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    app = create_app(
        _settings(tmp_path),
        agent_transport=httpx.MockTransport(handler),
        data_dir=tmp_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflow/counselling",
            files={"audio": ("session.wav", b"fake-audio", "audio/wav")},
            data={
                "patient_id": "PAT-001",
                "patient_consent": "true",
                "consent_timestamp": datetime(2026, 3, 26, tzinfo=timezone.utc).isoformat(),
                "session_type": "counselling",
                "department": "oncology",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_approval"
    assert payload["data"]["counselling_facts"][0]["id"].startswith("cf-csl-")
    session_file = next((tmp_path / "counselling_sessions").glob("*.json"))
    stored = json.loads(session_file.read_text())
    assert stored["patient_id"] == "PAT-001"
    assert stored["counselling_facts"][0]["id"] == payload["data"]["counselling_facts"][0]["id"]


def test_counselling_approval_queues_fact_graph_ingest_when_dependency_missing(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/transcribe":
            return httpx.Response(
                200,
                json={
                    "agent_id": "voice-transcription",
                    "patient_id": "PAT-001",
                    "result": {
                        "transcript_original": {"language": "hi", "segments": []},
                        "transcript_english": {"language": "en", "segments": []},
                        "full_text_english": "",
                    },
                },
            )
        if request.url.path == "/api/v1/summarize":
            return httpx.Response(
                200,
                json={
                    "agent_id": "counselling-summarizer",
                    "patient_id": "PAT-001",
                    "result": {
                        "counselling_facts": [{"fact": "Fear", "category": "CONCERN", "certainty": 0.9, "evidence_text": "Fear", "speaker": "patient", "selectable": True}],
                        "clinical_facts": [{"entity": "fear", "entity_type": "PRIMARY", "certainty": 0.9}],
                        "session_summary": "summary",
                        "stats": {},
                    },
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    app = create_app(
        _settings(tmp_path),
        agent_transport=httpx.MockTransport(handler),
        data_dir=tmp_path,
    )

    with TestClient(app) as client:
        session_response = client.post(
            "/api/v1/workflow/counselling",
            files={"audio": ("session.wav", b"fake-audio", "audio/wav")},
            data={
                "patient_id": "PAT-001",
                "patient_consent": "true",
                "consent_timestamp": datetime(2026, 3, 26, tzinfo=timezone.utc).isoformat(),
            },
        )
        session_id = session_response.json()["data"]["session_id"]
        fact_id = session_response.json()["data"]["counselling_facts"][0]["id"]
        approval_response = client.post(
            "/api/v1/workflow/counselling/approve",
            json={
                "patient_id": "PAT-001",
                "session_id": session_id,
                "approved_fact_ids": [fact_id],
            },
        )

    assert approval_response.status_code == 200
    payload = approval_response.json()
    assert payload["status"] == "pending_dependency"
    assert payload["deferred_jobs"][0]["dependency"] == "fact-graph"
    job_file = next((tmp_path / "deferred_jobs").glob("*.json"))
    stored = json.loads(job_file.read_text())
    assert stored["patient_id"] == "PAT-001"
    assert stored["payload"]["session_id"] == session_id


def test_generate_summary_uses_draft_summary_until_generator_exists(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/validate":
            body = json.loads(request.content.decode())
            assert body["discharge_summary"]["brief_summary"] == "Stable for discharge"
            return httpx.Response(
                200,
                json={
                    "agent_id": "qa-agent",
                    "result": {
                        "verdict": "PASS",
                        "issues": [],
                        "stats": {"total_checks_run": 4, "passed": 4, "failed": 0, "critical_failures": 0},
                        "audit_trail": {"validation_id": "VAL-1", "timestamp": "2026-03-26T00:00:00Z", "checks_performed": [], "summary_hash": "sha256:test"},
                    },
                },
            )
        if request.url.path == "/api/v1/translate":
            return httpx.Response(
                200,
                json={
                    "agent_id": "translation-layer",
                    "result": {
                        "translated_text": "sthir hai",
                        "source_language": "en-IN",
                        "target_language": "hi",
                        "translation_model": "mock",
                        "files": {"pdf_english": "/tmp/en.pdf", "pdf_translated": "/tmp/hi.pdf", "audio": None, "fhir_bundle": None},
                        "warnings": [],
                    },
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    app = create_app(
        _settings(tmp_path),
        agent_transport=httpx.MockTransport(handler),
        data_dir=tmp_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflow/generate-summary",
            json={
                "patient_id": "PAT-001",
                "discharge_summary": {"brief_summary": "Stable for discharge"},
                "source_facts": [{"entity": "stable", "entity_type": "PRIMARY", "certainty": 0.9}],
                "target_language": "hi",
                "generate_audio": False,
                "generate_pdf": True,
                "generate_fhir": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["data"]["translation"]["result"]["target_language"] == "hi"
