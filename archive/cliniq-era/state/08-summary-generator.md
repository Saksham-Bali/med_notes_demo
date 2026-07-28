# Agent 08: Summary Generator

> **Status:** NEW — build from scratch  
> **Deployment:** Standalone microservice  
> **Port:** `5008`  
> **Base URL:** `http://summary-generator:5008`

---

## 1. What This Agent Does

The Summary Generator composes the **final discharge summary** by reading the patient's full Fact Graph state, approved counselling facts, and RECIST tracking data. It produces a NABH-compliant structured document in English (the canonical version). Translation happens downstream.

---

## 2. Architecture

```
┌──────────────┐  ┌───────────────────┐  ┌──────────────┐
│  Fact Graph   │  │ Approved           │  │ RECIST       │
│  Patient State│  │ Counselling Facts  │  │ Tracker Data │
└──────┬───────┘  └────────┬──────────┘  └──────┬───────┘
       │                   │                     │
       └───────────┬───────┘─────────────────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │ Context Assembly     │  ◄── Combine all sources into
        │ - Patient demographics│      structured context object
        │ - Entity trajectories │
        │ - Counselling facts   │
        │ - RECIST measurements │
        └──────────┬──────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │ Summary Composition  │  ◄── Claude Sonnet 4
        │ - NABH template       │      Follows strict template
        │ - Section by section  │      Evidence-grounded
        └──────────┬──────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │ Output Formatting    │  ◄── Structured JSON + prose
        │ - Structured JSON     │
        │ - Prose narrative     │
        │ - Section metadata    │
        └─────────────────────┘
```

---

## 3. NABH Discharge Summary Template

The generator follows this standard structure:

```python
class DischargeSummary:
    # Section 1: Patient Demographics
    patient_name: str
    patient_id: str
    age: int
    gender: str
    admission_date: str
    discharge_date: str
    department: str
    attending_physician: str
    
    # Section 2: Admission Details
    admission_diagnosis: str
    chief_complaint: str
    history_of_present_illness: str
    
    # Section 3: Clinical History
    past_medical_history: str
    family_history: str
    social_history: str
    allergies: list[str]
    
    # Section 4: Investigations
    laboratory_results: list[LabResult]
    imaging_findings: list[ImagingFinding]  # from Fact Graph radiology entities
    pathology_results: list[PathResult]
    
    # Section 5: Treatment Given
    medications_during_stay: list[Medication]
    procedures_performed: list[Procedure]
    chemotherapy_details: ChemoDetails | None  # TMC-specific
    radiation_details: RadiationDetails | None  # TMC-specific
    
    # Section 6: Disease Progression (from RECIST)
    tumor_response: str           # e.g., "partial response per RECIST 1.1"
    measurement_trends: list[dict] # longitudinal measurements
    
    # Section 7: Counselling Summary (from approved facts only)
    counselling_notes: str
    patient_concerns_addressed: list[str]
    
    # Section 8: Condition at Discharge
    condition_at_discharge: str
    functional_status: str
    
    # Section 9: Discharge Instructions
    medications_on_discharge: list[Medication]
    follow_up_schedule: list[FollowUp]
    dietary_instructions: str
    activity_restrictions: str
    warning_signs: list[str]
    
    # Section 10: Summary Narrative
    brief_summary: str  # 3-4 sentence overview
```

---

## 4. Implementation

### 4.1 Context Assembly

```python
async def assemble_context(patient_id: str, approved_counselling_ids: list[str]) -> SummaryContext:
    # Get full patient state from Fact Graph
    patient_state = await http_client.get(
        f"http://fact-graph:5006/api/v1/patient/{patient_id}/state"
    )
    
    # Get RECIST data
    recist_data = await http_client.get(
        f"http://fact-graph:5006/api/v1/patient/{patient_id}/measurements"
    )
    
    # Get approved counselling facts
    counselling_facts = await http_client.post(
        f"http://fact-graph:5006/api/v1/patient/{patient_id}/facts",
        json={"source_type": "COUNSELLING", "ids": approved_counselling_ids}
    )
    
    return SummaryContext(
        patient_state=patient_state,
        recist_data=recist_data,
        counselling_facts=counselling_facts,
    )
```

### 4.2 Summary Composition Prompt

```text
You are a clinical discharge summary generator for Tata Memorial Centre (TMC).

PATIENT STATE:
{patient_state_json}

RECIST MEASUREMENTS:
{recist_data_json}

APPROVED COUNSELLING NOTES:
{counselling_facts_json}

Generate a complete discharge summary following NABH standards.

RULES:
1. Every clinical claim in the summary MUST be traceable to a fact in the patient state.
2. Do NOT add information that is not present in the provided data.
3. If a section has no data, write "Not available" — do not fabricate.
4. Use medical terminology appropriate for a clinical document.
5. The "Brief Summary" section should be 3-4 sentences that a referring physician 
   can read to quickly understand the patient's course.
6. For RECIST response, state the criteria used and the response category.
7. Include counselling notes ONLY from the approved facts provided.
8. List all medications with dosage, frequency, and duration.
9. Follow-up dates must be specific (not "in 2 weeks" but the actual date).

OUTPUT: Structured JSON matching the DischargeSummary schema.
```

---

## 5. API Contract

### 5.1 Generate Summary

```
POST /api/v1/generate
```

```json
{
  "patient_id": "PAT-12345",
  "admission_date": "2026-03-01",
  "discharge_date": "2026-03-25",
  "attending_physician": "Dr. Seema Gulia",
  "department": "Medical Oncology",
  "approved_counselling_fact_ids": ["cf-001", "cf-003", "cf-005"],
  "include_recist": true,
  "template": "nabh_standard"
}
```

### 5.2 Response

```json
{
  "agent_id": "summary-generator",
  "patient_id": "PAT-12345",
  "result": {
    "discharge_summary": { ... },
    "prose_version": "Mrs. X, 54F, was admitted on 2026-03-01 for...",
    "section_metadata": [
      {"section": "investigations", "fact_count": 8, "avg_certainty": 0.91},
      {"section": "treatment", "fact_count": 5, "avg_certainty": 0.95}
    ],
    "completeness_score": 0.88,
    "missing_sections": ["family_history"]
  },
  "errors": []
}
```

---

## 6. File Structure

```
summary-generator/
├── main.py
├── agents/
│   ├── context_assembler.py     # Gather data from Fact Graph + RECIST
│   ├── summary_composer.py      # LLM-based summary generation
│   └── output_formatter.py      # JSON + prose formatting
├── templates/
│   ├── nabh_standard.py         # NABH discharge summary template
│   └── tmc_oncology.py          # TMC-specific oncology template
├── models/
│   ├── discharge_summary.py
│   ├── request.py
│   └── response.py
├── prompts/
│   └── summary_generation.txt
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_context_assembly.py
    ├── test_completeness.py
    └── test_nabh_compliance.py
```
