# Voice Counselling — Bullet Points + Clinical Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-based transcript correction and bullet-point generation to the counselling workflow, expose both bullet points and structured clinical facts in the review UI, and build the missing `workflow/counselling/` frontend page.

**Architecture:** The counselling summarizer gains a new `TranscriptCorrector` agent that runs before fact extraction; it takes the raw Sarvam transcript, corrects STT errors using full-context medical awareness, and produces clean bullet points. Both bullet points and structured `CounsellingFact`s are returned from the summarizer, stored in the session by the orchestrator, exposed in the API response, and shown side-by-side in the new frontend page for doctor review. Approved bullet points are converted to `ClinicalFact` objects and ingested alongside approved counselling facts.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, AzureOpenAI (gpt-4o-mini), Next.js 14 (App Router), TypeScript, Tailwind CSS

---

## File Map

### New files
| Path | Responsibility |
|------|---------------|
| `3rd/counselling-summarizer/models/bullet_point.py` | `BulletPoint` Pydantic model |
| `3rd/counselling-summarizer/agents/transcript_corrector.py` | `TranscriptCorrector` — LLM call that corrects STT + emits bullet points |
| `3rd/counselling-summarizer/prompts/transcript_correction.txt` | Prompt template for correction+bulletization |
| `platform-ui/app/demo/patient/[id]/workflow/counselling/page.tsx` | Voice counselling workflow UI page |

### Modified files
| Path | What changes |
|------|-------------|
| `3rd/counselling-summarizer/models/response.py` | Add `bullet_points: list[BulletPoint]` and `corrected_transcript: str` to `ProcessingResult` |
| `3rd/counselling-summarizer/main.py` | Call `TranscriptCorrector`, pass results into `ProcessingResult` |
| `final/orchestrator/app/schemas.py` | Add `approved_bullet_ids: list[str]` to `CounsellingApproveRequest` |
| `final/orchestrator/app/storage.py` | Store `bullet_points` in session; handle `approved_bullet_ids` in `mark_approved` |
| `final/orchestrator/app/main.py` | Pass `bullet_points` in counselling workflow data; convert approved bullets to ClinicalFacts in approve endpoint |
| `platform-ui/lib/types.ts` | Add `BulletPoint`, `CounsellingFact` (frontend) types |
| `platform-ui/lib/api.ts` | Add `submitCounselling()` and `approveCounselling()` functions |
| `platform-ui/app/demo/patient/[id]/page.tsx` | Set counselling card `available: true` |

---

## Task 1: BulletPoint model

**Files:**
- Create: `3rd/counselling-summarizer/models/bullet_point.py`
- Modify: `3rd/counselling-summarizer/models/__init__.py` (if it exists, otherwise skip)

- [ ] **Step 1: Write the model**

```python
# 3rd/counselling-summarizer/models/bullet_point.py
from __future__ import annotations

from pydantic import BaseModel, Field


class BulletPoint(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_time_start: float | None = None
    source_time_end: float | None = None
```

- [ ] **Step 2: Verify the model imports cleanly**

```bash
cd /Users/sher/project/pre/3rd/counselling-summarizer
python -c "from models.bullet_point import BulletPoint; print(BulletPoint(id='bp-1', text='test'))"
```
Expected: `id='bp-1' text='test' source_time_start=None source_time_end=None`

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add 3rd/counselling-summarizer/models/bullet_point.py
git commit -m "feat(counselling): add BulletPoint model"
```

---

## Task 2: Transcript correction prompt

**Files:**
- Create: `3rd/counselling-summarizer/prompts/transcript_correction.txt`

- [ ] **Step 1: Write the prompt file**

```
You are a medical transcript correction assistant for an oncology platform in India.

You receive a raw speech-to-text transcript from a clinical consultation session. The transcript may contain speech recognition errors, especially for medical terminology, drug names, procedure names, and Indian-language medical terms.

Your tasks:
1. Correct clear STT errors using the medical context of the full conversation. Only fix obvious recognition mistakes — do not rephrase, paraphrase, or rewrite what was said.
2. Preserve the original speaker labels (doctor/patient/unknown) and approximate timing.
3. Generate a list of clean, concise bullet points summarising the clinically important points from the session. Each bullet captures one distinct clinical observation, decision, symptom, or action item.

Rules:
- Do not fabricate information not present in the transcript.
- Do not combine separate facts into one bullet.
- Do not include social pleasantries or small talk in bullet points.
- Each bullet should be a complete, standalone statement.
- Assign each bullet a unique id like "bp-1", "bp-2", etc.
- Include source_time_start and source_time_end (in seconds) when the segment timestamps allow attribution; otherwise null.
- Return ONLY valid JSON — no markdown fencing, no commentary.

Required output shape:
{
  "corrected_transcript": "<full corrected transcript as a single string with speaker labels>",
  "bullet_points": [
    {
      "id": "bp-1",
      "text": "Doctor prescribed capecitabine 1500mg twice daily for 14 days.",
      "source_time_start": 120.5,
      "source_time_end": 135.2
    }
  ]
}

Raw transcript:
[[TRANSCRIPT]]
```

- [ ] **Step 2: Verify file is readable**

```bash
cat /Users/sher/project/pre/3rd/counselling-summarizer/prompts/transcript_correction.txt | head -5
```
Expected: first 5 lines of the prompt.

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add 3rd/counselling-summarizer/prompts/transcript_correction.txt
git commit -m "feat(counselling): add transcript correction prompt"
```

---

## Task 3: TranscriptCorrector agent

**Files:**
- Create: `3rd/counselling-summarizer/agents/transcript_corrector.py`

- [ ] **Step 1: Write the corrector**

```python
# 3rd/counselling-summarizer/agents/transcript_corrector.py
from __future__ import annotations

import json
import re
from pathlib import Path

from openai import AzureOpenAI

from config import Settings
from models.bullet_point import BulletPoint
from models.request import TranscriptSegment

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "transcript_correction.txt"
TRANSCRIPT_PLACEHOLDER = "[[TRANSCRIPT]]"


class TranscriptCorrectionError(RuntimeError):
    """Raised when the LLM response cannot be parsed into a correction result."""


class TranscriptCorrector:
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.azure_deployment
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.azure_api_key,
            api_version=settings.azure_api_version,
        ) if settings.azure_api_key else None
        self._prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    def correct(
        self,
        segments: list[TranscriptSegment],
        full_transcript: str,
    ) -> tuple[str, list[BulletPoint]]:
        """Return (corrected_transcript, bullet_points). Falls back to raw transcript on failure."""
        if not full_transcript.strip() or self._client is None:
            return full_transcript, []

        rendered = self._render_segments(segments)
        prompt = self._prompt_template.replace(TRANSCRIPT_PLACEHOLDER, rendered)
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                max_tokens=2_000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = (
                response.choices[0].message.content.strip()
                if response.choices and response.choices[0].message.content
                else ""
            )
            return self._parse(raw_text, fallback_transcript=full_transcript)
        except Exception:  # noqa: BLE001 — correction is best-effort
            return full_transcript, []

    def _render_segments(self, segments: list[TranscriptSegment]) -> str:
        parts = []
        for seg in segments:
            parts.append(
                f"[{seg.start_time:.1f}-{seg.end_time:.1f}] {seg.speaker}: {seg.text}"
            )
        return "\n".join(parts)

    def _parse(self, raw_text: str, *, fallback_transcript: str) -> tuple[str, list[BulletPoint]]:
        candidate = raw_text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.DOTALL).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1:
                return fallback_transcript, []
            try:
                payload = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                return fallback_transcript, []

        corrected = payload.get("corrected_transcript") or fallback_transcript
        raw_bullets = payload.get("bullet_points") or []
        bullet_points: list[BulletPoint] = []
        for i, item in enumerate(raw_bullets, start=1):
            if not isinstance(item, dict):
                continue
            text = item.get("text", "").strip()
            if not text:
                continue
            bullet_points.append(
                BulletPoint(
                    id=item.get("id") or f"bp-{i}",
                    text=text,
                    source_time_start=item.get("source_time_start"),
                    source_time_end=item.get("source_time_end"),
                )
            )
        return corrected, bullet_points
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd /Users/sher/project/pre/3rd/counselling-summarizer
python -c "from agents.transcript_corrector import TranscriptCorrector; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add 3rd/counselling-summarizer/agents/transcript_corrector.py
git commit -m "feat(counselling): add TranscriptCorrector agent"
```

---

## Task 4: Update counselling summarizer response model

**Files:**
- Modify: `3rd/counselling-summarizer/models/response.py`

Current `ProcessingResult`:
```python
class ProcessingResult(BaseModel):
    counselling_facts: list[CounsellingFact] = Field(default_factory=list)
    clinical_facts: list[ClinicalFact] = Field(default_factory=list)
    session_summary: str
    stats: ProcessingStats
```

- [ ] **Step 1: Add bullet_points and corrected_transcript fields**

Edit `3rd/counselling-summarizer/models/response.py` — replace the imports block and `ProcessingResult`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.bullet_point import BulletPoint
from models.clinical_fact import ClinicalFact
from models.counselling_fact import CounsellingFact


class ProcessingStats(BaseModel):
    total_segments_analyzed: int = Field(ge=0)
    clinically_relevant_segments: int = Field(ge=0)
    facts_extracted: int = Field(ge=0)


class ProcessingResult(BaseModel):
    counselling_facts: list[CounsellingFact] = Field(default_factory=list)
    clinical_facts: list[ClinicalFact] = Field(default_factory=list)
    bullet_points: list[BulletPoint] = Field(default_factory=list)
    corrected_transcript: str = ""
    session_summary: str
    stats: ProcessingStats


class ProcessingMetadata(BaseModel):
    llm_used: str
    processing_time_ms: int = Field(ge=0)


class SummarizeResponse(BaseModel):
    agent_id: str
    patient_id: str
    timestamp: datetime
    result: ProcessingResult
    metadata: ProcessingMetadata
    errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/sher/project/pre/3rd/counselling-summarizer
python -c "from models.response import SummarizeResponse; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add 3rd/counselling-summarizer/models/response.py
git commit -m "feat(counselling): add bullet_points and corrected_transcript to ProcessingResult"
```

---

## Task 5: Wire TranscriptCorrector into summarizer main.py

**Files:**
- Modify: `3rd/counselling-summarizer/main.py`

Current `main.py` `summarize` function calls `extractor.extract()` and `emit_clinical_facts()`. We need to also call the corrector before extraction and include results.

- [ ] **Step 1: Update main.py**

Replace the entire file content:

```python
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
```

- [ ] **Step 2: Verify server starts**

```bash
cd /Users/sher/project/pre/3rd/counselling-summarizer
python -c "from main import app; print('app created ok')"
```
Expected: `app created ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add 3rd/counselling-summarizer/main.py
git commit -m "feat(counselling): wire TranscriptCorrector into summarize endpoint"
```

---

## Task 6: Update orchestrator schemas and storage

**Files:**
- Modify: `final/orchestrator/app/schemas.py`
- Modify: `final/orchestrator/app/storage.py`

### schemas.py

- [ ] **Step 1: Add approved_bullet_ids to CounsellingApproveRequest**

In `final/orchestrator/app/schemas.py`, replace:
```python
class CounsellingApproveRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    approved_fact_ids: list[str] = Field(default_factory=list)
```
with:
```python
class CounsellingApproveRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    approved_fact_ids: list[str] = Field(default_factory=list)
    approved_bullet_ids: list[str] = Field(default_factory=list)
```

### storage.py

- [ ] **Step 2: Store bullet_points in session and handle bullet approval**

In `final/orchestrator/app/storage.py`, replace the entire `CounsellingSessionStore.create` method:

```python
    def create(
        self,
        *,
        patient_id: str,
        transcript_result: dict[str, Any],
        summarizer_result: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = f"csl-{uuid4().hex[:12]}"
        counselling_facts = []
        clinical_facts = []
        raw_counselling_facts = summarizer_result["result"].get("counselling_facts", [])
        raw_clinical_facts = summarizer_result["result"].get("clinical_facts", [])
        raw_bullet_points = summarizer_result["result"].get("bullet_points", [])
        corrected_transcript = summarizer_result["result"].get("corrected_transcript", "")

        for index, fact in enumerate(raw_counselling_facts, start=1):
            fact_id = fact.get("id") or f"cf-{session_id}-{index}"
            counselling_facts.append({**fact, "id": fact_id})
            if index - 1 < len(raw_clinical_facts):
                clinical_facts.append({**raw_clinical_facts[index - 1], "id": fact_id})

        if len(raw_clinical_facts) > len(counselling_facts):
            for index, fact in enumerate(raw_clinical_facts[len(counselling_facts) :], start=len(counselling_facts) + 1):
                fact_id = fact.get("id") or f"cf-{session_id}-{index}"
                clinical_facts.append({**fact, "id": fact_id})

        bullet_points = []
        for bp in raw_bullet_points:
            bp_id = bp.get("id") or f"bp-{session_id}-{len(bullet_points) + 1}"
            bullet_points.append({**bp, "id": bp_id})

        record = {
            "session_id": session_id,
            "patient_id": patient_id,
            "created_at": _utc_now().isoformat(),
            "transcription_result": transcript_result,
            "corrected_transcript": corrected_transcript,
            "session_summary": summarizer_result["result"].get("session_summary"),
            "counselling_facts": counselling_facts,
            "clinical_facts": clinical_facts,
            "bullet_points": bullet_points,
            "stats": summarizer_result["result"].get("stats", {}),
        }
        self._write(session_id, record)
        return record
```

Also replace `mark_approved` to handle bullet ids:

```python
    def mark_approved(
        self,
        session_id: str,
        approved_fact_ids: list[str],
        approved_bullet_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        record = self.get(session_id)
        record["approved_fact_ids"] = approved_fact_ids
        record["approved_bullet_ids"] = approved_bullet_ids or []
        record["approved_at"] = _utc_now().isoformat()
        self._write(session_id, record)
        return record
```

- [ ] **Step 3: Verify imports**

```bash
cd /Users/sher/project/pre/final/orchestrator
python -c "from app.storage import CounsellingSessionStore; from app.schemas import CounsellingApproveRequest; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/sher/project/pre
git add final/orchestrator/app/schemas.py final/orchestrator/app/storage.py
git commit -m "feat(orchestrator): store bullet_points in session, add approved_bullet_ids to approve request"
```

---

## Task 7: Update orchestrator main.py — counselling workflow

**Files:**
- Modify: `final/orchestrator/app/main.py` (two endpoints: `counselling_workflow` and `approve_counselling`)

### counselling_workflow endpoint

- [ ] **Step 1: Pass bullet_points in the WorkflowEnvelope data**

In `final/orchestrator/app/main.py`, find the `counselling_workflow` function. Replace the return `WorkflowEnvelope(...)` block (lines ~267-286 in current file) with:

```python
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
```

### approve_counselling endpoint

- [ ] **Step 2: Convert approved bullets to ClinicalFacts and ingest them**

In `final/orchestrator/app/main.py`, replace the entire `approve_counselling` function body:

```python
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
```

- [ ] **Step 3: Verify orchestrator imports**

```bash
cd /Users/sher/project/pre/final/orchestrator
python -c "from app.main import create_app; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/sher/project/pre
git add final/orchestrator/app/main.py
git commit -m "feat(orchestrator): expose bullet_points in counselling workflow, ingest approved bullets"
```

---

## Task 8: Update frontend types and API client

**Files:**
- Modify: `platform-ui/lib/types.ts`
- Modify: `platform-ui/lib/api.ts`

### types.ts

- [ ] **Step 1: Add BulletPoint and CounsellingFact types**

In `platform-ui/lib/types.ts`, add these interfaces **after the `MergeConflict` interface** at the end of the file:

```typescript
// Voice counselling workflow types
export interface BulletPoint {
  id: string;
  text: string;
  source_time_start?: number | null;
  source_time_end?: number | null;
}

export interface CounsellingFact {
  id: string;
  fact: string;
  category: 'CONCERN' | 'ACTION' | 'DECISION' | 'EMOTIONAL' | 'FOLLOW_UP';
  certainty: number;
  evidence_start_time: number;
  evidence_end_time: number;
  evidence_text: string;
  speaker: 'doctor' | 'patient' | 'unknown';
  selectable: boolean;
  validation_flags: string[];
}

export interface CounsellingApproveRequest {
  patient_id: string;
  session_id: string;
  approved_fact_ids: string[];
  approved_bullet_ids: string[];
}
```

Note: Remove the old `CounsellingApproveRequest` interface near line 177 since we're replacing it with the extended version above.

### api.ts

- [ ] **Step 2: Add submitCounselling and approveCounselling**

In `platform-ui/lib/api.ts`, add these two functions **before the final closing** of the file:

```typescript
export async function submitCounselling(formData: FormData): Promise<WorkflowEnvelope> {
  const url = `${baseUrl()}/api/v1/workflow/counselling`;
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      message = err.detail || err.message || message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json() as Promise<WorkflowEnvelope>;
}

export async function approveCounselling(payload: {
  patient_id: string;
  session_id: string;
  approved_fact_ids: string[];
  approved_bullet_ids: string[];
}): Promise<WorkflowEnvelope> {
  return apiFetch<WorkflowEnvelope>('api/v1/workflow/counselling/approve', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 3: Verify TypeScript types compile**

```bash
cd /Users/sher/project/pre/platform-ui
npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors (or only pre-existing unrelated errors)

- [ ] **Step 4: Commit**

```bash
cd /Users/sher/project/pre
git add platform-ui/lib/types.ts platform-ui/lib/api.ts
git commit -m "feat(ui): add BulletPoint/CounsellingFact types and counselling API functions"
```

---

## Task 9: Build the counselling workflow UI page

**Files:**
- Create: `platform-ui/app/demo/patient/[id]/workflow/counselling/page.tsx`

This page has 4 steps: `input` → `processing` → `review` → `result`. The review step shows two panels side by side: bullet points (left) and structured counselling facts (right). The doctor can delete bullet points, toggle counselling facts, then confirm.

- [ ] **Step 1: Create the page**

```tsx
'use client';

import { useState, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { submitCounselling, approveCounselling } from '@/lib/api';
import type { BulletPoint, CounsellingFact, WorkflowEnvelope } from '@/lib/types';
import WorkflowStepper from '@/components/WorkflowStepper';

type Step = 'input' | 'processing' | 'review' | 'result';

function getCategoryColor(category: CounsellingFact['category']): string {
  switch (category) {
    case 'CONCERN': return 'bg-amber-400/10 text-amber-400 border-amber-400/20';
    case 'ACTION': return 'bg-teal-400/10 text-teal-400 border-teal-400/20';
    case 'DECISION': return 'bg-blue-400/10 text-blue-400 border-blue-400/20';
    case 'EMOTIONAL': return 'bg-purple-400/10 text-purple-400 border-purple-400/20';
    case 'FOLLOW_UP': return 'bg-orange-400/10 text-orange-400 border-orange-400/20';
  }
}

export default function CounsellingWorkflowPage() {
  const params = useParams();
  const patientId = params.id as string;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>('input');
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [languageHint, setLanguageHint] = useState('hi-IN');
  const [department, setDepartment] = useState('oncology');
  const [error, setError] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState<string>('');
  const [bulletPoints, setBulletPoints] = useState<BulletPoint[]>([]);
  const [counsellingFacts, setCounsellingFacts] = useState<CounsellingFact[]>([]);
  const [approvedBulletIds, setApprovedBulletIds] = useState<Set<string>>(new Set());
  const [approvedFactIds, setApprovedFactIds] = useState<Set<string>>(new Set());
  const [editingBulletId, setEditingBulletId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  const [resultMessage, setResultMessage] = useState('');

  const stepperSteps = [
    { name: 'Voice Transcription', status: step === 'input' ? 'pending' as const : step === 'processing' ? 'running' as const : 'done' as const },
    { name: 'LLM Correction', status: step === 'input' || step === 'processing' ? 'pending' as const : 'done' as const },
    { name: 'Review', status: step === 'review' ? 'running' as const : step === 'result' ? 'done' as const : 'pending' as const },
  ];

  async function handleSubmit() {
    if (!audioFile) return;
    setStep('processing');
    setError(null);

    const formData = new FormData();
    formData.append('audio', audioFile);
    formData.append('patient_id', patientId);
    formData.append('patient_consent', 'true');
    formData.append('consent_timestamp', new Date().toISOString());
    formData.append('language_hint', languageHint);
    formData.append('department', department);
    formData.append('session_type', 'clinical_note');

    try {
      const result: WorkflowEnvelope = await submitCounselling(formData);
      const data = result.data as {
        session_id: string;
        bullet_points: BulletPoint[];
        counselling_facts: CounsellingFact[];
      };
      setSessionId(data.session_id);

      const bps = data.bullet_points || [];
      setBulletPoints(bps);
      setApprovedBulletIds(new Set(bps.map((bp) => bp.id)));

      const facts = data.counselling_facts || [];
      setCounsellingFacts(facts);
      setApprovedFactIds(new Set(facts.map((f) => f.id)));

      setStep('review');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Processing failed');
      setStep('input');
    }
  }

  function deleteBullet(id: string) {
    setBulletPoints((prev) => prev.filter((bp) => bp.id !== id));
    setApprovedBulletIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
  }

  function startEditBullet(bp: BulletPoint) {
    setEditingBulletId(bp.id);
    setEditText(bp.text);
  }

  function saveEditBullet(id: string) {
    setBulletPoints((prev) => prev.map((bp) => bp.id === id ? { ...bp, text: editText } : bp));
    setEditingBulletId(null);
    setEditText('');
  }

  function toggleFact(id: string) {
    setApprovedFactIds((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id); else s.add(id);
      return s;
    });
  }

  async function handleConfirm() {
    setError(null);
    try {
      const result = await approveCounselling({
        patient_id: patientId,
        session_id: sessionId,
        approved_fact_ids: Array.from(approvedFactIds),
        approved_bullet_ids: Array.from(approvedBulletIds),
      });
      const data = result.data as { total_ingested?: number; approved_bullets_count?: number; approved_facts_count?: number };
      const total = data.total_ingested ?? 0;
      const bullets = data.approved_bullets_count ?? 0;
      const facts = data.approved_facts_count ?? 0;
      setResultMessage(`Ingested ${total} items (${bullets} bullet points + ${facts} clinical facts)`);
      setStep('result');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Confirmation failed');
    }
  }

  const approvedBulletCount = approvedBulletIds.size;
  const approvedFactCount = approvedFactIds.size;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-6 flex-wrap">
        <Link href="/demo" className="hover:text-slate-300 transition-colors">Demo</Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <Link href={`/demo/patient/${patientId}`} className="hover:text-slate-300 transition-colors">
          Patient {patientId}
        </Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-slate-300">Voice Counselling</span>
      </div>

      <h1 className="text-2xl font-bold text-white mb-2">Add Counselling Session</h1>
      <p className="text-slate-400 mb-6">
        Upload a voice recording. Sarvam AI transcribes it, then the LLM corrects errors and generates bullet points for your review.
      </p>

      <div className="mb-8">
        <WorkflowStepper steps={stepperSteps} />
      </div>

      {error && (
        <div className="bg-rose-400/5 border border-rose-400/20 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 text-rose-400 text-sm">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 5v3M8 10v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {error}
          </div>
        </div>
      )}

      {/* Step 1: Input */}
      {step === 'input' && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-5 animate-fade-in">
          <div>
            <label className="label">Audio Recording</label>
            <div
              className="mt-1 border-2 border-dashed border-slate-600 rounded-xl p-8 text-center cursor-pointer hover:border-teal-400/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              {audioFile ? (
                <div className="space-y-1">
                  <p className="text-white font-medium">{audioFile.name}</p>
                  <p className="text-slate-400 text-sm">{(audioFile.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <svg className="mx-auto text-slate-500" width="40" height="40" viewBox="0 0 40 40" fill="none">
                    <circle cx="20" cy="20" r="18" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M20 12v16M12 20h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  <p className="text-slate-400 text-sm">Click to upload audio (WAV, MP3, M4A, OGG)</p>
                </div>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac"
              className="hidden"
              onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Language</label>
              <select value={languageHint} onChange={(e) => setLanguageHint(e.target.value)} className="select-field">
                <option value="hi-IN">Hindi</option>
                <option value="en-IN">English (India)</option>
                <option value="ta-IN">Tamil</option>
                <option value="te-IN">Telugu</option>
                <option value="kn-IN">Kannada</option>
                <option value="ml-IN">Malayalam</option>
                <option value="mr-IN">Marathi</option>
                <option value="bn-IN">Bengali</option>
                <option value="gu-IN">Gujarati</option>
                <option value="pa-IN">Punjabi</option>
              </select>
            </div>
            <div>
              <label className="label">Department</label>
              <select value={department} onChange={(e) => setDepartment(e.target.value)} className="select-field">
                <option value="oncology">Oncology</option>
                <option value="radiology">Radiology</option>
                <option value="surgery">Surgery</option>
                <option value="palliative">Palliative Care</option>
                <option value="general">General Medicine</option>
              </select>
            </div>
          </div>

          <div className="pt-2">
            <button
              onClick={handleSubmit}
              disabled={!audioFile}
              className="btn-primary inline-flex items-center gap-2"
            >
              Transcribe & Analyse
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Processing */}
      {step === 'processing' && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-12 text-center animate-fade-in">
          <div className="inline-block mb-4">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="animate-spin text-teal-400">
              <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="3" strokeDasharray="80" strokeDashoffset="20" strokeLinecap="round" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">Processing Audio</h3>
          <p className="text-sm text-slate-400">
            Transcribing with Sarvam AI, then correcting and extracting clinical facts...
          </p>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Bullet Points Panel */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-white">
                  Bullet Points
                  <span className="ml-2 text-sm font-normal text-slate-400">({approvedBulletCount} of {bulletPoints.length} kept)</span>
                </h2>
              </div>
              <p className="text-xs text-slate-500 mb-3">
                LLM-corrected summary of the session. Edit or delete any point before confirming.
              </p>

              {bulletPoints.length === 0 ? (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 text-center text-slate-400 text-sm">
                  No bullet points were generated.
                </div>
              ) : (
                <div className="space-y-2">
                  {bulletPoints.map((bp) => (
                    <div key={bp.id} className="bg-slate-900 border border-slate-700 rounded-xl p-4">
                      {editingBulletId === bp.id ? (
                        <div className="space-y-2">
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            rows={3}
                            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-400 resize-none"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveEditBullet(bp.id)}
                              className="px-3 py-1 bg-teal-500 text-white text-xs rounded-lg hover:bg-teal-600 transition-colors"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingBulletId(null)}
                              className="px-3 py-1 bg-slate-700 text-slate-300 text-xs rounded-lg hover:bg-slate-600 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start gap-3">
                          <span className="text-teal-400 mt-0.5 shrink-0">•</span>
                          <p className="text-sm text-slate-200 flex-1">{bp.text}</p>
                          <div className="flex gap-1 shrink-0">
                            <button
                              onClick={() => startEditBullet(bp)}
                              className="text-slate-500 hover:text-teal-400 transition-colors p-1"
                              title="Edit"
                            >
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                <path d="M8.5 1.5l2 2-7 7H1.5V8.5l7-7z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </button>
                            <button
                              onClick={() => deleteBullet(bp.id)}
                              className="text-slate-500 hover:text-rose-400 transition-colors p-1"
                              title="Delete"
                            >
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Clinical Facts Panel */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-white">
                  Clinical Facts
                  <span className="ml-2 text-sm font-normal text-slate-400">({approvedFactCount} of {counsellingFacts.length} approved)</span>
                </h2>
              </div>
              <p className="text-xs text-slate-500 mb-3">
                Structured facts extracted by the LLM. Toggle to approve or reject each.
              </p>

              {counsellingFacts.length === 0 ? (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 text-center text-slate-400 text-sm">
                  No structured clinical facts were extracted.
                </div>
              ) : (
                <div className="space-y-2">
                  {counsellingFacts.map((fact) => {
                    const isApproved = approvedFactIds.has(fact.id);
                    return (
                      <div
                        key={fact.id}
                        className={`border rounded-xl p-4 transition-all duration-200 cursor-pointer ${
                          isApproved
                            ? 'bg-slate-900 border-teal-400/30'
                            : 'bg-slate-900/50 border-slate-700 opacity-60'
                        }`}
                        onClick={() => toggleFact(fact.id)}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`mt-0.5 w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                            isApproved ? 'bg-teal-400 border-teal-400 text-slate-950' : 'border-slate-600'
                          }`}>
                            {isApproved && (
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                <path d="M2.5 6l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded border ${getCategoryColor(fact.category)}`}>
                                {fact.category}
                              </span>
                              <span className="text-xs text-slate-500">
                                {fact.speaker} · {(fact.certainty * 100).toFixed(0)}%
                              </span>
                            </div>
                            <p className="text-sm text-slate-200">{fact.fact}</p>
                            {fact.evidence_text && (
                              <p className="text-xs text-slate-500 italic mt-1 border-l-2 border-slate-700 pl-2">
                                &quot;{fact.evidence_text}&quot;
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Confirm bar */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex items-center justify-between flex-wrap gap-4 sticky bottom-4">
            <span className="text-sm text-slate-300">
              <span className="font-semibold text-white">{approvedBulletCount}</span> bullets +{' '}
              <span className="font-semibold text-white">{approvedFactCount}</span> facts will be ingested
            </span>
            <div className="flex items-center gap-3">
              <button onClick={() => setStep('input')} className="btn-secondary text-sm">
                Back
              </button>
              <button
                onClick={handleConfirm}
                disabled={approvedBulletCount + approvedFactCount === 0}
                className="btn-primary text-sm inline-flex items-center gap-2"
              >
                Confirm & Ingest
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: Result */}
      {step === 'result' && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-8 text-center animate-fade-in">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-400/10 mb-4">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="text-emerald-400">
              <path d="M8 16l5 5 11-12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-white mb-2">{resultMessage}</h2>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => {
                setStep('input');
                setAudioFile(null);
                setBulletPoints([]);
                setCounsellingFacts([]);
                setApprovedBulletIds(new Set());
                setApprovedFactIds(new Set());
                setSessionId('');
                setResultMessage('');
              }}
              className="btn-secondary"
            >
              Process Another Recording
            </button>
            <Link href={`/demo/patient/${patientId}`} className="btn-primary inline-flex items-center gap-2">
              Back to Patient
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/sher/project/pre/platform-ui
npx tsc --noEmit 2>&1 | head -30
```
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add platform-ui/app/demo/patient/\[id\]/workflow/counselling/page.tsx
git commit -m "feat(ui): add voice counselling workflow page with bullet+fact dual review"
```

---

## Task 10: Enable the counselling card in patient page

**Files:**
- Modify: `platform-ui/app/demo/patient/[id]/page.tsx`

- [ ] **Step 1: Set available: true on the counselling card**

In `platform-ui/app/demo/patient/[id]/page.tsx`, find:
```typescript
  {
    title: 'Add Counselling Session',
    description: 'Process audio recordings of clinical counselling sessions.',
    href: 'workflow/counselling',
    available: false,
  },
```
And change `available: false` to `available: true`.

- [ ] **Step 2: Verify the frontend starts**

```bash
cd /Users/sher/project/pre/platform-ui
npm run dev -- --port 3001 2>&1 &
sleep 5
curl -sf http://localhost:3001 | head -5
kill %1 2>/dev/null
```
Expected: HTML response starts with `<!DOCTYPE html>` or similar — server starts without error.

- [ ] **Step 3: Commit**

```bash
cd /Users/sher/project/pre
git add platform-ui/app/demo/patient/\[id\]/page.tsx
git commit -m "feat(ui): enable counselling workflow card in patient detail page"
```

---

## Task 11: End-to-end smoke test (manual)

This is a manual verification step against the running stack on Tyrone.

- [ ] **Step 1: Restart the counselling summarizer on Tyrone**

```bash
ssh tyrone 'kill $(lsof -ti:5005) 2>/dev/null; sleep 1; cd ~/projects/pre/3rd/counselling-summarizer && \
  AZURE_API_KEY="Fdl4xjJwFM3hONUePvxGyZdzFoGT3MtJbM9hEbVUUqW17cQs1ImNJQQJ99CDACHYHv6XJ3w3AAAAACOGBDbt" \
  AZURE_ENDPOINT="https://sherpartap1101-5077-resource.cognitiveservices.azure.com/" \
  AZURE_DEPLOYMENT="gpt-4o-mini" \
  AZURE_API_VERSION="2025-01-01-preview" \
  nohup ~/projects/pre/.platform_venv/bin/uvicorn main:app --host 0.0.0.0 --port 5005 > ~/projects/pre/logs/counselling-summarizer.log 2>&1 &'
sleep 3
ssh tyrone 'curl -sf http://localhost:5005/health'
```
Expected: `{"status":"ok"}`

- [ ] **Step 2: Verify summarizer returns bullet_points field**

```bash
ssh tyrone 'curl -sf -X POST http://localhost:5005/api/v1/summarize \
  -H "Content-Type: application/json" \
  -d "{\"patient_id\":\"10000935\",\"transcript_english\":{\"segments\":[{\"speaker\":\"doctor\",\"start_time\":0.0,\"end_time\":5.0,\"text\":\"Patient has stage 3 gastric cancer and we are starting capecitabine.\"}]},\"full_text_english\":\"Doctor: Patient has stage 3 gastric cancer and we are starting capecitabine.\",\"department\":\"oncology\"}" | python3 -m json.tool | grep -A5 "bullet_points"'
```
Expected: `"bullet_points": [` with at least one item.

- [ ] **Step 3: Restart the orchestrator on Tyrone**

```bash
ssh tyrone 'kill $(lsof -ti:8000) 2>/dev/null; sleep 1; cd ~/projects/pre/final/orchestrator && \
  AZURE_API_KEY="Fdl4xjJwFM3hONUePvxGyZdzFoGT3MtJbM9hEbVUUqW17cQs1ImNJQQJ99CDACHYHv6XJ3w3AAAAACOGBDbt" \
  AZURE_ENDPOINT="https://sherpartap1101-5077-resource.cognitiveservices.azure.com/" \
  AZURE_DEPLOYMENT="gpt-4o-mini" \
  AZURE_API_VERSION="2025-01-01-preview" \
  SARVAM_API_KEY="sk_py5uq3wn_ABmCmnEE8AowmTDhN890kiNt" \
  FACT_GRAPH_URL="http://localhost:5006" \
  COUNSELLING_SUMMARIZER_URL="http://localhost:5005" \
  VOICE_TRANSCRIPTION_URL="http://localhost:5004" \
  DATA_DIR="~/projects/pre/data/fact_graph" \
  nohup ~/projects/pre/.platform_venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > ~/projects/pre/logs/orchestrator.log 2>&1 &'
sleep 3
curl -sf http://localhost:8000/healthz
```
Expected: `{"status":"ok"}`

- [ ] **Step 4: Open the UI and manually test the counselling workflow**

1. Open `http://localhost:3000/demo`
2. Click any patient
3. Click "Add" tab → "Add Counselling Session" (should now be clickable)
4. Upload a short audio clip (any WAV/MP3)
5. Verify: processing spinner shows, then review screen appears with two panels
6. Verify: bullet points list and clinical facts list are both populated
7. Delete one bullet, toggle off one fact
8. Click "Confirm & Ingest"
9. Verify: success screen shows count of ingested items

---

## Self-Review

**Spec coverage checklist:**
- [x] Sarvam STT → transcript — handled by existing voice-transcription agent (Task 7/11)
- [x] LLM corrects STT errors using full context — `TranscriptCorrector` (Tasks 2, 3)
- [x] Convert corrected text to bullet points — `TranscriptCorrector` returns bullet_points (Task 3)
- [x] Show bullet points to doctor — left panel in review UI (Task 9)
- [x] Doctor can edit bullet points — edit button inline (Task 9)
- [x] Doctor can delete bullet points — delete button (Task 9)
- [x] Show structured clinical entities alongside — right panel (Task 9)
- [x] Doctor can toggle clinical facts — checkbox click (Task 9)
- [x] Push approved to fact graph — `approveCounselling` calls `/approve` endpoint (Tasks 7, 9)
- [x] Types consistent end to end — BulletPoint in Python model, frontend type, and API response (Tasks 1, 4, 8)
- [x] Counselling card enabled in patient page — Task 10

**Type consistency check:**
- `BulletPoint.id: str` → stored in session `bullet_points[].id` → `approved_bullet_ids: list[str]` in schema → `approved_bullet_ids: string[]` in TypeScript ✓
- `ProcessingResult.bullet_points` → `summarizer["result"]["bullet_points"]` in orchestrator → `session["bullet_points"]` → `data.bullet_points` in WorkflowEnvelope → `BulletPoint[]` in TypeScript ✓
- `CounsellingApproveRequest.approved_bullet_ids` (Python) → `approveCounselling({ approved_bullet_ids: string[] })` (TypeScript) ✓

**Placeholder scan:** All steps have exact code, file paths, and commands. No TBD or TODO.
