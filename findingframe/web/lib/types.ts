/**
 * TypeScript DTOs mirroring the FindingFrame backend REST contract (`/api/v1`).
 *
 * Source of truth: docs/BUILD_SPEC.md (REST API contract) and the engine frame/track
 * field names in backend/app/engine. The backend Pydantic schemas were not yet
 * implemented when this was written, so a few field shapes (marked ASSUMED) are the
 * best reasonable reading of the contract; adjust here if the backend differs.
 */

// ---- Identity / org -------------------------------------------------------

export type Role = "admin" | "reviewer" | "viewer";

export interface Org {
  id: string;
  name: string;
  role: Role;
}

export interface Me {
  user: { id: string; email: string; full_name: string | null };
  orgs: Org[];
}

// ---- Patients -------------------------------------------------------------

export interface RunSummary {
  id: string;
  status: RunStatus;
  created_at: string;
  progress_done?: number | null;
  progress_total?: number | null;
  manifest_hash?: string | null;
}

export interface Patient {
  id: string;
  subject_code: string;
  cancer_type: string | null;
  report_count?: number;
  latest_run?: RunSummary | null;
  has_identifiers?: boolean;
  created_at?: string;
}

export interface CreatePatientInput {
  subject_code: string;
  cancer_type?: string;
  identifiers?: { mrn?: string; name?: string; dob?: string };
}

// ---- Reports --------------------------------------------------------------

export interface ReportVersion {
  id: string;
  version_no: number;
  text_sha256: string;
  text?: string;
}

export interface Report {
  id: string;
  report_date: string;
  note_type: string;
  external_note_id?: string | null;
  current_version: ReportVersion;
  version_count?: number;
}

export interface CreateReportInput {
  report_date: string;
  note_type: string;
  external_note_id?: string;
  text: string;
}

// ---- Extraction runs ------------------------------------------------------

export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export interface RunManifest {
  engine_git_sha: string;
  model_provider: string;
  model_id: string;
  prompt_version: string;
  schema_version: string;
  temperature: number;
  reasoning_effort?: string;
  manifest_hash: string;
  report_manifest: Array<{
    source_report_id: string;
    report_version_id?: string | null;
    text_sha256: string;
    chart_date: string;
  }>;
}

export interface Run {
  id: string;
  patient_id: string;
  status: RunStatus;
  manifest_hash: string | null;
  engine_git_sha: string | null;
  model_provider: string | null;
  model_id: string | null;
  prompt_version?: string | null;
  schema_version?: string | null;
  temperature?: number | null;
  progress_done: number | null;
  progress_total: number | null;
  cost_usd?: number | null;
  latency_seconds?: number | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

// ---- Digest / tracks / events --------------------------------------------

export type SectionKey =
  | "needs_attention"
  | "stable"
  | "resolved"
  | "uncertain"
  | "routine_negatives";

export type Assertion =
  | "present"
  | "absent"
  | "uncertain"
  | "resolved"
  | "stable"
  | string;

export interface TrackEvent {
  /** Live API sends `date`; normalized to report_date in the api client. */
  report_date: string;
  source_report_id?: string;
  report_version_id?: string | null;
  assertion: Assertion;
  evidence_text: string;
  measurement?: string | null;
  anatomy?: string | null;
  laterality?: string | null;
  temporal_change?: string | null;
  /** Full text of the source report for the "View full report" expander. */
  full_text: string;
  /** Evidence gate result: false => span not verbatim-locatable => quarantined. */
  evidence_verified?: boolean;
}

export interface Track {
  track_key: string;
  /** Not sent by the backend; derived from finding_type in the api client. */
  display_name: string;
  finding_type: string;
  anatomy?: string | null;
  laterality?: string | null;
  progression: string | null; // NEW / WORSENED / STABLE / IMPROVED / RESOLVED / PRESENT / null
  progression_detail?: string | null;
  latest_status?: string | null;
  measurement_trend?: string | null;
  report_range?: string | null;
  event_count?: number;
  clinical_section?: string | null;
  member_track_keys?: string[];
  unresolved_link: boolean;
  false_split_candidate: boolean;
  events: TrackEvent[];
}

/** A frame whose evidence span failed the gate (evidence_verified=false). */
export interface GateFailedFrame {
  frame_id?: string;
  track_key?: string | null;
  finding_type: string;
  finding_surface?: string | null;
  display_name?: string;
  assertion: Assertion;
  evidence_text: string;
  /** Not sent by the backend for gate-failed frames; derived from report_version_id. */
  report_date?: string;
  source_report_id?: string | null;
  report_version_id?: string | null;
  evidence_span_start?: number;
  evidence_span_end?: number;
  full_text: string;
  anatomy?: string | null;
  laterality?: string | null;
  measurement?: string | null;
  reason?: string | null;
}

export interface Digest {
  run_id: string;
  patient: { id: string; subject_code: string; cancer_type: string | null };
  report_count: number;
  status?: string;
  sections: Record<SectionKey, Track[]>;
  gate_failed: GateFailedFrame[];
  gate_failed_count?: number;
  unresolved_link_count?: number;
  false_split_candidate_count?: number;
  track_count?: number;
  frame_count?: number;
  manifest?: RunManifest;
}

// ---- Reviews (slot-level correctness) ------------------------------------

export interface ReviewInput {
  track_key: string;
  reviewed_value: unknown; // snapshot of exactly what the reviewer saw
  link_correct: boolean;
  type_correct: boolean;
  progression_correct: boolean;
  latest_status_correct: boolean;
  false_merge: boolean;
  false_split: boolean;
  evidence_valid: boolean;
  clinically_significant: boolean;
  correction_finding_type?: string;
  correction_anatomy?: string;
  correction_laterality?: string;
  correction_progression?: string;
  correction_latest_status?: string;
  comment?: string;
}

/** Review as returned by the backend (a subset of ReviewInput is echoed back). */
export interface Review {
  id?: string;
  run_id?: string;
  track_key: string;
  reviewer_id?: string;
  link_correct?: boolean;
  type_correct?: boolean;
  progression_correct?: boolean;
  latest_status_correct?: boolean;
  false_merge?: boolean;
  false_split?: boolean;
  evidence_valid?: boolean;
  clinically_significant?: boolean;
  comment?: string | null;
  model_output_visible: boolean;
  /** 'review' = slot-correctness pass. 'acknowledgement' = new evidence on an
   *  already-confirmed track was shown to the reviewer. */
  review_kind?: "review" | "acknowledgement";
  /** Arbitrary jsonb snapshot of what the reviewer saw. For an acknowledgement it holds
   *  `{ acknowledgement: { gained_event_dates, carried_from_run_id, ... } }`. */
  reviewed_value?: unknown;
  created_at: string;
}

// ---- Human-confirmed linking ---------------------------------------------

export type LinkDecisionKind =
  | "confirm"
  | "merge"
  | "split"
  | "mark_unresolved"
  | "reject";

export interface LinkDecisionInput {
  decision: LinkDecisionKind;
  primary_track_key: string;
  related_track_keys?: string[];
  resulting_track_key?: string;
  rationale?: string;
}

export interface LinkDecision extends LinkDecisionInput {
  id: string;
  run_id: string;
  signature_sha256?: string;
  payload_sha256?: string;
  decided_by?: string;
  decided_at?: string;
  created_at?: string;
}

export interface ConfirmedTrack extends Track {
  confirmed_track_key: string;
  confirmed: boolean;
}

// ---- RECIST ---------------------------------------------------------------

export interface TargetLesionSelection {
  confirmed_track_key: string;
  organ: string;
  baseline_mm: number;
}

export interface TargetLesionInput {
  baseline_report_version_id: string;
  selections: TargetLesionSelection[];
}

export interface TargetLesion extends TargetLesionSelection {
  id?: string;
  display_name?: string;
}

export type RecistResponse = "CR" | "PR" | "SD" | "PD";

/** Per-timepoint RECIST assessment. Field names are defensive: the backend may
 *  send report_date/date and sld_mm/sum_longest_diameter_mm. Empty for the seeded
 *  patient (packet data lacks normalized measurements) — render the empty state. */
export interface RecistAssessment {
  report_date?: string;
  date?: string;
  report_version_id?: string;
  sld_mm?: number;
  sum_longest_diameter_mm?: number;
  response?: RecistResponse | null;
  pct_change_from_baseline?: number | null;
  pct_change_from_nadir?: number | null;
  new_lesions?: boolean;
}

/** Real POST /runs/{id}/recist response. */
export interface RecistResult {
  run_id: string;
  target_selection_id: string | null;
  baseline_sld_mm: number | null;
  targets: TargetLesionSelection[];
  assessments: RecistAssessment[];
}

// ---- RECIST contrast (the money moment) ----------------------------------

export type RecistClassification = RecistResponse | "NE" | string;

export interface ContrastTimepoint {
  assessment_date: string;
  sld_mm: number;
  baseline_sld_mm: number;
  nadir_sld_mm: number;
  pct_from_baseline: number;
  pct_from_nadir: number;
  classification: RecistClassification;
  new_lesion: boolean;
}

export interface ContrastTargetTrack {
  track_key: string;
  organ: string;
  baseline_mm: number;
  is_nodal: boolean;
  source: string; // "machine" | "confirmed"
}

export interface ContrastArm {
  classification: RecistClassification;
  sld_timeline: ContrastTimepoint[];
  target_tracks: ContrastTargetTrack[];
  new_lesion: boolean;
  rationale: string;
}

/** GET /runs/{id}/recist/contrast — naive (machine linking) vs human-confirmed. */
export interface RecistContrast {
  run_id: string;
  naive: ContrastArm;
  confirmed: ContrastArm | null;
  discrepancy: boolean;
  discrepancy_note: string;
}

// ---- Disease trajectory ---------------------------------------------------

export interface ProgressionPoint {
  date: string;
  mm: number;
}

export interface ProgressionTarget {
  confirmed_track_key: string;
  display_name: string;
  finding_type: string | null;
  anatomy: string | null;
  organ: string | null;
  is_nodal: boolean;
  baseline_mm: number;
  series: ProgressionPoint[];
}

export interface ProgressionTimepoint {
  date: string;
  sld_mm: number;
  pct_from_baseline: number;
  pct_from_nadir: number;
  /** RECIST 1.1 needs BOTH >=20% and >=5mm over nadir to call PD, so both are carried. */
  abs_from_nadir_mm: number;
  classification: RecistClassification;
  new_lesion: boolean;
}

/** GET /runs/{id}/recist/progression — per-lesion diameters + the SLD timeline. */
export interface RecistProgression {
  run_id: string;
  baseline_sld_mm: number;
  baseline_date: string | null;
  nadir_sld_mm: number | null;
  nadir_date: string | null;
  targets: ProgressionTarget[];
  /** Selected targets not human-confirmed on THIS run — on an incremental run, the
   *  lesions reopened for re-attestation. While non-empty the trajectory is incomplete. */
  unconfirmed_targets: { confirmed_track_key: string; display_name: string }[];
  timeline: ProgressionTimepoint[];
}

// ---- Sign-off / audit -----------------------------------------------------

export interface Signoff {
  id?: string;
  patient_id?: string;
  scope?: string;
  payload_sha256: string;
  prev_signoff_sha256: string | null;
  row_sha256?: string | null;
  signed_by: string;
  signed_by_name?: string | null;
  signed_at: string;
}

export interface AuditFrame {
  frame_id?: string;
  track_key?: string | null;
  finding_type: string;
  finding_surface?: string | null;
  display_name?: string;
  anatomy?: string | null;
  laterality?: string | null;
  assertion: Assertion;
  measurement?: string | null;
  temporal_change?: string | null;
  evidence_text: string;
  evidence_verified: boolean;
  review_only?: boolean;
  report_date?: string;
  source_report_id?: string | null;
  report_version_id?: string | null;
  evidence_span_start?: number;
  evidence_span_end?: number;
}

/** Signed link decision as returned inside the audit packet (decided_at / signature_sha256). */
export interface AuditLinkDecision {
  id?: string;
  decision: LinkDecisionKind;
  primary_track_key: string;
  related_track_keys?: string[];
  resulting_track_key?: string | null;
  rationale?: string | null;
  decided_by?: string;
  decided_at?: string;
  signature_sha256?: string;
}

export interface AuditTargetSelection {
  selected_at?: string;
  selections: TargetLesionSelection[];
  signature_sha256?: string;
}

/** Tamper-evident read-time, derived from the hash-chained audit_log. */
export interface AuditTiming {
  first_action_at?: string | null;
  signoff_at?: string | null;
  elapsed_seconds?: number | null;
  active_review_seconds?: number | null;
  source?: string;
}

export interface AuditPacket {
  generated_at?: string;
  patient: { id: string; subject_code: string; cancer_type: string | null };
  manifest: RunManifest & { created_at?: string; finished_at?: string; status?: string };
  frames: AuditFrame[];
  tracks: Track[];
  link_decisions: AuditLinkDecision[];
  target_selection: AuditTargetSelection | TargetLesion[] | null;
  recist: RecistResult | RecistAssessment[] | null;
  reviews: Review[];
  signoffs: Signoff[];
  timing?: AuditTiming;
}

// ---- Audit log ------------------------------------------------------------

export interface AuditLogEntry {
  id: number;
  action: string;
  entity_type: string;
  entity_id?: string;
  actor_id?: string;
  request_id?: string;
  prev_hash?: string | null;
  row_hash?: string | null;
  created_at: string;
}

// ---- Review sessions (time-saved ROI) ------------------------------------

export interface ReviewSession {
  id: string;
  run_id?: string | null;
  patient_id?: string | null;
  started_at: string;
  ended_at?: string | null;
  active_seconds?: number | null;
  tracks_reviewed?: number | null;
}

// ---- Analytics ------------------------------------------------------------

export interface AnalyticsOverview {
  patients: number;
  runs: number;
  runs_by_status: Record<string, number>;
  frames_total: number;
  frames_gate_failed: number;
  tracks_total: number;
  reports_total: number;
  /** 0..1 fraction of frames whose evidence span failed the gate. */
  gate_failed_rate: number;
  avg_reports_per_patient: number;
}

export type RecistClass = "CR" | "PR" | "SD" | "PD" | "NE";

export interface RecistDistribution {
  by_assessment: Record<RecistClass, number>;
  total_assessments: number;
  by_run_best_overall: Record<RecistClass, number>;
  runs_assessed: number;
}

export interface ReviewerLeaderboardRow {
  reviewer_id: string;
  name: string;
  reviews: number;
  corrections: number;
  correction_rate: number;
  active_seconds: number;
  tracks_reviewed: number;
}

export interface ReviewThroughput {
  reviews_total: number;
  corrections: number;
  correction_rate: number;
  tracks_reviewed: number;
  review_sessions: number;
  patients_reviewed: number;
  total_active_review_seconds: number;
  avg_review_seconds_per_patient: number;
  avg_review_seconds_per_session: number;
  reviewer_leaderboard: ReviewerLeaderboardRow[];
  source: string;
}

export interface AgreementSummary {
  available: boolean;
  counts?: Record<string, number>;
  reason?: string | null;
  note?: string | null;
  items_annotated?: number | null;
  items_adjudicated?: number | null;
}

// ---- IRR / inter-rater reliability (Cohen's kappa) pilot -----------------

export type IrrUnit = "slot" | "frame" | "track";

export interface IrrAssignmentSummary {
  id: string;
  annotator_id: string;
  annotator_name?: string | null;
  run_id?: string | null;
  independence_group: string | null;
  model_output_visible: boolean;
  status: string;
  n_records: number;
  created_at?: string;
}

export interface IrrTask {
  id: string;
  name: string;
  protocol_id: string;
  unit_of_agreement: IrrUnit;
  description?: string | null;
  run_id?: string | null;
  sampling?: Record<string, unknown>;
  item_refs?: string[];
  n_items: number;
  created_at: string;
  n_assignments?: number;
  n_groups?: number;
  n_annotators?: number;
  assignments?: IrrAssignmentSummary[];
}

export interface IrrTaskCreateInput {
  name: string;
  unit_of_agreement: IrrUnit;
  run_id: string;
  sample_size: number;
  description?: string;
  protocol_id?: string;
}

export interface IrrKappaSlot {
  slot: string;
  n: number;
  observed_agreement: number | null;
  kappa: number | null;
  ci_low: number | null;
  ci_high: number | null;
  band: string;
}

export interface IrrKappaReader {
  annotator_id: string;
  annotator_name?: string | null;
  n_records: number;
  model_output_visible?: boolean;
}

export interface IrrKappaGroup {
  independence_group: string | null;
  scoreable: boolean;
  reason?: string;
  anchored_warning?: boolean;
  readers: IrrKappaReader[];
  n_common_items?: number;
  coverage_only_a?: number;
  coverage_only_b?: number;
  slots: IrrKappaSlot[];
}

export interface IrrKappaResult {
  available: boolean;
  reason?: string;
  task: IrrTask;
  groups: IrrKappaGroup[];
  landis_koch: Array<{ range: string; label: string }>;
}

export interface IrrMyAssignment {
  id: string;
  task_id: string;
  task_name: string;
  unit_of_agreement: IrrUnit;
  independence_group: string | null;
  model_output_visible: boolean;
  status: string;
  n_items: number;
  n_records: number;
  created_at?: string;
}

export interface IrrBlindedItem {
  item_ref: string;
  source_report_id?: string | null;
  evidence_text?: string | null;
  evidence_span_start?: number | null;
  evidence_span_end?: number | null;
  report_version_id?: string | null;
  full_text?: string | null;
  submitted?: boolean;
  // track-unit items instead carry member_evidence
  member_evidence?: Array<{ evidence_text: string; source_report_id?: string | null; full_text?: string | null }>;
}

export interface IrrItemsResponse {
  assignment: {
    id: string;
    task_id: string;
    task_name: string;
    unit_of_agreement: IrrUnit;
    independence_group: string | null;
    status: string;
  };
  blinded: boolean;
  model_output_visible: boolean;
  slot_fields: string[];
  n_items: number;
  n_submitted: number;
  items: IrrBlindedItem[];
}

export interface IrrRecordInput {
  item_ref: string;
  labels: Record<string, unknown>;
}

export interface IrrDisagreement {
  item_ref: string;
  independence_group: string | null;
  resolves_assignment_ids: string[];
  differing_slots: string[];
  reader_a: { annotator_id: string; annotator_name?: string | null; labels: Record<string, unknown> };
  reader_b: { annotator_id: string; annotator_name?: string | null; labels: Record<string, unknown> };
  evidence_text?: string | null;
  model?: Record<string, unknown>;
}

export interface IrrDisagreements {
  task: IrrTask;
  count: number;
  disagreements: IrrDisagreement[];
}

export interface IrrAdjudicationInput {
  item_ref: string;
  resolves_assignment_ids: string[];
  consensus: Record<string, unknown>;
  emit_gold?: boolean;
}

// ---- Settings / config ----------------------------------------------------

export interface AppSettings {
  llm_provider: string;
  llm_model: string;
  available_models: string[];
  reasoning_effort: string;
  temperature: number;
  engine_git_sha: string;
  region: string;
  env: string;
  read_only: boolean;
  prompt_version?: string | null;
  schema_version?: string | null;
}

// ---- Section metadata (frontend presentation) ----------------------------

export const SECTION_ORDER: SectionKey[] = [
  "needs_attention",
  "uncertain",
  "stable",
  "resolved",
  "routine_negatives",
];

export const SECTION_META: Record<
  SectionKey,
  { label: string; description: string; tone: "danger" | "warn" | "good" | "info" | "quiet" }
> = {
  needs_attention: {
    label: "Needs attention",
    description: "New or worsened findings",
    tone: "danger",
  },
  uncertain: {
    label: "Uncertain",
    description: "Indeterminate or ambiguous findings",
    tone: "warn",
  },
  stable: {
    label: "Stable",
    description: "Active but unchanged findings",
    tone: "info",
  },
  resolved: {
    label: "Resolved / improved",
    description: "Findings that improved or cleared",
    tone: "good",
  },
  routine_negatives: {
    label: "Routine negatives",
    description: "Absent throughout — batch-verifiable",
    tone: "quiet",
  },
};

// ---- Run delta (what one new report actually changed) ---------------------

/** How a previously-confirmed lesion identity fared when a new report arrived. */
export type IdentityStatus = "carry" | "acknowledge" | "reopen" | "new";

export interface DeltaIdentity {
  confirmed_track_key: string;
  status: IdentityStatus;
  reason: string;
  member_track_keys: string[];
  gained_event_dates: string[];
  /** A per-report catch-all fragment, not a lesion that links across scans. */
  review_only?: boolean;
}

export interface RunDelta {
  run_id: string;
  parent_run_id: string;
  /** RECIST call on the parent run, and what it becomes with the new evidence. */
  recist_call_before: string | null;
  recist_call_after: string | null;
  category_moved: boolean;
  /** The whole history this run covers. */
  reports_total: number;
  /** How many of them the model actually had to read. */
  llm_calls: number | null;
  cache_served: number;
  reports_added: { report_version_id: string; source_report_id: string; chart_date: string }[];
  identities: DeltaIdentity[];
  counts: Record<IdentityStatus, number>;
  carried_member_track_keys: string[];
  /** Present on the apply response only. */
  carried_link_decisions?: number;
  carried_target_selection?: boolean;
}

export const IDENTITY_META: Record<
  IdentityStatus,
  { label: string; description: string; tone: "danger" | "warn" | "good" | "info" | "quiet" }
> = {
  carry: {
    label: "Carried forward",
    description: "Identity unchanged — the earlier confirmation still stands",
    tone: "good",
  },
  acknowledge: {
    label: "New evidence",
    description: "Same lesion, new measurement — acknowledge what was added",
    tone: "info",
  },
  reopen: {
    label: "Needs re-confirmation",
    description: "The identity picture changed, so it is asked again",
    tone: "warn",
  },
  new: {
    label: "New finding",
    description: "First seen on this report — needs a fresh decision",
    tone: "danger",
  },
};
