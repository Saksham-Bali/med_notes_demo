/**
 * In-memory mock backend. Implements the full `/api/v1` surface used by the UI so
 * the app runs standalone (no backend, no Supabase) for the demo. State lives in a
 * module singleton persisted to sessionStorage so it survives client navigations.
 */
import type {
  AuditPacket,
  ConfirmedTrack,
  CreatePatientInput,
  CreateReportInput,
  Digest,
  LinkDecision,
  LinkDecisionInput,
  Me,
  Patient,
  RecistAssessment,
  RecistContrast,
  RecistResult,
  Report,
  Review,
  ReviewInput,
  ReviewSession,
  Run,
  TargetLesion,
  TargetLesionInput,
  Track,
} from "./types";
import {
  MOCK_GATE_FAILED,
  MOCK_MANIFEST,
  MOCK_MEASUREMENTS_MM,
  MOCK_ORG,
  MOCK_SECTIONS,
  MOCK_TRACKS,
  seedPatient,
  seedReports,
} from "./mockData";

interface MockState {
  patients: Patient[];
  reports: Record<string, Report[]>; // patientId -> reports
  runs: Record<string, Run[]>; // patientId -> runs
  reviews: Record<string, Review[]>; // runId -> reviews
  linkDecisions: Record<string, LinkDecision[]>; // runId -> decisions
  targets: Record<string, TargetLesion[]>; // runId -> target lesions
  targetBaselineRV: Record<string, string>; // runId -> baseline report version id
  signoffs: Record<string, Array<AuditPacket["signoffs"][number]>>; // patientId -> signoffs
  sessions: ReviewSession[];
}

const KEY = "ff_mock_state_v1";

function seed(): MockState {
  const p = seedPatient();
  const reports = seedReports();
  const run: Run = {
    id: "run-tmc-0417-1",
    patient_id: p.id,
    status: "succeeded",
    manifest_hash: MOCK_MANIFEST.manifest_hash,
    engine_git_sha: MOCK_MANIFEST.engine_git_sha,
    model_provider: MOCK_MANIFEST.model_provider,
    model_id: MOCK_MANIFEST.model_id,
    prompt_version: MOCK_MANIFEST.prompt_version,
    schema_version: MOCK_MANIFEST.schema_version,
    temperature: MOCK_MANIFEST.temperature,
    progress_done: 3,
    progress_total: 3,
    cost_usd: 0.042,
    latency_seconds: 111,
    created_at: "2025-07-15T10:02:00Z",
    started_at: "2025-07-15T10:02:05Z",
    finished_at: "2025-07-15T10:03:56Z",
  };
  return {
    patients: [{ ...p, latest_run: { id: run.id, status: run.status, created_at: run.created_at, progress_done: 3, progress_total: 3, manifest_hash: run.manifest_hash } }],
    reports: { [p.id]: reports },
    runs: { [p.id]: [run] },
    reviews: {},
    linkDecisions: {},
    targets: {},
    targetBaselineRV: {},
    signoffs: {},
    sessions: [],
  };
}

let _state: MockState | null = null;

function load(): MockState {
  if (_state) return _state;
  if (typeof window !== "undefined") {
    const raw = sessionStorage.getItem(KEY);
    if (raw) {
      try {
        _state = JSON.parse(raw) as MockState;
        return _state;
      } catch {
        /* fall through to seed */
      }
    }
  }
  _state = seed();
  save();
  return _state;
}

function save() {
  if (typeof window !== "undefined" && _state) {
    sessionStorage.setItem(KEY, JSON.stringify(_state));
  }
}

function delay<T>(v: T, ms = 220): Promise<T> {
  return new Promise((r) => setTimeout(() => r(v), ms));
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

async function sha256Hex(s: string): Promise<string> {
  if (typeof window !== "undefined" && window.crypto?.subtle) {
    const buf = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
  // deterministic fallback
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16).padStart(8, "0").repeat(8);
}

// ---- Handlers -------------------------------------------------------------

export const mock = {
  async me(): Promise<Me> {
    return delay({
      user: { id: "mock-user", email: "reviewer@findingframe.dev", full_name: "Demo Reviewer" },
      orgs: [MOCK_ORG],
    });
  },

  async listPatients(): Promise<Patient[]> {
    return delay(load().patients);
  },

  async getPatient(id: string): Promise<Patient> {
    const p = load().patients.find((x) => x.id === id);
    if (!p) throw new ApiNotFound("patient");
    return delay(p);
  },

  async createPatient(input: CreatePatientInput): Promise<Patient> {
    const s = load();
    const p: Patient = {
      id: uid("pat"),
      subject_code: input.subject_code,
      cancer_type: input.cancer_type ?? null,
      report_count: 0,
      has_identifiers: Boolean(input.identifiers?.mrn || input.identifiers?.name),
      created_at: new Date().toISOString(),
      latest_run: null,
    };
    s.patients = [p, ...s.patients];
    s.reports[p.id] = [];
    s.runs[p.id] = [];
    save();
    return delay(p);
  },

  async deleteIdentifiers(id: string): Promise<void> {
    const s = load();
    const p = s.patients.find((x) => x.id === id);
    if (p) p.has_identifiers = false;
    save();
    return delay(undefined);
  },

  async listReports(patientId: string): Promise<Report[]> {
    return delay(load().reports[patientId] ?? []);
  },

  async createReports(patientId: string, inputs: CreateReportInput[]): Promise<Report[]> {
    const s = load();
    const list = s.reports[patientId] ?? [];
    const created: Report[] = [];
    for (const inp of inputs) {
      const rvId = uid("rv");
      const rep: Report = {
        id: uid("rep"),
        report_date: inp.report_date,
        note_type: inp.note_type,
        external_note_id: inp.external_note_id ?? null,
        version_count: 1,
        current_version: {
          id: rvId,
          version_no: 1,
          text_sha256: (await sha256Hex(inp.text)).slice(0, 12),
          text: inp.text,
        },
      };
      list.push(rep);
      created.push(rep);
    }
    s.reports[patientId] = list;
    const p = s.patients.find((x) => x.id === patientId);
    if (p) p.report_count = list.length;
    save();
    return delay(created);
  },

  async listRuns(patientId: string): Promise<Run[]> {
    return delay(load().runs[patientId] ?? []);
  },

  async getRun(runId: string): Promise<Run> {
    const s = load();
    for (const runs of Object.values(s.runs)) {
      const r = runs.find((x) => x.id === runId);
      if (r) {
        // advance a simulated in-progress run each poll
        if (r.status === "queued") {
          r.status = "running";
          r.started_at = new Date().toISOString();
          r.progress_done = 0;
        } else if (r.status === "running") {
          r.progress_done = Math.min((r.progress_done ?? 0) + 1, r.progress_total ?? 1);
          if ((r.progress_done ?? 0) >= (r.progress_total ?? 1)) {
            r.status = "succeeded";
            r.finished_at = new Date().toISOString();
            r.cost_usd = Number(((r.progress_total ?? 1) * 0.014).toFixed(3));
            r.latency_seconds = (r.progress_total ?? 1) * 37;
          }
        }
        save();
        return delay({ ...r }, 150);
      }
    }
    throw new ApiNotFound("run");
  },

  async createRun(patientId: string): Promise<Run> {
    const s = load();
    const reports = s.reports[patientId] ?? [];
    // idempotent: return the existing succeeded run if present
    const existing = (s.runs[patientId] ?? []).find((r) => r.status === "succeeded");
    if (existing) return delay(existing);
    const total = Math.max(reports.length, 1);
    const run: Run = {
      id: uid("run"),
      patient_id: patientId,
      status: "queued",
      manifest_hash: MOCK_MANIFEST.manifest_hash,
      engine_git_sha: MOCK_MANIFEST.engine_git_sha,
      model_provider: MOCK_MANIFEST.model_provider,
      model_id: MOCK_MANIFEST.model_id,
      prompt_version: MOCK_MANIFEST.prompt_version,
      schema_version: MOCK_MANIFEST.schema_version,
      temperature: MOCK_MANIFEST.temperature,
      progress_done: 0,
      progress_total: total,
      created_at: new Date().toISOString(),
    };
    s.runs[patientId] = [run, ...(s.runs[patientId] ?? [])];
    const p = s.patients.find((x) => x.id === patientId);
    if (p) p.latest_run = { id: run.id, status: run.status, created_at: run.created_at, progress_done: 0, progress_total: total, manifest_hash: run.manifest_hash };
    save();
    return delay(run);
  },

  async getDigest(runId: string): Promise<Digest> {
    // The seeded run carries the full demo digest; freshly-created runs (from
    // demo report uploads) reuse the same shape so the workbench is always rich.
    return delay({
      run_id: runId,
      patient: { id: "pat-tmc-0417", subject_code: "TMC-0417", cancer_type: "Non-small-cell lung carcinoma" },
      report_count: 3,
      sections: MOCK_SECTIONS,
      gate_failed: MOCK_GATE_FAILED,
      manifest: MOCK_MANIFEST as Digest["manifest"],
    });
  },

  async listReviews(runId: string): Promise<Review[]> {
    return delay(load().reviews[runId] ?? []);
  },

  async createReview(runId: string, input: ReviewInput): Promise<Review> {
    const s = load();
    const review: Review = {
      ...input,
      id: uid("rev"),
      run_id: runId,
      reviewer_id: "mock-user",
      model_output_visible: true,
      created_at: new Date().toISOString(),
    };
    s.reviews[runId] = [...(s.reviews[runId] ?? []).filter((r) => r.track_key !== input.track_key), review];
    save();
    return delay(review);
  },

  async listLinkDecisions(runId: string): Promise<LinkDecision[]> {
    return delay(load().linkDecisions[runId] ?? []);
  },

  async createLinkDecision(runId: string, input: LinkDecisionInput): Promise<LinkDecision> {
    const s = load();
    const payload = JSON.stringify({ runId, ...input });
    const decision: LinkDecision = {
      ...input,
      id: uid("link"),
      run_id: runId,
      payload_sha256: await sha256Hex(payload),
      decided_by: "mock-user",
      created_at: new Date().toISOString(),
    };
    s.linkDecisions[runId] = [...(s.linkDecisions[runId] ?? []), decision];
    save();
    return delay(decision);
  },

  async confirmedTracks(runId: string): Promise<ConfirmedTrack[]> {
    const s = load();
    const decisions = s.linkDecisions[runId] ?? [];
    const rejected = new Set<string>();
    const confirmed = new Set<string>();
    const merged = new Map<string, string>(); // related -> resulting/primary
    for (const d of decisions) {
      if (d.decision === "reject") rejected.add(d.primary_track_key);
      if (d.decision === "confirm" || d.decision === "split") confirmed.add(d.primary_track_key);
      if (d.decision === "merge") {
        const target = d.resulting_track_key || d.primary_track_key;
        confirmed.add(target);
        for (const rk of d.related_track_keys ?? []) merged.set(rk, target);
      }
    }
    const out: ConfirmedTrack[] = [];
    for (const t of MOCK_TRACKS) {
      if (rejected.has(t.track_key)) continue;
      if (merged.has(t.track_key)) continue; // folded into another track
      out.push({
        ...t,
        confirmed_track_key: t.track_key,
        confirmed: confirmed.has(t.track_key) || (!t.unresolved_link && !t.false_split_candidate),
      });
    }
    return delay(out);
  },

  async setTargetLesions(runId: string, input: TargetLesionInput): Promise<TargetLesion[]> {
    const s = load();
    const targets: TargetLesion[] = input.selections.map((sel) => {
      const t = MOCK_TRACKS.find((x) => x.track_key === sel.confirmed_track_key);
      return { ...sel, id: uid("tl"), display_name: t?.display_name ?? sel.confirmed_track_key };
    });
    s.targets[runId] = targets;
    s.targetBaselineRV[runId] = input.baseline_report_version_id;
    save();
    return delay(targets);
  },

  async getRecist(runId: string): Promise<RecistResult> {
    const s = load();
    const targets = s.targets[runId] ?? [];
    const confirmed = (s.linkDecisions[runId] ?? []).length > 0;
    if (!confirmed) {
      throw new ApiUnprocessable("No confirmed track links. Confirm track links before computing RECIST.");
    }
    if (targets.length === 0) {
      throw new ApiUnprocessable("No target lesions selected. Select target lesions from confirmed tracks first.");
    }
    return delay(computeRecist(runId, targets));
  },

  async recistContrast(runId: string): Promise<RecistContrast> {
    // Demo the discrepancy: a false split fabricates a "new lesion" -> naive PD,
    // but the human merge collapses it -> confirmed PR. One merge flips PD->PR.
    const naiveDates = ["2025-01-12", "2025-04-08", "2025-07-15"];
    const mk = (
      dates: string[],
      slds: number[],
      classes: string[],
      newLesions: boolean[]
    ) =>
      dates.map((d, i) => {
        const baseline = slds[0];
        const nadir = Math.min(...slds.slice(0, i + 1));
        return {
          assessment_date: `${d}T09:30:00+00:00`,
          sld_mm: slds[i],
          baseline_sld_mm: baseline,
          nadir_sld_mm: nadir,
          pct_from_baseline: Number((((slds[i] - baseline) / baseline) * 100).toFixed(1)),
          pct_from_nadir: Number((((slds[i] - nadir) / nadir) * 100).toFixed(1)),
          classification: classes[i],
          new_lesion: newLesions[i],
        };
      });
    return delay({
      run_id: runId,
      naive: {
        classification: "PD",
        sld_timeline: mk(naiveDates, [53, 44, 43], ["SD", "PD", "SD"], [false, true, false]),
        target_tracks: [
          { track_key: "malignant_mass|lung_upper_lobe|right", organ: "lung", baseline_mm: 32, is_nodal: false, source: "machine" },
          { track_key: "lymphadenopathy|mediastinum_paratracheal|right", organ: "mediastinum", baseline_mm: 18, is_nodal: true, source: "machine" },
        ],
        new_lesion: true,
        rationale:
          "Over the machine tracks as-is, the right-lung nodule first appears after baseline, so RECIST's new-lesion rule fires -> best overall PD. This reflects the deterministic linker's false split, not a confirmed new lesion.",
      },
      confirmed: {
        classification: "PR",
        sld_timeline: mk(naiveDates, [50, 35, 32], ["SD", "PR", "PR"], [false, false, false]),
        target_tracks: [
          { track_key: "malignant_mass|lung_upper_lobe|right", organ: "lung", baseline_mm: 32, is_nodal: false, source: "confirmed" },
          { track_key: "lymphadenopathy|mediastinum_paratracheal|right", organ: "mediastinum", baseline_mm: 18, is_nodal: true, source: "confirmed" },
        ],
        new_lesion: false,
        rationale:
          "After applying the human link decisions (merging the split tracks), no new lesion remains and the SLD trend gives best overall PR.",
      },
      discrepancy: true,
      discrepancy_note:
        "Naive RECIST over the machine tracks = PD (driven by a false split), but after the human link decisions the confirmed call is PR. One merge flips the response.",
    });
  },

  async auditPacketPdf(runId: string): Promise<{ blob: Blob; filename: string }> {
    const packet = await this.auditPacket(runId);
    const blob = new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" });
    return { blob, filename: `audit-packet-${runId}.json` };
  },

  async signoff(patientId: string): Promise<AuditPacket["signoffs"][number]> {
    const s = load();
    const prev = (s.signoffs[patientId] ?? []).slice(-1)[0]?.payload_sha256 ?? null;
    const payload = JSON.stringify({ patientId, at: Date.now(), prev });
    const so = {
      id: uid("so"),
      patient_id: patientId,
      payload_sha256: await sha256Hex(payload),
      prev_signoff_sha256: prev,
      signed_by: "mock-user",
      signed_by_name: "Demo Reviewer",
      signed_at: new Date().toISOString(),
    };
    s.signoffs[patientId] = [...(s.signoffs[patientId] ?? []), so];
    save();
    return delay(so);
  },

  async listSignoffs(patientId: string): Promise<AuditPacket["signoffs"]> {
    return delay(load().signoffs[patientId] ?? []);
  },

  async auditPacket(runId: string): Promise<AuditPacket> {
    const s = load();
    // find patient owning this run
    let patientId = "pat-tmc-0417";
    for (const [pid, runs] of Object.entries(s.runs)) {
      if (runs.some((r) => r.id === runId)) patientId = pid;
    }
    const targets = s.targets[runId] ?? [];
    let recist: RecistResult | null = null;
    if (targets.length && (s.linkDecisions[runId] ?? []).length) recist = computeRecist(runId, targets);

    const frames: AuditPacket["frames"] = [];
    for (const t of MOCK_TRACKS) {
      for (const e of t.events) {
        frames.push({
          track_key: t.track_key,
          finding_type: t.finding_type,
          display_name: t.display_name,
          anatomy: e.anatomy ?? t.anatomy,
          laterality: e.laterality ?? t.laterality,
          assertion: e.assertion,
          measurement: e.measurement ?? null,
          temporal_change: e.temporal_change ?? null,
          evidence_text: e.evidence_text,
          evidence_verified: e.evidence_verified ?? true,
          report_date: e.report_date,
          report_version_id: e.report_version_id,
        });
      }
    }
    for (const g of MOCK_GATE_FAILED) {
      frames.push({
        track_key: g.track_key,
        finding_type: g.finding_type,
        display_name: g.display_name,
        anatomy: g.anatomy,
        laterality: g.laterality,
        assertion: g.assertion,
        measurement: g.measurement ?? null,
        evidence_text: g.evidence_text,
        evidence_verified: false,
        report_date: g.report_date,
      });
    }

    return delay({
      generated_at: new Date().toISOString(),
      patient: { id: patientId, subject_code: "TMC-0417", cancer_type: "Non-small-cell lung carcinoma" },
      manifest: MOCK_MANIFEST as AuditPacket["manifest"],
      frames,
      tracks: MOCK_TRACKS,
      link_decisions: s.linkDecisions[runId] ?? [],
      target_selection: targets,
      recist,
      reviews: s.reviews[runId] ?? [],
      signoffs: s.signoffs[patientId] ?? [],
      timing: {
        first_action_at: new Date(Date.now() - 262_000).toISOString(),
        signoff_at: new Date().toISOString(),
        elapsed_seconds: 262,
        active_review_seconds: 262,
        source: "hash-chained audit_log",
      },
    });
  },

  async startSession(runId: string, patientId?: string): Promise<ReviewSession> {
    const s = load();
    const session: ReviewSession = {
      id: uid("sess"),
      run_id: runId,
      patient_id: patientId ?? null,
      started_at: new Date().toISOString(),
    };
    s.sessions.push(session);
    save();
    return delay(session, 80);
  },

  async endSession(id: string, activeSeconds: number, tracksReviewed: number): Promise<ReviewSession> {
    const s = load();
    const sess = s.sessions.find((x) => x.id === id);
    if (sess) {
      sess.ended_at = new Date().toISOString();
      sess.active_seconds = activeSeconds;
      sess.tracks_reviewed = tracksReviewed;
      save();
      return delay(sess, 80);
    }
    throw new ApiNotFound("session");
  },
};

function computeRecist(runId: string, targets: TargetLesion[]): RecistResult {
  const dates = ["2025-01-12", "2025-04-08", "2025-07-15"];
  const baseline = targets.reduce((sum, t) => sum + (t.baseline_mm || 0), 0);
  let nadir = baseline;
  const assessments: RecistAssessment[] = dates.map((date, idx) => {
    let sld = 0;
    for (const t of targets) {
      const series = MOCK_MEASUREMENTS_MM[t.confirmed_track_key];
      const mm = series?.[date] ?? (idx === 0 ? t.baseline_mm : null);
      if (mm != null) sld += mm;
    }
    nadir = Math.min(nadir, sld);
    const fromBaseline = baseline ? ((sld - baseline) / baseline) * 100 : 0;
    const fromNadir = nadir ? ((sld - nadir) / nadir) * 100 : 0;
    let response: RecistAssessment["response"];
    if (sld === 0) response = "CR";
    else if (fromBaseline <= -30) response = "PR";
    else if (fromNadir >= 20 && sld - nadir >= 5) response = "PD";
    else response = "SD";
    return {
      report_date: date,
      sld_mm: sld,
      response,
      pct_change_from_baseline: Number(fromBaseline.toFixed(1)),
      pct_change_from_nadir: Number(fromNadir.toFixed(1)),
    };
  });
  return {
    run_id: runId,
    target_selection_id: `tsel-${runId}`,
    baseline_sld_mm: baseline,
    targets: targets.map((t) => ({
      confirmed_track_key: t.confirmed_track_key,
      organ: t.organ,
      baseline_mm: t.baseline_mm,
    })),
    assessments,
  };
}

// ---- typed errors ---------------------------------------------------------

export class ApiNotFound extends Error {
  status = 404;
  constructor(entity: string) {
    super(`${entity} not found`);
  }
}
export class ApiUnprocessable extends Error {
  status = 422;
  constructor(msg: string) {
    super(msg);
  }
}
