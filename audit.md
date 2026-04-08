# Agent Audit Report — Clinical Intelligence Platform
> Date: April 4, 2026

## Executive Summary

The Clinical Intelligence Platform comprises 10 agents spanning OCR, clinical extraction, voice transcription, counselling summarization, fact graph persistence, department-level merging, summary generation, quality assurance, and patient-facing translation. After a thorough code-level audit of every agent's prompt files, LLM integration code, output parsing, guardrails, and error handling, the platform presents as a **competently engineered system with several strong areas and a handful of meaningful gaps**.

The strongest agents are the SOAP Extractor (Agent 02), Radiology Extractor (Agent 03), Counselling Summarizer (Agent 05), QA Agent (Agent 09), and Department Merger (Agent 07). These exhibit few-shot prompting, structured output enforcement via Pydantic, hallucination guardrails (evidence-grounding checks, negation handling, confidence scoring), and multi-layered fallback strategies. The weakest areas are in output schema enforcement for agents that rely on regex-based JSON extraction rather than structured output modes (Agents 01, 02, 07's conflict analyzer), and in cross-agent error propagation — several agents silently swallow upstream failures or return empty results without surfacing warnings.

Key platform-wide concerns include: (1) no retry/circuit-breaker logic for LLM calls anywhere in the codebase, (2) temperature=0 is used consistently but `seed` parameters are absent, limiting reproducibility, and (3) the human-in-the-loop integration is well-designed at the counselling and QA stages but absent at the OCR-to-SOAP boundary where it would matter most for patient safety.

---

## Agent-by-Agent Audit

### Agent 01: OCR Agent (Port 5001)

**Files reviewed:** `ocr-agent/app/ocr.py` (130 lines), `ocr-agent/app/main.py` (48 lines)

#### Previous State
The OCR agent is a straightforward vision-LLM wrapper that sends a base64-encoded medical image to Azure GPT-4o and returns raw transcribed text. It includes confidence scoring based on `[ILLEGIBLE]` token counting and a basic layout-region heuristic.

#### Issues Identified
- **No Pydantic output model**: The response dict is built manually at line 119-129 of `ocr.py`. There is no schema validation on the output. If the LLM returns unexpected content, the only defense is the regex strip at lines 71-72.
- **No retry on LLM failure**: `extract_text_from_image()` (line 49) makes a single call with no retry, timeout configuration, or circuit breaker. A transient Azure outage returns a raw 500 to the caller.
- **Confidence heuristic is simplistic**: Each `[ILLEGIBLE]` token deducts 0.05 from confidence (line 79). This means 20 illegible words still yields 0.0 confidence, but a document with zero illegible markers but wildly wrong transcription gets 1.0 confidence. There is no self-consistency check or secondary verification pass.
- **Layout region split is naive**: Lines 90-104 split by "first 3 lines = header, rest = body." This fails for prescriptions, lab reports, and multi-page documents.
- **No input size validation**: `main.py` checks for empty files (line 37) and MIME type (line 29), but does not enforce a maximum file size. A 50MB image will be base64-encoded and sent to the LLM.
- **Indic script detection is limited**: `_detect_indic_script` (line 84) only checks Devanagari range `\u0900-\u097F`. Tamil, Telugu, Kannada, Malayalam, Bengali, and Gujarati scripts are not detected despite the platform supporting Indian hospitals.

#### Research-Backed Improvements
- Use a two-pass OCR strategy: a fast deterministic OCR engine (Tesseract/PaddleOCR) for a baseline, then GPT-4o for handwriting correction. Compare the two for self-consistency scoring.
- Enforce output schema via Pydantic `response_model` or structured output mode.
- Add exponential backoff retry (3 attempts) for LLM calls.
- Extend Indic detection to all Unicode Indic blocks (`\u0900-\u0D7F`).

#### Changes Made / Recommended
- **Recommended**: Add `max_file_size` validation in `main.py` (e.g., 10MB).
- **Recommended**: Replace manual dict construction with a Pydantic `OCRResult` model.
- **Recommended**: Add retry wrapper with exponential backoff around `client.chat.completions.create()`.
- **Recommended**: Add Unicode ranges for all Indian scripts in `_detect_indic_script`.

#### Verdict: ADEQUATE

---

### Agent 02: SOAP Extractor (Port 5002)

**Files reviewed:** `soap-extractor/app/soap.py` (460 lines), `soap-extractor/app/main.py` (46 lines)

#### Previous State
The SOAP extractor is a two-stage pipeline: (1) LLM-based SOAP extraction from OCR text, (2) deterministic conversion of SOAP data to ClinicalFact dicts. The prompt is the best-engineered in the entire platform — 271 lines with 3 few-shot examples covering full extraction, OCR noise handling, and low-confidence illegibility scenarios.

#### Issues Identified
- **JSON parsing relies on regex**: `parse_json_from_response()` (lines 287-297) first tries markdown code block extraction, then falls back to matching the outermost `{...}`. This is fragile: nested JSON with trailing commentary can cause `json.loads` to fail on the wrong substring. The platform should use the OpenAI structured output / JSON mode feature.
- **No Pydantic validation of LLM output**: The SOAP JSON is parsed into a raw dict and traversed with `.get()` chains. If the LLM omits `soap_note` or changes the key to `soapNote`, the code silently returns empty/default values rather than flagging the structural violation.
- **Medications are always certainty 0.99**: Line 373 hardcodes medication certainty to 0.99. This ignores the `handwriting_confidence` field that the LLM itself returns, which could be as low as 0.40 (per Example 3 in the prompt).
- **No retry logic**: Same as Agent 01 — a single LLM call with no retry or timeout override.
- **Empty text check is at API layer only**: `main.py` line 28 checks for empty text, but `call_soap_llm()` does not validate input, so internal callers can pass empty strings.

#### Research-Backed Improvements
- Use OpenAI's `response_format={"type": "json_object"}` or structured output to guarantee valid JSON.
- Add Pydantic models for the SOAP schema and validate the LLM response against them.
- Propagate `handwriting_confidence` into medication fact certainty instead of hardcoding 0.99.

#### Changes Made / Recommended
- **Recommended**: Switch to JSON mode or structured output in the OpenAI call.
- **Recommended**: Create `SOAPNote` Pydantic model and validate LLM output with `model_validate()`.
- **Recommended**: Use `med["handwriting_confidence"]` as the medication certainty score (line 373).
- **Recommended**: Add input validation in `call_soap_llm()`.

#### Verdict: GOOD

The prompt engineering is excellent — the few-shot examples cover edge cases (OCR noise, illegibility, negation). The two-stage pipeline (LLM extraction + deterministic fact emission) is a sound architecture. The main weakness is the lack of schema enforcement on LLM output.

---

### Agent 03: Radiology Extractor (Port 5003)

**Files reviewed:** `radiology-extractor/app/extractor.py` (317 lines), `radiology-extractor/app/cfs_adapter.py` (207 lines), `radiology-extractor/tmc_core/extraction/prompts.py` (536 lines), `radiology-extractor/tmc_core/extraction/rule_extractor.py` (first 50 lines)

#### Previous State
This is the most sophisticated agent in the platform. It implements a hybrid extraction pipeline: Tier 0 rule-based extraction (spaCy NLP + regex patterns for measurements, negation via NegEx), then LLM extraction for complex findings. The prompt is 235 lines for single reports and 80 lines for paired temporal reports, with extensive few-shot examples covering Format A (structured CT/MRI), Format B (impression-only X-ray), and Format C (hybrid per-region X-ray).

#### Issues Identified
- **Silent failure on extraction errors**: `extractor.py` line 83 catches all exceptions from `self.extractor.extract()` and returns an empty list. This means an LLM timeout or malformed response silently produces "no findings" rather than surfacing an error. For oncology patients, a silently empty extraction could delay detection of disease progression.
- **Entity grounding failures are logged but continue**: Lines 127-129 catch grounding exceptions and set `grounding_method = "error"` with `grounding_confidence = 0.0`. This is reasonable but should be surfaced as a warning in the response, not just logged.
- **The CFS adapter's certainty mapping has a gap**: `cfs_adapter.py` line 110 has a `_LABEL_MAP` that maps qualitative labels to scores, but "definitive" maps to 0.96 while "confirmed" also maps to 0.96. The prompt uses "confirmed" with range 0.95-1.00, so the mapping truncates confirmed findings to 0.96 rather than preserving the LLM's original numeric score.
- **Measurement extraction has 3 fallback paths**: `_extract_measurement()` in `cfs_adapter.py` tries `measurement_normalized`, then `measurement`, then regex from `evidence_text`. This is robust but the regex fallback (line 52) only handles `mm` and `cm` — it misses `in` (inches) despite `_to_mm()` supporting inch conversion.
- **No deduplication across extraction tiers**: The rule extractor and LLM extractor may both extract the same finding. `_dedupe_findings()` handles this but uses a tuple key that does not normalize entity names (e.g., "pleural effusion" vs "Pleural Effusion" would not be deduped because `entity.strip().lower()` is applied, but `negation_language` is not normalized).

#### Research-Backed Improvements
- Surface extraction failures as structured warnings in the API response rather than silent empty returns.
- Add the `in` unit to the measurement regex in `cfs_adapter.py`.
- Consider adding a confidence floor: if extraction confidence is below a threshold, flag for radiologist review.

#### Changes Made / Recommended
- **Recommended**: Replace silent `return []` on extraction failure with a structured error response including the exception type.
- **Recommended**: Add `in` to the regex at `cfs_adapter.py` line 52.
- **Recommended**: Prefer the LLM's numeric `confidence_score` over the label-to-score mapping when both are available.

#### Verdict: GOOD

The prompt engineering is the best in the platform. The multi-format detection (Format A/B/C), the extensive negation handling rules, the explicit "do not promote history into findings" instructions, and the entity naming guidelines are all excellent. The hybrid rule+LLM pipeline is architecturally sound. The main gap is silent failure handling.

---

### Agent 04: Voice Transcription (Port 5004)

**Files reviewed:** `2nd/agents/transcriber.py` (134 lines), `2nd/agents/diarizer.py` (123 lines), `2nd/agents/language_detector.py` (69 lines), `2nd/agents/consent_validator.py` (11 lines), `2nd/agents/translator.py` (33 lines), `2nd/main.py` (283 lines)

#### Previous State
The voice transcription agent uses the Sarvam AI speech-to-text API (not a local LLM) with Google Cloud Speech-to-Text as a fallback. It supports 20+ Indian languages, speaker diarization, code-mixed Hindi-English transcription, and batch processing for long audio files. The architecture is clean: separate agent modules for transcription, diarization, language detection, consent validation, and translation.

#### Issues Identified
- **No LLM prompt to audit**: This agent does not use an LLM — it is a pure API wrapper around Sarvam and Google STT services. Prompt quality is not applicable.
- **Consent validation is minimal**: `consent_validator.py` (11 lines) checks only for the boolean flag and timestamp. It does not verify consent recency (a consent from 2 years ago would pass) or consent scope.
- **Audio quality assessment is referenced but not readable**: `main.py` line 66 calls `assess_audio_quality()` from `utils`, which was not in the audit scope. The quality score is passed through but it is unclear if low-quality audio triggers any guardrail.
- **Batch API error handling is broad**: `transcriber.py` line 120 catches `Exception` (all exceptions) for the batch path. While it re-raises `ProviderError`, other exceptions (e.g., `KeyError`, `FileNotFoundError`) get wrapped into a generic `ProviderError`, losing diagnostic information.
- **No audio duration estimation before upload**: The service checks `max_audio_duration_seconds` after upload (`main.py` line 61), meaning a 2-hour audio file is fully uploaded and stored before being rejected.
- **Google fallback does not propagate language detection**: When falling back to Google STT (`main.py` line 88-93), the detected language defaults to the hint or "en-IN", not the actual detected language.

#### Research-Backed Improvements
- Add consent recency check (e.g., consent must be within 24 hours of transcription request).
- Validate audio duration from file headers before full processing.
- Use streaming transcription for real-time consultations.

#### Changes Made / Recommended
- **Recommended**: Add consent recency validation (configurable max age).
- **Recommended**: Extract duration from audio headers before upload to reject oversized files early.
- **Recommended**: Use narrower exception handling in batch transcription path.

#### Verdict: GOOD

The agent is well-structured with proper separation of concerns, multi-provider fallback, and Pydantic models for requests/responses. The consent validation and audio quality integration show awareness of clinical requirements. The main gaps are in consent recency and early audio validation.

---

### Agent 05: Counselling Summarizer (Port 5005)

**Files reviewed:** `3rd/counselling-summarizer/agents/fact_extractor.py` (91 lines), `3rd/counselling-summarizer/prompts/counselling_extraction.txt` (48 lines), `3rd/counselling-summarizer/agents/guardrails.py` (66 lines), `3rd/counselling-summarizer/agents/segment_analyzer.py` (111 lines), `3rd/counselling-summarizer/agents/cfs_emitter.py` (79 lines)

#### Previous State
The counselling summarizer is a 4-stage pipeline: (1) segment analysis to filter small talk and identify clinically relevant segments, (2) LLM-based fact extraction with a dedicated prompt, (3) guardrail validation with evidence grounding and diagnosis filtering, (4) ClinicalFact emission. This is one of the most carefully designed agents in the platform.

#### Issues Identified
- **Prompt is clean but lacks few-shot examples**: The prompt at `counselling_extraction.txt` (48 lines) gives a single JSON example and clear rules, but no few-shot examples showing edge cases (e.g., how to handle a patient who says "I heard chemo causes cancer" — this is a concern, not a diagnosis). The SOAP extractor's 3-example approach should be replicated.
- **Pydantic validation is properly used**: `fact_extractor.py` line 58 uses `CounsellingFact.model_validate(item)`, making this one of the few agents that validates LLM output against a Pydantic model. This is excellent.
- **Evidence grounding check is rigorous**: `guardrails.py` line 27 checks if the evidence text actually exists in the transcript. If not found, certainty is halved and a `evidence_not_found_in_transcript` flag is set. This is a strong anti-hallucination measure.
- **Diagnosis filter could be broader**: `guardrails.py` lines 7-9 only checks for diagnosis-related terms via two regex patterns. Medical conditions mentioned in passing (e.g., "my blood sugar has been high") could slip through if the word "diagnosed" is not present.
- **Segment analyzer's relevance threshold is low**: `segment_analyzer.py` line 96 considers any segment with 6+ words as relevant if no clinical keywords are found. This could let irrelevant small talk through for longer utterances.
- **No temperature or seed parameter**: `fact_extractor.py` line 47 uses `temperature=0` but no `seed`, same pattern as all other agents.

#### Research-Backed Improvements
- Add 2-3 few-shot examples to the prompt covering: (a) patient concern that mentions a condition but is not a diagnosis, (b) implicit emotional state, (c) ambiguous follow-up item.
- Consider adding a medical entity recognition step before the diagnosis filter to catch conditions mentioned without the word "diagnosis."

#### Changes Made / Recommended
- **Recommended**: Add few-shot examples to `counselling_extraction.txt`.
- **Recommended**: Expand diagnosis filter patterns to include common condition names.
- **Recommended**: Increase the minimum word count for non-keyword segments from 6 to 10.

#### Verdict: GOOD

This is one of the best-designed agents in the platform. The 4-stage pipeline (segment filter -> LLM extraction -> guardrail validation -> fact emission) is textbook. The evidence-grounding check in `guardrails.py` is the strongest anti-hallucination measure in the entire platform. The `selectable: true` default enables human-in-the-loop review.

---

### Agent 06: Fact Graph Engine (Port 5006)

**Files reviewed:** `fact-graph-service/app/store.py` (361 lines), `fact-graph-service/fact_graph/fact_store.py` (first 100 lines)

#### Previous State
The Fact Graph Engine is a persistence and query layer, not an LLM-based agent. It uses an append-only fact graph with SQLite as the primary backend and JSON export for compatibility. It receives ClinicalFact dicts from upstream agents and stores them in a patient-scoped entity graph with temporal tracking.

#### Issues Identified
- **No LLM prompt to audit**: This is a pure data storage agent. Prompt quality, output schema enforcement, and hallucination checks are not applicable.
- **Conflict detection is rule-based and sound**: `store.py` lines 317-360 implement conflict detection by comparing incoming facts against existing entity status. The logic correctly catches resolved-but-reasserted, absent-but-present, and active-but-negated conflicts.
- **Body region inference is keyword-based**: `fact_store.py` lines 24-88 use a static dictionary mapping keywords to body regions. This is deterministic and fast but misses compound terms (e.g., "hepatopulmonary" would match "hepatic" -> abdomen_pelvis but not "pulmonary" -> chest).
- **No input validation on ingested facts**: `store.py` line 97 `ingest()` does not validate that incoming `ClinicalFact` objects have required fields. If `entity_name` is None, the entity would be stored with a None key.
- **File-based storage is a scalability concern**: Each patient gets a JSON file and SQLite database. For a hospital with 100,000+ patients, directory listing performance will degrade. The `list_patients()` method (line 275) iterates all subdirectories.

#### Research-Backed Improvements
- Add input validation on required ClinicalFact fields before ingestion.
- Consider a shared database (PostgreSQL) for production deployments.
- Add compound body region inference for multi-system findings.

#### Changes Made / Recommended
- **Recommended**: Add Pydantic validation on `ClinicalFact` before ingestion.
- **Recommended**: Add an index or database for patient listing rather than filesystem iteration.

#### Verdict: ADEQUATE

The graph model is well-designed with entity-level temporal tracking, certainty trajectories, and conflict detection. The main concerns are operational (file-based storage scalability) rather than clinical safety.

---

### Agent 07: Department Merger (Port 5007)

**Files reviewed:** `4th/department-merger/agents/parallel_extractor.py` (183 lines), `4th/department-merger/agents/conflict_analyzer.py` (162 lines), `4th/department-merger/agents/entity_aligner.py` (167 lines), `4th/department-merger/agents/conflict_detector.py` (154 lines), `4th/department-merger/prompts/conflict_analysis.txt` (26 lines)

#### Previous State
The department merger is a 4-stage pipeline: (1) parallel extraction from all department notes via the SOAP extractor, (2) entity alignment across departments using RadLex IDs and text normalization, (3) conflict detection between departments, (4) LLM-powered conflict analysis with deterministic fallback. The architecture is sound and the agent correctly delegates extraction to Agent 02 rather than duplicating that logic.

#### Issues Identified
- **Conflict analysis prompt is minimal**: `conflict_analysis.txt` (26 lines) provides no few-shot examples. For a task as nuanced as cross-department conflict resolution, the prompt should include examples of: (a) medication dosage conflict, (b) staging disagreement, (c) temporal confusion.
- **JSON extraction from LLM is fragile**: `conflict_analyzer.py` lines 118-129 use `content.find("{")` / `content.rfind("}")` to extract JSON. This is the weakest parsing strategy in the platform — it cannot handle JSON with nested braces correctly if there is trailing text.
- **Fallback analysis is always used on any exception**: `conflict_analyzer.py` line 69 catches bare `Exception` and falls back to the heuristic. This means authentication errors, rate limits, and schema violations all silently degrade to the heuristic path. The LLM could be permanently failing and no one would know.
- **Entity alignment is RadLex-first, which is good**: `entity_aligner.py` line 88-98 `should_merge_radlex()` correctly prefers RadLex ID matching over text matching, falling back to normalized text + category comparison. This is robust.
- **Conflict severity assessment is well-designed**: `conflict_detector.py` lines 123-136 correctly marks staging and medication conflicts as critical, status conflicts as moderate, and date conflicts as minor (or moderate if >90 days). This aligns with clinical risk priorities.
- **The coercion layer in parallel_extractor is impressively flexible**: `_coerce_facts()` (lines 79-154) handles multiple key naming conventions for the same concept (e.g., "entity" / "name" / "label" / "term" / "fact"). This is excellent defensive coding against schema drift in the SOAP extractor.

#### Research-Backed Improvements
- Add few-shot examples to the conflict analysis prompt.
- Use JSON mode or structured output for the conflict analysis LLM call.
- Add logging/alerting when the LLM fallback is triggered repeatedly.

#### Changes Made / Recommended
- **Recommended**: Add 2-3 few-shot examples to `conflict_analysis.txt`.
- **Recommended**: Log a warning (not just silently fallback) when the LLM conflict analysis fails.
- **Recommended**: Switch to JSON mode for the conflict analysis LLM call.

#### Verdict: GOOD

The overall architecture is excellent. The 4-stage pipeline with deterministic fallback at each stage is a model for the other agents. The main weakness is the minimal conflict analysis prompt and fragile JSON extraction.

---

### Agent 08: Summary Generator (Port 5008)

**Files reviewed:** `5th/agents/context_assembler.py` (108 lines), `5th/agents/summary_composer.py` (130 lines), `5th/agents/output_formatter.py` (185 lines), `5th/prompts/summary_generation.txt` (32 lines)

#### Previous State
The summary generator is a 3-stage pipeline: (1) context assembly from the Fact Graph, (2) LLM-powered summary composition, (3) output formatting with completeness scoring. This agent uses the **OpenAI structured output / `responses.parse()` API** — the only agent in the platform to do so.

#### Issues Identified
- **Structured output is properly used**: `summary_composer.py` line 43 uses `client.responses.parse()` with `text_format=DischargeSummary`. This is the gold standard for schema enforcement — the LLM output is guaranteed to conform to the Pydantic model. Other agents should adopt this pattern.
- **Prompt is thin**: `summary_generation.txt` (32 lines) is template-driven but contains no few-shot examples. Given the complexity of discharge summaries, at least one example showing proper grounding of claims to source data would improve output quality.
- **Model refusal is detected**: `summary_composer.py` lines 61-66 check for refusal content and raise `ModelRefusalError`. This is a good safety measure.
- **Context assembler has robust payload unwrapping**: `context_assembler.py` lines 84-96 `_unwrap_payload()` handles multiple API response wrapper patterns (`result`, `data`, `payload`). This is good defensive coding.
- **Completeness scoring is mechanical**: `output_formatter.py` line 54 computes completeness as `present_fields / total_fields`. This treats all fields as equally important — a missing `lifestyle_dietary_instructions` counts the same as a missing `medications_on_discharge`. The scoring should be weighted.
- **Thread offloading for sync client**: `summary_composer.py` line 34 uses `asyncio.to_thread()` to run the synchronous OpenAI client in a thread pool. This is correct and avoids blocking the event loop.

#### Research-Backed Improvements
- Add a weighted completeness score (critical fields count more).
- Add few-shot examples to the prompt template.
- Consider adding a self-critique step: generate summary, then ask the LLM to verify each claim against the source data.

#### Changes Made (April 5, 2026)
- **DONE**: Rewrote `summary_generation.txt` from 32 lines to ~70 lines with SOTA-informed improvements:
  - **Entity-guided planning** (inspired by SPEER, arXiv:2401.02369): Prompt now instructs the LLM to identify salient entities from the Patient State per section before writing, ensuring entity coverage and reducing hallucination.
  - **Source-grounded generation** (inspired by LCDS, arXiv:2507.05319): Every clinical claim must trace back to a specific entity, event, or fact. Instructions include using `canonical_name`, `certainty_trajectory`, and temporal data from the Fact Graph.
  - **Self-verification step** (inspired by MedFactEval, arXiv:2509.05878): Added a post-generation verification checklist — the LLM must verify each claim against source data before finalizing. Checks for date fabrication, certainty label accuracy, negation consistency, and measurement fidelity.
  - **One-shot example**: Added a concrete section excerpt showing how to ground claims in entity status and certainty trajectory data — best performing strategy per benchmarking (arXiv:2512.06812, Gemini with one-shot outperformed all other strategies).
  - **TMC-specific rules**: Instructions for deriving `tumor_response` from certainty trajectories, grouping entities by `body_region`, and basing `condition_at_discharge` on primary disease entity status.
- **DONE**: Made `admission_date`, `discharge_date`, `attending_physician`, `department` optional in `GenerateSummaryRequest` model — previously required, causing 422 errors when the orchestrator sent null values.
- **DONE**: Fixed `fact_graph_base_url` config to accept `FACT_GRAPH_BASE_URL` env var (was hardcoded to Docker DNS `http://fact-graph:5006`, breaking bare-metal deployment).
- **DONE**: Added `ENABLE_SUMMARY_GENERATOR=true` to `deploy_tyrone.sh` (was missing, causing orchestrator to report "Summary generator is not enabled yet").
- **DONE**: Azure API version bumped to `2025-03-01-preview` for the summary generator — the `responses.parse()` structured output API requires `2025-03-01-preview` or later, but all agents were using `2025-01-01-preview`. Introduced a separate `SUMMARY_AZURE_API_VERSION` env var alias so the summary generator uses the correct version without affecting other agents.
- **DONE**: Increased orchestrator timeout for summary-generator from 45s to 120s, and QA agent from 30s to 90s. Patient 10000935 has 155 entities — the structured output LLM call takes 30-60s, and the full pipeline (summary → QA → translation) was exceeding the default timeout.
- **DONE**: Made `context_assembler.py` handle 404 from the Fact Graph's `/measurements` endpoint gracefully (returns `None` instead of crashing) — the RECIST measurements endpoint is not yet implemented, but `include_recist` was defaulting to `true`.
- **DONE**: Changed `include_recist` default to `false` in both the orchestrator schema (`SummaryWorkflowRequest`) and the summary generator's `GenerateSummaryRequest` — prevents 502 errors until the measurements endpoint is built.
- **Recommended**: Weight completeness scoring by section criticality.
- **Recommended**: All other agents should adopt the `responses.parse()` pattern used here.

#### Verdict: GOOD → STRONG (after changes)

This agent sets the standard for the platform in terms of output schema enforcement. The use of `responses.parse()` with a Pydantic model should be the template for all LLM-calling agents. The prompt is now SOTA-informed with entity planning, source attribution, self-verification, and a one-shot example — addressing all previously identified gaps.

---

### Agent 09: QA Agent (Port 5009)

**Files reviewed:** `6th/qa-agent/checks/traceability.py` (155 lines), `6th/qa-agent/checks/completeness.py` (41 lines), `6th/qa-agent/checks/confidence.py` (27 lines), `6th/qa-agent/checks/consistency.py` (90 lines), `6th/qa-agent/checks/nabh_compliance.py` (112 lines), `6th/qa-agent/utils.py` (206 lines), `6th/qa-agent/main.py` (109 lines)

#### Previous State
The QA agent runs 5 check categories against a generated discharge summary: completeness, consistency (diagnosis/medication matching against source facts), confidence thresholds, traceability (claim-to-fact linking via heuristic or LLM), and NABH compliance (India's National Accreditation Board for Hospitals). It produces a structured verdict (PASS/FAIL) with prioritized issues and an audit trail.

#### Issues Identified
- **Traceability has a sophisticated dual-mode design**: `traceability.py` supports three modes: `disabled`, `heuristic` (lexical matching), and `llm` (Azure OpenAI reasoning model with configurable effort). The auto mode tries LLM first and falls back to heuristic. This is excellent.
- **The LLM traceability check uses the Responses API with reasoning**: Line 112-113 uses `client.responses.create()` with `reasoning={"effort": settings.traceability_reasoning_effort}`. This leverages the reasoning model for deeper claim verification.
- **Heuristic traceability has a meaningful overlap check**: `utils.py` lines 96-111 `lexical_match()` uses token-based overlap with stop word filtering and configurable minimum overlap. This is a reasonable approximation when the LLM is unavailable.
- **NABH compliance checks are well-targeted**: `nabh_compliance.py` checks for patient identifier, admission/discharge dates, urgent care instructions, medication details, lifestyle instructions, and death case cause of death. These align with NABH 2025 standards.
- **Consistency checks cross-reference diagnoses and medications**: `consistency.py` verifies that every diagnosis and medication in the summary exists in the source facts. This is a strong anti-hallucination check at the summary level.
- **Traceability JSON parsing has a silent failure**: `traceability.py` lines 143-154 `_parse_traceability_json()` falls back to `{"unsupported_claims": []}` if JSON parsing fails. This means a malformed LLM response is treated as "all claims are supported" — the exact opposite of safe behavior. It should default to flagging all claims as unverified.
- **No cross-check for negation consistency**: The consistency check verifies presence of diagnoses and medications but does not check for negation consistency (e.g., summary says "no diabetes" but source facts say "diabetes confirmed").
- **Audit trail is deterministic**: `main.py` lines 85-98 generate a validation ID, timestamp, and summary hash. This enables reproducible auditing.

#### Research-Backed Improvements
- **Critical**: Change the JSON parse fallback in `_parse_traceability_json()` to treat parse failures as "all claims unverified" rather than "all claims supported."
- Add negation-aware consistency checking.
- Add medication dosage consistency checking (not just name matching).

#### Changes Made / Recommended
- **Recommended (P0)**: Change `_parse_traceability_json()` fallback to flag all claims as unverified.
- **Recommended**: Add negation-aware fact matching in `check_consistency()`.
- **Recommended**: Add dosage-level medication verification.

#### Verdict: GOOD

The QA agent is the safety net of the entire platform and is well-designed for the role. The dual-mode traceability, NABH compliance checks, and structured audit trail are all strong. The critical issue is the JSON parse fallback that silently passes all claims on LLM output failure.

---

### Agent 10: Translation Layer (Port 5010)

**Files reviewed:** `7th/agents/translator.py` (131 lines), `7th/agents/pdf_generator.py` (61 lines), `7th/agents/fhir_exporter.py` (99 lines), `7th/agents/tts_generator.py` (106 lines), `7th/translation_service.py` (168 lines), `7th/main.py` (32 lines)

#### Previous State
The translation layer converts English discharge summaries into Indian languages (via Sarvam AI translation API), generates bilingual PDFs (via Jinja2 + WeasyPrint), produces audio narration (via Sarvam TTS), and exports FHIR R4 bundles. This is a pure integration agent with no LLM prompts.

#### Issues Identified
- **No LLM prompt to audit**: This agent uses the Sarvam translation and TTS APIs, not a local LLM. Prompt quality is not applicable.
- **Text chunking is well-implemented**: `translator.py` lines 18-62 `chunk_text()` splits by paragraph boundaries, then by sentence if paragraphs are too large. This preserves semantic units for translation.
- **FHIR export is structurally correct but minimal**: `fhir_exporter.py` generates a valid FHIR R4 Bundle with Patient, Composition, and DocumentReference resources. However, it does not include Condition, MedicationRequest, or other clinical resources that would make the bundle useful for EHR integration.
- **PDF generation uses Jinja2 with autoescape**: `pdf_generator.py` line 13 uses `select_autoescape(["html", "xml"])`. This prevents XSS in the HTML template. Good practice.
- **TTS has a character limit but no chunking strategy**: `tts_generator.py` line 49 raises an error if text exceeds `tts_max_chars`. Unlike the translator, there is no automatic chunking — the entire summary must fit in one TTS call.
- **No translation quality verification**: There is no back-translation or human review step to verify translation accuracy. For medical documents, a mistranslation of dosage instructions could be dangerous.
- **`render_discharge_summary()` is a generic dict/list renderer**: `translation_service.py` lines 25-59 recursively render any dict/list structure into human-readable text. This is flexible but produces unstructured output that may not be ideal for translation (medical terms buried in nested lists).

#### Research-Backed Improvements
- Add automatic chunking for TTS (split text, generate audio per chunk, concatenate WAV files — the infrastructure for WAV merging already exists in `_merge_audio`).
- Add a back-translation verification step: translate back to English and compare key medical terms.
- Extend the FHIR bundle to include Condition and MedicationRequest resources.

#### Changes Made / Recommended
- **Recommended**: Add TTS chunking to match the translator's chunking strategy.
- **Recommended**: Add back-translation verification for critical terms (medications, dosages).
- **Recommended**: Expand FHIR bundle to include clinical resources.

#### Verdict: ADEQUATE

The agent is well-built as an integration layer. The main concerns are the lack of translation quality verification and the TTS character limit without chunking.

---

## Cross-Cutting Findings

### Prompt Engineering

| Agent | Prompt Lines | Few-Shot Examples | Structured Output Spec | Negation Handling | Certainty Scoring |
|---|---|---|---|---|---|
| 01 OCR | 20 | 0 | No (raw text) | Via [ILLEGIBLE] token | Post-hoc heuristic |
| 02 SOAP | 271 | 3 (excellent) | JSON schema in prompt | Yes (explicit rule) | Per-field CD score |
| 03 Radiology | 235 + 80 (paired) | 3+ inline examples | JSON schema in prompt | Yes (extensive NegEx) | 4-tier certainty |
| 05 Counselling | 48 | 1 (minimal) | JSON shape in prompt | Via diagnosis filter | Per-fact certainty |
| 07 Conflict | 26 | 0 | JSON keys in prompt | N/A | N/A |
| 08 Summary | ~70 | 1 (section excerpt) | Pydantic model (API) | Yes (entity status check) | Via certainty trajectory |
| 09 QA Trace | 6 (inline) | 0 | JSON shape in prompt | N/A | N/A |

**Key finding**: Only Agents 02 and 03 have production-grade prompts with few-shot examples. Agents 05, 07, 08, and 09 would benefit from adding examples. Agent 01's prompt is simple but appropriate for its task (raw transcription).

### Output Schema Enforcement

| Agent | Method | Robustness |
|---|---|---|
| 01 OCR | Manual dict construction | No validation |
| 02 SOAP | Regex JSON extraction + `.get()` chains | Fragile |
| 03 Radiology | Hybrid (rule extractor returns typed objects, LLM output parsed) | Moderate |
| 05 Counselling | `CounsellingFact.model_validate()` | Strong |
| 07 Conflict Analyzer | `content.find("{")` extraction | Very fragile |
| 08 Summary | `responses.parse()` with Pydantic model | Excellent |
| 09 QA Traceability | `json.loads()` with find/rfind fallback | Fragile |

**Key finding**: Only Agent 08 uses the OpenAI structured output API. Agent 05 is the only other agent that validates LLM output against a Pydantic model. All other LLM-calling agents use regex-based JSON extraction, which is a reliability risk.

### Error Handling Patterns

| Pattern | Agents Using It | Assessment |
|---|---|---|
| Bare `except Exception` with silent fallback | 03, 04, 07 | Dangerous — masks permanent failures |
| `HTTPException` wrapping with error detail | 01, 02, 04, 10 | Good for API consumers |
| No retry on LLM calls | All agents | Platform-wide gap |
| Graceful degradation on LLM failure | 07, 09 | Good — deterministic fallback exists |
| Parse failure returns empty/default | 03, 09 | Dangerous — silent data loss |

**Key finding**: No agent in the platform implements retry logic for LLM calls. Every LLM integration makes a single attempt and either returns or fails. Given the known transient failure rate of Azure OpenAI (rate limits, timeouts), this is a platform-wide reliability gap.

### Human-in-the-Loop Integration

| Touchpoint | Agent | Mechanism | Assessment |
|---|---|---|---|
| OCR review flag | 01 | `needs_human_review` when illegible_count > 3 or confidence < 0.6 | Good threshold |
| Counselling fact selection | 05 | `selectable: true` default + approved IDs passed to Agent 08 | Excellent design |
| QA validation verdict | 09 | PASS/FAIL with prioritized issues | Good — clinician reviews before release |
| Conflict resolution | 07 | `suggested_resolution` always defers to clinician | Excellent — never auto-resolves |

**Key finding**: The human-in-the-loop design is strongest at the counselling and conflict resolution stages. The gap is between OCR (Agent 01) and SOAP extraction (Agent 02) — there is no review gate for the corrected OCR text before it becomes structured clinical data. A misread medication dosage could flow through to the discharge summary unreviewed.

---

## Recommendations Priority Matrix

| Priority | Agent | Issue | Impact | Effort |
|---|---|---|---|---|
| P0 | 09 QA | `_parse_traceability_json()` fallback treats parse failures as "all claims supported" | **Critical** — defeats the safety net | Low (change default return) |
| P0 | All | No retry logic on any LLM call | **High** — transient failures cause silent data loss | Medium (add shared retry wrapper) |
| P0 | 03 Radiology | Silent empty return on extraction failure | **High** — missed cancer progression in oncology context | Low (return error response) |
| P1 | 02 SOAP | Medication certainty hardcoded to 0.99, ignoring handwriting_confidence | **Moderate** — inflated confidence on illegible prescriptions | Low (use existing field) |
| P1 | 02, 07, 09 | Regex-based JSON extraction from LLM output | **Moderate** — malformed LLM output causes parse failures | Medium (switch to JSON mode/structured output) |
| P1 | 01 OCR | No max file size validation | **Moderate** — DoS vector via large image upload | Low (add size check) |
| P1 | 05 Counselling | Prompt lacks few-shot examples | **Moderate** — edge case extraction quality | Low (add examples) |
| P1 | 07 Conflict | Conflict analysis prompt lacks few-shot examples | **Moderate** — conflict resolution quality | Low (add examples) |
| P2 | All | No `seed` parameter for reproducibility | **Low** — results vary between identical runs | Low (add seed param) |
| P2 | 01 OCR | Indic script detection limited to Devanagari | **Low** — other Indian scripts not flagged | Low (extend regex) |
| P2 | 10 Translation | No back-translation verification | **Moderate** — medication dosage mistranslation risk | High (new pipeline stage) |
| P2 | 10 Translation | TTS lacks chunking (translator has it) | **Low** — long summaries cannot be narrated | Medium (port chunking logic) |
| P2 | 06 Fact Graph | File-based per-patient storage | **Low** (operational) — scalability concern at >100K patients | High (database migration) |
| P2 | 08 Summary | Completeness scoring treats all fields equally | **Low** — misleading score | Low (add weight map) |
| ~~P1~~ | ~~08 Summary~~ | ~~Prompt lacks few-shot examples~~ | ~~**Moderate**~~ | ~~DONE — rewritten with SOTA techniques~~ |
| ~~P1~~ | ~~08 Summary~~ | ~~ENABLE_SUMMARY_GENERATOR not set in deploy script~~ | ~~**High** — agent disabled~~ | ~~DONE — added to deploy_tyrone.sh~~ |
| ~~P1~~ | ~~08 Summary~~ | ~~Azure API version too old for responses.parse()~~ | ~~**High** — 400 error~~ | ~~DONE — bumped to 2025-03-01-preview~~ |
| ~~P1~~ | ~~08 Summary~~ | ~~Timeouts too low for large patient graphs~~ | ~~**High** — 502 timeout~~ | ~~DONE — 120s summary, 90s QA~~ |
| ~~P1~~ | ~~08 Summary~~ | ~~RECIST endpoint 404 crashes pipeline~~ | ~~**High** — 502 error~~ | ~~DONE — graceful 404 + default false~~ |
| ~~P1~~ | ~~Frontend~~ | ~~API type mismatches (getPatients, getPatientState)~~ | ~~**High** — "seed required" shown~~ | ~~DONE — fixed all API types~~ |
| ~~P1~~ | ~~Frontend~~ | ~~Clinical Summary shows 155 raw entity cards~~ | ~~**Moderate** — unusable~~ | ~~DONE — prose narrative with significance tiering~~ |
| ~~P1~~ | ~~Deploy~~ | ~~6 of 10 ENABLE_* flags missing~~ | ~~**High** — agents disabled~~ | ~~DONE — all flags set~~ |
| ~~P1~~ | ~~Deploy~~ | ~~Seed script event_id collisions~~ | ~~**High** — 4/5 patients failed~~ | ~~DONE — entity_id in event_id~~ |
| P3 | 09 QA | No negation-aware consistency checking | **Moderate** — "no diabetes" vs "diabetes" not caught | Medium |
| P3 | 04 Voice | Consent validation lacks recency check | **Low** — regulatory compliance edge case | Low |

---

## Frontend & Deployment Changes (April 5, 2026)

### Clinical Summary UI Rewrite

**Problem**: The Clinical Summary tab displayed all 155 entities as flat cards showing raw entity IDs (e.g., `finding_gray_white_matter_differentiation_preserved`) with certainty bars and date ranges. This was unusable — 155 cards of equal visual weight with no clinical prioritization.

**Analysis of entity distribution** (Patient 10000935):
- 79 absent/excluded — not clinically relevant for current state
- 47 active with only 1 event — incidental findings from single reports
- 27 active with multiple events — actively tracked across imaging studies
- 2 uncertain — under evaluation

**Changes made** (informed by RadGraph hierarchical entity display, SPEER entity planning, and TMC clinical report conventions):
- **Entity-to-prose transformation**: Each entity is now rendered as a clinical sentence instead of a card. E.g., `finding_hemorrhage` with status `absent` and 5 events → *"Hemorrhage was previously documented but has since been excluded (10 May 2182 – 17 Oct 2187)."*
- **Clinical significance tiering**: Entities are split into 4 tiers by `event_count` and `status`:
  1. **Tracked findings** (active, multi-event): shown immediately as prose — these are actively monitored
  2. **Uncertain findings**: always shown — require clinical attention
  3. **Incidental findings** (active, single-event): collapsed by default — click to expand
  4. **Excluded findings** (absent/negated): shown as a count only — *"79 previously documented findings have since been excluded"*
- **Body region grouping**: Sections sorted by number of significant (tracked) entities, not total count
- **Certainty language mapping**: Raw scores → clinical hedging: ≥0.9 = "confirmed", ≥0.7 = "likely", ≥0.5 = "suspected", <0.5 = "uncertain"
- **Trajectory-based trend reporting**: When an entity has ≥2 certainty data points, the trend is computed (increasing/stable/decreasing) and appended to the sentence

**Result**: Default view shows ~29 entities as readable clinical prose instead of 155 cards. Clinicians see what matters immediately; incidentals are one click away; excluded findings are just a count.

### Discharge Summary Page Fixes

- **React rendering crash**: `data.discharge_summary` is a structured object (35 keys), not a string. The TypeScript `as string` cast did not convert it — React threw "Objects are not valid as a React child" when trying to render it. Fixed by properly detecting object vs string type and routing to the structured renderer.
- **QA issues field mismatch**: UI read `issue.description` but the QA agent returns `issue.message`. Fixed.
- **Structured summary renderer**: Added section-by-section display of the `DischargeSummary` object (Patient Name, Admission Diagnosis, Imaging Findings, Medications, Follow-up Schedule, etc.) with proper rendering for strings, arrays, and nested objects.
- **Copy to clipboard**: Added button to copy the full summary text.
- **Status banner**: Shows workflow status message (e.g., "QA validation failed") with appropriate color coding.
- **Date validation**: Frontend now validates dates as strict `YYYY-MM-DD` with 4-digit years — previously allowed malformed dates like `20000-01-01` to reach the backend, causing Pydantic 422 errors.

### API Client Fixes (lib/api.ts)

- **`getPatients()`**: Was expecting `{ patients: string[] }` but the orchestrator returns a raw array of `PatientSummary` objects from the fact-graph. Fixed return type.
- **`getPatientState()` / `getPatientTimeline()`**: These endpoints return `WorkflowEnvelope` wrappers, but the frontend expected flat `PatientState`/`PatientTimeline`. Added unwrapping of `.data` field.
- **Entity normalization**: Added `normalizeEntity()` function to map backend field names (`first_documented` → `first_seen`, `last_documented` → `last_seen`) and compute derived fields (`certainty_score` from trajectory, `trend` from trajectory delta, `negated` from status).

### Event Timeline UI Rewrite

**Problem**: The Event Timeline tab displayed all 304 events as individual cards — one card per finding per report. For Patient 10000935, this meant 304 vertically-stacked cards of equal visual weight with no temporal grouping, no report context, and no way to see the clinical narrative of a single imaging session.

**Analysis of event distribution** (Patient 10000935):
- 304 total events across 29 unique imaging dates
- Events span May 2182 – Oct 2187 (5+ years of longitudinal imaging)
- Each imaging session typically produces 5–15 findings from a single report
- Measurements (tumor sizes, etc.) were buried as raw JSON in individual cards

**Changes made** (informed by temporal EHR visualization research — TimelineJS clinical adaptations, event-clustering approaches):
- **Date → Report → Findings hierarchy**: Events are grouped first by date (29 groups), then by `source_report_id` within each date. Each report is a collapsible card showing all findings from that imaging session together.
- **Narrative finding summaries**: Instead of individual cards, each report card shows a single-paragraph narrative of its findings. `findingToPhrase()` converts events to inline clinical phrases (e.g., "confirmed hemorrhage" or "no evidence of midline shift"), joined as natural prose.
- **Measurement table**: When a report contains events with measurements (tumor sizes, distances), these are extracted into a structured table within the expanded report view, showing entity name, raw measurement text, and normalized mm value.
- **Negated/excluded findings**: Explicitly separated from positive findings in the expanded view, shown in muted styling — clinically important to distinguish "found" vs "ruled out".
- **Progressive disclosure**: Only the 8 most recent dates are shown by default, with a clickable expander showing "N older sessions — click to show". Each report card is collapsed by default, expandable to show full detail.
- **Summary statistics bar**: Top-level overview shows total events, total imaging sessions, and date span (e.g., "304 events across 29 imaging sessions spanning 10 May 2182 – 17 Oct 2187").
- **Certainty indicators**: Each finding in the expanded view gets a color-coded dot (green ≥0.8, amber ≥0.5, red <0.5, grey for negated) with certainty label and score.
- **Modality badges**: Each report card shows the imaging modality (CT, MR, X-Ray, etc.) as a colored badge.

**Result**: Default view shows 8 date groups with collapsible report cards instead of 304 individual cards. A clinician can quickly scan longitudinal imaging history, expand any session to see the full clinical picture, and identify measurement trends. The 21 older sessions are one click away.

### Timeline Component Fixes (prior)

- **Field name mismatches**: Backend returns `event.date` and `event.canonical_name`, but the timeline component used `event.timestamp` and `event.entity_name`. Fixed to handle both.
- **Measurement rendering**: `event.measurement` changed from `string` to `Record<string, unknown>` — caused TypeScript build errors and React rendering crashes. Fixed with proper type narrowing.

### Orchestrator Deployment Fixes

- **Missing feature flags**: `deploy_tyrone.sh` only set 4 of 10 `ENABLE_*` flags. Added the missing 6: `ENABLE_VOICE_TRANSCRIPTION`, `ENABLE_COUNSELLING_SUMMARIZER`, `ENABLE_DEPARTMENT_MERGER`, `ENABLE_SUMMARY_GENERATOR`, `ENABLE_QA_AGENT`, `ENABLE_TRANSLATION_LAYER`.
- **Orchestrator agent timeouts**: Summary generator timeout increased from 45s → 120s, QA agent from 30s → 90s. The full summary pipeline (generate → QA → translate) requires ~60-90s for large patient graphs.
- **Registry notes updated**: Summary generator agent definition updated to reflect Responses API dependency and timeout requirements.

### Seed Script Fix

- **Event ID collision**: `scripts/seed_patients.py` generated event IDs as `evt_{patient_id}_r{report_num}_{idx:03d}` where `idx` resets per entity. Multiple entities from the same report got identical event IDs (e.g., `evt_19540374_r1_000`), violating SQLite's UNIQUE constraint on `(event_id, subject_id)`. Fixed by including `entity_id` in the event ID: `evt_{patient_id}_{entity_id}_r{report_num}_{idx:03d}`.
- **Voice transcription missing dependency**: `sarvamai` pip package was not installed in the venv. Added to deployment.

---

## Voice Counselling Pipeline Changes (April 7, 2026)

### Overview

Implemented end-to-end voice counselling workflow: Sarvam STT → LLM transcript correction + bullet generation → structured fact extraction → human review → fact graph ingestion. This adds a new LLM agent (TranscriptCorrector), extends the counselling summarizer pipeline, updates the orchestrator API, and builds the counselling workflow UI page.

---

### New: TranscriptCorrector Agent

**Files created/modified:**
- `3rd/counselling-summarizer/models/bullet_point.py` — NEW: Pydantic v2 model
- `3rd/counselling-summarizer/agents/transcript_corrector.py` — NEW: LLM agent
- `3rd/counselling-summarizer/prompts/transcript_correction.txt` — NEW: correction + bullet generation prompt

**What it does**: A best-effort, fallback-safe LLM step between Sarvam STT and the fact extractor. Receives raw diarized segments (`[start-end] speaker: text`), uses gpt-4o-mini via AzureOpenAI to: (1) correct clear STT errors using full-conversation medical context, and (2) generate concise bullet points for the session.

**Design choices:**
- Falls back to `(raw_transcript, [])` on any failure — correction is strictly best-effort
- `AzureOpenAI` client is skipped entirely (`None`) when `AZURE_API_KEY` is absent — safe for dev/test
- JSON parsing is robust: strips markdown fencing, tries direct parse, falls back to `{...}` extraction
- Uses `BulletPoint` Pydantic model (`id`, `text`, `source_time_start`, `source_time_end`)

**Audit findings:**
- Prompt initially lacked few-shot examples and Chain-of-Thought — addressed in this session (see prompt improvements below)
- Model: `gpt-4o-mini` via `settings.azure_deployment` — appropriate cost/quality balance for correction
- `max_tokens=2000` is sufficient for sessions up to ~30 minutes

---

### Agent 05: Counselling Summarizer — Pipeline Extension

**Files modified:** `3rd/counselling-summarizer/main.py`, `3rd/counselling-summarizer/models/response.py`

**Changes:**
- `ProcessingResult` gained `bullet_points: list[BulletPoint]` and `corrected_transcript: str`
- `create_app()` now accepts injected `transcript_corrector` for testability
- Summarize endpoint now runs 4 stages in order: (1) correct transcript + generate bullets, (2) segment analysis on original segments for timing accuracy, (3) fact extraction on corrected transcript, (4) guardrail validation + ClinicalFact emission
- Fact extractor now receives `corrected_transcript or full_text` — corrected transcript has better punctuation and medical term accuracy, improving extraction quality

**Audit finding addressed**: The `TranscriptCorrectionError` class was defined but never raised (dead code); removed.

---

### Orchestrator Changes

**Files modified:** `final/orchestrator/app/schemas.py`, `final/orchestrator/app/storage.py`, `final/orchestrator/app/main.py`

#### schemas.py
- `CounsellingApproveRequest` gained `approved_bullet_ids: list[str] = Field(default_factory=list)` — allows the frontend to submit bullet point approvals alongside fact approvals

#### storage.py (`CounsellingSessionStore`)
- `create()`: extracts `bullet_points` from summarizer result, normalizes IDs with `bp-{session_id}-{n}` fallback, persists in record alongside counselling facts and clinical facts
- `mark_approved()`: now accepts `approved_bullet_ids` parameter; persists both `approved_fact_ids` and `approved_bullet_ids` in the record

#### main.py (`counselling_workflow` endpoint)
- WorkflowEnvelope data now includes `bullet_points` and `corrected_transcript` from the summarizer result
- `approve_counselling` endpoint rewritten to handle dual approval:
  - Filters `counselling_facts` by `approved_fact_ids`
  - Converts approved bullet points to `ClinicalFact`-compatible dicts (`certainty=0.9`, `source_type="COUNSELLING"`)
  - Merges facts + converted bullets into `all_clinical_facts` for ingestion
  - Returns `approved_facts_count`, `approved_bullets_count`, `total_ingested` in response

**Human-in-the-loop integration note**: The dual approval model (facts + bullets) is deliberate. Structured facts go through guardrail validation; bullet points are doctor-authored summaries that bypass extraction but get a fixed certainty of 0.9. This means doctors have two complementary review surfaces: machine-structured facts they can toggle, and their own plain-language notes they can edit/delete.

---

### Frontend Changes

**Files created/modified:**
- `platform-ui/lib/types.ts` — Added `BulletPoint`, `CounsellingFact`, `CounsellingApproveRequest` interfaces
- `platform-ui/lib/api.ts` — Added `submitCounselling()` and `approveCounselling()` API functions
- `platform-ui/app/demo/patient/[id]/workflow/counselling/page.tsx` — NEW: full counselling workflow page
- `platform-ui/app/demo/patient/[id]/page.tsx` — Changed counselling card from `available: false` to `available: true`

#### Counselling workflow page
4-step UI (input → processing → review → result):
- **Review step**: Two-panel grid (lg:grid-cols-2) — left panel bullet points, right panel counselling facts
- **Bullet points panel**: Inline edit (textarea on click) + delete (X button). All bullets selected by default.
- **Facts panel**: Checkbox cards with category badge (color-coded per CONCERN/ACTION/DECISION/EMOTIONAL/FOLLOW_UP) and certainty percentage. All facts selected by default.
- **Sticky confirm bar**: "N bullets + M facts will be ingested" summary + "Confirm & Ingest" button. Dynamically updates as doctor toggles items.
- **State management**: `approvedBulletIds` and `approvedFactIds` use `Set<string>` with correct React mutation pattern (`new Set(prev)` on every toggle).

---

### Prompt Improvements (April 7, 2026)

#### transcript_correction.txt
Rewritten with:
- **Chain-of-Thought structure**: Explicit 3-phase reasoning (identify errors → classify severity → correct minimally)
- **3 few-shot examples** covering: (1) drug name mishearing in Hindi-English code-mixed speech, (2) dosage number error in an oncology context, (3) clean transcript that needs no correction
- **Uncertainty flagging**: Instructions to mark uncertain corrections with `[?]` rather than guess
- **Clinical meaning preservation**: Explicit rule — if correction would change clinical meaning, leave original
- Research basis: CoT improves LLM correction quality per arXiv 2501.15310; few-shot examples critical for clinical NLP consistency per PMC clinical NLP benchmark

#### counselling_extraction.txt
Updated with:
- **3 few-shot examples** covering edge cases identified in the original audit: (1) patient concern mentioning a condition but not a diagnosis, (2) implicit emotional state inferred from behaviour, (3) ambiguous follow-up item with low certainty
- Examples are drawn from Indian oncology counselling context for domain alignment
- Research basis: 2-5 few-shot examples significantly improve consistency in clinical NLP tasks per systematic review

---

### Testability Assessment

**Can the voice pipeline be tested against existing datasets?**

| Level | Component | Recommended Dataset | Metric |
|---|---|---|---|
| L1: STT accuracy | Sarvam `sarvam-saaras-v3` | `ekacare/eka-medical-asr-evaluation-dataset` (HuggingFace, 3,900+ Indian medical recordings) | WER, MC-WER (medical concept WER) |
| L2: LLM correction quality | `TranscriptCorrector.correct()` | Same EkaCare ASR dataset — compare WER pre/post correction | WER delta, semantic similarity |
| L3: Bullet point quality | Bullet generation in `transcript_correction.txt` | `ekacare/clinical_note_generation_dataset` (156 doctor-patient conversations, Hindi/English/Marathi, ground truth JSON) | Rubric-based LLM judge (relevance, completeness, no hallucination) |
| L4: Fact extraction quality | `counselling_extraction.txt` + guardrails | Same EkaCare clinical note dataset — compare extracted facts vs gold annotations | F1 per category (CONCERN/ACTION/DECISION/EMOTIONAL/FOLLOW_UP) |

**Key finding**: The EkaCare Medical ASR Evaluation Dataset (`ekacare/eka-medical-asr-evaluation-dataset`) is the closest public benchmark to the platform's deployment context — Indian hospitals, multilingual speakers, medical terminology. MC-WER (which weights medical term errors more than function words) is the appropriate primary metric for L1/L2 evaluation.

**Per arXiv 2501.15310**: LLM-based transcript correction yields the largest WER reduction when the baseline transcription quality is poor (high error rate). Indian-accented medical speech to non-specialized STT systems typically has 15-30% WER baseline, making LLM correction a high-value step in this context.

**Recommended evaluation script** (not yet implemented):
```python
# pip install datasets jiwer
from datasets import load_dataset
from jiwer import wer
dataset = load_dataset("ekacare/eka-medical-asr-evaluation-dataset")
# for each sample: run Sarvam STT → TranscriptCorrector → compute WER vs ground truth
```

---

### Recommendations Priority Matrix (additions)

| Priority | Component | Issue | Impact | Status |
|---|---|---|---|---|
| ~~P1~~ | ~~Agent 05 Counselling~~ | ~~Prompt lacks few-shot examples~~ | ~~Moderate~~ | ~~DONE — 3 examples added~~ |
| ~~P1~~ | ~~Agent 04 Voice~~ | ~~No LLM correction step between STT and fact extraction~~ | ~~High — STT errors propagate to facts~~ | ~~DONE — TranscriptCorrector added~~ |
| ~~P1~~ | ~~Frontend~~ | ~~Counselling workflow page missing~~ | ~~High — workflow unusable~~ | ~~DONE — full 4-step page built~~ |
| ~~P1~~ | ~~Orchestrator~~ | ~~Approve endpoint only handled structured facts, not bullets~~ | ~~High — bullet approvals lost~~ | ~~DONE — dual approval implemented~~ |
| P1 | TranscriptCorrector | No retry logic on AzureOpenAI call | Moderate — single transient failure drops correction | Low (add exponential backoff) |
| P1 | TranscriptCorrector | `max_tokens=2000` may truncate long sessions (>30 min) | Moderate — bullets silently cut off | Low (increase to 4000 or add chunking) |
| P2 | Bullet points | Certainty hardcoded at 0.9 for all approved bullets | Low — no per-bullet quality signal | Medium (add confidence scoring to correction prompt) |
| P2 | Evaluation | No automated test harness against EkaCare ASR dataset | Low (testing gap) | High (implement evaluation script) |

---

## Appendix: Prompts Analyzed

| File / Location | Agent | Lines | Type |
|---|---|---|---|
| `ocr-agent/app/ocr.py` lines 14-33 | 01 OCR | 20 | Inline string |
| `soap-extractor/app/soap.py` lines 17-271 | 02 SOAP | 255 | Inline string |
| `radiology-extractor/tmc_core/extraction/prompts.py` lines 12-235 | 03 Radiology (single) | 224 | Module constant |
| `radiology-extractor/tmc_core/extraction/prompts.py` lines 242-320 | 03 Radiology (paired) | 79 | Module constant |
| `radiology-extractor/tmc_core/extraction/prompts.py` lines 327-426 | 03 Entity Normalization | 100 | Module constant |
| `radiology-extractor/tmc_core/extraction/prompts.py` lines 433-476 | 03 Fact Graph Render | 44 | Module constant |
| `radiology-extractor/tmc_core/extraction/prompts.py` lines 483-500 | 03 Non-target Supplement | 18 | Module constant |
| `radiology-extractor/tmc_core/extraction/prompts.py` lines 506-535 | 03 Extraction Eval | 30 | Module constant |
| `3rd/counselling-summarizer/prompts/counselling_extraction.txt` | 05 Counselling | ~85 | External file (rewritten with 3 few-shot examples, April 7) |
| `3rd/counselling-summarizer/prompts/transcript_correction.txt` | 04+05 TranscriptCorrector | ~90 | External file (NEW, April 7, CoT + 3 few-shot examples) |
| `4th/department-merger/prompts/conflict_analysis.txt` | 07 Conflict | 26 | External file |
| `5th/prompts/summary_generation.txt` | 08 Summary | ~70 | External file (rewritten with SOTA techniques) |
| `6th/qa-agent/checks/traceability.py` lines 97-102 | 09 QA Traceability | 6 | Inline string |

**Total prompt content reviewed**: ~1060 lines across 14 prompt locations in 10 agents.
