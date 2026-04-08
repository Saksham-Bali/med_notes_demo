# Agent 02: SOAP Extractor

> **Status:** EXISTS — needs upgrades  
> **Deployment:** Standalone microservice  
> **Port:** `5002`  
> **Base URL:** `http://soap-extractor:5002`

---

## 1. What This Agent Does

The SOAP Extractor takes **clean text** (output from OCR Agent or from digital clinical notes) and parses it into the standard **SOAP framework** (Subjective, Objective, Assessment, Plan). It also assigns **certainty scores** to each extracted field and links every claim back to its **source evidence**.

This is the agent that converts messy clinical language into structured, trustworthy data.

---

## 2. Current State (What Already Exists)

You have a strong, production-ready two-stage extraction pipeline:

**Stage 1 — Raw Extraction:** LLM extracts all possible SOAP fields from the text.  
**Stage 2 — Validation & Structuring:** A second LLM pass (or rule engine) validates the extraction, assigns certainty scores, links evidence, and enforces the output schema.

Key strengths already built:
- Explicit `certainty_degree` on every field
- Evidence linking (each claim traces back to source text)
- `"Unknown"` output instead of hallucination when evidence is weak
- Negation handling rules
- Strong schema constraints on output

---

## 3. What Needs to Change

### 3.1 Output Clinical Fact Schema (CFS) Alongside SOAP

**Why:** The Fact Graph doesn't consume SOAP JSON directly. It needs facts in the unified Clinical Fact Schema format. Right now, SOAP output and Fact Graph input are misaligned schemas.

**How:** Add a third stage that converts SOAP fields into CFS objects.

```
Current:   Text → Stage 1 (Extract) → Stage 2 (Validate) → SOAP JSON
                                                              ✕ (not Fact Graph compatible)

Upgraded:  Text → Stage 1 (Extract) → Stage 2 (Validate) → SOAP JSON
                                                              │
                                                              ▼
                                                     Stage 3 (CFS Emit)
                                                              │
                                                              ▼
                                                     clinical_facts[]
                                                              ✓ (Fact Graph compatible)
```

**Implementation of Stage 3:**

```python
def soap_to_clinical_facts(soap: SOAPOutput, metadata: dict) -> list[ClinicalFact]:
    facts = []
    
    # Extract facts from Subjective
    for symptom in soap.subjective.symptoms:
        facts.append(ClinicalFact(
            entity=symptom.name,
            radlex_id=None,  # SOAP items typically don't have RadLex IDs
            entity_type="PRIMARY",
            certainty=symptom.certainty_degree,
            evidence=symptom.source_text,
            source_type="HANDWRITTEN",
            source_department=metadata["department"],
            timestamp=metadata["document_date"],
            negated=symptom.is_negated,
            status=infer_status(symptom),
        ))
    
    # Extract facts from Objective (vitals, exam findings)
    for finding in soap.objective.findings:
        facts.append(ClinicalFact(
            entity=finding.name,
            radlex_id=lookup_radlex(finding.name),  # attempt grounding
            entity_type=classify_entity_type(finding),
            certainty=finding.certainty_degree,
            evidence=finding.source_text,
            source_type="HANDWRITTEN",
            source_department=metadata["department"],
            timestamp=metadata["document_date"],
            negated=finding.is_negated,
            status=infer_status(finding),
        ))
    
    # Similar for Assessment and Plan sections...
    
    return facts
```

### 3.2 Add Entity Type Classification

**Why:** The Fact Graph needs to distinguish PRIMARY findings from INCIDENTAL ones and NEGATED ones. Currently everything from SOAP is treated as equally important.

**How:** Add classification logic in Stage 2 or Stage 3:

```python
def classify_entity_type(finding) -> str:
    if finding.is_negated:
        return "NEGATED"
    if finding.section == "assessment" and finding.is_primary_diagnosis:
        return "PRIMARY"
    if finding.mentioned_in_plan:
        return "PRIMARY"  # if it's in the plan, it's actionable = primary
    if finding.is_anatomical_reference_only:
        return "ANATOMICAL"
    return "INCIDENTAL"
```

### 3.3 Accept Layout Regions from OCR Agent

**Why:** The OCR Agent now outputs layout-aware regions (headings, body, tables). The SOAP Extractor should use this structural information to improve extraction accuracy — e.g., text under a "Chief Complaint" heading maps directly to Subjective.

**How:**

```python
class SOAPExtractRequest(BaseModel):
    text: str                           # full extracted text
    layout_regions: list[LayoutRegion]  # NEW: from OCR Agent
    patient_id: str
    source_confidence: float            # NEW: OCR confidence
    department: str | None = None
    document_date: str | None = None
```

In the extraction prompt, include layout hints:

```
The following text was extracted from a handwritten clinical note.
Layout analysis identified these sections:
- Region 1 (heading): "Chief Complaint"  
- Region 2 (body): "Patient complains of..."
- Region 3 (heading): "Examination"
- Region 4 (body): "BP 140/90, HR 88..."

Use these layout hints to improve your SOAP classification.
If the OCR confidence for a region is below 0.6, mark extracted facts 
from that region with reduced certainty.
```

### 3.4 Add Clinical Intent Awareness

**Why:** This is the "scope control" fix from System A's diagnosis. Not everything in a clinical note is relevant to the primary clinical question. The SOAP Extractor should identify the clinical intent and prioritize accordingly.

**How:** In Stage 1, before extracting SOAP fields, extract:

```python
class ClinicalIntent:
    primary_complaint: str        # "persistent cough for 2 weeks"
    clinical_question: str        # "evaluate for TB vs pneumonia"
    relevant_systems: list[str]   # ["respiratory", "infectious"]
```

Then in Stage 2, use the intent to classify entity types — findings related to the clinical question are PRIMARY, unrelated findings are INCIDENTAL.

---

## 4. API Contract

### 4.1 Endpoint

```
POST /api/v1/extract
Content-Type: application/json
```

### 4.2 Request

```json
{
  "text": "Patient complains of persistent cough for 2 weeks. No fever. BP 140/90...",
  "layout_regions": [
    {"type": "heading", "text": "Chief Complaint", "confidence": 0.95, "order": 1},
    {"type": "body", "text": "Patient complains of...", "confidence": 0.87, "order": 2}
  ],
  "patient_id": "PAT-12345",
  "source_confidence": 0.87,
  "department": "oncology",
  "document_date": "2026-03-25"
}
```

### 4.3 Response

```json
{
  "agent_id": "soap-extractor",
  "patient_id": "PAT-12345",
  "timestamp": "2026-03-26T10:31:00Z",
  "result": {
    "soap": {
      "subjective": {
        "chief_complaint": "Persistent cough for 2 weeks",
        "history": "No associated fever. Non-smoker.",
        "symptoms": [
          {
            "name": "persistent cough",
            "duration": "2 weeks",
            "certainty_degree": 0.95,
            "source_text": "Patient complains of persistent cough for 2 weeks",
            "is_negated": false
          },
          {
            "name": "fever",
            "certainty_degree": 0.90,
            "source_text": "No fever",
            "is_negated": true
          }
        ]
      },
      "objective": {
        "vitals": {"bp": "140/90", "hr": "88"},
        "findings": []
      },
      "assessment": { "diagnoses": [], "differential": [] },
      "plan": { "medications": [], "follow_up": [], "investigations": [] }
    },
    "clinical_intent": {
      "primary_complaint": "persistent cough",
      "clinical_question": "evaluate cause of chronic cough",
      "relevant_systems": ["respiratory"]
    },
    "clinical_facts": [
      {
        "entity": "persistent cough",
        "radlex_id": null,
        "entity_type": "PRIMARY",
        "certainty": 0.95,
        "evidence": "Patient complains of persistent cough for 2 weeks",
        "source_type": "HANDWRITTEN",
        "source_department": "oncology",
        "timestamp": "2026-03-25T00:00:00Z",
        "negated": false,
        "status": "PRESENT"
      },
      {
        "entity": "fever",
        "radlex_id": null,
        "entity_type": "NEGATED",
        "certainty": 0.90,
        "evidence": "No fever",
        "source_type": "HANDWRITTEN",
        "source_department": "oncology",
        "timestamp": "2026-03-25T00:00:00Z",
        "negated": true,
        "status": "ABSENT"
      }
    ]
  },
  "metadata": {
    "llm_used": "claude-sonnet-4",
    "processing_time_ms": 3200,
    "extraction_stages_completed": 3
  },
  "errors": []
}
```

---

## 5. Deployment

### 5.1 Environment Variables

```env
ANTHROPIC_API_KEY=your-claude-api-key
GEMINI_API_KEY=your-gemini-api-key            # if using Gemini as backup LLM
LLM_PROVIDER=anthropic                        # "anthropic" or "google"
LLM_MODEL=claude-sonnet-4-20250514
EXTRACTION_CONFIDENCE_THRESHOLD=0.5
RADLEX_LOOKUP_ENABLED=true
RADLEX_DB_PATH=/data/radlex.db
LOG_LEVEL=INFO
```

### 5.2 Health Check

```
GET /health → { "status": "ok", "llm_provider": "anthropic", "model": "claude-sonnet-4" }
```

---

## 6. How the Orchestrator Calls This Agent

```python
# Called after OCR Agent returns
async def process_soap_extraction(ocr_result, patient_id, department):
    soap_result = await http_client.post(
        "http://soap-extractor:5002/api/v1/extract",
        json={
            "text": ocr_result["result"]["full_text"],
            "layout_regions": ocr_result["result"]["layout_regions"],
            "patient_id": patient_id,
            "source_confidence": ocr_result["result"]["overall_confidence"],
            "department": department,
        }
    )
    
    # clinical_facts are ready to go into Fact Graph
    clinical_facts = soap_result["result"]["clinical_facts"]
    
    # Send to Fact Graph
    await http_client.post(
        "http://fact-graph:5006/api/v1/ingest",
        json={"patient_id": patient_id, "facts": clinical_facts}
    )
```

---

## 7. Testing Checklist

- [ ] Clean English note → correct SOAP classification
- [ ] Note with negations → `is_negated` correctly set, entity_type = "NEGATED"
- [ ] Note with low-confidence OCR regions → certainty scores reduced accordingly
- [ ] Layout regions improve section detection (heading "Exam" → Objective)
- [ ] Clinical intent extracted correctly from chief complaint
- [ ] CFS output (`clinical_facts[]`) matches schema exactly
- [ ] Unknown/uncertain findings → `"Unknown"` not hallucinated
- [ ] Empty/minimal note → graceful handling, no fabricated content
- [ ] LLM timeout → retry with exponential backoff, then error response
- [ ] Response within 8 seconds for typical single-page note

---

## 8. File Structure

```
soap-extractor/
├── main.py                    # FastAPI app, routes
├── agents/
│   ├── stage1_extract.py      # Raw SOAP extraction (LLM call)
│   ├── stage2_validate.py     # Validation, certainty, evidence linking
│   └── stage3_cfs_emit.py     # Convert SOAP → Clinical Fact Schema
├── models/
│   ├── soap.py                # SOAP data models
│   ├── clinical_fact.py       # CFS schema
│   ├── request.py             # Input schemas
│   └── response.py            # Output schemas
├── prompts/
│   ├── extraction.txt         # Stage 1 system prompt
│   ├── validation.txt         # Stage 2 system prompt
│   └── intent.txt             # Clinical intent extraction prompt
├── utils/
│   ├── radlex_lookup.py       # RadLex ontology lookup
│   ├── entity_classifier.py   # PRIMARY/INCIDENTAL/NEGATED classification
│   └── evidence_linker.py     # Link claims to source text
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_extraction.py
    ├── test_cfs_conversion.py
    └── test_negation.py
```
