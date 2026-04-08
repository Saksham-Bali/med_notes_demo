from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .agent_client import AgentClient, collect_agent_health
from .config import Settings
from .errors import AgentCallError, MissingDependencyError, OrchestratorError, SessionNotFoundError
from .registry import build_registry
from .schemas import (
    CounsellingApproveRequest,
    DeferredJobInfo,
    DepartmentMergeRequest,
    DepartmentResolveRequest,
    HealthAgentStatus,
    HealthResponse,
    PreviewConfirmRequest,
    RadiologyPreviewRequest,
    RadiologyWorkflowRequest,
    SummaryWorkflowRequest,
    WorkflowEnvelope,
    WorkflowStep,
)
from .storage import CounsellingSessionStore, DeferredJobStore


def _now() -> datetime:
    return datetime.now(UTC)


def _build_deferred_job_info(job: dict[str, Any]) -> DeferredJobInfo:
    return DeferredJobInfo(
        job_id=job["job_id"],
        dependency=job["dependency"],
        job_type=job["job_type"],
        status=job["status"],
    )


def create_app(
    settings: Settings | None = None,
    *,
    agent_transport: httpx.AsyncBaseTransport | None = None,
    data_dir: Path | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_data_dir = (data_dir or resolved_settings.data_dir).resolve()
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    registry = build_registry(resolved_settings)
    session_store = CounsellingSessionStore(resolved_data_dir / "counselling_sessions")
    deferred_job_store = DeferredJobStore(resolved_data_dir / "deferred_jobs")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved_settings
        app.state.registry = registry
        app.state.agent_client = AgentClient(registry, transport=agent_transport)
        app.state.session_store = session_store
        app.state.deferred_job_store = deferred_job_store
        yield
        await app.state.agent_client.close()

    app = FastAPI(
        title="Clinical Intelligence Platform Orchestrator",
        version=resolved_settings.version,
        lifespan=lifespan,
    )

    @app.exception_handler(OrchestratorError)
    async def orchestrator_error_handler(_, exc: OrchestratorError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def orchestrator_health() -> HealthResponse:
        health = await collect_agent_health(app.state.agent_client)
        return HealthResponse(
            service=resolved_settings.service_name,
            timestamp=_now(),
            agents=[HealthAgentStatus(**item) for item in health],
        )

    @app.post("/api/v1/workflow/handwritten-note", response_model=WorkflowEnvelope)
    async def handwritten_note_workflow(
        image: UploadFile = File(...),
        patient_id: str = Form(...),
        department: str | None = Form(default=None),
    ) -> WorkflowEnvelope:
        missing = [
            name
            for name in ("ocr-agent", "soap-extractor")
            if not app.state.registry.is_enabled(name)
        ]
        if missing:
            detail = ", ".join(missing)
            return WorkflowEnvelope(
                workflow="handwritten-note",
                status="pending_dependency",
                message=f"Workflow scaffolded, waiting on: {detail}",
                steps=[WorkflowStep(agent=name, status="pending_dependency") for name in missing],
                data={"patient_id": patient_id, "department": department, "filename": image.filename},
            )

        image_bytes = await image.read()
        ocr_result = await app.state.agent_client.call(
            "ocr-agent",
            "extract",
            files={"image": (image.filename or "note.png", image_bytes, image.content_type or "application/octet-stream")},
            data={"patient_id": patient_id, "department": department or "", "source_type": "handwritten"},
        )
        soap_result = await app.state.agent_client.call(
            "soap-extractor",
            "extract",
            json={
                "text": ocr_result.get("result", {}).get("full_text", ""),
                "layout_regions": ocr_result.get("result", {}).get("layout_regions", []),
                "patient_id": patient_id,
                "source_confidence": ocr_result.get("result", {}).get("overall_confidence"),
                "department": department,
            },
        )
        deferred_jobs = []
        steps = [
            WorkflowStep(agent="ocr-agent", status="success"),
            WorkflowStep(agent="soap-extractor", status="success"),
        ]
        if app.state.registry.is_enabled("fact-graph"):
            await app.state.agent_client.call(
                "fact-graph",
                "ingest",
                json={"patient_id": patient_id, "facts": soap_result.get("result", {}).get("clinical_facts", [])},
            )
            steps.append(WorkflowStep(agent="fact-graph", status="success"))
            status = "completed"
            message = "Handwritten note processed and ingested."
        else:
            job = app.state.deferred_job_store.create(
                dependency="fact-graph",
                job_type="fact_graph_ingest",
                patient_id=patient_id,
                payload={"facts": soap_result.get("result", {}).get("clinical_facts", [])},
            )
            deferred_jobs.append(_build_deferred_job_info(job))
            steps.append(WorkflowStep(agent="fact-graph", status="pending_dependency"))
            status = "pending_dependency"
            message = "Note processed. Fact Graph ingest has been queued."
        return WorkflowEnvelope(
            workflow="handwritten-note",
            status=status,
            message=message,
            steps=steps,
            data={
                "patient_id": patient_id,
                "soap": soap_result.get("result", {}).get("soap"),
                "clinical_facts": soap_result.get("result", {}).get("clinical_facts", []),
                "ocr": ocr_result.get("result", {}),
            },
            deferred_jobs=deferred_jobs,
        )

    @app.post("/api/v1/workflow/radiology-report", response_model=WorkflowEnvelope)
    async def radiology_report_workflow(payload: RadiologyWorkflowRequest) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("radiology-extractor"):
            return WorkflowEnvelope(
                workflow="radiology-report",
                status="pending_dependency",
                message="Radiology extractor is not enabled yet.",
                steps=[WorkflowStep(agent="radiology-extractor", status="pending_dependency")],
                data=payload.model_dump(),
            )
        result = await app.state.agent_client.call(
            "radiology-extractor",
            "extract",
            json=payload.model_dump(),
        )
        deferred_jobs = []
        steps = [WorkflowStep(agent="radiology-extractor", status="success")]
        if app.state.registry.is_enabled("fact-graph"):
            await app.state.agent_client.call(
                "fact-graph",
                "ingest",
                json={"patient_id": payload.patient_id, "facts": result.get("result", {}).get("clinical_facts", [])},
            )
            steps.append(WorkflowStep(agent="fact-graph", status="success"))
            status = "completed"
            message = "Radiology report processed and ingested."
        else:
            job = app.state.deferred_job_store.create(
                dependency="fact-graph",
                job_type="fact_graph_ingest",
                patient_id=payload.patient_id,
                payload={"facts": result.get("result", {}).get("clinical_facts", [])},
            )
            deferred_jobs.append(_build_deferred_job_info(job))
            steps.append(WorkflowStep(agent="fact-graph", status="pending_dependency"))
            status = "pending_dependency"
            message = "Radiology findings are ready. Fact Graph ingest has been queued."
        return WorkflowEnvelope(
            workflow="radiology-report",
            status=status,
            message=message,
            steps=steps,
            data=result,
            deferred_jobs=deferred_jobs,
        )

    @app.post("/api/v1/workflow/counselling", response_model=WorkflowEnvelope)
    async def counselling_workflow(
        audio: UploadFile = File(...),
        patient_id: str = Form(...),
        patient_consent: bool = Form(...),
        consent_timestamp: datetime = Form(...),
        language_hint: str | None = Form(default=None),
        session_type: str | None = Form(default=None),
        department: str | None = Form(default=None),
    ) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("voice-transcription"):
            raise MissingDependencyError("voice-transcription")
        if not app.state.registry.is_enabled("counselling-summarizer"):
            raise MissingDependencyError("counselling-summarizer")

        audio_bytes = await audio.read()
        transcription = await app.state.agent_client.call(
            "voice-transcription",
            "transcribe",
            files={
                "audio": (
                    audio.filename or "session.wav",
                    audio_bytes,
                    audio.content_type or "application/octet-stream",
                )
            },
            data={
                "patient_id": patient_id,
                "patient_consent": str(patient_consent).lower(),
                "consent_timestamp": consent_timestamp.isoformat(),
                "language_hint": language_hint or "",
                "session_type": session_type or "",
                "department": department or "",
            },
        )
        summarizer = await app.state.agent_client.call(
            "counselling-summarizer",
            "summarize",
            json={
                "patient_id": patient_id,
                "transcript_english": transcription["result"]["transcript_english"],
                "full_text_english": transcription["result"]["full_text_english"],
                "session_type": session_type or "counselling",
                "department": department or "unknown",
            },
        )
        session = app.state.session_store.create(
            patient_id=patient_id,
            transcript_result=transcription,
            summarizer_result=summarizer,
        )
        return WorkflowEnvelope(
            workflow="counselling",
            status="awaiting_approval",
            message="Counselling facts are ready for clinician review.",
            steps=[
                WorkflowStep(agent="voice-transcription", status="success"),
                WorkflowStep(agent="counselling-summarizer", status="success"),
                WorkflowStep(agent="fact-graph", status="skipped", detail="Waiting for clinician approval."),
            ],
            data={
                "session_id": session["session_id"],
                "patient_id": patient_id,
                "session_summary": session.get("session_summary"),
                "corrected_transcript": session.get("corrected_transcript", ""),
                "transcript_english": transcription["result"]["transcript_english"],
                "transcript_original": transcription["result"]["transcript_original"],
                "counselling_facts": session["counselling_facts"],
                "clinical_facts": session["clinical_facts"],
                "bullet_points": session["bullet_points"],
                "stats": session["stats"],
            },
        )

    @app.post("/api/v1/workflow/counselling/approve", response_model=WorkflowEnvelope)
    async def approve_counselling(payload: CounsellingApproveRequest) -> WorkflowEnvelope:
        record = app.state.session_store.get(payload.session_id)
        if record["patient_id"] != payload.patient_id:
            raise HTTPException(status_code=400, detail="Patient ID does not match the stored session.")

        approved_fact_ids = set(payload.approved_fact_ids)
        approved_bullet_ids = set(payload.approved_bullet_ids)

        approved_counselling_facts = [f for f in record["counselling_facts"] if f["id"] in approved_fact_ids]
        approved_clinical_facts = [f for f in record["clinical_facts"] if f["id"] in approved_fact_ids]

        # Convert approved bullet points into ClinicalFacts for ingestion
        from datetime import UTC, datetime as _dt
        now_iso = _dt.now(UTC).isoformat()
        bullet_clinical_facts = [
            {
                "entity": bp["text"],
                "radlex_id": None,
                "entity_type": "PRIMARY",
                "certainty": 0.9,
                "evidence": bp["text"],
                "source_type": "COUNSELLING",
                "source_department": "counselling",
                "timestamp": now_iso,
                "negated": False,
                "status": "PRESENT",
            }
            for bp in record.get("bullet_points", [])
            if bp["id"] in approved_bullet_ids
        ]

        all_clinical_facts = approved_clinical_facts + bullet_clinical_facts
        app.state.session_store.mark_approved(
            payload.session_id,
            list(approved_fact_ids),
            list(approved_bullet_ids),
        )

        deferred_jobs = []
        steps = [WorkflowStep(agent="counselling-review", status="success")]
        if app.state.registry.is_enabled("fact-graph"):
            await app.state.agent_client.call(
                "fact-graph",
                "ingest",
                json={"patient_id": payload.patient_id, "facts": all_clinical_facts},
            )
            steps.append(WorkflowStep(agent="fact-graph", status="success"))
            status = "completed"
            message = "Approved counselling facts and bullet points were ingested."
        else:
            job = app.state.deferred_job_store.create(
                dependency="fact-graph",
                job_type="fact_graph_ingest",
                patient_id=payload.patient_id,
                payload={"session_id": payload.session_id, "facts": all_clinical_facts},
            )
            deferred_jobs.append(_build_deferred_job_info(job))
            steps.append(WorkflowStep(agent="fact-graph", status="pending_dependency"))
            status = "pending_dependency"
            message = "Approved facts were saved. Fact Graph ingest is queued until that service is ready."

        return WorkflowEnvelope(
            workflow="counselling-approve",
            status=status,
            message=message,
            steps=steps,
            data={
                "session_id": payload.session_id,
                "patient_id": payload.patient_id,
                "approved_facts_count": len(approved_clinical_facts),
                "approved_bullets_count": len(bullet_clinical_facts),
                "total_ingested": len(all_clinical_facts),
            },
            deferred_jobs=deferred_jobs,
        )

    @app.post("/api/v1/workflow/department-merge", response_model=WorkflowEnvelope)
    async def department_merge_workflow(payload: DepartmentMergeRequest) -> WorkflowEnvelope:
        result = await app.state.agent_client.call(
            "department-merger",
            "merge",
            json=payload.model_dump(mode="json"),
        )
        conflicts = result.get("result", {}).get("conflicts", [])
        unified_facts = result.get("result", {}).get("unified_facts", [])
        steps = [WorkflowStep(agent="department-merger", status="success")]
        deferred_jobs = []

        if conflicts:
            return WorkflowEnvelope(
                workflow="department-merge",
                status="needs_review",
                message="Cross-department conflicts require clinician review before ingest.",
                steps=steps + [WorkflowStep(agent="fact-graph", status="skipped", detail="Waiting for conflict resolution.")],
                data={
                    "patient_id": payload.patient_id,
                    "unified_facts": unified_facts,
                    "conflicts": conflicts,
                    "stats": result.get("result", {}).get("stats", {}),
                },
            )

        if app.state.registry.is_enabled("fact-graph"):
            await app.state.agent_client.call(
                "fact-graph",
                "ingest",
                json={"patient_id": payload.patient_id, "facts": unified_facts},
            )
            steps.append(WorkflowStep(agent="fact-graph", status="success"))
            status = "completed"
            message = "Department notes merged and ingested."
        else:
            job = app.state.deferred_job_store.create(
                dependency="fact-graph",
                job_type="fact_graph_ingest",
                patient_id=payload.patient_id,
                payload={"facts": unified_facts},
            )
            deferred_jobs.append(_build_deferred_job_info(job))
            steps.append(WorkflowStep(agent="fact-graph", status="pending_dependency"))
            status = "pending_dependency"
            message = "Department merge is complete. Fact Graph ingest has been queued."

        return WorkflowEnvelope(
            workflow="department-merge",
            status=status,
            message=message,
            steps=steps,
            data={
                "patient_id": payload.patient_id,
                "unified_facts": unified_facts,
                "conflicts": conflicts,
                "stats": result.get("result", {}).get("stats", {}),
            },
            deferred_jobs=deferred_jobs,
        )

    @app.post("/api/v1/workflow/department-merge/resolve", response_model=WorkflowEnvelope)
    async def resolve_department_merge(payload: DepartmentResolveRequest) -> WorkflowEnvelope:
        deferred_jobs = []
        steps = [WorkflowStep(agent="department-merge", status="success", detail="Conflicts resolved by clinician.")]
        if app.state.registry.is_enabled("fact-graph"):
            await app.state.agent_client.call(
                "fact-graph",
                "ingest",
                json={"patient_id": payload.patient_id, "facts": payload.resolved_facts},
            )
            steps.append(WorkflowStep(agent="fact-graph", status="success"))
            status = "completed"
            message = "Resolved department facts were ingested."
        else:
            job = app.state.deferred_job_store.create(
                dependency="fact-graph",
                job_type="fact_graph_ingest",
                patient_id=payload.patient_id,
                payload={
                    "facts": payload.resolved_facts,
                    "resolution_note": payload.resolution_note,
                },
            )
            deferred_jobs.append(_build_deferred_job_info(job))
            steps.append(WorkflowStep(agent="fact-graph", status="pending_dependency"))
            status = "pending_dependency"
            message = "Resolved department facts were saved and queued for future Fact Graph ingest."
        return WorkflowEnvelope(
            workflow="department-merge-resolve",
            status=status,
            message=message,
            steps=steps,
            data=payload.model_dump(mode="json"),
            deferred_jobs=deferred_jobs,
        )

    @app.post("/api/v1/workflow/generate-summary", response_model=WorkflowEnvelope)
    async def generate_summary_workflow(payload: SummaryWorkflowRequest) -> WorkflowEnvelope:
        steps: list[WorkflowStep] = []
        discharge_summary = payload.discharge_summary
        generator_response: dict[str, Any] | None = None

        if discharge_summary is None:
            if not app.state.registry.is_enabled("summary-generator"):
                return WorkflowEnvelope(
                    workflow="generate-summary",
                    status="pending_dependency",
                    message=(
                        "Summary generator is not enabled yet. Submit a draft discharge summary "
                        "to use QA and translation immediately."
                    ),
                    steps=[WorkflowStep(agent="summary-generator", status="pending_dependency")],
                    data=payload.model_dump(mode="json"),
                )
            generator_response = await app.state.agent_client.call(
                "summary-generator",
                "generate",
                json={
                    "patient_id": payload.patient_id,
                    "admission_date": payload.admission_date.isoformat() if payload.admission_date else None,
                    "discharge_date": payload.discharge_date.isoformat() if payload.discharge_date else None,
                    "attending_physician": payload.attending_physician,
                    "department": payload.department,
                    "approved_counselling_fact_ids": payload.approved_counselling_fact_ids,
                    "include_recist": payload.include_recist,
                    "template": payload.template,
                },
            )
            discharge_summary = generator_response.get("result", {}).get("discharge_summary")
            steps.append(WorkflowStep(agent="summary-generator", status="success"))

        qa_response = await app.state.agent_client.call(
            "qa-agent",
            "validate",
            json={
                "patient_id": payload.patient_id,
                "discharge_summary": discharge_summary,
                "source_facts": payload.source_facts,
            },
        )
        steps.append(WorkflowStep(agent="qa-agent", status="success"))
        verdict = qa_response.get("result", {}).get("verdict")
        if verdict != "PASS":
            return WorkflowEnvelope(
                workflow="generate-summary",
                status="needs_review",
                message="QA validation failed. Review the issues and regenerate or edit the summary.",
                steps=steps + [WorkflowStep(agent="translation-layer", status="skipped", detail="Blocked by QA failure.")],
                data={
                    "patient_id": payload.patient_id,
                    "discharge_summary": discharge_summary,
                    "qa": qa_response,
                    "generator": generator_response,
                },
            )

        translation_response = await app.state.agent_client.call(
            "translation-layer",
            "translate",
            json={
                "patient_id": payload.patient_id,
                "patient_name": payload.patient_name,
                "discharge_summary": discharge_summary,
                "target_language": payload.target_language,
                "generate_audio": payload.generate_audio,
                "generate_pdf": payload.generate_pdf,
                "generate_fhir": payload.generate_fhir,
            },
        )
        steps.append(WorkflowStep(agent="translation-layer", status="success"))
        return WorkflowEnvelope(
            workflow="generate-summary",
            status="completed",
            message="Summary passed QA and translation artifacts were generated.",
            steps=steps,
            data={
                "patient_id": payload.patient_id,
                "discharge_summary": discharge_summary,
                "qa": qa_response,
                "translation": translation_response,
                "generator": generator_response,
            },
        )

    @app.get("/api/v1/patients")
    async def list_patients():
        if not app.state.registry.is_enabled("fact-graph"):
            return []
        result = await app.state.agent_client.call(
            "fact-graph", "patients", method="GET",
        )
        return result

    @app.get("/api/v1/patient/{patient_id}/state", response_model=WorkflowEnvelope)
    async def patient_state(patient_id: str) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("fact-graph"):
            return WorkflowEnvelope(
                workflow="patient-state",
                status="pending_dependency",
                message="Fact Graph is not enabled yet.",
                steps=[WorkflowStep(agent="fact-graph", status="pending_dependency")],
                data={"patient_id": patient_id},
            )
        result = await app.state.agent_client.call(
            "fact-graph",
            "patient_state",
            method="GET",
            path_params={"patient_id": patient_id},
        )
        return WorkflowEnvelope(
            workflow="patient-state",
            status="completed",
            steps=[WorkflowStep(agent="fact-graph", status="success")],
            data=result,
        )

    @app.get("/api/v1/patient/{patient_id}/timeline", response_model=WorkflowEnvelope)
    async def patient_timeline(patient_id: str) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("fact-graph"):
            return WorkflowEnvelope(
                workflow="patient-timeline",
                status="pending_dependency",
                message="Fact Graph is not enabled yet.",
                steps=[WorkflowStep(agent="fact-graph", status="pending_dependency")],
                data={"patient_id": patient_id},
            )
        result = await app.state.agent_client.call(
            "fact-graph",
            "patient_timeline",
            method="GET",
            path_params={"patient_id": patient_id},
        )
        return WorkflowEnvelope(
            workflow="patient-timeline",
            status="completed",
            steps=[WorkflowStep(agent="fact-graph", status="success")],
            data=result,
        )

    @app.get("/api/v1/patient/{patient_id}/entity/{entity_id}", response_model=WorkflowEnvelope)
    async def entity_history(patient_id: str, entity_id: str) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("fact-graph"):
            return WorkflowEnvelope(
                workflow="entity-history",
                status="pending_dependency",
                message="Fact Graph is not enabled yet.",
                steps=[WorkflowStep(agent="fact-graph", status="pending_dependency")],
                data={"patient_id": patient_id, "entity_id": entity_id},
            )
        result = await app.state.agent_client.call(
            "fact-graph",
            "entity_history",
            method="GET",
            path_params={"patient_id": patient_id, "entity_id": entity_id},
        )
        return WorkflowEnvelope(
            workflow="entity-history",
            status="completed",
            steps=[WorkflowStep(agent="fact-graph", status="success")],
            data=result,
        )

    # ------------------------------------------------------------------
    # Preview / Confirm endpoints
    # ------------------------------------------------------------------

    @app.post("/api/v1/workflow/radiology-report/preview", response_model=WorkflowEnvelope)
    async def radiology_preview(payload: RadiologyPreviewRequest) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("radiology-extractor"):
            return WorkflowEnvelope(
                workflow="radiology-report-preview",
                status="pending_dependency",
                message="Radiology extractor is not enabled.",
                steps=[WorkflowStep(agent="radiology-extractor", status="pending_dependency")],
                data=payload.model_dump(mode="json"),
            )
        result = await app.state.agent_client.call(
            "radiology-extractor", "extract",
            json={
                "patient_id": payload.patient_id,
                "report_text": payload.report_text,
                "prior_report_text": payload.prior_report_text,
                "modality": payload.modality,
                "body_region": payload.body_region,
                "report_date": payload.report_date or datetime.now(UTC).date().isoformat(),
                "report_id": payload.report_id or f"report_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
                "hadm_id": payload.hadm_id or "",
            },
        )
        facts = result.get("result", {}).get("clinical_facts", [])
        return WorkflowEnvelope(
            workflow="radiology-report-preview",
            status="awaiting_review",
            message=f"Extracted {len(facts)} clinical facts. Review and approve before ingestion.",
            steps=[
                WorkflowStep(agent="radiology-extractor", status="success"),
                WorkflowStep(agent="fact-graph", status="skipped", detail="Waiting for clinician review."),
            ],
            data={
                "patient_id": payload.patient_id,
                "clinical_facts": facts,
                "extraction_metadata": {
                    "entity_count": result.get("result", {}).get("entity_count", len(facts)),
                    "extraction_source": result.get("result", {}).get("extraction_source", "hybrid"),
                    "processing_time_ms": result.get("result", {}).get("processing_time_ms"),
                },
            },
        )

    @app.post("/api/v1/workflow/handwritten-note/preview", response_model=WorkflowEnvelope)
    async def handwritten_note_preview(
        image: UploadFile = File(...),
        patient_id: str = Form(...),
        department: str | None = Form(default=None),
    ) -> WorkflowEnvelope:
        missing = [name for name in ("ocr-agent", "soap-extractor") if not app.state.registry.is_enabled(name)]
        if missing:
            return WorkflowEnvelope(
                workflow="handwritten-note-preview", status="pending_dependency",
                message=f"Waiting on: {', '.join(missing)}",
                steps=[WorkflowStep(agent=n, status="pending_dependency") for n in missing],
                data={"patient_id": patient_id},
            )

        image_bytes = await image.read()
        ocr_result = await app.state.agent_client.call(
            "ocr-agent", "extract",
            files={"image": (image.filename or "note.png", image_bytes, image.content_type or "application/octet-stream")},
            data={"patient_id": patient_id, "department": department or "", "source_type": "handwritten"},
        )
        soap_result = await app.state.agent_client.call(
            "soap-extractor", "extract",
            json={
                "text": ocr_result.get("result", {}).get("full_text", ""),
                "layout_regions": ocr_result.get("result", {}).get("layout_regions", []),
                "patient_id": patient_id,
                "source_confidence": ocr_result.get("result", {}).get("overall_confidence"),
                "department": department,
            },
        )
        facts = soap_result.get("result", {}).get("clinical_facts", [])
        return WorkflowEnvelope(
            workflow="handwritten-note-preview", status="awaiting_review",
            message=f"Extracted {len(facts)} facts from handwritten note. Review before ingestion.",
            steps=[
                WorkflowStep(agent="ocr-agent", status="success"),
                WorkflowStep(agent="soap-extractor", status="success"),
                WorkflowStep(agent="fact-graph", status="skipped", detail="Waiting for clinician review."),
            ],
            data={
                "patient_id": patient_id,
                "ocr": ocr_result.get("result", {}),
                "soap": soap_result.get("result", {}).get("soap"),
                "clinical_facts": facts,
            },
        )

    @app.post("/api/v1/workflow/department-merge/preview", response_model=WorkflowEnvelope)
    async def department_merge_preview(payload: DepartmentMergeRequest) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("department-merger"):
            raise MissingDependencyError("department-merger")

        merge_result = await app.state.agent_client.call(
            "department-merger", "merge",
            json={
                "patient_id": payload.patient_id,
                "department_notes": [n.model_dump(mode="json") for n in payload.department_notes],
            },
        )
        facts = merge_result.get("result", {}).get("unified_facts", [])
        conflicts = merge_result.get("result", {}).get("conflicts", [])

        status = "awaiting_review"
        message = f"Merged {len(facts)} facts from {len(payload.department_notes)} departments."
        if conflicts:
            message += f" {len(conflicts)} conflicts detected — please resolve."

        return WorkflowEnvelope(
            workflow="department-merge-preview", status=status,
            message=message,
            steps=[
                WorkflowStep(agent="department-merger", status="success"),
                WorkflowStep(agent="fact-graph", status="skipped", detail="Waiting for review."),
            ],
            data={
                "patient_id": payload.patient_id,
                "clinical_facts": facts,
                "conflicts": conflicts,
            },
        )

    @app.post("/api/v1/workflow/confirm", response_model=WorkflowEnvelope)
    async def confirm_facts(payload: PreviewConfirmRequest) -> WorkflowEnvelope:
        if not app.state.registry.is_enabled("fact-graph"):
            return WorkflowEnvelope(
                workflow="confirm", status="pending_dependency",
                message="Fact Graph is not enabled.",
                steps=[WorkflowStep(agent="fact-graph", status="pending_dependency")],
                data={"patient_id": payload.patient_id},
            )

        ingest_result = await app.state.agent_client.call(
            "fact-graph", "ingest",
            json={"patient_id": payload.patient_id, "facts": payload.approved_facts},
        )

        # Fetch updated patient state
        updated_state = await app.state.agent_client.call(
            "fact-graph", "patient_state",
            method="GET",
            path_params={"patient_id": payload.patient_id},
        )

        return WorkflowEnvelope(
            workflow="confirm", status="completed",
            message=f"Ingested {ingest_result.get('facts_ingested', len(payload.approved_facts))} approved facts.",
            steps=[WorkflowStep(agent="fact-graph", status="success")],
            data={
                "patient_id": payload.patient_id,
                "ingest_result": ingest_result,
                "updated_state": updated_state,
            },
        )

    return app


app = create_app()
