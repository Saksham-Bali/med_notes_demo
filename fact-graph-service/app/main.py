"""
fact-graph-service — Agent 06

Wraps the radiology fact graph in an HTTP API on port 5006.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .models import ClinicalFact, ImportRequest, IngestRequest, IngestResponse, PatientSummary
from .store import PatientStore

# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

_settings = Settings.from_env()
_patient_store: PatientStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _patient_store
    _settings.data_dir.mkdir(parents=True, exist_ok=True)
    _patient_store = PatientStore(data_dir=_settings.data_dir)
    yield
    _patient_store = None


app = FastAPI(
    title="fact-graph-service",
    description="Agent 06 — Clinical Fact Graph HTTP API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _store() -> PatientStore:
    if _patient_store is None:
        raise RuntimeError("PatientStore not initialised — lifespan not running")
    return _patient_store


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/ingest",
    response_model=IngestResponse,
    tags=["ingest"],
    summary="Ingest a batch of ClinicalFacts for one or more patients",
)
def ingest(request: IngestRequest) -> IngestResponse:
    """
    Accepts a batch of ClinicalFacts and appends them to the fact graph.
    All facts must have `patient_id` set; the request-level `patient_id` is
    used as the default and validated against each fact.
    """
    # Ensure each fact carries the correct patient_id from the request envelope.
    for fact in request.facts:
        if fact.patient_id != request.patient_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Fact {fact.fact_id} has patient_id='{fact.patient_id}' "
                    f"but request patient_id='{request.patient_id}'."
                ),
            )

    try:
        stats = _store().ingest(request.facts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IngestResponse(
        patient_id=request.patient_id,
        facts_ingested=stats["facts_ingested"],
        entities_created=stats["entities_created"],
        entities_updated=stats["entities_updated"],
    )


# ---------------------------------------------------------------------------
# Patient state
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/patient/{patient_id}/state",
    tags=["query"],
    summary="Get the current entity state for a patient",
)
def get_state(patient_id: str) -> dict[str, Any]:
    try:
        return _store().get_state(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/v1/patient/{patient_id}/timeline",
    tags=["query"],
    summary="Get the chronological event timeline for a patient",
)
def get_timeline(patient_id: str) -> dict[str, Any]:
    try:
        return _store().get_timeline(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/v1/patient/{patient_id}/entity/{entity_id}/history",
    tags=["query"],
    summary="Get the full event history for a single entity",
)
def get_entity_history(patient_id: str, entity_id: str) -> dict[str, Any]:
    result = _store().get_entity_history(patient_id, entity_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{entity_id}' not found for patient '{patient_id}'.",
        )
    return result


# ---------------------------------------------------------------------------
# Conflict check
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/patient/{patient_id}/check-conflicts",
    tags=["query"],
    summary="Check incoming facts for conflicts against the existing graph",
)
def check_conflicts(patient_id: str, facts: list[ClinicalFact]) -> dict[str, Any]:
    # Ensure all facts carry the path patient_id.
    for fact in facts:
        fact.patient_id = patient_id
    try:
        return _store().check_conflicts(patient_id, facts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Import & list
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/patient/{patient_id}/import",
    tags=["seed"],
    summary="Import a raw TMC FactGraph JSON for a patient",
)
def import_graph(patient_id: str, request: ImportRequest) -> dict:
    if request.patient_id != patient_id:
        raise HTTPException(status_code=422, detail="Path and body patient_id mismatch")
    try:
        return _store().import_graph(patient_id, request.fact_graph)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/v1/patients",
    tags=["query"],
    summary="List all patients with summary stats",
)
def list_patients() -> list[dict]:
    return _store().list_patients()
