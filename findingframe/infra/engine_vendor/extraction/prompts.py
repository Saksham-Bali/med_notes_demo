"""
Prompt templates for the Cancer Longitudinal GC System.

This module contains all LLM prompts used by the extraction and GC systems.
NOTE: Uses double braces {{}} for literal braces in JSON examples (Python .format() escaping)
"""

# ==============================================================================
# AGENT 1: Radiology Finding Extractor
# ==============================================================================

RADIOLOGY_FINDING_EXTRACTION_PROMPT = """### SYSTEM ROLE
You are an expert Medical Information Extraction System specialized in radiology reports for oncology patients.

### CRITICAL RULE: MISSING NO DATA
You must capture ALL clinical findings. Do not summarize or omit details. Every measurement, every finding, every comparison must be extracted individually. Extract every finding that is explicitly stated in the report. Do not omit findings. Do not invent findings not stated. These two rules have equal weight.

### TASK
Extract ALL clinical findings from the radiology report below. This is a LOSSLESS extraction—no summarization allowed.

### EXTRACTION RULES (NON-NEGOTIABLE)
1. **Extract POSITIVE findings** (masses, lesions, abnormalities)
2. **Extract PRESUMPTIVE findings** ("suspicious for", "concerning for", "likely represents")
3. **Extract DIFFERENTIAL diagnoses** ("differential includes")
4. **Preserve UNCERTAINTY language** (do not convert "suspicious" to "confirmed")
5. **Extract ALL MEASUREMENTS** with units and anatomical location
6. **Extract COMPARISONS** to prior studies ("increased from", "new since", "stable")
7. **Extract CLINICALLY SIGNIFICANT NEGATIVES** ("no evidence of metastasis")
8. **DO NOT summarize** - extract verbatim
9. **DO NOT interpret** - just extract what is stated
10. **Include temporal context** (baseline, interval change, new, resolved)
11. **Do NOT promote clinical history into current findings**
    - HISTORY / CLINICAL HISTORY / INDICATION sections are context, not imaging findings.
    - Phrases like "history of", "status post", "prior", "known", "post-surgical", "resection for carcinoid"
      MUST NOT become present entities unless the FINDINGS or IMPRESSION explicitly states the abnormality is visible on this study.
    - Example: "Status post right lower lobe resection for carcinoid" does NOT justify extracting a current tumor.

ENTITY NAMING — CRITICAL:
When naming an extracted finding, always name the FINDING not the anatomic structure.
Use the SHORTEST accurate name for the finding type (2–5 words maximum). Do NOT include
measurements, qualifiers like "mild"/"moderate"/"severe", or full anatomical paths in the entity name.
Include anatomy only when it disambiguates the finding (e.g. "right hemidiaphragm elevation" not just "elevation").
  WRONG: "right hemidiaphragm" (anatomy)        → RIGHT: "right hemidiaphragm elevation" (finding)
  WRONG: "paranasal sinuses" (anatomy)           → RIGHT: "paranasal sinuses normally aerated" (finding)
  WRONG: "posterior rib" (anatomy)              → RIGHT: "surgical fracture right posterior sixth rib" (finding)
  WRONG: "lung" or "small lung component"       → RIGHT: "low lung volumes" (finding)
  WRONG: "calcarine spur" (brain anatomy)       → RIGHT: "bone spur / osteophyte" for knee reports
  WRONG: "moderate joint space narrowing of the medial compartment of the knee bilaterally"
         → RIGHT: "joint space narrowing" (the qualifier "moderate medial bilateral" goes in measurement/evidence)
  WRONG: "mild degenerative changes of the lateral and patellofemoral compartments"
         → RIGHT: "degenerative changes lateral patellofemoral"
  WRONG: "mild lateral translocation of the tibia relative to the femur"
         → RIGHT: "tibial lateral translocation"

CANCER ENTITY NAMING — use THESE canonical names consistently across all reports:
  "pulmonary metastases" — NOT "lung metastases", "pulmonary metastatic disease", "lung mets"
  "hepatic metastases" — NOT "liver metastases", "liver mets", "hepatic metastatic disease"
  "metastatic disease" — use for general "metastases" without specific organ
  "primary malignancy" — NOT "primary tumor", "primary cancer", "unknown primary"
  "colon cancer" — NOT "colorectal carcinoma", "colon malignancy", "colorectal cancer"
  "carcinoid tumor" — NOT "carcinoid", "carcinoid cancer", "neuroendocrine tumor"
  "lymphangitic carcinomatosis" — NOT "lymphangitic spread", "lymphangitis carcinomatosa"
  "osseous metastases" — NOT "bone metastases", "skeletal metastases", "bony mets"
  "lymph node metastasis" — NOT "nodal metastasis", "lymph node met", "LN metastasis"

These names MUST be identical every time the same concept appears. Do NOT vary them.
If the report describes a cancer finding that does not match any canonical name above,
use the simplest consistent form: "[organ] [disease]" (e.g., "adrenal metastasis").

For normal observations, the entity IS the normal state — do not name the underlying pathology:
  WRONG: "heart size abnormality" or "cardiomegaly" when report says "Heart size normal"
         → RIGHT: extract as significant_negatives: "heart enlargement", is_negated=true  OR omit entirely
  WRONG: "abnormal contours of upper mediastinum" when report says "Upper mediastinum has normal contours"
         → RIGHT: omit — a normal structure observation with no pathological finding is not extractable

DO NOT over-specify beyond what the report states:
  WRONG: "chance fracture" when report says only "no acute fracture"
         → RIGHT: "acute fracture", is_negated=true. Do NOT infer a specific fracture subtype (Chance, burst, etc.)
  WRONG: "soft tissue calcification or radiopaque foreign body" → extract these as two separate negated entities
         → "soft tissue calcification", is_negated=true  AND  "radiopaque foreign body", is_negated=true
   WRONG: "soft tissue administration" — this is not a medical concept; never generate this entity name
          CONCRETE EXAMPLE: Report says "No soft tissue calcification or radiopaque foreign body"
            WRONG output: {{ "entity": "soft_tissue_administration", "is_negated": false }}
            RIGHT output: significant_negatives with {{ "entity": "soft tissue calcification", "is_negated": true }}
                                                  AND {{ "entity": "radiopaque foreign body", "is_negated": true }}
  WRONG: extracting "territorial" as a separate entity from "no major vascular territorial infarct"
         → RIGHT: one entity "vascular territorial infarct", is_negated=true
  WRONG: making clinical inferences from normal observations, e.g. "acromegaly" from "Heart size normal"
         → RIGHT: never infer a diagnosis from a normal finding. Extract only what the report explicitly states.

NEVER INVERT A NORMAL OBSERVATION INTO AN ABNORMAL FINDING:
  Report says "X is normal" or "X has normal contours" → do NOT extract "abnormal X"
  The only exception: if clinical context makes the normal finding itself significant (e.g. "no hemorrhage"
  after head trauma), extract it as is_negated=true with the correct negation language.

NEGATION DETECTION — CRITICAL:
For every finding, you MUST set "is_negated": true if the finding is:

ONCOLOGIC DIAGNOSIS EXTRACTION — CRITICAL:
You are processing radiology reports for ONCOLOGY patients. Your most important job
is to extract cancer-relevant diagnoses, not just morphological descriptions.

RULE: When the report states or strongly implies an oncologic diagnosis, extract the
DIAGNOSIS as the entity, not just the anatomical observation.

Examples:
  Report says: "innumerable hepatic metastases replacing hepatic parenchyma"
    WRONG: entity="hepatomegaly" (describes organ size, not the disease)
    RIGHT: entity="hepatic metastases", is_negated=false
    ALSO extract: entity="hepatomegaly" (organ enlargement is a separate finding)

  Report says: "innumerable bilateral pulmonary nodules... compatible with metastases"
    WRONG: entity="pulmonary nodules" (describes morphology, not the diagnosis)
    RIGHT: entity="pulmonary metastases", is_negated=false
    ALSO extract: entity="pulmonary nodules" (the nodules themselves are a finding)

  Report says: "no evidence of metastatic disease"
    WRONG: nothing extracted (missed the important negative)
    RIGHT: entity="metastatic disease", is_negated=true, in significant_negatives

  Report says: "suspicious for primary malignancy"
    RIGHT: entity="primary malignancy", certainty="suspected"

  Report says: "findings compatible with lymphangitic carcinomatosis"
    RIGHT: entity="lymphangitic carcinomatosis"

  Report says: "newly diagnosed metastatic colon cancer" (in INDICATION/HISTORY)
    RIGHT: extract as significant_negatives only if the current study explicitly
           evaluates for it. Do NOT fabricate a positive finding from history.
           If the current study FINDINGS confirms metastases, extract the diagnosis
           from the FINDINGS/IMPRESSION section only.

RULE: Cancer diagnosis entities are SEPARATE from morphological entities.
  "hepatic metastases" ≠ "hepatomegaly" — extract BOTH as separate entities.
  "pulmonary metastases" ≠ "pulmonary nodules" — extract BOTH.
  A patient can have nodules (morphology) that ARE metastases (diagnosis).

RULE: When the report mentions a specific cancer TYPE (e.g., "colon cancer",
"carcinoid", "lung primary"), extract that as a separate entity.
  Report says: "known metastatic colon cancer" → entity="colon cancer",
               entity_type="primary_tumor"
  Report says: "prior resection for carcinoid" → THIS IS HISTORY, do NOT extract
               as a present finding unless current study confirms visible disease.

NEGATION DETECTION — CRITICAL:
For every finding, you MUST set "is_negated": true if the finding is:
  - Explicitly absent: "no hemorrhage", "no effusion", "without infarct"
  - Ruled out: "infarct excluded", "no evidence of mass"
  - Not identified: "no focal abnormality identified", "not seen"
  - Normal: "normal in size", "unremarkable"

If is_negated is true, also capture the exact phrase in "negation_language".

NEVER mark a negated finding as present.
NEVER omit a negated finding — significant negatives belong in significant_negatives[].
NEVER create both a positive/present version and a negated version of the same finding.
NEVER duplicate the same negated finding in both primary_findings[] and significant_negatives[].
If the report says "No hemorrhage, hydrocephalus, or midline shift", all three must be negated findings only.
If the report says a structure is "normal" or "preserved", do not invent an abnormal positive pathology for that structure.

Examples:
  Report: "No hemorrhage, hydrocephalus, or shift of midline structures."
  → three findings, all is_negated=true:
    {{ "entity": "hemorrhage", "is_negated": true, "negation_language": "No" }}
    {{ "entity": "hydrocephalus", "is_negated": true, "negation_language": "No" }}
    {{ "entity": "midline shift", "is_negated": true, "negation_language": "No" }}

  Report: "No evidence of abnormal parenchymal, vascular or meningeal enhancement."
  → all enhancement findings are negated only, not present:
    significant_negatives: [
      {{ "entity": "abnormal parenchymal enhancement", "is_negated": true, "negation_language": "no evidence of" }},
      {{ "entity": "abnormal vascular enhancement", "is_negated": true, "negation_language": "no evidence of" }},
      {{ "entity": "abnormal meningeal enhancement", "is_negated": true, "negation_language": "no evidence of" }}
    ]

REPORT FORMAT DETECTION:
Radiology reports come in several formats. Identify which applies before extracting:

FORMAT A — Structured (CT/MRI):
  Sections: CLINICAL HISTORY / TECHNIQUE / FINDINGS / IMPRESSION
  Strategy: Extract from FINDINGS section primarily; use IMPRESSION to verify.

FORMAT B — Impression-only (Chest X-ray, Plain Film):
  Sections: HISTORY / IMPRESSION (findings embedded in impression prose)
  Example indicators: "PA AND LATERAL CHEST", "THREE VIEWS", "PA and lateral"
  Strategy: IMPRESSION IS YOUR PRIMARY SOURCE. Extract all findings from it.
  Ignore disease names that appear only in HISTORY/INDICATION unless the impression/body confirms them on this study.
  Do NOT return empty findings list because there is no FINDINGS section.

FORMAT C — Hybrid (some X-rays):
  Sections: HISTORY / per-region findings / IMPRESSION
  Example: "LEFT KNEE, THREE VIEWS: There is no acute fracture..."
  Strategy: Extract EVERY finding from EACH per-region paragraph. Do NOT collapse them into
  the impression summary. Each sentence typically contains a separate finding.

For FORMAT B and C reports, you MUST extract findings from the impression/body text.
Returning an empty findings list for a report with a non-empty impression is ALWAYS wrong.

CRITICAL FOR FORMAT C: Do NOT summarize per-region findings into one entity from the impression.
Extract EACH finding individually. A single paragraph like:
  "There is no acute fracture or dislocation. There is moderate joint space narrowing
   of the medial compartment, with associated osteophytes. Mild degenerative changes
   of the patellofemoral compartment. There is no joint effusion."
contains AT LEAST 5 separate findings:
  1. acute fracture (negated)
  2. dislocation (negated)
  3. joint space narrowing (positive)
  4. osteophytes (positive)
  5. degenerative changes patellofemoral (positive)
  6. joint effusion (negated)
Do NOT collapse these into just "osteoarthritis" — that is a SUMMARY, not extraction.

EXAMPLE — FORMAT B (Chest X-ray):

Report text:
  "PA AND LATERAL CHEST
   HISTORY: Status post right lower lobe resection for carcinoid. Now short of breath.
   IMPRESSION: No interval radiographic change. Lung volumes are small and the right
   hemidiaphragm is moderately elevated. No focal pulmonary abnormality. No left
   pleural effusion. Heart size normal. Granulomatous calcifications in hilar nodes.
   Periosteal regrowth does not fully bridge surgical fracture of right posterior sixth rib."

Correct extraction:
  primary_findings: [
    {{ "entity": "right hemidiaphragm elevation", "is_negated": false,
      "certainty": "confirmed", "measurement": {{"current": "moderately elevated"}},
      "anatomical_location": "right hemidiaphragm" }},
    {{ "entity": "granulomatous calcifications", "is_negated": false,
      "certainty": "confirmed", "anatomical_location": "hilar lymph nodes" }},
    {{ "entity": "surgical rib fracture", "is_negated": false,
      "certainty": "confirmed", "measurement": {{"current": "incomplete periosteal bridging"}},
      "anatomical_location": "right posterior sixth rib" }}
  ]
  significant_negatives: [
    {{ "entity": "pleural effusion", "is_negated": true,
      "anatomical_location": "left", "certainty": "confirmed" }},
    {{ "entity": "focal pulmonary abnormality", "is_negated": true,
      "certainty": "confirmed" }}
  ]
  Do NOT extract "carcinoid" or "status post resection" as a current tumor finding from the HISTORY alone.

EXAMPLE — FORMAT C (Bilateral Knee X-ray):

Report text:
  "HISTORY: Osteoarthritis of bilateral knees, evaluate for progression.
   LEFT KNEE, THREE VIEWS: There is no acute fracture or dislocation.
   There is moderate joint space narrowing of the medial compartment of the
   knee, with associated osteophytes. There is mild lateral translocation
   of the tibia relative to the femur. Mild degenerative changes of the
   lateral and patellofemoral compartments are seen. There is no joint effusion.
   IMPRESSION: Moderate osteoarthritis of the medial compartment bilaterally."

Correct extraction (extract EVERY finding from per-region text, not just impression):
  primary_findings: [
    {{ "entity": "joint space narrowing", "is_negated": false,
      "certainty": "confirmed", "measurement": {{"current": "moderate"}},
      "anatomical_location": "medial compartment bilateral knees" }},
    {{ "entity": "osteophytes", "is_negated": false,
      "certainty": "confirmed", "anatomical_location": "medial compartment bilateral knees" }},
    {{ "entity": "tibial lateral translocation", "is_negated": false,
      "certainty": "confirmed", "measurement": {{"current": "mild"}},
      "anatomical_location": "bilateral knees" }},
    {{ "entity": "degenerative changes", "is_negated": false,
      "certainty": "confirmed", "measurement": {{"current": "mild"}},
      "anatomical_location": "lateral and patellofemoral compartments bilateral knees" }}
  ]
  significant_negatives: [
    {{ "entity": "acute fracture", "is_negated": true, "certainty": "confirmed" }},
    {{ "entity": "dislocation", "is_negated": true, "certainty": "confirmed" }},
    {{ "entity": "joint effusion", "is_negated": true, "certainty": "confirmed" }}
  ]
  WRONG: extracting only {{ "entity": "osteoarthritis" }} from the impression — that is summarization, not extraction.

MODALITY-SPECIFIC INSTRUCTIONS:
{modality_instructions}

### CERTAINTY LEVELS
For each finding, assign certainty:
- **confirmed** (0.95-1.00): Definitive language ("there is", "demonstrates")
- **suspected** (0.70-0.94): Presumptive language ("suspicious for", "concerning for", "likely")
- **differential** (0.50-0.69): Multiple possibilities listed
- **uncertain** (<0.50): Equivocal or illegible

### OUTPUT FORMAT (JSON)
Return ONLY valid JSON with this structure:
- report_metadata: object with study_date, study_type, comparison_study
- primary_findings: array of finding objects with entity, anatomical_location, finding_type, measurement (with current, prior, trend), measurement_normalized (value_mm, is_qualitative, delta_mm when available), modality, temporal_qualifier, certainty, confidence_score, evidence_text, is_negated, negation_language, span_start (integer: character offset where the source sentence starts in the report text), span_end (integer: character offset where the source sentence ends)
- significant_negatives: array of objects with finding, evidence_text, is_negated (true), negation_language, span_start, span_end
- overall_extraction_confidence: number 0-1
- critical_ambiguities: array of strings

### INPUT RADIOLOGY REPORT
Study Date: {chart_date}
Study Type: {study_type}

{report_text}

Extract all findings now and return ONLY valid JSON:
"""


# ==============================================================================
# PAIRED REPORT PROCESSING: Chronological Extraction with Temporal Classification
# ==============================================================================

PAIRED_REPORT_EXTRACTION_PROMPT = """### SYSTEM ROLE
You are an expert Medical Information Extraction System specialized in longitudinal radiology report analysis for oncology patients.

### CONTEXT: PAIRED REPORT PROCESSING
You are extracting findings from the CURRENT report with knowledge of the PREVIOUS report.
This enables:
1. Consistent entity naming across reports (use same names for same findings)
2. Temporal change classification (NEW/UNCHANGED/IMPROVED/WORSENED/RESOLVED)
3. Measurement continuity tracking

### CRITICAL INSTRUCTION #1: CONSISTENT ENTITY NAMING
When the same clinical finding appears in both reports, you MUST use IDENTICAL entity names.

Examples:
- Previous report: "right lower lobe nodule"
- Current report: "the RLL pulmonary nodule has enlarged"
→ CORRECT: Both use "right lower lobe nodule" (not "RLL pulmonary nodule")

- Previous report: "small pleural effusion"
- Current report: "moderate right pleural effusion"
→ CORRECT: Both use "pleural effusion" (consistent base name)

WRONG: Using different names like:
- "right lower lobe nodule" vs "RLL nodule" vs "pulmonary nodule RLL"
- "pleural effusion" vs "right pleural effusion" vs "pleural fluid"

### CRITICAL INSTRUCTION #2: TEMPORAL CHANGE CLASSIFICATION
For EACH finding in the CURRENT report, classify its temporal status:

**NEW**: Finding not present in previous report
- Example: "new 1.2 cm nodule in right upper lobe" (not in previous)
- temporal_change: "NEW"

**UNCHANGED**: Finding present before with no significant change
- Example: "stable small pleural effusion" or "unchanged from prior"
- temporal_change: "UNCHANGED"

**IMPROVED**: Finding better than previous (smaller, less severe, resolving)
- Example: "pleural effusion has decreased" or "nodule smaller than prior"
- temporal_change: "IMPROVED"

**WORSENED**: Finding worse than previous (larger, more severe, new complications)
- Example: "mass has enlarged from 2.1 to 3.4 cm" or "new areas of enhancement"
- temporal_change: "WORSENED"

**RESOLVED**: Finding present before, now absent
- Example: "prior pleural effusion has resolved" or "no longer seen"
- temporal_change: "RESOLVED"

### CRITICAL INSTRUCTION #3: MEASUREMENT CONTINUITY
When a finding has measurements in both reports, record BOTH:

Example:
- Previous: "nodule measuring 1.2 cm"
- Current: "nodule now 1.5 cm, increased from prior"
→ Record: current=1.5cm, prior=1.2cm, trend="increased"

### CRITICAL INSTRUCTION #4: CURRENT-REPORT EVIDENCE ANCHORING
Every finding you extract MUST be supported by text in the CURRENT report. The PREVIOUS report
is provided ONLY for context (consistent naming, temporal change classification).

STRICT RULES:
1. **evidence_text MUST come from the CURRENT report.** Copy the exact sentence or phrase
   from the CURRENT report that mentions this finding. Do NOT use text from the PREVIOUS report
   as evidence_text.
2. **Do NOT extract findings that appear ONLY in the PREVIOUS report.** If a condition was
   mentioned in the previous report but is NOT referenced in the current report, do NOT
   extract it. The finding must be explicitly stated or implied in the CURRENT report.
3. **Do NOT promote previous-report negatives into current-report findings.** If the previous
   report said "no pleural effusion" and the current report does not mention pleural effusion
   at all, do NOT extract "no pleural effusion" as a current finding. Only extract negated
   findings when the CURRENT report explicitly states the negation.
4. **If the current report says a structure is normal (e.g., "adrenal glands are
   unremarkable"), do NOT extract this as a positive finding named "adrenal abnormality."
   Extract it ONLY if the report explicitly identifies it as a finding (e.g., as a
   significant negative worth tracking).

Violating these rules produces context bleed — noise that makes the output less trustworthy.
Context bleed findings will be automatically rejected by the pipeline and will not appear
in the final fact graph.

### EXTRACTION RULES (same as single-report)
{extraction_rules}

### OUTPUT FORMAT (JSON)
Return ONLY valid JSON with this structure:
- report_metadata: object with study_date, study_type, comparison_study
- primary_findings: array of finding objects with:
  - entity: finding name (consistent with previous report if same finding)
  - anatomical_location, finding_type, measurement (current, prior, trend)
  - temporal_change: MUST be one of ["NEW", "UNCHANGED", "IMPROVED", "WORSENED", "RESOLVED", null]
  - certainty, confidence_score, evidence_text, is_negated, negation_language
- significant_negatives: array (same structure)
- overall_extraction_confidence: number 0-1

### PREVIOUS REPORT (Date: {prev_date}, Report #{prev_num})
{previous_report_text}

### CURRENT REPORT (Date: {curr_date}, Report #{curr_num})
{report_text}

Extract all findings with temporal_change classification now and return ONLY valid JSON:
"""


# ==============================================================================
# AGENT 2: Entity Normalization
# ==============================================================================

ENTITY_NORMALIZATION_PROMPT = """### SYSTEM ROLE
You are a Clinical Entity Normalization System for oncology findings.

### TASK
Standardize and merge duplicate entities across multiple radiology reports for the same patient.

### NORMALIZATION RULES
1. **Same anatomical entity** = same canonical name
   - "RUL mass", "right upper lobe lesion", "lung mass RUL" → "lung_primary_right_upper_lobe"
2. **Metastatic sites** = organ-specific naming
   - "hepatic lesion", "liver met", "liver metastasis" → "metastasis_liver"
3. **Preserve measurement timelines** - don't merge different measurements
4. **Flag contradictions** - don't resolve, just mark them

### CANONICAL NAMING CONVENTION
Primary tumors: primary_organ_location
Metastases: metastasis_organ_specific_site
Lymph nodes: lymph_node_station_or_region

### CRITICAL: ONCOLOGIC CANONICAL NAMES REQUIRE ONCOLOGIC CONTEXT
Canonical names that imply oncologic disease (e.g. metastasis_*, primary_*) MUST ONLY be used when:
  (a) The current report explicitly uses oncologic language (e.g. "metastasis", "malignancy", "tumor", "neoplasm"), OR
  (b) Prior reports in the timeline already contain confirmed oncologic entities.
If neither condition is met, use a non-oncologic canonical name:
  Report says "hepatic lesion" in a non-oncologic context → use "hepatic_lesion" NOT "metastasis_liver"
  Report says "lung nodule" with no oncologic context → use "pulmonary_nodule" NOT "metastasis_lung"
Do NOT promote findings to oncologic canonical names based on anatomic location alone.

### CRITICAL: FINDING vs ANATOMY — ALWAYS name the FINDING, not the structure
The canonical_name MUST describe the pathological or clinical finding, NOT the anatomic structure.
  WRONG: "right_hemidiaphragm"          → RIGHT: "right_hemidiaphragm_elevation"
  WRONG: "paranasal_sinuses"            → RIGHT: "paranasal_sinuses_normally_aerated"
  WRONG: "mastoid_air_cells"            → RIGHT: "mastoid_air_cells_normally_aerated"
  WRONG: "posterior_rib"               → RIGHT: "surgical_fracture_right_posterior_sixth_rib"
  WRONG: "lung"                         → RIGHT: "low_lung_volumes"
  WRONG: "liver"                        → RIGHT: "hepatic_metastasis" or "normal_liver"

If the report says a structure is normal/unremarkable/preserved, the canonical_name must include
that qualifier (e.g., "normally_aerated", "_normal", "_preserved") so the finding is complete.

If the extracted entity is a pure anatomy term with no finding qualifier, rename it to include
the finding: look at the evidence_text and derive the correct finding label.

### DO NOT OVER-SPECIFY: use the most precise label the report supports, no more
  WRONG: "chance_fracture" (specific fracture type) when report says only "no acute fracture"
         → RIGHT: "acute_fracture" (negated)
  WRONG: "calcarine_spur" (brain anatomy) when report mentions knee bone spurs
         → RIGHT: "osteophyte" or "bone_spur" (the actual knee finding)
  WRONG: "territorial" alone when report says "no major vascular territorial infarct"
         → RIGHT: "vascular_territorial_infarct" (negated), do NOT also extract "territorial" separately

### OUTPUT FORMAT
Return JSON with:
- normalized_entities: array of objects with canonical_name, variants_seen, first_documented, timeline (array of date/measurement/source), current_status, certainty_evolution
- flagged_contradictions: array of objects with entity, contradiction, conflicting_reports

### FEW-SHOT EXAMPLE
Input:
{{
  "findings_from_multiple_reports": [
    {{
      "report_date": "2024-01-10",
      "hadm_id": "111",
      "findings": [
        {{"entity": "RUL mass", "anatomical_location": "Right upper lobe", "measurement": {{"current": "3.2 x 2.9 cm"}}}}
      ]
    }},
    {{
      "report_date": "2024-03-15",
      "hadm_id": "222",
      "findings": [
        {{"entity": "right upper lobe lesion", "anatomical_location": "Right upper lobe", "measurement": {{"current": "3.8 x 3.4 cm"}}}}
      ]
    }}
  ]
}}

Output:
{{
  "normalized_entities": [
    {{
      "canonical_name": "primary_lung_right_upper_lobe",
      "variants_seen": ["RUL mass", "right upper lobe lesion"],
      "first_documented": "2024-01-10",
      "timeline": [
        {{"date": "2024-01-10", "measurement": "3.2 x 2.9 cm", "source": "report"}},
        {{"date": "2024-03-15", "measurement": "3.8 x 3.4 cm", "source": "report"}}
      ],
      "current_status": "progressive",
      "certainty_evolution": []
    }}
  ],
  "flagged_contradictions": []
}}

### INPUT DATA
{findings_array}

Normalize now and return ONLY valid JSON:
"""


# ==============================================================================
# AGENT 3 v2: Fact Graph Renderer (Incremental + Full)
# ==============================================================================

FACT_GRAPH_INCREMENTAL_GC_RENDER_PROMPT = """### SYSTEM ROLE
You are an oncology clinical documentation renderer.

### TASK
Update the existing GC markdown using ONLY the newly-added Fact Graph events below.

### RULES
1. Keep existing content unless contradicted by explicit new data.
2. Add new evidence in chronological order.
3. Preserve measurements, modality, certainty labels, and ontology identifiers when available.
4. Do not invent events not present in input.
5. Return markdown only.

### CURRENT GC
{current_gc}

### FACT GRAPH CONTEXT
{fact_graph_json}

### NEW EVENTS ONLY
{new_events_json}

Render updated GC markdown now:
"""


FACT_GRAPH_FULL_GC_RENDER_PROMPT = """### SYSTEM ROLE
You are an oncology clinical documentation renderer.

### TASK
Generate a complete longitudinal GC markdown view from the full Fact Graph.

### RULES
1. This is presentation only: do not alter factual content.
2. Include per-entity timelines with dates, measurements (mm when available), modality, and certainty.
3. Include certainty trajectory transitions where evident.
4. Include RECIST-relevant signals (target burden trend, new lesions) when present in graph metadata.
5. Return markdown only.

### FACT GRAPH
{fact_graph_json}

Render full GC markdown now:
"""


# ==============================================================================
# AGENT 4 v2: Non-target lesion supplement
# ==============================================================================

NON_TARGET_SUPPLEMENT_PROMPT = """### SYSTEM ROLE
You are an oncology response-assessment assistant.

### TASK
Review non-target lesion events and provide qualitative interpretation supporting RECIST assessment.

### INPUT JSON
{non_target_events_json}

### OUTPUT JSON
Return ONLY JSON:
{{
  "non_target_progression": <true|false>,
  "summary": "<1-3 sentence clinical narrative>",
  "evidence": ["...", "..."],
  "confidence": <0-1>
}}
"""

# ==============================================================================
# EVALUATION: Extraction Completeness Checker
# ==============================================================================

EXTRACTION_EVAL_PROMPT = """### SYSTEM ROLE
You are a Medical QA Validator.

### TASK
Compare AI extraction against manually annotated ground truth.

### EVALUATION CRITERIA
Calculate:
1. **Recall:** How many ground truth findings were captured?
   - Formula: findings_extracted / total_ground_truth_findings
2. **Precision:** How many extracted findings were accurate?
   - Formula: accurate_extractions / total_extractions
3. **Measurement accuracy:** Are measurements exact?

### INPUT
**Ground Truth (manually annotated):**
{ground_truth_findings}

**AI Extraction:**
{ai_extracted_findings}

### OUTPUT FORMAT
Return JSON with:
- metrics: object with recall, precision, f1_score
- missed_findings: array of strings
- false_positives: array of strings
- measurement_errors: array of objects with finding, ground_truth, extracted, error

Evaluate now and return ONLY valid JSON:
"""
