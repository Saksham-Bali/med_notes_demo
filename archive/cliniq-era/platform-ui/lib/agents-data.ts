export interface AgentInfo {
  slug: string;
  number: string;
  name: string;
  fullName: string;
  port: number;
  status: 'active' | 'pending';
  category: 'input' | 'core' | 'processing' | 'output';
  purpose: string;
  inputSchema: Record<string, string>;
  outputSchema: Record<string, string>;
  promptStrategy: string;
  pipelinePosition: string;
  exampleInput: string;
  exampleOutput: string;
  failureModes: string[];
  sourceLocation: string;
}

export const agents: AgentInfo[] = [
  {
    slug: 'ocr-agent',
    number: '01',
    name: 'OCR',
    fullName: 'OCR Agent',
    port: 5001,
    status: 'active',
    category: 'input',
    purpose:
      'Converts handwritten or scanned clinical notes into machine-readable text using Azure GPT-4o-mini vision capabilities. The agent processes uploaded images of clinical documents and produces structured text output with per-line confidence scoring. It preserves the original layout and marks illegible sections with [ILLEGIBLE] tags rather than guessing, ensuring downstream agents receive honest input.',
    inputSchema: {
      image: 'base64 | multipart file',
      department: 'string (optional)',
      patient_id: 'string',
    },
    outputSchema: {
      raw_text: 'string',
      confidence: 'number (0-1)',
      illegible_count: 'number',
      line_confidences: 'number[]',
    },
    promptStrategy:
      'Zero-shot OCR specialist prompt with strict no-correction rules. The model is instructed to transcribe exactly what it sees, never infer missing words, and tag uncertain regions as [ILLEGIBLE]. Confidence is computed deterministically by counting [ILLEGIBLE] tags relative to total line count.',
    pipelinePosition:
      'First agent in the handwritten note workflow. Receives raw image input and produces plain text that feeds into the SOAP Extractor for structured parsing.',
    exampleInput: JSON.stringify(
      { image: '<base64-encoded-png>', department: 'Cardiology', patient_id: '10000935' },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        raw_text: 'Patient complains of chest pain radiating to left arm...',
        confidence: 0.87,
        illegible_count: 2,
      },
      null,
      2
    ),
    failureModes: [
      'Very low-resolution images may yield mostly [ILLEGIBLE] output with confidence below 0.3',
      'Non-English handwriting is not supported and will produce garbled text',
      'Photos with heavy shadows or skew may lose line structure',
      'Rate-limited by Azure OpenAI token quotas on the vision endpoint',
    ],
    sourceLocation: 'ocr-agent/app/ocr.py',
  },
  {
    slug: 'soap-extractor',
    number: '02',
    name: 'SOAP',
    fullName: 'SOAP Extractor',
    port: 5002,
    status: 'active',
    category: 'input',
    purpose:
      'Parses raw clinical text into structured SOAP (Subjective, Objective, Assessment, Plan) JSON and then converts each section into standardized ClinicalFact objects. Uses a two-stage pipeline: first an LLM extraction pass with few-shot examples, then a deterministic conversion stage that maps SOAP fields to the ClinicalFact schema. This ensures consistent output format regardless of LLM variability.',
    inputSchema: {
      raw_text: 'string',
      patient_id: 'string',
      department: 'string (optional)',
    },
    outputSchema: {
      soap: '{ subjective: string, objective: string, assessment: string, plan: string }',
      clinical_facts: 'ClinicalFact[]',
    },
    promptStrategy:
      'Few-shot prompting with 3 curated examples covering common clinical note styles. Uses spiral prompting methodology where the model first identifies key clinical observations, then maps them to SOAP categories, and finally extracts discrete clinical facts with certainty scores.',
    pipelinePosition:
      'Second agent in the handwritten note workflow. Receives OCR text and produces structured SOAP + ClinicalFacts that feed into the review step before ingestion into the Fact Graph.',
    exampleInput: JSON.stringify(
      {
        raw_text:
          'Patient complains of chest pain radiating to left arm. BP 140/90. Assessment: Possible ACS. Plan: ECG stat, troponin levels.',
        patient_id: '10000935',
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        soap: {
          subjective: 'Chest pain radiating to left arm',
          objective: 'BP 140/90',
          assessment: 'Possible acute coronary syndrome',
          plan: 'ECG stat, troponin levels',
        },
        clinical_facts: [
          {
            entity_name: 'chest_pain',
            certainty: 0.95,
            body_region: 'chest',
            temporal_change: 'NEW',
          },
        ],
      },
      null,
      2
    ),
    failureModes: [
      'Highly abbreviated or shorthand notes may be misclassified between SOAP sections',
      'Notes without clear structure may produce empty Subjective/Objective fields',
      'Very long notes (>2000 words) may hit token limits and truncate the Plan section',
      'Non-standard medical abbreviations may be expanded incorrectly',
    ],
    sourceLocation: 'soap-extractor/app/extractor.py',
  },
  {
    slug: 'radiology-extractor',
    number: '03',
    name: 'RAD',
    fullName: 'Radiology Extractor',
    port: 5003,
    status: 'active',
    category: 'input',
    purpose:
      'Extracts RadLex-grounded findings from radiology reports using a hybrid rule-based and LLM approach. Tier 0 uses 159 hand-crafted regex patterns to identify common findings without any LLM call, providing instant and deterministic extraction. Tier 1 uses LLM extraction for complex or ambiguous findings. A 4-tier grounding pipeline (TF-IDF, Fuzzy, LLM, Manual) maps every finding to RadLex ontology terms. Supports paired report processing for temporal change detection.',
    inputSchema: {
      report_text: 'string',
      patient_id: 'string',
      modality: 'string (CT | MRI | PET | X-Ray | Ultrasound)',
      body_region: 'string',
      report_date: 'string (ISO date)',
    },
    outputSchema: {
      clinical_facts: 'ClinicalFact[]',
      extraction_tier: 'number (0 | 1)',
      grounding_stats: '{ tfidf: number, fuzzy: number, llm: number, ungrounded: number }',
    },
    promptStrategy:
      'Hybrid rule+LLM approach. 159 regex patterns handle common findings deterministically (Tier 0). For remaining findings, LLM extraction uses structured output prompting with RadLex vocabulary priming. The grounding pipeline tries TF-IDF similarity first, then fuzzy matching, then LLM-based mapping, falling back to ungrounded only as a last resort.',
    pipelinePosition:
      'Primary agent in the radiology workflow. Receives raw report text and produces grounded ClinicalFacts that go through human review before ingestion into the Fact Graph.',
    exampleInput: JSON.stringify(
      {
        report_text:
          'FINDINGS: There is a 2.3 cm nodule in the right upper lobe. Moderate left-sided pleural effusion. No pneumothorax.',
        patient_id: '19540374',
        modality: 'CT',
        body_region: 'chest',
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        clinical_facts: [
          {
            entity_name: 'pulmonary_nodule',
            radlex_id: 'RID3875',
            certainty: 0.95,
            body_region: 'chest',
            temporal_change: 'NEW',
            negated: false,
            measurements: { size_cm: 2.3 },
          },
          {
            entity_name: 'pleural_effusion',
            radlex_id: 'RID4836',
            certainty: 0.92,
            body_region: 'chest',
            temporal_change: 'NEW',
            negated: false,
          },
          {
            entity_name: 'pneumothorax',
            radlex_id: 'RID4799',
            certainty: 0.98,
            body_region: 'chest',
            temporal_change: 'ABSENT',
            negated: true,
          },
        ],
        extraction_tier: 0,
        grounding_stats: { tfidf: 2, fuzzy: 1, llm: 0, ungrounded: 0 },
      },
      null,
      2
    ),
    failureModes: [
      'Regex patterns may miss rare or newly described findings not in the pattern library',
      'Comparative reports without a prior study reference may miss temporal changes',
      'Non-standard report formats (bullet points, tables) may confuse section parsing',
      'RadLex grounding may map to parent terms when a more specific child term exists',
    ],
    sourceLocation: 'radiology-extractor/app/extractor.py',
  },
  {
    slug: 'voice-transcription',
    number: '04',
    name: 'VOI',
    fullName: 'Voice Transcription',
    port: 5004,
    status: 'active',
    category: 'input',
    purpose:
      'Converts audio recordings of clinical conversations to timestamped transcripts using Sarvam AI Saaras v3 speech-to-text model. Handles Hindi-English code-mixing common in Indian clinical settings. Provides speaker diarization to distinguish between clinician and patient voices. Outputs a structured transcript with timestamps that feeds into the Counselling Summarizer.',
    inputSchema: {
      audio: 'multipart file (wav | mp3 | m4a)',
      patient_id: 'string',
      language_hint: 'string (optional, default: hi-en)',
    },
    outputSchema: {
      transcript: '{ speaker: string, text: string, start_ms: number, end_ms: number }[]',
      duration_seconds: 'number',
      language_detected: 'string',
    },
    promptStrategy:
      'No LLM prompting involved. Uses Sarvam AI Saaras v3 ASR model directly for transcription. Speaker diarization is performed as a post-processing step using energy-based segmentation. Language detection is automatic via the multilingual model.',
    pipelinePosition:
      'First agent in the counselling workflow. Receives raw audio and produces timestamped transcript that feeds into the Counselling Summarizer for clinical fact extraction.',
    exampleInput: JSON.stringify(
      { audio: '<audio-file.wav>', patient_id: '10000935', language_hint: 'hi-en' },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        transcript: [
          { speaker: 'Doctor', text: 'Aapko kab se pain ho raha hai?', start_ms: 0, end_ms: 2500 },
          {
            speaker: 'Patient',
            text: 'Last week se, doctor. Left side mein.',
            start_ms: 2600,
            end_ms: 5100,
          },
        ],
        duration_seconds: 45.2,
        language_detected: 'hi-en',
      },
      null,
      2
    ),
    failureModes: [
      'Background noise in clinical settings may reduce transcription accuracy significantly',
      'Audio files longer than 10 minutes may timeout due to processing constraints',
      'Heavy dialect or accent variations may not be well-handled by the ASR model',
      'Speaker diarization may fail with more than 3 speakers in the conversation',
    ],
    sourceLocation: '2nd/app/main.py',
  },
  {
    slug: 'counselling-summarizer',
    number: '05',
    name: 'COUN',
    fullName: 'Counselling Summarizer',
    port: 5005,
    status: 'active',
    category: 'input',
    purpose:
      'Extracts clinical facts from counselling session transcripts, categorizing them into CONCERN, ACTION, DECISION, EMOTIONAL, and FOLLOW_UP types. Includes guardrails for sensitive mental health content to ensure appropriate handling. Produces structured clinical facts that undergo human review before ingestion into the patient record.',
    inputSchema: {
      transcript: 'TranscriptSegment[]',
      patient_id: 'string',
      session_type: 'string (optional)',
    },
    outputSchema: {
      clinical_facts: 'ClinicalFact[]',
      session_summary: 'string',
      categories: '{ CONCERN: number, ACTION: number, DECISION: number, EMOTIONAL: number, FOLLOW_UP: number }',
    },
    promptStrategy:
      'Structured extraction prompt with explicit category definitions and examples for each fact type. Includes guardrails that flag potentially sensitive content (suicidal ideation, abuse disclosure) for immediate clinician attention rather than standard review. Uses chain-of-thought reasoning to distinguish between patient-reported concerns and clinician observations.',
    pipelinePosition:
      'Second agent in the counselling workflow. Receives transcript from Voice Transcription and produces categorized ClinicalFacts that go through human review before Fact Graph ingestion.',
    exampleInput: JSON.stringify(
      {
        transcript: [
          { speaker: 'Doctor', text: 'How have you been feeling since the last session?' },
          { speaker: 'Patient', text: 'The medication is helping with sleep but I still feel anxious.' },
        ],
        patient_id: '10000935',
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        clinical_facts: [
          {
            entity_name: 'sleep_improvement',
            category: 'ACTION',
            certainty: 0.85,
            source_text: 'medication is helping with sleep',
          },
          {
            entity_name: 'persistent_anxiety',
            category: 'CONCERN',
            certainty: 0.9,
            source_text: 'still feel anxious',
          },
        ],
        session_summary: 'Patient reports medication-assisted sleep improvement with persistent anxiety.',
        categories: { CONCERN: 1, ACTION: 1, DECISION: 0, EMOTIONAL: 0, FOLLOW_UP: 0 },
      },
      null,
      2
    ),
    failureModes: [
      'Transcription errors from the Voice agent may propagate and cause misidentified concerns',
      'Sensitive content guardrails may be overly cautious, flagging benign statements',
      'Sessions with heavy code-mixing may lose nuance in the English-language fact extraction',
      'Very long sessions (>1 hour) may lose context in later portions of the transcript',
    ],
    sourceLocation: '3rd/counselling-summarizer/app/summarizer.py',
  },
  {
    slug: 'fact-graph-engine',
    number: '06',
    name: 'FG',
    fullName: 'Fact Graph Engine',
    port: 5006,
    status: 'active',
    category: 'core',
    purpose:
      'The central append-only clinical fact store that maintains a longitudinal patient record. Uses no LLM — all operations are deterministic. Performs entity merge (deduplication of equivalent clinical findings), ontology grounding via RadLex hierarchy, and trajectory tracking to monitor how findings change over time. Backed by SQLite with the RadLex ontology loaded as a lookup hierarchy.',
    inputSchema: {
      patient_id: 'string',
      clinical_facts: 'ClinicalFact[]',
      source_workflow: 'string',
    },
    outputSchema: {
      entities_created: 'number',
      entities_updated: 'number',
      entities_merged: 'number',
      patient_entity_count: 'number',
    },
    promptStrategy:
      'No LLM prompting. All operations are deterministic. Entity merge uses canonical name normalization, RadLex ID matching, and configurable similarity thresholds. Trajectory tracking compares incoming certainty scores and temporal markers against existing entity state to compute trends (improving, worsening, stable).',
    pipelinePosition:
      'Central hub that all workflows feed into after human review. Receives approved ClinicalFacts and maintains the canonical patient state. Queried by the Summary Generator and QA Agent for downstream processing.',
    exampleInput: JSON.stringify(
      {
        patient_id: '19540374',
        clinical_facts: [
          { entity_name: 'pleural_effusion', radlex_id: 'RID4836', certainty: 0.92, body_region: 'chest' },
        ],
        source_workflow: 'radiology-report',
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      { entities_created: 0, entities_updated: 1, entities_merged: 0, patient_entity_count: 155 },
      null,
      2
    ),
    failureModes: [
      'Entity merge may incorrectly merge distinct findings with similar names (e.g., left vs right pleural effusion)',
      'RadLex hierarchy lookups may be slow if the ontology cache is not warmed',
      'SQLite write contention under concurrent workflow submissions for the same patient',
      'Trajectory tracking requires at least 2 observations to compute a trend',
    ],
    sourceLocation: 'fact-graph-service/app/graph.py',
  },
  {
    slug: 'department-merger',
    number: '07',
    name: 'DEPT',
    fullName: 'Department Merger',
    port: 5007,
    status: 'active',
    category: 'processing',
    purpose:
      'Merges clinical notes from multiple hospital departments into a unified set of clinical facts. Performs parallel extraction from each department note, then aligns entities across departments and detects conflicts (e.g., different certainty scores or contradictory findings for the same condition). Uses LLM-powered conflict analysis to suggest resolutions.',
    inputSchema: {
      patient_id: 'string',
      department_notes: '{ department: string, text: string, date: string, author?: string }[]',
    },
    outputSchema: {
      clinical_facts: 'ClinicalFact[]',
      conflicts: '{ entity: string, departments: string[], description: string, resolution: string }[]',
      department_count: 'number',
    },
    promptStrategy:
      'Two-stage approach. First, each department note is independently parsed for clinical facts using department-aware prompting (e.g., cardiology notes emphasize cardiac findings). Second, an alignment pass identifies duplicate entities across departments and a conflict analysis prompt evaluates contradictory findings, suggesting resolutions based on clinical hierarchy (specialist opinion weighted higher).',
    pipelinePosition:
      'Primary agent in the department merge workflow. Receives multiple department notes and produces a unified ClinicalFact set with conflict annotations that go through human review before Fact Graph ingestion.',
    exampleInput: JSON.stringify(
      {
        patient_id: '10000935',
        department_notes: [
          {
            department: 'Cardiology',
            text: 'Echo shows EF 35%. Moderate MR.',
            date: '2182-07-01',
            author: 'Dr. Smith',
          },
          {
            department: 'Internal Medicine',
            text: 'Cardiac function appears preserved. Mild MR on echo.',
            date: '2182-07-02',
            author: 'Dr. Jones',
          },
        ],
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        clinical_facts: [
          { entity_name: 'reduced_ejection_fraction', certainty: 0.9, body_region: 'chest', source_department: 'Cardiology' },
          { entity_name: 'mitral_regurgitation', certainty: 0.85, body_region: 'chest' },
        ],
        conflicts: [
          {
            entity: 'mitral_regurgitation',
            departments: ['Cardiology', 'Internal Medicine'],
            description: 'Severity disagreement: Moderate (Cardiology) vs Mild (Internal Medicine)',
            resolution: 'Cardiology specialist assessment preferred: Moderate MR',
          },
        ],
        department_count: 2,
      },
      null,
      2
    ),
    failureModes: [
      'Department notes from different time periods may reflect legitimate clinical change, not true conflict',
      'Notes with very different terminology styles may miss entity alignment',
      'Conflict resolution may incorrectly prefer one department over another',
      'More than 5 departments may hit token limits in the conflict analysis pass',
    ],
    sourceLocation: '4th/department-merger/app/merger.py',
  },
  {
    slug: 'summary-generator',
    number: '08',
    name: 'SUMM',
    fullName: 'Summary Generator',
    port: 5008,
    status: 'active',
    category: 'processing',
    purpose:
      'Generates NABH (National Accreditation Board for Hospitals) compliant discharge summaries from the patient fact graph data. Uses a template-based approach with LLM composition to produce structured, standardized discharge documents. Pulls all approved entities from the Fact Graph and organizes them into clinically appropriate sections.',
    inputSchema: {
      patient_id: 'string',
      admission_date: 'string (ISO date)',
      discharge_date: 'string (ISO date)',
      attending_physician: 'string',
      department: 'string',
      template: 'string (default: nabh_standard)',
      include_recist: 'boolean',
    },
    outputSchema: {
      summary_text: 'string (markdown)',
      sections: 'string[]',
      entity_count: 'number',
      template_used: 'string',
    },
    promptStrategy:
      'Template-based composition where each discharge summary section (Chief Complaint, History of Present Illness, Hospital Course, Discharge Instructions, etc.) is generated by a focused prompt that receives only the relevant entities for that section. The final summary is assembled deterministically from section outputs. RECIST criteria integration is optional and pulls measurement trajectory data.',
    pipelinePosition:
      'First agent in the discharge summary pipeline. Pulls data from the Fact Graph and produces a draft summary that feeds into the QA Agent for validation before final output through the Translation Layer.',
    exampleInput: JSON.stringify(
      {
        patient_id: '19540374',
        admission_date: '2182-06-01',
        discharge_date: '2182-07-15',
        attending_physician: 'Dr. Sharma',
        department: 'Oncology',
        template: 'nabh_standard',
        include_recist: true,
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        summary_text: '# Discharge Summary\n\n## Patient Information\n...\n\n## Hospital Course\n...',
        sections: [
          'Patient Information',
          'Chief Complaint',
          'History of Present Illness',
          'Hospital Course',
          'Discharge Medications',
          'Follow-up Instructions',
        ],
        entity_count: 42,
        template_used: 'nabh_standard',
      },
      null,
      2
    ),
    failureModes: [
      'Patients with very few entities may produce sparse summaries with placeholder text',
      'RECIST criteria require measurement data that may not be available for all entities',
      'Very long hospital stays with hundreds of entities may exceed summary length limits',
      'Template sections may not cover all speciality-specific documentation requirements',
    ],
    sourceLocation: '5th/app/generator.py',
  },
  {
    slug: 'qa-agent',
    number: '09',
    name: 'QA',
    fullName: 'QA Agent',
    port: 5009,
    status: 'active',
    category: 'output',
    purpose:
      'Validates discharge summaries against source facts in the Fact Graph to ensure accuracy and completeness. Performs traceability checking — every claim in the summary must be traceable to an approved clinical entity. Issues a PASS or FAIL verdict with a detailed list of issues including missing entities, unsupported claims, and inconsistencies.',
    inputSchema: {
      summary_text: 'string',
      patient_id: 'string',
      source_entities: 'ClinicalEntity[]',
    },
    outputSchema: {
      verdict: 'PASS | FAIL',
      score: 'number (0-100)',
      issues: '{ type: string, severity: string, description: string, location: string }[]',
      traceable_claims: 'number',
      total_claims: 'number',
    },
    promptStrategy:
      'Two-pass validation. First pass: claim extraction — identify every factual claim in the summary text. Second pass: traceability checking — for each claim, search the source entities for a matching fact. Claims without a traceable source are flagged. Severity is assigned based on clinical impact (medication errors are critical, formatting issues are low).',
    pipelinePosition:
      'Second agent in the discharge summary pipeline. Receives the generated summary and source entities, validates correctness, and passes the verdict to the orchestrator. A FAIL verdict blocks translation and output generation until issues are resolved.',
    exampleInput: JSON.stringify(
      {
        summary_text: 'Patient had bilateral pleural effusion requiring thoracentesis...',
        patient_id: '19540374',
        source_entities: [{ entity_name: 'pleural_effusion', certainty: 0.92, body_region: 'chest' }],
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        verdict: 'FAIL',
        score: 78,
        issues: [
          {
            type: 'unsupported_claim',
            severity: 'high',
            description: 'Summary states "bilateral" but source only documents unilateral effusion',
            location: 'Hospital Course, paragraph 2',
          },
          {
            type: 'missing_procedure',
            severity: 'medium',
            description: 'Thoracentesis mentioned but not found in source entities',
            location: 'Hospital Course, paragraph 2',
          },
        ],
        traceable_claims: 14,
        total_claims: 18,
      },
      null,
      2
    ),
    failureModes: [
      'Paraphrased claims may not match source entities despite being semantically equivalent',
      'Negated findings in the summary may be incorrectly flagged as unsupported',
      'Very long summaries with many claims may hit token limits during validation',
      'Claims about procedures or medications may not have corresponding Fact Graph entities',
    ],
    sourceLocation: '6th/qa-agent/app/validator.py',
  },
  {
    slug: 'translation-layer',
    number: '10',
    name: 'TRANS',
    fullName: 'Translation Layer',
    port: 5010,
    status: 'active',
    category: 'output',
    purpose:
      'Translates validated discharge summaries into Indian regional languages using the Sarvam AI translation API. Supports Hindi, Marathi, Tamil, Telugu, and other major Indian languages. Also provides text-to-speech audio generation for accessibility, PDF document generation for printing, and FHIR R4 JSON export for interoperability with hospital information systems.',
    inputSchema: {
      summary_text: 'string',
      target_language: 'string (hi | mr | ta | te | en)',
      generate_audio: 'boolean',
      generate_pdf: 'boolean',
      generate_fhir: 'boolean',
      patient_id: 'string',
    },
    outputSchema: {
      translated_text: 'string',
      audio_url: 'string | null',
      pdf_url: 'string | null',
      fhir_json: 'object | null',
      target_language: 'string',
    },
    promptStrategy:
      'No LLM prompting for translation — uses Sarvam AI translation API directly. Medical terminology is preserved untranslated when no equivalent exists in the target language. PDF generation uses a template with hospital branding placeholders. FHIR export maps summary sections to DiagnosticReport and Composition resources.',
    pipelinePosition:
      'Final agent in the discharge summary pipeline. Receives QA-validated summary and produces translated text, audio, PDF, and FHIR outputs. This is the terminal step — outputs go directly to the clinician or hospital system.',
    exampleInput: JSON.stringify(
      {
        summary_text: '# Discharge Summary\n\nPatient was admitted for...',
        target_language: 'hi',
        generate_audio: true,
        generate_pdf: true,
        generate_fhir: false,
        patient_id: '19540374',
      },
      null,
      2
    ),
    exampleOutput: JSON.stringify(
      {
        translated_text: '#退院サマリー (translated to Hindi in practice)',
        audio_url: '/outputs/19540374_summary_hi.wav',
        pdf_url: '/outputs/19540374_summary_hi.pdf',
        fhir_json: null,
        target_language: 'hi',
      },
      null,
      2
    ),
    failureModes: [
      'Sarvam API rate limits may cause timeouts for very long summaries',
      'Medical jargon may be mistranslated in languages with limited medical vocabulary',
      'Audio generation for very long summaries (>5000 words) may be truncated',
      'FHIR export may not capture all custom fields from the clinical workflow',
    ],
    sourceLocation: '7th/app/translator.py',
  },
];

export function getAgentBySlug(slug: string): AgentInfo | undefined {
  return agents.find((a) => a.slug === slug);
}

export function getAgentsByCategory(category: AgentInfo['category']): AgentInfo[] {
  return agents.filter((a) => a.category === category);
}

export function getCategoryColor(category: AgentInfo['category']): string {
  switch (category) {
    case 'input':
      return 'teal';
    case 'core':
      return 'amber';
    case 'processing':
      return 'blue';
    case 'output':
      return 'purple';
  }
}
