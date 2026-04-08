# Agent 05: Counselling Summarizer

> **Status:** NEW — build from scratch  
> **Deployment:** Standalone microservice  
> **Port:** `5005`  
> **Base URL:** `http://counselling-summarizer:5005`

---

## 1. What This Agent Does

The Counselling Summarizer takes **English transcripts** (from the Voice Transcription Agent) and extracts **clinically relevant structured facts**. It identifies patient concerns, recommended actions, follow-up items, emotional state, and clinical decisions discussed during the session.

Each fact gets a certainty score and evidence link. The output feeds into the **Selective Inclusion UI** where clinicians choose what goes into the discharge summary.

---

## 2. Why This Exists

Counselling sessions contain valuable clinical information (patient anxiety about treatment, discussed alternatives, follow-up commitments) but are currently undocumented. Dr. Bhawesh Pangaria at TMC requested that this information be captured — but with clinician control over what gets included.

---

## 3. Architecture

```
English Transcript (from Voice Transcription Agent)
        │
        ▼
┌──────────────────────────┐
│ Stage 1: Segment Analysis │  ◄── Identify clinically relevant segments
│ - Skip small talk          │      vs irrelevant conversation
│ - Identify clinical turns  │
│ - Mark emotional signals   │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│ Stage 2: Fact Extraction  │  ◄── Claude Sonnet 4
│ - Patient concerns         │      System B discipline:
│ - Recommended actions      │      - certainty scores
│ - Clinical decisions       │      - evidence linking
│ - Emotional state          │      - "Unknown" not hallucinate
│ - Follow-up items          │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│ Stage 3: CFS Emit         │  ◄── Convert to Clinical Fact Schema
│ - Each fact → CFS object   │      All facts default selectable=true
│ - Category tagging          │
│ - Selective inclusion flags │
└──────────────────────────┘
```

---

## 4. Implementation Details

### 4.1 Stage 2 Prompt (Core Logic)

```text
You are a clinical counselling summarizer. You will receive an English transcript 
of a counselling session between a doctor and a patient.

EXTRACT the following categories of clinical facts:

1. CONCERN: Patient-expressed worries, fears, or anxieties about their condition or treatment.
   Example: "Patient expressed significant anxiety about chemotherapy side effects"

2. ACTION: Specific actions recommended by the doctor during counselling.
   Example: "Doctor recommended joining a support group for post-surgery recovery"

3. DECISION: Clinical decisions discussed or agreed upon.
   Example: "Patient agreed to proceed with second-line chemotherapy after discussion of alternatives"

4. EMOTIONAL: Significant emotional states observed.
   Example: "Patient appeared distressed when discussing prognosis"

5. FOLLOW_UP: Follow-up items or commitments made.
   Example: "Doctor scheduled follow-up counselling session in 2 weeks"

RULES:
- Every fact MUST have a direct evidence link to a specific part of the transcript.
- Assign a certainty score (0.0 to 1.0) based on how clearly the fact is stated.
- If something is implied but not clearly stated, set certainty below 0.6.
- If you cannot determine something, output "Unknown". Do NOT fabricate.
- Do NOT extract medical diagnoses or treatment plans — those come from other agents.
  Only extract counselling-specific information.
- Do NOT include small talk, greetings, or non-clinical conversation.
- Preserve the patient's voice — use their phrasing when describing concerns.

TRANSCRIPT:
{transcript}

OUTPUT FORMAT (JSON array):
[
  {
    "fact": "Patient expressed fear about hair loss from chemotherapy",
    "category": "CONCERN",
    "certainty": 0.92,
    "evidence_start_time": 45.2,
    "evidence_end_time": 52.8,
    "evidence_text": "Patient: I am really scared about losing my hair...",
    "speaker": "patient",
    "selectable": true
  }
]
```

### 4.2 Evidence Linking

Every fact must trace back to a specific segment of the transcript:

```python
class CounsellingFact:
    fact: str                    # The extracted fact
    category: str                # CONCERN | ACTION | DECISION | EMOTIONAL | FOLLOW_UP
    certainty: float             # 0.0 to 1.0
    evidence_start_time: float   # Timestamp in seconds
    evidence_end_time: float     # Timestamp in seconds
    evidence_text: str           # The exact transcript segment
    speaker: str                 # "doctor" or "patient"
    selectable: bool             # Default true — clinician can toggle in UI
```

### 4.3 Guardrails

```python
def validate_counselling_facts(facts: list[CounsellingFact], transcript: str) -> list[CounsellingFact]:
    validated = []
    for fact in facts:
        # Check 1: Evidence text must actually exist in transcript
        if fact.evidence_text not in transcript:
            fact.certainty *= 0.5  # Reduce confidence if evidence doesn't match
            fact.flag = "evidence_not_found_in_transcript"
        
        # Check 2: No medical diagnoses (those belong to other agents)
        if contains_diagnosis(fact.fact):
            continue  # Skip — not this agent's job
        
        # Check 3: Certainty must be reasonable
        if fact.certainty < 0.3:
            continue  # Too uncertain to include
        
        validated.append(fact)
    
    return validated
```

---

## 5. API Contract

### 5.1 Endpoint

```
POST /api/v1/summarize
Content-Type: application/json
```

### 5.2 Request

```json
{
  "patient_id": "PAT-12345",
  "transcript_english": {
    "segments": [
      {"speaker": "doctor", "start_time": 0.0, "end_time": 5.2, "text": "Do you have any concerns?"},
      {"speaker": "patient", "start_time": 5.8, "end_time": 12.4, "text": "I am very afraid of chemotherapy side effects"}
    ]
  },
  "full_text_english": "Doctor: Do you have any concerns?\nPatient: I am very afraid of chemotherapy side effects",
  "session_type": "counselling",
  "department": "oncology"
}
```

### 5.3 Response

```json
{
  "agent_id": "counselling-summarizer",
  "patient_id": "PAT-12345",
  "timestamp": "2026-03-26T10:35:00Z",
  "result": {
    "counselling_facts": [
      {
        "fact": "Patient expressed significant fear about chemotherapy side effects",
        "category": "CONCERN",
        "certainty": 0.92,
        "evidence_start_time": 5.8,
        "evidence_end_time": 12.4,
        "evidence_text": "I am very afraid of chemotherapy side effects",
        "speaker": "patient",
        "selectable": true
      }
    ],
    "clinical_facts": [
      {
        "entity": "patient anxiety about chemotherapy side effects",
        "radlex_id": null,
        "entity_type": "PRIMARY",
        "certainty": 0.92,
        "evidence": "Patient: I am very afraid of chemotherapy side effects [5.8s-12.4s]",
        "source_type": "COUNSELLING",
        "source_department": "oncology",
        "timestamp": "2026-03-26T10:33:00Z",
        "negated": false,
        "status": "PRESENT"
      }
    ],
    "session_summary": "Counselling session focused on patient concerns about upcoming chemotherapy. Patient expressed significant anxiety about side effects, particularly hair loss and nausea.",
    "stats": {
      "total_segments_analyzed": 45,
      "clinically_relevant_segments": 12,
      "facts_extracted": 6
    }
  },
  "metadata": {
    "llm_used": "claude-sonnet-4",
    "processing_time_ms": 3800
  },
  "errors": []
}
```

---

## 6. Deployment

### 6.1 Environment Variables

```env
ANTHROPIC_API_KEY=your-claude-api-key
LLM_MODEL=claude-sonnet-4-20250514
MIN_CERTAINTY_THRESHOLD=0.3
DIAGNOSIS_FILTER_ENABLED=true    # Filter out medical diagnoses
LOG_LEVEL=INFO
```

---

## 7. Testing Checklist

- [ ] Transcript with clear patient concern → CONCERN fact extracted with high certainty
- [ ] Doctor recommendation → ACTION fact extracted
- [ ] Shared decision → DECISION fact with both speakers referenced
- [ ] Small talk segments → correctly skipped, not extracted
- [ ] Medical diagnosis mentioned → NOT extracted (not this agent's job)
- [ ] Vague implication → certainty < 0.6
- [ ] Evidence links → timestamps match actual transcript segments
- [ ] All facts default to `selectable: true`
- [ ] Empty transcript → graceful handling, 0 facts
- [ ] CFS output correctly formatted for Fact Graph ingestion

---

## 8. File Structure

```
counselling-summarizer/
├── main.py
├── agents/
│   ├── segment_analyzer.py      # Identify clinically relevant segments
│   ├── fact_extractor.py        # LLM-based fact extraction
│   ├── cfs_emitter.py           # Convert to Clinical Fact Schema
│   └── guardrails.py            # Validation, diagnosis filtering
├── models/
│   ├── counselling_fact.py
│   ├── clinical_fact.py
│   ├── request.py
│   └── response.py
├── prompts/
│   └── counselling_extraction.txt
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_concern_extraction.py
    ├── test_evidence_linking.py
    └── test_guardrails.py
```
