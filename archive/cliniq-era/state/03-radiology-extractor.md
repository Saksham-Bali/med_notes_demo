# Agent 03: Radiology Extractor

> **Status:** EXISTS — needs major refactor  
> **Deployment:** Standalone microservice  
> **Port:** `5003`  
> **Base URL:** `http://radiology-extractor:5003`

---

## 1. What This Agent Does

The Radiology Extractor processes **radiology reports** (CT, MRI, X-ray, PET-CT) and extracts structured clinical findings grounded to the **RadLex ontology**. It replaces the old `FindingExtractor` with System B's disciplined two-stage approach.

This is the agent that must solve the **precision collapse problem** — extracting only what matters for longitudinal disease tracking, not everything that might exist in the report.

---

## 2. Current State (What Already Exists)

You have a FindingExtractor that:
- Extracts findings from radiology reports using an LLM
- Grounds entities to RadLex IDs (post-fix)
- Feeds into the Fact Graph

**Known problems:**
- 81 predictions vs 41 gold = precision collapse (FP explosion)
- CT abdomen scans extract ~20 false positives (incidentals)
- No distinction between PRIMARY / INCIDENTAL / NEGATED findings
- No clinical scope control (extracts everything regardless of study purpose)
- Deduplication uses string similarity instead of ontology identity
- Generic entity collapse (e.g., "granulomatous calcifications" → "calcifications")

---

## 3. What Needs to Change (This Is a Refactor, Not a Patch)

### 3.1 Replace the Extraction Logic with System B's Two-Stage Discipline

**Current (broken):**
```
Report Text → LLM ("extract everything") → Flat list of findings
```

**New (constrained):**
```
Report Text
    │
    ▼
┌──────────────────────────┐
│ Stage 0: Clinical Intent  │  ◄── NEW: "What is this report answering?"
│ Extract study purpose,    │
│ indication, relevant      │
│ anatomy                   │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ Stage 1: Scoped Extract   │  ◄── Constrained by clinical intent
│ Only extract findings     │      Focus on Impression + Indication
│ relevant to the clinical  │      sections
│ question                  │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ Stage 2: Validate +       │  ◄── System B discipline
│ Classify + Ground         │      Certainty scores
│ - Certainty scoring       │      Evidence linking
│ - Entity type tagging     │      RadLex grounding
│ - RadLex grounding        │      No hallucination
│ - Evidence linking        │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ Stage 3: CFS Emit         │  ◄── Clinical Fact Schema output
│ Convert to unified format │
│ for Fact Graph ingestion  │
└──────────────────────────┘
```

### 3.2 Implement Clinical Intent Extractor (Stage 0)

This is the **biggest single fix** for precision. Before extracting anything, determine:

```python
class RadiologyIntent:
    study_type: str          # "CT abdomen with contrast"
    clinical_indication: str # "evaluate for bowel obstruction"
    relevant_anatomy: list   # ["bowel", "intestine", "colon"]
    clinical_question: str   # "is there bowel obstruction?"
```

**Prompt for Stage 0:**

```text
You are a clinical intent analyzer for radiology reports.

Given the following radiology report, extract:
1. study_type: What imaging modality and body region (e.g., "CT abdomen with contrast")
2. clinical_indication: Why was this study ordered? (from the "Clinical History" or "Indication" section)
3. relevant_anatomy: Which anatomical structures are relevant to the clinical question?
4. clinical_question: What specific question is this report trying to answer?

IMPORTANT: If the report does not have a clear indication section, infer from context.

Report:
{report_text}
```

### 3.3 Scope the Extraction (Stage 1)

**Prompt for Stage 1 (the key change):**

```text
You are a radiology findings extractor. 

CLINICAL CONTEXT:
- Study: {study_type}
- Indication: {clinical_indication}  
- Clinical question: {clinical_question}
- Relevant anatomy: {relevant_anatomy}

EXTRACTION RULES:
1. Extract ONLY findings that are relevant to the clinical indication and question.
2. Focus primarily on the IMPRESSION and FINDINGS sections.
3. Do NOT extract incidental findings unless they are clinically significant (e.g., new malignancy).
4. For each finding, note:
   - The finding itself
   - Whether it is negated ("no evidence of...")
   - Size/measurement if present
   - Comparison to prior studies if mentioned
   - Your confidence in the extraction (0.0 to 1.0)
5. If you are unsure about a finding, output "Unknown" — do not guess.
6. NEVER reduce semantic specificity. "Granulomatous calcifications" stays as 
   "granulomatous calcifications", not "calcifications".

Report:
{report_text}
```

### 3.4 Add Entity Type Classification (Stage 2)

```python
def classify_radiology_entity(finding, intent) -> str:
    # Negated findings
    if finding.is_negated:
        return "NEGATED"
    
    # Check relevance to clinical question
    if is_relevant_to_intent(finding, intent):
        return "PRIMARY"
    
    # Check if it's a new significant finding even if not related to indication
    if finding.is_new and finding.severity in ["moderate", "severe"]:
        return "PRIMARY"  # New significant findings always matter
    
    # Pure anatomical reference
    if finding.is_anatomical_landmark:
        return "ANATOMICAL"
    
    return "INCIDENTAL"
```

### 3.5 Fix RadLex Grounding (Stage 2)

**Current bug:** Grounding happens as a post-fix and doesn't inform deduplication.

**Fix:** Ground during extraction, and use RadLex IDs as the primary identity for merging.

```python
async def ground_to_radlex(finding_text: str) -> RadLexGrounding:
    # Step 1: Direct lookup
    exact_match = radlex_db.lookup(finding_text)
    if exact_match:
        return RadLexGrounding(id=exact_match.id, label=exact_match.label, method="exact")
    
    # Step 2: Semantic similarity (using embeddings)
    similar = radlex_db.semantic_search(finding_text, top_k=3)
    if similar[0].score > 0.85:
        return RadLexGrounding(id=similar[0].id, label=similar[0].label, method="semantic")
    
    # Step 3: Ontology parent matching
    parent = radlex_db.find_parent_concept(finding_text)
    if parent:
        return RadLexGrounding(id=parent.id, label=parent.label, method="parent")
    
    return RadLexGrounding(id=None, label=None, method="ungrounded")
```

### 3.6 Preserve Semantic Specificity

**Rule:** Never reduce resolution below what the report states.

```python
# BAD: over-normalization
"granulomatous calcifications" → "calcifications"  # WRONG
"right lower lobe pulmonary nodule" → "nodule"     # WRONG

# GOOD: preserve specificity, ground to most specific RadLex concept
"granulomatous calcifications" → RadLex: "granulomatous calcification" (RID12345)
"right lower lobe pulmonary nodule" → RadLex: "pulmonary nodule" (RID5678) + location: "right lower lobe"
```

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
  "report_text": "CT Abdomen with Contrast\n\nIndication: Evaluate for bowel obstruction...\n\nFindings: ...\n\nImpression: ...",
  "patient_id": "PAT-12345",
  "report_date": "2026-03-25",
  "modality": "CT",
  "body_region": "abdomen"
}
```

### 4.3 Response

```json
{
  "agent_id": "radiology-extractor",
  "patient_id": "PAT-12345",
  "timestamp": "2026-03-26T10:32:00Z",
  "result": {
    "clinical_intent": {
      "study_type": "CT abdomen with contrast",
      "clinical_indication": "evaluate for bowel obstruction",
      "clinical_question": "Is there evidence of bowel obstruction?",
      "relevant_anatomy": ["bowel", "small intestine", "colon", "mesentery"]
    },
    "findings": [
      {
        "text": "dilated loops of small bowel up to 4.2 cm",
        "entity_type": "PRIMARY",
        "radlex_id": "RID34567",
        "radlex_label": "small bowel dilatation",
        "grounding_method": "semantic",
        "measurement": {"value": 4.2, "unit": "cm"},
        "certainty": 0.94,
        "negated": false,
        "comparison_to_prior": null,
        "evidence": "Dilated loops of small bowel measuring up to 4.2 cm in the pelvis",
        "status": "PRESENT"
      }
    ],
    "clinical_facts": [
      {
        "entity": "small bowel dilatation",
        "radlex_id": "RID34567",
        "entity_type": "PRIMARY",
        "certainty": 0.94,
        "evidence": "Dilated loops of small bowel measuring up to 4.2 cm in the pelvis",
        "source_type": "RADIOLOGY",
        "source_department": "radiology",
        "timestamp": "2026-03-25T00:00:00Z",
        "negated": false,
        "status": "PRESENT"
      }
    ]
  },
  "metadata": {
    "llm_used": "claude-sonnet-4",
    "findings_extracted": 5,
    "findings_filtered_as_incidental": 12,
    "processing_time_ms": 4100
  },
  "errors": []
}
```

**Note the key metric:** `findings_filtered_as_incidental: 12` — this is the precision fix in action. Before, those 12 would have been false positives.

---

## 5. Deployment

### 5.1 Environment Variables

```env
ANTHROPIC_API_KEY=your-claude-api-key
LLM_MODEL=claude-sonnet-4-20250514
RADLEX_DB_PATH=/data/radlex.db
RADLEX_EMBEDDING_MODEL=text-embedding-3-small
EXTRACTION_FOCUS=impression_and_indication
INCIDENTAL_FILTER_ENABLED=true
SPECIFICITY_PRESERVATION=true
LOG_LEVEL=INFO
```

---

## 6. Testing Checklist

- [ ] CT abdomen for bowel obstruction → only bowel-related findings extracted (not gallstones, pancreas)
- [ ] MRI brain → incidental findings filtered out unless clinically significant
- [ ] Negated findings → correctly tagged as NEGATED entity type
- [ ] RadLex grounding → correct IDs assigned, no over-normalization
- [ ] "Granulomatous calcifications" → stays specific, not collapsed to "calcifications"
- [ ] Comparison to prior → `comparison_to_prior` field populated when report mentions prior study
- [ ] RECIST-relevant measurements → extracted with correct units
- [ ] findings_filtered_as_incidental count → visible in metadata for quality monitoring
- [ ] F1 score improvement: target 0.55-0.60 (from 0.47)
- [ ] Grounding accuracy improvement: target 0.40+ (from 0.25)

---

## 7. File Structure

```
radiology-extractor/
├── main.py
├── agents/
│   ├── stage0_intent.py         # Clinical intent extraction
│   ├── stage1_scoped_extract.py # Scoped finding extraction
│   ├── stage2_validate.py       # Validate, classify, ground
│   └── stage3_cfs_emit.py       # CFS conversion
├── models/
│   ├── finding.py               # RadiologyFinding schema
│   ├── intent.py                # ClinicalIntent schema
│   ├── clinical_fact.py         # CFS schema
│   └── response.py
├── prompts/
│   ├── intent_extraction.txt
│   ├── scoped_extraction.txt
│   └── validation.txt
├── grounding/
│   ├── radlex_lookup.py         # Direct + semantic + parent lookup
│   ├── radlex_db.py             # RadLex database interface
│   └── specificity_guard.py     # Prevent over-normalization
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_intent.py
    ├── test_extraction_precision.py
    ├── test_radlex_grounding.py
    └── test_specificity.py
```
