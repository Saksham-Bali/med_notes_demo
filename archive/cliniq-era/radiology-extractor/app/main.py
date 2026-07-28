"""
radiology-extractor — Agent 03 of the clinical intelligence platform.

Wraps the TMC HybridExtractor + EntityGrounder as a stateless HTTP service.
Port: 5003
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.cfs_adapter import grounded_finding_to_cfs
from app.extractor import RadiologyExtractor

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("radiology_extractor.main")


# ---------------------------------------------------------------------------
# Lifespan: initialise heavy objects once at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting radiology-extractor service …")
    app.state.extractor = RadiologyExtractor()
    logger.info("radiology-extractor ready on port 5003.")
    yield
    logger.info("radiology-extractor shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="radiology-extractor",
    description=(
        "Agent 03 — Extracts and grounds clinical findings from radiology "
        "reports using the TMC HybridExtractor + EntityGrounder pipeline."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class ExtractRequest(BaseModel):
    patient_id: str = Field(..., description="Patient identifier")
    report_text: str = Field(..., description="Current radiology report text")
    prior_report_text: Optional[str] = Field(
        None, description="Previous report text for temporal comparison"
    )
    report_id: str = Field(default="", description="Report identifier")
    report_date: str = Field(default="", description="Report date (YYYY-MM-DD)")
    modality: str = Field(default="CT", description="Imaging modality")
    body_region: str = Field(default="", description="Anatomical body region")
    hadm_id: str = Field(default="", description="Hospital admission ID")


class ExtractResult(BaseModel):
    clinical_facts: list[dict]
    entity_count: int
    extraction_source: str
    llm_calls_made: Optional[int] = None
    processing_time_ms: int


class ExtractResponse(BaseModel):
    result: ExtractResult


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "radiology-extractor"}


@app.post("/api/v1/extract", response_model=ExtractResponse)
async def extract(request: ExtractRequest) -> ExtractResponse:
    """
    Extract clinical findings from a radiology report and return
    them as ClinicalFact objects grounded to RadLex/SNOMED ontologies.
    """
    if not request.report_text or not request.report_text.strip():
        raise HTTPException(status_code=422, detail="report_text must not be empty")

    start_time = time.time()

    extractor: RadiologyExtractor = app.state.extractor

    try:
        findings = extractor.extract(
            report_text=request.report_text,
            prior_report_text=request.prior_report_text,
            report_id=request.report_id,
            report_date=request.report_date,
            modality=request.modality,
            body_region=request.body_region,
            hadm_id=request.hadm_id,
        )
    except Exception as exc:
        logger.exception(
            "Extraction error for patient %s report %s",
            request.patient_id,
            request.report_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {type(exc).__name__}: {exc}",
        )

    # Convert grounded findings to ClinicalFact dicts
    clinical_facts = [
        grounded_finding_to_cfs(
            finding=f,
            patient_id=request.patient_id,
            report_id=request.report_id,
            report_date=request.report_date,
            modality=request.modality,
            hadm_id=request.hadm_id,
        )
        for f in findings
    ]

    processing_time_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "patient=%s report=%s facts=%d time_ms=%d",
        request.patient_id,
        request.report_id,
        len(clinical_facts),
        processing_time_ms,
    )

    return ExtractResponse(
        result=ExtractResult(
            clinical_facts=clinical_facts,
            entity_count=len(clinical_facts),
            extraction_source="hybrid",
            processing_time_ms=processing_time_ms,
        )
    )
