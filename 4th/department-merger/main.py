from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request

from agents.conflict_analyzer import ConflictAnalyzer
from agents.conflict_detector import detect_conflicts
from agents.entity_aligner import align_entities, build_unified_facts
from agents.parallel_extractor import ExtractionError, SOAPExtractorClient
from config import Settings, get_settings
from models.department_note import MergeRequest
from models.response import MergeResponse, MergeResult, ProcessingStats

AGENT_ID = "department-merger"


def create_app(
    settings: Settings | None = None,
    extractor: SOAPExtractorClient | None = None,
    conflict_analyzer: ConflictAnalyzer | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Department Merger",
        version="0.1.0",
        description="Merge cross-department clinical notes into a unified timeline.",
    )
    resolved_settings = settings or get_settings()
    app.state.settings = resolved_settings
    app.state.extractor = extractor or SOAPExtractorClient(
        base_url=resolved_settings.soap_extractor_url,
        timeout_seconds=resolved_settings.request_timeout_seconds,
    )
    app.state.conflict_analyzer = conflict_analyzer or ConflictAnalyzer(resolved_settings)

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/merge", response_model=MergeResponse)
    async def merge_departments(payload: MergeRequest, request: Request) -> MergeResponse:
        started_at = perf_counter()
        extractor = request.app.state.extractor
        analyzer = request.app.state.conflict_analyzer

        try:
            dept_extractions = await extractor.extract_all_departments(
                patient_id=payload.patient_id,
                department_notes=payload.department_notes,
            )
        except ExtractionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        aligned_entities = align_entities(dept_extractions)
        detected_conflicts = detect_conflicts(aligned_entities)
        analyzed_conflicts = await analyzer.analyze_many(detected_conflicts)
        unified_facts = build_unified_facts(aligned_entities, analyzed_conflicts)

        total_facts = sum(len(extraction.facts) for extraction in dept_extractions)
        _ = int((perf_counter() - started_at) * 1000)

        return MergeResponse(
            agent_id=AGENT_ID,
            patient_id=payload.patient_id,
            timestamp=datetime.now(UTC),
            result=MergeResult(
                unified_facts=unified_facts,
                conflicts=analyzed_conflicts,
                stats=ProcessingStats(
                    departments_processed=len(payload.department_notes),
                    total_facts_extracted=total_facts,
                    facts_merged=max(total_facts - len(unified_facts), 0),
                    conflicts_detected=len(analyzed_conflicts),
                ),
            ),
            errors=[],
        )

    return app


app = create_app()
