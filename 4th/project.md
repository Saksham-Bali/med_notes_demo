# Agent 07: Department Merger

> **Status:** NEW — build from scratch  
> **Deployment:** Standalone microservice  
> **Port:** `5007`  
> **Base URL:** `http://department-merger:5007`

---

## 1. What This Agent Does

The Department Merger consolidates clinical notes from **multiple departments** (oncology, radiology, pathology, palliative care, surgery, etc.) into a **unified clinical timeline**. It aligns entities across departments, deduplicates findings, detects conflicts, and tags every piece of data with its department of origin.

This is the most **reasoning-heavy** new agent — it uses Claude Sonnet 4's strong reasoning for conflict resolution.

---

## 2. Why This Exists

At TMC, a single patient is seen by multiple departments simultaneously. Dr. Arvind Guru explained that the EMR integrates notes from consultants, treating doctors, investigation reports, and palliative care. Without a merger agent, the Fact Graph would have duplicate and potentially contradictory entries from different departments.

---

## 3. Architecture

```
Department Notes (multiple)
 ┌─────────┬──────────┬──────────┬──────────┐
 │ Oncology│ Pathology│ Palliative│ Surgery  │
 └────┬────┴────┬─────┴────┬─────┴────┬─────┘
      │         │          │          │
      ▼         ▼          ▼          ▼
┌────────────────────────────────────────────┐
│ Step 1: Parallel Structured Extraction      │  ◄── Each dept processed via
│ (calls SOAP Extractor for each dept's notes)│      SOAP Extractor (Agent 02)
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│ Step 2: Cross-Department Entity Alignment   │  ◄── RadLex-based matching
│ - Match entities across departments          │      Ontology parent merge
│ - Deduplicate while preserving provenance    │      Temporal alignment
└─────────────────────┬──────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────┐
│ Step 3: Conflict Detection                  │  ◄── Claude Sonnet 4
│ - Contradictory medications                  │      NEVER auto-resolve
│ - Inconsistent staging                       │      Flag for clinician
│ - Date mismatches                            │
└─────────────────────┬──────────────────────┘
                      │
              ┌───────┴───────┐
              │               │
              ▼               ▼
        No Conflicts     Conflicts Found
              │               │
              ▼               ▼
     Unified Timeline    Flagged for
     → Fact Graph        Clinician Review
```

---

## 4. Implementation Details

### 4.1 Step 1: Parallel Extraction

The merger doesn't do its own extraction — it delegates to the SOAP Extractor:

```python
async def extract_all_departments(department_notes: list[DepartmentNote]) -> list[DeptExtraction]:
    tasks = []
    for note in department_notes:
        task = http_client.post(
            "http://soap-extractor:5002/api/v1/extract",
            json={
                "text": note.text,
                "patient_id": note.patient_id,
                "department": note.department,
                "document_date": note.date,
            }
        )
        tasks.append(task)
    
    # Run all extractions in parallel
    results = await asyncio.gather(*tasks)
    return [DeptExtraction(dept=note.department, facts=r["result"]["clinical_facts"]) 
            for note, r in zip(department_notes, results)]
```

### 4.2 Step 2: Entity Alignment

```python
def align_entities(dept_extractions: list[DeptExtraction]) -> list[AlignedEntity]:
    """Align entities across departments using RadLex ontology."""
    all_facts = []
    for extraction in dept_extractions:
        for fact in extraction.facts:
            fact.source_department = extraction.dept
            all_facts.append(fact)
    
    # Group by RadLex ID (primary identity)
    aligned = {}
    for fact in all_facts:
        merged = False
        for key, group in aligned.items():
            if should_merge_radlex(fact, group[0]):
                group.append(fact)
                merged = True
                break
        if not merged:
            aligned[fact.entity + "_" + (fact.radlex_id or "ungrounded")] = [fact]
    
    # Convert to aligned entities with provenance
    result = []
    for key, facts in aligned.items():
        result.append(AlignedEntity(
            canonical_name=facts[0].entity,
            radlex_id=facts[0].radlex_id,
            facts=facts,
            departments=[f.source_department for f in facts],
            has_conflict=detect_conflict(facts),
        ))
    
    return result
```

### 4.3 Step 3: Conflict Detection

```python
class Conflict:
    entity: str                    # Which entity has conflicting info
    conflict_type: str             # "medication" | "staging" | "date" | "status" | "other"
    department_a: str              # First department's version
    department_b: str              # Second department's version
    fact_a: ClinicalFact           # First department's fact
    fact_b: ClinicalFact           # Second department's fact
    severity: str                  # "critical" | "moderate" | "minor"
    suggested_resolution: str      # LLM suggestion (NOT auto-applied)

def detect_conflict(facts: list[ClinicalFact]) -> list[Conflict]:
    conflicts = []
    for i, fact_a in enumerate(facts):
        for fact_b in facts[i+1:]:
            if fact_a.source_department == fact_b.source_department:
                continue  # Same department, not a cross-dept conflict
            
            # Check for status contradiction
            if fact_a.status != fact_b.status:
                conflicts.append(Conflict(
                    entity=fact_a.entity,
                    conflict_type="status",
                    department_a=fact_a.source_department,
                    department_b=fact_b.source_department,
                    fact_a=fact_a,
                    fact_b=fact_b,
                    severity=assess_severity(fact_a, fact_b),
                ))
            
            # Check for negation contradiction
            if fact_a.negated != fact_b.negated:
                conflicts.append(Conflict(
                    entity=fact_a.entity,
                    conflict_type="status",
                    ...
                ))
    
    return conflicts
```

### 4.4 Conflict Resolution (LLM-Assisted, Human-Decided)

```text
PROMPT for conflict analysis (Claude Sonnet 4):

You are analyzing a clinical data conflict between two departments.

CONFLICT:
- Entity: {entity}
- Department A ({dept_a}): {fact_a.evidence}
- Department B ({dept_b}): {fact_b.evidence}

Analyze this conflict and provide:
1. What is the nature of the disagreement?
2. Which department is more likely to be authoritative for this type of finding?
3. A suggested resolution (BUT note: this will NOT be auto-applied — a clinician will decide)

IMPORTANT: You are providing analysis, not making a clinical decision. 
The clinician will make the final call.
```

---

## 5. API Contract

### 5.1 Merge Departments

```
POST /api/v1/merge
Content-Type: application/json
```

```json
{
  "patient_id": "PAT-12345",
  "department_notes": [
    {
      "department": "oncology",
      "text": "Patient started on second-line chemotherapy...",
      "date": "2026-03-24",
      "author": "Dr. Smith"
    },
    {
      "department": "palliative_care",
      "text": "Patient reports severe nausea, pain score 7/10...",
      "date": "2026-03-25",
      "author": "Dr. Pangaria"
    }
  ]
}
```

### 5.2 Response

```json
{
  "agent_id": "department-merger",
  "patient_id": "PAT-12345",
  "timestamp": "2026-03-26T10:36:00Z",
  "result": {
    "unified_facts": [ ... ],
    "conflicts": [
      {
        "entity": "pain management plan",
        "conflict_type": "medication",
        "department_a": "oncology",
        "department_b": "palliative_care",
        "description": "Oncology recommends continuing current analgesics; Palliative care recommends dose escalation",
        "severity": "moderate",
        "suggested_resolution": "Palliative care is typically authoritative for pain management. Recommend reviewing with both teams.",
        "requires_clinician_review": true
      }
    ],
    "stats": {
      "departments_processed": 2,
      "total_facts_extracted": 18,
      "facts_merged": 4,
      "conflicts_detected": 1
    }
  },
  "errors": []
}
```

---

## 6. Deployment

```env
ANTHROPIC_API_KEY=your-claude-api-key
LLM_MODEL=claude-sonnet-4-20250514
SOAP_EXTRACTOR_URL=http://soap-extractor:5002
FACT_GRAPH_URL=http://fact-graph:5006
CONFLICT_AUTO_RESOLVE=false          # NEVER set to true
RADLEX_DB_PATH=/data/radlex.db
LOG_LEVEL=INFO
```

---

## 7. File Structure

```
department-merger/
├── main.py
├── agents/
│   ├── parallel_extractor.py    # Calls SOAP Extractor for each dept
│   ├── entity_aligner.py        # Cross-dept RadLex-based alignment
│   ├── conflict_detector.py     # Identify contradictions
│   └── conflict_analyzer.py     # LLM-assisted analysis (not resolution)
├── models/
│   ├── department_note.py
│   ├── aligned_entity.py
│   ├── conflict.py
│   └── response.py
├── prompts/
│   └── conflict_analysis.txt
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_alignment.py
    ├── test_conflict_detection.py
    └── test_parallel_extraction.py
```
