"""SOAP extraction logic using OpenRouter / OpenAI-compatible API."""
import json
import os
import re
import time
import uuid
from datetime import date
from openai import OpenAI

from app.config import (
    OPENROUTER_API_KEY,
    OPENAI_BASE_URL,
    LLM_MODEL,
)

SOAP_FROM_TEXT_ENHANCED_PROMPT = """### SYSTEM ROLE
You are an expert Clinical Data Structuring Specialist. Your task is to parse raw, noisy OCR text from a general doctor's note and extract structured data into a precise JSON format.

### CRITICAL RULE: MISSING NO DATA
You must capture ALL clinical information. Do not summarize or omit details. Every symptom, every medication, every vital sign must be extracted individually. Err on the side of over-extraction.

### INSTRUCTIONS
Based on the clinical text provided in the "INPUT" section, extract the value, evidence, and certainty degree (CD: 0.00 to 1.00) for the attributes listed in the Schema below.

**1. OCR Correction & Inference:** The input is raw OCR text and may contain typos (e.g., "10mg" read as "l0mg"). You must infer the correct medical terms based on context. If a term is ambiguous, lower the Certainty Degree (CD).

**2. SOAP Structure:**
Extract the following fields. If a field is not mentioned, return "Unknown" or null.

**3. Output Requirements (Spiral Logic):**
For diagnosis and medications, you must provide:
- `value`: The cleaned, standardized value
- `certainty_degree`: A float between 0.00 and 1.00 indicating certainty
- `evidence_text`: The exact substring from the OCR text used as basis

**4. Handling Negation & Nuance:**
- Ensure valid inference. Do not extract "Diabetes" as a diagnosis if the text says "No history of Diabetes."
- If evidence is not explicitly present, return value as "Unknown".

---

### COMPLETENESS CALIBRATION: FEW-SHOT EXAMPLES

**EXAMPLE 1: Full Extraction**
*Input:* "Date: 12/5/24. Pt c/o headache x 3 days, nausea, photophobia. PMHx: HTN. Exam: BP 140/90, HR 88. Neuro exam: no focal deficits. Dx: Migraine. Rx: Sumatriptan 50mg PO PRN, Ibuprofen 400mg q6h x5d. F/u 1 week."
*Extraction:*
{
  "soap_note": {
    "subjective": {
      "chief_complaint": "Headache for 3 days",
      "hpi": "Patient complains of headache for 3 days, associated with nausea and photophobia.",
      "symptoms": ["Headache", "Nausea", "Photophobia"],
      "patient_history": "Hypertension (HTN)"
    },
    "objective": {
      "vitals": {
        "bp": "140/90",
        "hr": "88",
        "temp": null,
        "rr": null,
        "weight": null
      },
      "physical_exam": {
        "findings": ["Neurological exam: no focal deficits"],
        "text_raw": "Neuro exam: no focal deficits"
      },
      "labs_imaging": "Pending"
    },
    "assessment": {
      "primary_diagnosis": {
        "value": "Migraine",
        "certainty_degree": 0.95,
        "evidence_text": "Dx: Migraine"
      },
      "differential_diagnosis": []
    },
    "plan": {
      "medications": [
        {
          "drug": "Sumatriptan",
          "dosage": "50mg",
          "sig": "PO PRN",
          "handwriting_confidence": 0.95
        },
        {
          "drug": "Ibuprofen",
          "dosage": "400mg",
          "sig": "q6h for 5 days",
          "handwriting_confidence": 0.95
        }
      ],
      "procedures_ordered": [],
      "patient_instructions": "Follow-up in 1 week"
    }
  },
  "metadata": {
    "ocr_quality_check": "Clear and legible",
    "critical_ambiguities": []
  }
}

---

**EXAMPLE 2: Handling OCR Noise & Multiple Symptoms**
*Input:* "45 y/o M, DM type 2. C/O: polyuria, polydipsia, fatigue, weight loss 10 lbs/3 mo. Vitals: BP l30/85, HR 78, T 98.6F, Wt l75 lbs. Labs: FBS 250 mg/dL, HbAlc 9.2%. A: Uncontrolled DM. P: Metformin 500mg BID, Glipizide 5mg QD. Diet counseling. Recheck HbAlc in 3 mo."
*Reasoning:* "l30/85" is OCR noise for "130/85". "l75 lbs" is "175 lbs". "HbAlc" is "HbA1c".
*Extraction:*
{
  "soap_note": {
    "subjective": {
      "chief_complaint": "Polyuria, polydipsia, fatigue, weight loss",
      "hpi": "45-year-old male with Type 2 Diabetes Mellitus presenting with polyuria, polydipsia, fatigue, and 10 lbs weight loss over 3 months.",
      "symptoms": ["Polyuria", "Polydipsia", "Fatigue", "Weight loss (10 lbs in 3 months)"],
      "patient_history": "Diabetes Mellitus Type 2"
    },
    "objective": {
      "vitals": {
        "bp": "130/85",
        "hr": "78",
        "temp": "98.6F",
        "rr": null,
        "weight": "175 lbs"
      },
      "physical_exam": {
        "findings": [],
        "text_raw": "Unknown"
      },
      "labs_imaging": "FBS 250 mg/dL, HbA1c 9.2%"
    },
    "assessment": {
      "primary_diagnosis": {
        "value": "Uncontrolled Diabetes Mellitus",
        "certainty_degree": 0.98,
        "evidence_text": "A: Uncontrolled DM"
      },
      "differential_diagnosis": []
    },
    "plan": {
      "medications": [
        {
          "drug": "Metformin",
          "dosage": "500mg",
          "sig": "BID",
          "handwriting_confidence": 0.95
        },
        {
          "drug": "Glipizide",
          "dosage": "5mg",
          "sig": "QD (once daily)",
          "handwriting_confidence": 0.95
        }
      ],
      "procedures_ordered": ["Diet counseling", "Recheck HbA1c in 3 months"],
      "patient_instructions": "Diet counseling. Return for HbA1c recheck in 3 months."
    }
  },
  "metadata": {
    "ocr_quality_check": "Minor OCR noise in vitals (numbers), corrected based on context.",
    "critical_ambiguities": []
  }
}

---

**EXAMPLE 3: Low Confidence Due to Illegibility**
*Input:* "Pt w/ c[illegible]gh x 5d. [illegible] BP 120/80. Dx: ?URI. Rx: [illegible]mg Amox TID x 7d."
*Reasoning:* Chief complaint is partially illegible. Diagnosis is uncertain (indicated by ?). Dosage of Amoxicillin is illegible.
*Extraction:*
{
  "soap_note": {
    "subjective": {
      "chief_complaint": "Cough for 5 days (partially illegible)",
      "hpi": "Patient with cough for 5 days. Additional history illegible.",
      "symptoms": ["Cough"],
      "patient_history": "Unknown"
    },
    "objective": {
      "vitals": {
        "bp": "120/80",
        "hr": null,
        "temp": null,
        "rr": null,
        "weight": null
      },
      "physical_exam": {
        "findings": [],
        "text_raw": "[ILLEGIBLE]"
      },
      "labs_imaging": "Pending"
    },
    "assessment": {
      "primary_diagnosis": {
        "value": "Upper Respiratory Infection (Probable)",
        "certainty_degree": 0.60,
        "evidence_text": "Dx: ?URI"
      },
      "differential_diagnosis": []
    },
    "plan": {
      "medications": [
        {
          "drug": "Amoxicillin",
          "dosage": "Unknown (illegible)",
          "sig": "TID for 7 days",
          "handwriting_confidence": 0.40
        }
      ],
      "procedures_ordered": [],
      "patient_instructions": "Unknown"
    }
  },
  "metadata": {
    "ocr_quality_check": "Poor legibility. Multiple sections illegible.",
    "critical_ambiguities": ["Chief complaint partially illegible", "Amoxicillin dosage illegible", "Physical exam findings illegible"]
  }
}

---

### TARGET SCHEMA (JSON)
Output ONLY this JSON object. Do not include markdown formatting or conversational text.

{
  "soap_note": {
    "subjective": {
      "chief_complaint": "<Primary reason for visit>",
      "hpi": "<History of Present Illness - narrative>",
      "symptoms": ["<List ALL reported symptoms - DO NOT OMIT ANY>"],
      "patient_history": "<Relevant past medical history or Unknown>"
    },
    "objective": {
      "vitals": {
        "bp": "<Blood Pressure or null>",
        "hr": "<Heart Rate or null>",
        "temp": "<Temperature or null>",
        "rr": "<Respiratory Rate or null>",
        "weight": "<Weight or null>"
      },
      "physical_exam": {
        "findings": ["<List ALL distinct physical exam observations>"],
        "text_raw": "<Full text of exam section>"
      },
      "labs_imaging": "<Any results mentioned or Pending>"
    },
    "assessment": {
      "primary_diagnosis": {
        "value": "<The main diagnosis>",
        "certainty_degree": 0.00,
        "evidence_text": "<Exact text snippet used>"
      },
      "differential_diagnosis": ["<List ALL potential diagnoses mentioned>"]
    },
    "plan": {
      "medications": [
        {
          "drug": "<Name>",
          "dosage": "<Strength e.g. 500mg>",
          "sig": "<Instructions e.g. BID x 7 days>",
          "handwriting_confidence": 0.00
        }
      ],
      "procedures_ordered": ["<List ALL labs/referrals/follow-ups>"],
      "patient_instructions": "<Advice given to patient>"
    }
  },
  "metadata": {
    "ocr_quality_check": "<Comment on overall legibility>",
    "critical_ambiguities": "<List any text that was too messy to read safely>"
  }
}"""

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=OPENAI_BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )
    return _client


def parse_json_from_response(text: str) -> dict:
    """Parse a JSON object from a raw LLM response string."""
    # Try markdown code block first
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    # Try raw JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON found in response: {text[:200]}")


def call_soap_llm(ocr_text: str) -> dict:
    """Stage 1: Call Azure GPT-4o-mini to extract SOAP JSON from OCR text."""
    client = get_client()
    user_message = f'INPUT TEXT:\n"""\n{ocr_text}\n"""'
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SOAP_FROM_TEXT_ENHANCED_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=4000,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    return parse_json_from_response(raw)


def soap_to_clinical_facts(
    soap: dict, patient_id: str, department: str | None
) -> list[dict]:
    """Stage 2: Deterministically convert SOAP data to ClinicalFact list."""
    facts = []
    today = date.today().isoformat()
    soap_note = soap.get("soap_note", {})

    assessment = soap_note.get("assessment", {})
    primary_dx = assessment.get("primary_diagnosis", {})
    if primary_dx.get("value") and primary_dx["value"] not in ("Unknown", "unknown", ""):
        certainty = float(primary_dx.get("certainty_degree", 0.8))
        facts.append(
            {
                "fact_id": str(uuid.uuid4()),
                "patient_id": patient_id,
                "entity_name": primary_dx["value"].lower().replace(" ", "_"),
                "entity_type": "diagnosis",
                "certainty": certainty,
                "certainty_label": "confirmed" if certainty > 0.8 else "suspected",
                "is_negated": False,
                "source_type": "soap",
                "department": department,
                "evidence_text": primary_dx.get("evidence_text", ""),
                "date": today,
                "modality": "clinical_note",
            }
        )

    # Differential diagnoses
    for diff_dx in assessment.get("differential_diagnosis", []):
        if diff_dx and diff_dx not in ("Unknown", "unknown"):
            facts.append(
                {
                    "fact_id": str(uuid.uuid4()),
                    "patient_id": patient_id,
                    "entity_name": diff_dx.lower().replace(" ", "_"),
                    "entity_type": "diagnosis",
                    "certainty": 0.5,
                    "certainty_label": "suspected",
                    "is_negated": False,
                    "source_type": "soap",
                    "department": department,
                    "evidence_text": diff_dx,
                    "date": today,
                    "modality": "clinical_note",
                }
            )

    # Medications from plan
    plan = soap_note.get("plan", {})
    for med in plan.get("medications", []):
        if med.get("drug"):
            facts.append(
                {
                    "fact_id": str(uuid.uuid4()),
                    "patient_id": patient_id,
                    "entity_name": f"medication_{med['drug'].lower().replace(' ', '_')}",
                    "entity_type": "medication",
                    "certainty": 0.99,
                    "certainty_label": "confirmed",
                    "is_negated": False,
                    "source_type": "soap",
                    "department": department,
                    "evidence_text": f"{med.get('drug')} {med.get('dosage', '')}".strip(),
                    "date": today,
                    "modality": "clinical_note",
                }
            )

    return facts


def _compute_extraction_confidence(soap: dict, source_confidence: float) -> float:
    """
    Derive an overall extraction confidence from the SOAP data and the
    upstream OCR confidence.
    """
    soap_note = soap.get("soap_note", {})
    scores = [source_confidence]

    primary_dx = soap_note.get("assessment", {}).get("primary_diagnosis", {})
    if primary_dx.get("certainty_degree") is not None:
        scores.append(float(primary_dx["certainty_degree"]))

    for med in soap_note.get("plan", {}).get("medications", []):
        if med.get("handwriting_confidence") is not None:
            scores.append(float(med["handwriting_confidence"]))

    return round(sum(scores) / len(scores), 4) if scores else 0.0


def run_soap_extraction(
    text: str,
    patient_id: str,
    department: str | None,
    source_confidence: float,
    layout_regions: list,
) -> dict:
    """Full two-stage SOAP extraction pipeline."""
    start = time.time()

    soap = call_soap_llm(text)
    clinical_facts = soap_to_clinical_facts(soap, patient_id, department)

    elapsed_ms = int((time.time() - start) * 1000)
    extraction_confidence = _compute_extraction_confidence(soap, source_confidence)

    soap_note = soap.get("soap_note", {})

    # Normalise into the canonical response shape
    subjective = soap_note.get("subjective", {})
    objective = soap_note.get("objective", {})
    assessment = soap_note.get("assessment", {})
    plan = soap_note.get("plan", {})

    return {
        "soap": {
            "subjective": {
                "chief_complaint": subjective.get("chief_complaint", "Unknown"),
                "symptoms": subjective.get("symptoms", []),
                "hpi": subjective.get("hpi", "Unknown"),
                "patient_history": subjective.get("patient_history", "Unknown"),
            },
            "objective": {
                "vitals": objective.get("vitals", {}),
                "physical_exam": objective.get("physical_exam", {}),
                "labs_imaging": objective.get("labs_imaging", "Pending"),
            },
            "assessment": {
                "primary_diagnosis": assessment.get("primary_diagnosis", {}),
                "differential_diagnosis": assessment.get("differential_diagnosis", []),
            },
            "plan": {
                "medications": plan.get("medications", []),
                "procedures_ordered": plan.get("procedures_ordered", []),
                "patient_instructions": plan.get("patient_instructions", "Unknown"),
            },
        },
        "clinical_facts": clinical_facts,
        "extraction_confidence": extraction_confidence,
        "processing_time_ms": elapsed_ms,
    }
