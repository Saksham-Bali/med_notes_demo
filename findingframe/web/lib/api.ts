/**
 * Typed FindingFrame API client. Attaches the Supabase access token as
 * `Authorization: Bearer <token>` on every call. In mock mode it delegates to the
 * in-memory mock backend so the UI runs standalone.
 *
 * Live responses are normalized here into the UI's internal shapes so components
 * stay backend-shape-agnostic. Real shapes were captured by hitting the live API.
 */
import { API_URL, IS_MOCK } from "./env";
import { getAccessToken } from "./auth";
import { mock } from "./mock";
import type {
  AgreementSummary,
  AnalyticsOverview,
  AppSettings,
  AuditPacket,
  ConfirmedTrack,
  CreatePatientInput,
  CreateReportInput,
  Digest,
  GateFailedFrame,
  IrrAdjudicationInput,
  IrrDisagreements,
  IrrItemsResponse,
  IrrKappaResult,
  IrrMyAssignment,
  IrrRecordInput,
  IrrTask,
  IrrTaskCreateInput,
  LinkDecision,
  LinkDecisionInput,
  Me,
  Patient,
  RecistContrast,
  RecistDistribution,
  RecistProgression,
  RecistResult,
  Report,
  Review,
  ReviewInput,
  ReviewSession,
  ReviewThroughput,
  Run,
  RunManifest,
  SectionKey,
  Signoff,
  TargetLesionInput,
  Track,
  TrackEvent,
  RunDelta,
} from "./types";

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;
  constructor(status: number, message: string, code?: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Network error reaching the API at ${API_URL}. Is the backend running?`);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    // Errors are always {error:{code,message}} — with a FastAPI {detail} fallback.
    const env = data as { error?: { code?: string; message?: string }; detail?: unknown } | null;
    const code = env?.error?.code;
    const message =
      env?.error?.message ??
      (typeof env?.detail === "string" ? env.detail : `Request failed (${res.status})`);
    throw new ApiError(res.status, message, code, data);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Fetch a binary payload (e.g. the PDF audit packet) with the Bearer token. */
async function requestBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  const token = await getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${path}`, { headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, `Network error reaching the API at ${API_URL}.`);
  }
  if (!res.ok) {
    const text = await res.text();
    const env = safeJson(text) as { error?: { code?: string; message?: string } } | null;
    throw new ApiError(res.status, env?.error?.message ?? `Request failed (${res.status})`, env?.error?.code);
  }
  const disp = res.headers.get("content-disposition") ?? "";
  const m = disp.match(/filename="?([^"]+)"?/);
  return { blob: await res.blob(), filename: m?.[1] ?? "audit-packet.pdf" };
}

// ---- normalizers (live -> internal) --------------------------------------

// The backend sends `measurement` as a FrameMeasurement object
// ({raw,text,unit,value,values,normalized_mm}); the UI renders it as a string.
// Rendering the object directly triggers React error #31, so flatten it here.
export function fmtMeasurement(m: unknown): string | null {
  if (m == null) return null;
  if (typeof m === "string") return m || null;
  if (typeof m === "object") {
    const o = m as Record<string, unknown>;
    if (typeof o.text === "string" && o.text) return o.text;
    if (typeof o.raw === "string" && o.raw) return o.raw;
    if (o.normalized_mm != null) return `${o.normalized_mm} mm`;
    if (Array.isArray(o.values) && o.values.length)
      return `${(o.values as unknown[]).join(" × ")}${o.unit ? " " + String(o.unit) : " mm"}`;
    if (o.value != null) return `${o.value}${o.unit ? " " + String(o.unit) : ""}`;
    return null;
  }
  return String(m);
}

function humanize(findingType: string): string {
  if (!findingType) return "Finding";
  const s = findingType.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function normalizeEvent(
  raw: Record<string, unknown>,
  track: { anatomy?: string | null; laterality?: string | null }
): TrackEvent {
  return {
    report_date: String(raw.date ?? raw.report_date ?? ""),
    source_report_id: raw.source_report_id as string | undefined,
    report_version_id: (raw.report_version_id as string | null | undefined) ?? null,
    assertion: String(raw.assertion ?? ""),
    evidence_text: String(raw.evidence_text ?? ""),
    measurement: fmtMeasurement(raw.measurement),
    anatomy: (raw.anatomy as string | null | undefined) ?? track.anatomy ?? null,
    laterality: (raw.laterality as string | null | undefined) ?? track.laterality ?? null,
    temporal_change: (raw.temporal_change as string | null | undefined) ?? null,
    full_text: String(raw.full_text ?? ""),
    // Digest/confirmed track events have already passed the gate; gate failures
    // are surfaced separately via digest.gate_failed.
    evidence_verified: true,
  };
}

function normalizeTrack(raw: Record<string, unknown>): Track {
  const anatomy = (raw.anatomy as string | null | undefined) ?? null;
  const laterality = (raw.laterality as string | null | undefined) ?? null;
  const events = Array.isArray(raw.events)
    ? (raw.events as Record<string, unknown>[]).map((e) => normalizeEvent(e, { anatomy, laterality }))
    : [];
  return {
    track_key: String(raw.track_key ?? raw.confirmed_track_key ?? ""),
    display_name: humanize(String(raw.finding_type ?? "")),
    finding_type: String(raw.finding_type ?? ""),
    anatomy,
    laterality,
    progression: (raw.progression as string | null | undefined) ?? null,
    progression_detail: (raw.progression_detail as string | null | undefined) ?? null,
    latest_status: (raw.latest_status as string | null | undefined) ?? null,
    measurement_trend: (raw.measurement_trend as string | null | undefined) ?? null,
    report_range: (raw.report_range as string | null | undefined) ?? null,
    event_count: (raw.event_count as number | undefined) ?? events.length,
    clinical_section: (raw.clinical_section as string | null | undefined) ?? null,
    member_track_keys: (raw.member_track_keys as string[] | undefined) ?? undefined,
    unresolved_link: Boolean(raw.unresolved_link),
    false_split_candidate: Boolean(raw.false_split_candidate),
    events,
  };
}

function normalizeGateFrame(raw: Record<string, unknown>, rvDate: Record<string, string>): GateFailedFrame {
  const rv = (raw.report_version_id as string | undefined) ?? undefined;
  return {
    frame_id: raw.frame_id as string | undefined,
    track_key: (raw.track_key as string | null | undefined) ?? null,
    finding_type: String(raw.finding_type ?? ""),
    finding_surface: (raw.finding_surface as string | null | undefined) ?? null,
    display_name: humanize(String(raw.finding_type ?? "")),
    assertion: String(raw.assertion ?? ""),
    evidence_text: String(raw.evidence_text ?? ""),
    report_date: rv ? rvDate[rv] : undefined,
    source_report_id: (raw.source_report_id as string | null | undefined) ?? null,
    report_version_id: rv ?? null,
    evidence_span_start: raw.evidence_span_start as number | undefined,
    evidence_span_end: raw.evidence_span_end as number | undefined,
    full_text: String(raw.full_text ?? ""),
    anatomy: (raw.anatomy as string | null | undefined) ?? null,
    laterality: (raw.laterality as string | null | undefined) ?? null,
    measurement: fmtMeasurement(raw.measurement),
    reason: (raw.reason as string | null | undefined) ?? null,
  };
}

function manifestFromRun(run: Record<string, unknown>): RunManifest {
  const rm = (run.report_manifest as RunManifest["report_manifest"]) ?? [];
  return {
    engine_git_sha: String(run.engine_git_sha ?? ""),
    model_provider: String(run.model_provider ?? ""),
    model_id: String(run.model_id ?? ""),
    prompt_version: String(run.prompt_version ?? ""),
    schema_version: String(run.schema_version ?? ""),
    temperature: (run.temperature as number | undefined) ?? 0,
    reasoning_effort: (run.reasoning_effort as string | undefined) ?? "",
    manifest_hash: String(run.manifest_hash ?? ""),
    report_manifest: rm,
  };
}

function rvDateMap(run: Record<string, unknown>): Record<string, string> {
  const map: Record<string, string> = {};
  const rm = (run.report_manifest as Array<{ report_version_id?: string; chart_date?: string }>) ?? [];
  for (const r of rm) if (r.report_version_id) map[r.report_version_id] = String(r.chart_date ?? "");
  return map;
}

/** Live patient detail is wrapped: {patient, report_count, has_identifiers, latest_run}. */
function normalizePatientDetail(raw: Record<string, unknown>): Patient {
  const p = (raw.patient as Record<string, unknown>) ?? raw;
  return {
    id: String(p.id ?? ""),
    subject_code: String(p.subject_code ?? ""),
    cancer_type: (p.cancer_type as string | null | undefined) ?? null,
    created_at: p.created_at as string | undefined,
    report_count: (raw.report_count as number | undefined) ?? 0,
    has_identifiers: Boolean(raw.has_identifiers),
    latest_run: (raw.latest_run as Patient["latest_run"]) ?? null,
  };
}

// ---- API surface ----------------------------------------------------------

export const api = {
  // identity
  me: (): Promise<Me> => (IS_MOCK ? mock.me() : request("GET", "/me")),

  // patients
  listPatients: (): Promise<Patient[]> =>
    IS_MOCK ? mock.listPatients() : request("GET", "/patients"),
  getPatient: async (id: string): Promise<Patient> => {
    if (IS_MOCK) return mock.getPatient(id);
    const raw = await request<Record<string, unknown>>("GET", `/patients/${id}`);
    return normalizePatientDetail(raw);
  },
  createPatient: (input: CreatePatientInput): Promise<Patient> =>
    IS_MOCK ? mock.createPatient(input) : request("POST", "/patients", input),
  deleteIdentifiers: (id: string): Promise<void> =>
    IS_MOCK ? mock.deleteIdentifiers(id) : request("DELETE", `/patients/${id}/identifiers`),

  // reports
  listReports: async (patientId: string): Promise<Report[]> => {
    if (IS_MOCK) return mock.listReports(patientId);
    const raw = await request<Array<Record<string, unknown>>>("GET", `/patients/${patientId}/reports`);
    return raw.map((row) => {
      const r = (row.report as Record<string, unknown>) ?? row;
      const cv = (row.current_version as Record<string, unknown>) ?? {};
      return {
        id: String(r.id ?? ""),
        report_date: String(r.report_date ?? ""),
        note_type: String(r.note_type ?? ""),
        external_note_id: (r.external_note_id as string | null | undefined) ?? null,
        current_version: {
          id: String(cv.id ?? ""),
          version_no: Number(cv.version_no ?? 1),
          text_sha256: String(cv.text_sha256 ?? ""),
        },
      } as Report;
    });
  },
  createReports: (patientId: string, inputs: CreateReportInput[]): Promise<Report[]> =>
    IS_MOCK
      ? mock.createReports(patientId, inputs)
      : request("POST", `/patients/${patientId}/reports`, inputs),

  // runs
  listRuns: (patientId: string): Promise<Run[]> =>
    IS_MOCK ? mock.listRuns(patientId) : request("GET", `/patients/${patientId}/runs`),
  getRun: (runId: string): Promise<Run> =>
    IS_MOCK ? mock.getRun(runId) : request("GET", `/runs/${runId}`),
  createRun: (patientId: string): Promise<Run> =>
    IS_MOCK ? mock.createRun(patientId) : request("POST", `/patients/${patientId}/runs`),

  // digest + reviews
  getDigest: async (runId: string): Promise<Digest> => {
    if (IS_MOCK) return mock.getDigest(runId);
    const d = await request<Record<string, unknown>>("GET", `/runs/${runId}/digest`);
    const patientId = String(d.patient_id ?? "");
    const [patient, run] = await Promise.all([
      api.getPatient(patientId),
      request<Record<string, unknown>>("GET", `/runs/${runId}`),
    ]);
    const rvDate = rvDateMap(run);
    const rawSections = (d.sections as Record<string, Record<string, unknown>[]>) ?? {};
    const sections = {} as Digest["sections"];
    (["needs_attention", "stable", "resolved", "uncertain", "routine_negatives"] as SectionKey[]).forEach(
      (k) => {
        sections[k] = (rawSections[k] ?? []).map(normalizeTrack);
      }
    );
    return {
      run_id: String(d.run_id ?? runId),
      patient: { id: patient.id, subject_code: patient.subject_code, cancer_type: patient.cancer_type },
      report_count: patient.report_count ?? 0,
      status: d.status as string | undefined,
      sections,
      gate_failed: ((d.gate_failed as Record<string, unknown>[]) ?? []).map((f) =>
        normalizeGateFrame(f, rvDate)
      ),
      gate_failed_count: d.gate_failed_count as number | undefined,
      unresolved_link_count: d.unresolved_link_count as number | undefined,
      false_split_candidate_count: d.false_split_candidate_count as number | undefined,
      track_count: d.track_count as number | undefined,
      frame_count: d.frame_count as number | undefined,
      manifest: manifestFromRun(run),
    };
  },
  listReviews: (runId: string): Promise<Review[]> =>
    IS_MOCK ? mock.listReviews(runId) : request("GET", `/runs/${runId}/reviews`),
  createReview: (runId: string, input: ReviewInput): Promise<Review> =>
    IS_MOCK ? mock.createReview(runId, input) : request("POST", `/runs/${runId}/reviews`, input),

  // human-confirmed linking
  listLinkDecisions: (runId: string): Promise<LinkDecision[]> =>
    IS_MOCK ? mock.listLinkDecisions(runId) : request("GET", `/runs/${runId}/link-decisions`),
  createLinkDecision: (runId: string, input: LinkDecisionInput): Promise<LinkDecision> =>
    IS_MOCK
      ? mock.createLinkDecision(runId, input)
      : request("POST", `/runs/${runId}/link-decisions`, input),
  confirmedTracks: async (runId: string): Promise<ConfirmedTrack[]> => {
    if (IS_MOCK) return mock.confirmedTracks(runId);
    const raw = await request<{ confirmed_tracks?: Record<string, unknown>[] }>(
      "GET",
      `/runs/${runId}/confirmed-tracks`
    );
    return (raw.confirmed_tracks ?? []).map((t) => {
      const base = normalizeTrack(t);
      const key = String(t.confirmed_track_key ?? base.track_key);
      const trend =
        base.events
          .map((e) => e.measurement)
          .filter(Boolean)
          .join(" → ") || null;
      return {
        ...base,
        track_key: key,
        confirmed_track_key: key,
        confirmed: true,
        measurement_trend: base.measurement_trend ?? trend,
      };
    });
  },

  // RECIST
  setTargetLesions: (runId: string, input: TargetLesionInput): Promise<{ id?: string }> =>
    IS_MOCK
      ? mock.setTargetLesions(runId, input).then(() => ({}))
      : request("POST", `/runs/${runId}/target-lesions`, input),
  // RECIST compute is POST; returns 422 {error:{code:'no_confirmed_tracks'|...}} until
  // there are human-confirmed tracks AND a target-lesion selection.
  getRecist: (runId: string): Promise<RecistResult> =>
    IS_MOCK ? mock.getRecist(runId) : request("POST", `/runs/${runId}/recist`),
  // The money moment: naive (machine linking) vs human-confirmed RECIST side by side.
  getRecistContrast: (runId: string): Promise<RecistContrast> =>
    IS_MOCK ? mock.recistContrast(runId) : request("GET", `/runs/${runId}/recist/contrast`),
  // Read-only disease trajectory: per-lesion diameters + the SLD timeline. 422 until
  // there are confirmed tracks and a target-lesion selection, same as the worksheet.
  getRecistProgression: (runId: string): Promise<RecistProgression> =>
    request("GET", `/runs/${runId}/recist/progression`),

  // what one new report changed, relative to the run this one extends. Returns null for a
  // first run (nothing to compare against) and in mock mode, which has no run lineage.
  getRunDelta: async (runId: string): Promise<RunDelta | null> => {
    if (IS_MOCK) return null;
    try {
      return await request<RunDelta>("GET", `/runs/${runId}/delta`);
    } catch (e) {
      if (e instanceof ApiError && (e.code === "no_parent_run" || e.status === 404)) return null;
      throw e;
    }
  },
  applyCarryForward: (runId: string): Promise<RunDelta> =>
    request("POST", `/runs/${runId}/carry-forward`),

  // sign-off + audit
  signoff: (patientId: string): Promise<Signoff> =>
    IS_MOCK ? mock.signoff(patientId) : request("POST", `/patients/${patientId}/signoff`),
  auditPacket: async (runId: string): Promise<AuditPacket> => {
    if (IS_MOCK) return mock.auditPacket(runId);
    const p = await request<AuditPacket>("GET", `/runs/${runId}/audit-packet`);
    // Flatten measurement objects on packet frames so the UI can render them as text.
    if (p && Array.isArray(p.frames)) {
      for (const f of p.frames) {
        f.measurement = fmtMeasurement(f.measurement);
      }
    }
    return p;
  },
  auditPacketPdf: (runId: string): Promise<{ blob: Blob; filename: string }> =>
    IS_MOCK ? mock.auditPacketPdf(runId) : requestBlob(`/runs/${runId}/audit-packet?format=pdf`),

  // review sessions (ROI)
  startSession: (runId: string, patientId?: string): Promise<ReviewSession> =>
    IS_MOCK
      ? mock.startSession(runId, patientId)
      : request("POST", "/review-sessions", { run_id: runId, patient_id: patientId }),
  endSession: (id: string, activeSeconds: number, tracksReviewed: number): Promise<ReviewSession> =>
    IS_MOCK
      ? mock.endSession(id, activeSeconds, tracksReviewed)
      : request("PATCH", `/review-sessions/${id}`, {
          active_seconds: activeSeconds,
          tracks_reviewed: tracksReviewed,
        }),

  // analytics (org-scoped, read-only). In mock mode we return representative demo
  // aggregates so the dashboard renders standalone.
  analyticsOverview: (): Promise<AnalyticsOverview> =>
    IS_MOCK ? Promise.resolve(MOCK_ANALYTICS.overview) : request("GET", "/analytics/overview"),
  recistDistribution: (): Promise<RecistDistribution> =>
    IS_MOCK
      ? Promise.resolve(MOCK_ANALYTICS.recist)
      : request("GET", "/analytics/recist-distribution"),
  reviewThroughput: (): Promise<ReviewThroughput> =>
    IS_MOCK ? Promise.resolve(MOCK_ANALYTICS.throughput) : request("GET", "/analytics/review-throughput"),
  agreement: (): Promise<AgreementSummary> =>
    IS_MOCK ? Promise.resolve(MOCK_ANALYTICS.agreement) : request("GET", "/analytics/agreement"),

  // IRR / inter-rater reliability (Cohen's kappa) pilot. Live-only; in mock mode return
  // honest empty states so the page renders standalone.
  irrListTasks: (): Promise<IrrTask[]> =>
    IS_MOCK ? Promise.resolve([]) : request("GET", "/irr/tasks"),
  irrGetTask: (taskId: string): Promise<IrrTask> => request("GET", `/irr/tasks/${taskId}`),
  irrCreateTask: (input: IrrTaskCreateInput): Promise<IrrTask> =>
    request("POST", "/irr/tasks", input),
  irrCreateAssignment: (
    taskId: string,
    input: { annotator_id: string; independence_group: string }
  ): Promise<IrrAssignmentSummaryLite> =>
    request("POST", `/irr/tasks/${taskId}/assignments`, input),
  irrKappa: (taskId: string): Promise<IrrKappaResult> =>
    request("GET", `/irr/tasks/${taskId}/kappa`),
  irrDisagreements: (taskId: string): Promise<IrrDisagreements> =>
    request("GET", `/irr/tasks/${taskId}/disagreements`),
  irrAdjudicate: (taskId: string, input: IrrAdjudicationInput): Promise<unknown> =>
    request("POST", `/irr/tasks/${taskId}/adjudications`, input),
  irrMyAssignments: (): Promise<{ assignments: IrrMyAssignment[]; count: number }> =>
    IS_MOCK ? Promise.resolve({ assignments: [], count: 0 }) : request("GET", "/irr/assignments/mine"),
  irrAssignmentItems: (assignmentId: string): Promise<IrrItemsResponse> =>
    request("GET", `/irr/assignments/${assignmentId}/items`),
  irrSubmitRecord: (assignmentId: string, input: IrrRecordInput): Promise<unknown> =>
    request("POST", `/irr/assignments/${assignmentId}/records`, input),

  // settings / config (read-only)
  getSettings: (): Promise<AppSettings> =>
    IS_MOCK ? Promise.resolve(MOCK_SETTINGS) : request("GET", "/settings"),
};

type IrrAssignmentSummaryLite = { id: string; annotator_id: string; independence_group: string | null };

// ---- mock stubs (mock mode only) -----------------------------------------
const MOCK_ANALYTICS = {
  overview: {
    patients: 3,
    runs: 3,
    runs_by_status: { succeeded: 3 },
    frames_total: 160,
    frames_gate_failed: 13,
    tracks_total: 88,
    reports_total: 43,
    gate_failed_rate: 0.0813,
    avg_reports_per_patient: 14.33,
  } as AnalyticsOverview,
  recist: {
    by_assessment: { CR: 0, PR: 2, SD: 2, PD: 0, NE: 0 },
    total_assessments: 4,
    by_run_best_overall: { CR: 0, PR: 1, SD: 0, PD: 0, NE: 0 },
    runs_assessed: 1,
  } as RecistDistribution,
  throughput: {
    reviews_total: 2,
    corrections: 0,
    correction_rate: 0,
    tracks_reviewed: 3,
    review_sessions: 1,
    patients_reviewed: 1,
    total_active_review_seconds: 262,
    avg_review_seconds_per_patient: 262,
    avg_review_seconds_per_session: 262,
    reviewer_leaderboard: [
      {
        reviewer_id: "demo",
        name: "Demo Reviewer",
        reviews: 2,
        corrections: 0,
        correction_rate: 0,
        active_seconds: 262,
        tracks_reviewed: 3,
      },
    ],
    source: "review_sessions + reviews (attested)",
  } as ReviewThroughput,
  agreement: { available: false, reason: "No annotation data in mock mode." } as AgreementSummary,
};

const MOCK_SETTINGS: AppSettings = {
  llm_provider: "openrouter",
  llm_model: "deepseek/deepseek-v4-pro",
  available_models: [
    "deepseek/deepseek-v4-pro",
    "openai/gpt-5.5",
    "anthropic/claude-opus-4.8",
    "google/gemini-3-pro",
    "meta-llama/llama-4-405b-instruct",
  ],
  reasoning_effort: "medium",
  temperature: 0,
  engine_git_sha: "mockmode000000",
  region: "ap-southeast-1",
  env: "dev",
  read_only: true,
};
