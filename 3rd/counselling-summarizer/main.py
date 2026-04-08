from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request

from agents.cfs_emitter import build_session_summary, emit_clinical_facts
from agents.fact_extractor import FactExtractionError, OpenRouterFactExtractor
from agents.guardrails import validate_counselling_facts
from agents.segment_analyzer import analyze_segments
from agents.transcript_corrector import TranscriptCorrector
from config import Settings, get_settings
from models.request import SummarizeRequest, TranscriptSegment
from models.response import (
    ProcessingMetadata,
    ProcessingResult,
    ProcessingStats,
    SummarizeResponse,
)

AGENT_ID = "counselling-summarizer"


def create_app(
    settings: Settings | None = None,
    fact_extractor: OpenRouterFactExtractor | None = None,
    transcript_corrector: TranscriptCorrector | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Counselling Summarizer",
        version="0.1.0",
        description="Extract clinically relevant counselling facts from English transcripts.",
    )
    resolved_settings = settings or get_settings()
    app.state.settings = resolved_settings
    app.state.fact_extractor = fact_extractor or OpenRouterFactExtractor(resolved_settings)
    app.state.transcript_corrector = transcript_corrector or TranscriptCorrector(resolved_settings)

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/summarize", response_model=SummarizeResponse)
    def summarize(payload: SummarizeRequest, request: Request) -> SummarizeResponse:
        started_at = perf_counter()
        settings = request.app.state.settings
        extractor = request.app.state.fact_extractor
        corrector = request.app.state.transcript_corrector

        full_text = payload.full_text_english.strip() or _render_full_text(
            payload.transcript_english.segments
        )

        # Step 1: Correct transcript + generate bullet points
        corrected_transcript, bullet_points = corrector.correct(
            segments=payload.transcript_english.segments,
            full_transcript=full_text,
        )

        # Step 2: Segment analysis uses original segments for timing accuracy
        analysis = analyze_segments(payload.transcript_english.segments)

        # Step 3: Structured fact extraction (uses corrected transcript for better accuracy)
        try:
            raw_facts = extractor.extract(analysis.relevant_segments, corrected_transcript or full_text)
        except FactExtractionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        validated_facts = validate_counselling_facts(
            facts=raw_facts,
            transcript=corrected_transcript or full_text,
            min_certainty_threshold=settings.min_certainty_threshold,
            diagnosis_filter_enabled=settings.diagnosis_filter_enabled,
        )
        clinical_facts = emit_clinical_facts(
            counselling_facts=validated_facts,
            department=payload.department,
            emitted_at=datetime.now(UTC),
        )

        response = SummarizeResponse(
            agent_id=AGENT_ID,
            patient_id=payload.patient_id,
            timestamp=datetime.now(UTC),
            result=ProcessingResult(
                counselling_facts=validated_facts,
                clinical_facts=clinical_facts,
                bullet_points=bullet_points,
                corrected_transcript=corrected_transcript,
                session_summary=build_session_summary(validated_facts),
                stats=ProcessingStats(
                    total_segments_analyzed=len(payload.transcript_english.segments),
                    clinically_relevant_segments=len(analysis.relevant_segments),
                    facts_extracted=len(validated_facts),
                ),
            ),
            metadata=ProcessingMetadata(
                llm_used=getattr(extractor, "model_name", settings.llm_model),
                processing_time_ms=int((perf_counter() - started_at) * 1000),
            ),
            errors=[],
        )
        return response

    return app


def _render_full_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"{segment.speaker.title()}: {segment.text}" for segment in segments)


app = create_app()
