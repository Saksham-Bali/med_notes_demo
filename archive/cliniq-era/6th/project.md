# Agent 09: QA Validation Agent

> **Status:** NEW — build from scratch  
> **Deployment:** Standalone microservice  
> **Port:** `5009`  
> **Base URL:** `http://qa-agent:5009`

---

## 1. What This Agent Does

The QA Agent is the **gatekeeper** before any discharge summary is released. It validates clinical accuracy, checks for missing fields, flags inconsistencies, verifies that every claim traces back to evidence, and produces an audit trail for regulatory compliance.

It either **PASSES** the summary (→ goes to Translation Layer) or **FAILS** it (→ returns to clinician with specific issues).

---

## 2. Validation Checks

### 2.1 Completeness Check
```python
REQUIRED_SECTIONS = [
    "patient_demographics",
    "admission_diagnosis",
    "chief_complaint",
    "investigations",
    "treatment_given",
    "medications_on_discharge",
    "condition_at_discharge",
    "follow_up_schedule",
    "brief_summary",
]

def check_completeness(summary: DischargeSummary) -> list[Issue]:
    issues = []
    for section in REQUIRED_SECTIONS:
        value = getattr(summary, section, None)
        if not value or value == "Not available":
            issues.append(Issue(
                type="MISSING_FIELD",
                severity="critical" if section in ["medications_on_discharge", "follow_up_schedule"] else "moderate",
                section=section,
                message=f"Required section '{section}' is missing or empty",
            ))
    return issues
```

### 2.2 Consistency Check
```python
async def check_consistency(summary: DischargeSummary, patient_state: PatientState) -> list[Issue]:
    issues = []
    
    # Check: Diagnosis in summary matches Fact Graph
    summary_diagnoses = extract_diagnoses(summary)
    graph_diagnoses = [e for e in patient_state.entities if e.entity_type == "PRIMARY"]
    for diag in summary_diagnoses:
        if not any(matches(diag, gd) for gd in graph_diagnoses):
            issues.append(Issue(
                type="INCONSISTENCY",
                severity="critical",
                message=f"Diagnosis '{diag}' in summary not found in Fact Graph",
            ))
    
    # Check: Medications listed are consistent
    # Check: Dates are logical (discharge after admission)
    # Check: RECIST response matches measurement data
    ...
    
    return issues
```

### 2.3 Confidence Threshold Check
```python
def check_confidence(summary: DischargeSummary, facts: list[ClinicalFact]) -> list[Issue]:
    MIN_CONFIDENCE = 0.6
    issues = []
    for fact in facts:
        if fact.certainty < MIN_CONFIDENCE:
            issues.append(Issue(
                type="LOW_CONFIDENCE",
                severity="moderate",
                message=f"Fact '{fact.entity}' has certainty {fact.certainty:.2f} (below threshold {MIN_CONFIDENCE})",
                evidence=fact.evidence,
            ))
    return issues
```

### 2.4 Evidence Traceability
```python
def check_traceability(summary: DischargeSummary, patient_state: PatientState) -> list[Issue]:
    """Every claim in the summary must trace back to a source fact."""
    # Uses Claude Sonnet 4 to verify each summary statement has a backing fact
    ...
```

### 2.5 NABH Compliance
```python
def check_nabh_compliance(summary: DischargeSummary) -> list[Issue]:
    """Check against NABH mandatory elements for discharge summaries."""
    ...
```

---

## 3. API Contract

### 3.1 Validate

```
POST /api/v1/validate
```

```json
{
  "patient_id": "PAT-12345",
  "discharge_summary": { ... },
  "source_facts": [ ... ]
}
```

### 3.2 Response

```json
{
  "agent_id": "qa-agent",
  "result": {
    "verdict": "FAIL",
    "issues": [
      {
        "type": "MISSING_FIELD",
        "severity": "critical",
        "section": "medications_on_discharge",
        "message": "Required section 'medications_on_discharge' is empty"
      },
      {
        "type": "LOW_CONFIDENCE",
        "severity": "moderate",
        "message": "Fact 'hepatic lesion' has certainty 0.45 (below threshold 0.6)"
      }
    ],
    "stats": {
      "total_checks_run": 28,
      "passed": 26,
      "failed": 2,
      "critical_failures": 1
    },
    "audit_trail": {
      "validation_id": "VAL-20260326-001",
      "timestamp": "2026-03-26T10:40:00Z",
      "checks_performed": ["completeness", "consistency", "confidence", "traceability", "nabh"],
      "summary_hash": "sha256:abc123..."
    }
  }
}
```

---

## 4. File Structure

```
qa-agent/
├── main.py
├── checks/
│   ├── completeness.py
│   ├── consistency.py
│   ├── confidence.py
│   ├── traceability.py
│   └── nabh_compliance.py
├── models/
│   ├── issue.py
│   ├── audit_trail.py
│   └── response.py
├── config.py
├── Dockerfile
├── requirements.txt
└── tests/
    ├── test_completeness.py
    ├── test_consistency.py
    └── test_confidence.py
```
