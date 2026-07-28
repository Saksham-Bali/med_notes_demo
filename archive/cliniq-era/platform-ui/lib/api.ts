import type {
  HealthResponse,
  PatientState,
  PatientTimeline,
  WorkflowEnvelope,
} from './types';
import { normalizeEntity } from './types';

function baseUrl(): string {
  if (typeof window !== 'undefined') {
    return '/api/proxy';
  }
  return process.env.NEXT_PUBLIC_ORCHESTRATOR_URL || 'http://localhost:8000';
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${baseUrl()}/${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      message = err.detail || err.message || message;
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

// Health
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('api/v1/health');
}

// Patients — orchestrator returns the fact-graph array directly
export interface PatientSummary {
  patient_id: string;
  entity_count: number;
  event_count: number;
  first_event_date: string | null;
  last_event_date: string | null;
  body_regions: string[];
}

export async function getPatients(): Promise<PatientSummary[]> {
  return apiFetch<PatientSummary[]>('api/v1/patients');
}

// Patient state/timeline come wrapped in WorkflowEnvelope — unwrap .data
export async function getPatientState(patientId: string): Promise<PatientState> {
  const envelope = await apiFetch<WorkflowEnvelope>(`api/v1/patient/${encodeURIComponent(patientId)}/state`);
  const raw = (envelope.data as unknown) as PatientState;
  return {
    ...raw,
    entities: (raw.entities || []).map(normalizeEntity),
  };
}

export async function getPatientTimeline(patientId: string): Promise<PatientTimeline> {
  const envelope = await apiFetch<WorkflowEnvelope>(`api/v1/patient/${encodeURIComponent(patientId)}/timeline`);
  return (envelope.data as unknown) as PatientTimeline;
}

// Preview workflows (extract without ingesting)
export async function previewRadiology(payload: {
  patient_id: string;
  report_text: string;
  modality?: string;
  body_region?: string;
  report_date?: string;
}): Promise<WorkflowEnvelope> {
  return apiFetch<WorkflowEnvelope>('api/v1/workflow/radiology-report/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function previewHandwrittenNote(formData: FormData): Promise<WorkflowEnvelope> {
  const url = `${baseUrl()}/api/v1/workflow/handwritten-note/preview`;
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      message = err.detail || err.message || message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json() as Promise<WorkflowEnvelope>;
}

export async function previewDepartmentMerge(payload: {
  patient_id: string;
  department_notes: { department: string; text: string; date: string; author?: string }[];
}): Promise<WorkflowEnvelope> {
  return apiFetch<WorkflowEnvelope>('api/v1/workflow/department-merge/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// Confirm (ingest approved facts)
export async function confirmFacts(
  patientId: string,
  approvedFacts: unknown[],
  sourceWorkflow: string
): Promise<WorkflowEnvelope> {
  return apiFetch<WorkflowEnvelope>('api/v1/workflow/confirm', {
    method: 'POST',
    body: JSON.stringify({
      patient_id: patientId,
      approved_facts: approvedFacts,
      source_workflow: sourceWorkflow,
    }),
  });
}

// Discharge summary
export async function generateSummary(payload: {
  patient_id: string;
  admission_date?: string;
  discharge_date?: string;
  attending_physician?: string;
  department?: string;
  include_recist?: boolean;
  template?: string;
  target_language?: string;
  generate_audio?: boolean;
  generate_pdf?: boolean;
}): Promise<WorkflowEnvelope> {
  return apiFetch<WorkflowEnvelope>('api/v1/workflow/generate-summary', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function submitCounselling(formData: FormData): Promise<WorkflowEnvelope> {
  const url = `${baseUrl()}/api/v1/workflow/counselling`;
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      message = err.detail || err.message || message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json() as Promise<WorkflowEnvelope>;
}

export async function approveCounselling(payload: {
  patient_id: string;
  session_id: string;
  approved_fact_ids: string[];
  approved_bullet_ids: string[];
}): Promise<WorkflowEnvelope> {
  return apiFetch<WorkflowEnvelope>('api/v1/workflow/counselling/approve', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
