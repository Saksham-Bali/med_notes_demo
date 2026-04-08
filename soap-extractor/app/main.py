from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="soap-extractor", version="1.0.0")


class ExtractRequest(BaseModel):
    text: str
    patient_id: str
    department: str | None = None
    source_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    layout_regions: list[Any] = Field(default_factory=list)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "soap-extractor"}


@app.post("/api/v1/extract")
async def extract(request: ExtractRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="'text' field must not be empty.")

    from app.soap import run_soap_extraction

    try:
        result = run_soap_extraction(
            text=request.text,
            patient_id=request.patient_id,
            department=request.department,
            source_confidence=request.source_confidence,
            layout_regions=request.layout_regions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(content={"result": result})
