// Orchestrator workflow types

export interface WorkflowStep {
  agent: string;
  status: 'success' | 'needs_review' | 'pending_dependency' | 'skipped' | 'pending' | 'running' | 'error';
  detail?: string | null;
}

export interface DeferredJobInfo {
  job_id: string;
  dependency: string;
  job_type: string;
  status: string;
}

export interface WorkflowEnvelope {
  workflow: string;
  status: string;
  message?: string | null;
  steps: WorkflowStep[];
  data: Record<string, unknown>;
  deferred_jobs: DeferredJobInfo[];
}

// Health check types
export interface HealthAgentStatus {
  agent: string;
  status: string;
  details?: Record<string, unknown> | null;
  error?: string | null;
  notes?: string | null;
}

export interface HealthResponse {
  service: string;
  timestamp: string;
  agents: HealthAgentStatus[];
}

// Fact graph entity (matches fact-graph-service response)
export interface ClinicalEntity {
  entity_id: string;
  canonical_name: string;
  radlex_id?: string | null;
  snomed_id?: string | null;
  entity_type?: string | null;
  anatomical_site?: string | null;
  body_region?: string | null;
  first_documented?: string | null;
  last_documented?: string | null;
  status?: 'active' | 'resolved' | 'absent' | 'uncertain' | null;
  event_count?: number;
  certainty_trajectory?: { date: string; certainty: number; label: string }[];
  // Computed convenience fields (set by normalizeEntity)
  trend?: 'improving' | 'worsening' | 'stable' | null;
  certainty_score?: number | null;
  first_seen?: string | null;
  last_seen?: string | null;
  negated?: boolean;
}

/** Map raw fact-graph entity to the shape UI components expect */
export function normalizeEntity(raw: ClinicalEntity): ClinicalEntity {
  const traj = raw.certainty_trajectory || [];
  const latestCertainty = traj.length > 0 ? traj[traj.length - 1].certainty : undefined;
  let trend: ClinicalEntity['trend'] = null;
  if (traj.length >= 2) {
    const delta = traj[traj.length - 1].certainty - traj[0].certainty;
    if (delta > 0.05) trend = 'worsening';
    else if (delta < -0.05) trend = 'improving';
    else trend = 'stable';
  }
  return {
    ...raw,
    first_seen: raw.first_seen ?? raw.first_documented ?? null,
    last_seen: raw.last_seen ?? raw.last_documented ?? null,
    certainty_score: raw.certainty_score ?? latestCertainty ?? null,
    trend: raw.trend ?? trend,
    negated: raw.negated ?? (raw.status === 'absent'),
  };
}

// Patient state
export interface PatientState {
  patient_id: string;
  schema_version?: string;
  entity_count?: number;
  entities: ClinicalEntity[];
  last_updated?: string | null;
}

// Timeline event (matches fact-graph-service response)
export interface TimelineEvent {
  event_id: string;
  entity_id?: string;
  canonical_name?: string;
  patient_id?: string;
  event_type?: string;
  description?: string;
  date?: string;
  timestamp?: string;
  entity_name?: string | null;
  source_report_id?: string | null;
  hadm_id?: string | null;
  modality?: string | null;
  certainty?: number | null;
  certainty_label?: string | null;
  trend?: string | null;
  is_negated?: boolean | null;
  measurement?: Record<string, unknown> | string | null;
  source?: string | null;
  agent?: string | null;
  data?: Record<string, unknown>;
}

export interface PatientTimeline {
  patient_id: string;
  event_count?: number;
  events: TimelineEvent[];
}

// Clinical fact from extraction (pre-ingestion)
export interface ClinicalFact {
  entity_name: string;
  canonical_name?: string;
  radlex_id?: string | null;
  certainty: number;
  body_region?: string;
  temporal_change?: 'NEW' | 'STABLE' | 'WORSENED' | 'IMPROVED' | 'RESOLVED' | 'ABSENT';
  negated?: boolean;
  evidence?: string;
  measurements?: Record<string, unknown>;
  source_department?: string;
  category?: string;
  source_text?: string;
}

// Radiology request
export interface RadiologyWorkflowRequest {
  patient_id: string;
  report_text: string;
  modality?: string | null;
  body_region?: string | null;
}

// Department merge
export interface DepartmentNoteInput {
  department: string;
  text: string;
  date: string;
  author?: string | null;
}

export interface DepartmentMergeRequest {
  patient_id: string;
  department_notes: DepartmentNoteInput[];
}

// Summary generation
export interface SummaryWorkflowRequest {
  patient_id: string;
  admission_date?: string | null;
  discharge_date?: string | null;
  attending_physician?: string | null;
  department?: string | null;
  approved_counselling_fact_ids?: string[];
  include_recist?: boolean;
  template?: string;
  patient_name?: string | null;
  target_language?: string;
  generate_audio?: boolean;
  generate_pdf?: boolean;
  generate_fhir?: boolean;
}

// Conflict from department merge
export interface MergeConflict {
  entity: string;
  departments: string[];
  description: string;
  resolution: string;
}

// Voice counselling workflow types
export interface BulletPoint {
  id: string;
  text: string;
  source_time_start?: number | null;
  source_time_end?: number | null;
}

export interface CounsellingFact {
  id: string;
  fact: string;
  category: 'CONCERN' | 'ACTION' | 'DECISION' | 'EMOTIONAL' | 'FOLLOW_UP';
  certainty: number;
  evidence_start_time: number;
  evidence_end_time: number;
  evidence_text: string;
  speaker: 'doctor' | 'patient' | 'unknown';
  selectable: boolean;
  validation_flags: string[];
}

export interface CounsellingApproveRequest {
  patient_id: string;
  session_id: string;
  approved_fact_ids: string[];
  approved_bullet_ids: string[];
}
