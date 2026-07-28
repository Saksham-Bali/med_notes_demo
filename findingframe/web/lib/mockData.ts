/**
 * Realistic in-memory demo dataset for mock mode. One lung-cancer patient with a
 * longitudinal CT series: a measurable primary mass, mediastinal nodes, a liver
 * lesion, an unresolved-link / false-split pair (RUL nodule vs right-lung nodule),
 * routine negatives, and a gate-failed frame that must be quarantined.
 */
import type {
  Digest,
  GateFailedFrame,
  Patient,
  Report,
  Track,
  TrackEvent,
} from "./types";

export const MOCK_ORG = { id: "org-tmc", name: "Tata Memorial (demo org)", role: "reviewer" as const };

// Full source report texts. Evidence sentences below are verbatim substrings of these.
const RPT_1 = `CT CHEST WITH CONTRAST — 2025-01-12

CLINICAL HISTORY: 61M, newly diagnosed non-small-cell lung carcinoma. Baseline staging.

FINDINGS:
Lungs: There is a 32 mm spiculated mass in the right upper lobe. No additional pulmonary nodules are identified in the left lung. No pleural effusion. No pneumothorax.
Mediastinum: Enlarged right paratracheal lymph node measuring 18 mm in short axis. No pericardial effusion.
Upper abdomen: A 21 mm hypodense lesion in hepatic segment VII, indeterminate.
Bones: No aggressive osseous lesion.

IMPRESSION: Right upper lobe primary lung carcinoma with mediastinal nodal involvement. Indeterminate hepatic lesion — recommend correlation.`;

const RPT_2 = `CT CHEST WITH CONTRAST — 2025-04-08

CLINICAL HISTORY: NSCLC on first-line therapy. Restaging.

FINDINGS:
Lungs: The right upper lobe mass now measures 24 mm, decreased from prior. Small right lung nodule 6 mm, likely inflammatory. Trace right pleural effusion, new.
Mediastinum: Right paratracheal lymph node now 11 mm, decreased.
Upper abdomen: Hepatic segment VII lesion now 14 mm, decreased.

IMPRESSION: Partial response of the primary mass and nodal disease. New trace right effusion. New small right lung nodule — likely inflammatory, short-interval follow-up.`;

const RPT_3 = `CT CHEST WITH CONTRAST — 2025-07-15

CLINICAL HISTORY: NSCLC, restaging.

FINDINGS:
Lungs: Right upper lobe mass measures 22 mm, stable. The previously noted right lung nodule is no longer visualized. No pleural effusion.
Mediastinum: Right paratracheal lymph node 10 mm, stable.
Upper abdomen: Hepatic segment VII lesion 13 mm, stable. Findings likely reflect treatment effect.
Additional: Trace pericardial fluid noted.

IMPRESSION: Stable disease. Resolved right pleural effusion and right lung nodule.`;

export const MOCK_REPORT_TEXTS: Record<string, string> = {
  "rv-1": RPT_1,
  "rv-2": RPT_2,
  "rv-3": RPT_3,
};

const DATES = ["2025-01-12", "2025-04-08", "2025-07-15"];

function ev(
  i: number,
  assertion: string,
  evidence_text: string,
  measurement: string | null,
  anatomy: string,
  laterality: string | null,
  full_text: string,
  evidence_verified = true,
  temporal_change: string | null = null
): TrackEvent {
  return {
    report_date: DATES[i],
    source_report_id: `report_${i + 1}`,
    report_version_id: `rv-${i + 1}`,
    assertion,
    evidence_text,
    measurement,
    anatomy,
    laterality,
    temporal_change,
    full_text,
    evidence_verified,
  };
}

// ---- Tracks ---------------------------------------------------------------

const trackPrimary: Track = {
  track_key: "malignant_mass|lung_upper_lobe|right",
  display_name: "Primary lung mass",
  finding_type: "malignant_mass",
  anatomy: "right upper lobe",
  laterality: "right",
  progression: "IMPROVED",
  progression_detail: "32 → 24 → 22 mm over 3 studies",
  latest_status: "present, improving",
  measurement_trend: "32 mm → 24 mm → 22 mm",
  unresolved_link: false,
  false_split_candidate: false,
  events: [
    ev(0, "present", "There is a 32 mm spiculated mass in the right upper lobe.", "32 mm", "right upper lobe", "right", RPT_1),
    ev(1, "present", "The right upper lobe mass now measures 24 mm, decreased from prior.", "24 mm", "right upper lobe", "right", RPT_2, true, "decreased"),
    ev(2, "present", "Right upper lobe mass measures 22 mm, stable.", "22 mm", "right upper lobe", "right", RPT_3, true, "stable"),
  ],
};

const trackNode: Track = {
  track_key: "lymphadenopathy|mediastinum_paratracheal|right",
  display_name: "Mediastinal lymph node",
  finding_type: "lymphadenopathy",
  anatomy: "right paratracheal",
  laterality: "right",
  progression: "IMPROVED",
  progression_detail: "18 → 11 → 10 mm short axis",
  latest_status: "present, improving",
  measurement_trend: "18 mm → 11 mm → 10 mm",
  unresolved_link: false,
  false_split_candidate: false,
  events: [
    ev(0, "present", "Enlarged right paratracheal lymph node measuring 18 mm in short axis.", "18 mm", "right paratracheal", "right", RPT_1),
    ev(1, "present", "Right paratracheal lymph node now 11 mm, decreased.", "11 mm", "right paratracheal", "right", RPT_2, true, "decreased"),
    ev(2, "present", "Right paratracheal lymph node 10 mm, stable.", "10 mm", "right paratracheal", "right", RPT_3, true, "stable"),
  ],
};

const trackLiver: Track = {
  track_key: "metastasis|liver_segment_vii|na",
  display_name: "Hepatic lesion",
  finding_type: "metastasis",
  anatomy: "hepatic segment VII",
  laterality: null,
  progression: "IMPROVED",
  progression_detail: "21 → 14 → 13 mm",
  latest_status: "present, improving",
  measurement_trend: "21 mm → 14 mm → 13 mm",
  unresolved_link: false,
  false_split_candidate: false,
  events: [
    ev(0, "present", "A 21 mm hypodense lesion in hepatic segment VII, indeterminate.", "21 mm", "hepatic segment VII", null, RPT_1),
    ev(1, "present", "Hepatic segment VII lesion now 14 mm, decreased.", "14 mm", "hepatic segment VII", null, RPT_2, true, "decreased"),
    ev(2, "present", "Hepatic segment VII lesion 13 mm, stable.", "13 mm", "hepatic segment VII", null, RPT_3, true, "stable"),
  ],
};

// Unresolved link / false-split pair: "right upper lobe nodule" that the linker
// split from a later "right lung nodule". Reviewer must confirm/merge/split.
const trackNoduleA: Track = {
  track_key: "pulmonary_nodule|lung_upper_lobe|right",
  display_name: "Pulmonary nodule (RUL)",
  finding_type: "pulmonary_nodule",
  anatomy: "right upper lobe",
  laterality: "right",
  progression: "UNCERTAIN",
  progression_detail: "possible split from right-lung nodule track",
  latest_status: "uncertain",
  measurement_trend: null,
  unresolved_link: true,
  false_split_candidate: true,
  events: [
    ev(0, "absent", "No additional pulmonary nodules are identified in the left lung.", null, "left lung", "left", RPT_1),
  ],
};

const trackNoduleB: Track = {
  track_key: "pulmonary_nodule|lung|right",
  display_name: "Pulmonary nodule (right lung)",
  finding_type: "pulmonary_nodule",
  anatomy: "right lung",
  laterality: "right",
  progression: "RESOLVED",
  progression_detail: "6 mm, then resolved",
  latest_status: "resolved",
  measurement_trend: "6 mm → resolved",
  unresolved_link: true,
  false_split_candidate: true,
  events: [
    ev(1, "present", "Small right lung nodule 6 mm, likely inflammatory.", "6 mm", "right lung", "right", RPT_2),
    ev(2, "resolved", "The previously noted right lung nodule is no longer visualized.", null, "right lung", "right", RPT_3),
  ],
};

const trackEffusion: Track = {
  track_key: "pleural_effusion|pleura|right",
  display_name: "Pleural effusion",
  finding_type: "pleural_effusion",
  anatomy: "pleura",
  laterality: "right",
  progression: "RESOLVED",
  progression_detail: "new trace effusion, then resolved",
  latest_status: "resolved",
  measurement_trend: null,
  unresolved_link: false,
  false_split_candidate: false,
  events: [
    ev(0, "absent", "No pleural effusion.", null, "pleura", "right", RPT_1),
    ev(1, "present", "Trace right pleural effusion, new.", null, "pleura", "right", RPT_2, true, "new"),
    ev(2, "resolved", "No pleural effusion.", null, "pleura", "right", RPT_3),
  ],
};

// Routine negatives — absent throughout, batch-verifiable.
const trackPneumothorax: Track = {
  track_key: "pneumothorax|pleura|na",
  display_name: "Pneumothorax",
  finding_type: "pneumothorax",
  anatomy: "pleura",
  laterality: null,
  progression: "ABSENT THROUGHOUT",
  progression_detail: "absent in all 3 reports",
  latest_status: "absent",
  measurement_trend: null,
  unresolved_link: false,
  false_split_candidate: false,
  events: [ev(0, "absent", "No pneumothorax.", null, "pleura", null, RPT_1)],
};

const trackBone: Track = {
  track_key: "osseous_lesion|bone|na",
  display_name: "Aggressive osseous lesion",
  finding_type: "osseous_lesion",
  anatomy: "bone",
  laterality: null,
  progression: "ABSENT THROUGHOUT",
  progression_detail: "absent in baseline",
  latest_status: "absent",
  measurement_trend: null,
  unresolved_link: false,
  false_split_candidate: false,
  events: [ev(0, "absent", "No aggressive osseous lesion.", null, "bone", null, RPT_1)],
};

const trackPericardial: Track = {
  track_key: "pericardial_effusion|pericardium|na",
  display_name: "Pericardial effusion",
  finding_type: "pericardial_effusion",
  anatomy: "pericardium",
  laterality: null,
  progression: "NEW",
  progression_detail: "trace pericardial fluid on latest study",
  latest_status: "present",
  measurement_trend: null,
  unresolved_link: false,
  false_split_candidate: false,
  events: [
    ev(0, "absent", "No pericardial effusion.", null, "pericardium", null, RPT_1),
    // NOTE: this event's span failed the evidence gate (see gate_failed below).
    ev(2, "present", "Trace pericardial fluid noted.", null, "pericardium", null, RPT_3, false, "new"),
  ],
};

export const MOCK_TRACKS: Track[] = [
  trackPrimary,
  trackNode,
  trackLiver,
  trackNoduleA,
  trackNoduleB,
  trackEffusion,
  trackPericardial,
  trackPneumothorax,
  trackBone,
];

export const MOCK_SECTIONS: Digest["sections"] = {
  needs_attention: [trackPericardial],
  uncertain: [trackNoduleA, trackNoduleB],
  stable: [trackPrimary, trackNode, trackLiver],
  resolved: [trackEffusion],
  routine_negatives: [trackPneumothorax, trackBone],
};

// A frame whose evidence span did NOT verbatim-locate — must be quarantined.
export const MOCK_GATE_FAILED: GateFailedFrame[] = [
  {
    frame_id: "frame-gate-1",
    track_key: "pericardial_effusion|pericardium|na",
    finding_type: "pericardial_effusion",
    display_name: "Pericardial effusion",
    assertion: "present",
    evidence_text: "small pericardial effusion measuring approximately 8 mm",
    report_date: "2025-07-15",
    full_text: RPT_3,
    anatomy: "pericardium",
    laterality: null,
    measurement: "8 mm",
    reason:
      "Evidence span not verbatim-locatable in the source report (report says 'Trace pericardial fluid noted' — no '8 mm' measurement present).",
  },
];

// Measurements used by the mock RECIST computation, keyed by track + timepoint.
export const MOCK_MEASUREMENTS_MM: Record<string, Record<string, number>> = {
  "malignant_mass|lung_upper_lobe|right": {
    "2025-01-12": 32,
    "2025-04-08": 24,
    "2025-07-15": 22,
  },
  "lymphadenopathy|mediastinum_paratracheal|right": {
    "2025-01-12": 18,
    "2025-04-08": 11,
    "2025-07-15": 10,
  },
  "metastasis|liver_segment_vii|na": {
    "2025-01-12": 21,
    "2025-04-08": 14,
    "2025-07-15": 13,
  },
};

export function seedPatient(): Patient {
  return {
    id: "pat-tmc-0417",
    subject_code: "TMC-0417",
    cancer_type: "Non-small-cell lung carcinoma",
    report_count: 3,
    has_identifiers: true,
    created_at: "2025-01-12T09:00:00Z",
  };
}

export function seedReports(): Report[] {
  return [
    {
      id: "rep-1",
      report_date: "2025-01-12",
      note_type: "CT chest w/ contrast",
      external_note_id: "ACC-2025-0112-RR",
      version_count: 1,
      current_version: { id: "rv-1", version_no: 1, text_sha256: "3f1a…c2e9", text: RPT_1 },
    },
    {
      id: "rep-2",
      report_date: "2025-04-08",
      note_type: "CT chest w/ contrast",
      external_note_id: "ACC-2025-0408-RR",
      version_count: 1,
      current_version: { id: "rv-2", version_no: 1, text_sha256: "9b7d…4a11", text: RPT_2 },
    },
    {
      id: "rep-3",
      report_date: "2025-07-15",
      note_type: "CT chest w/ contrast",
      external_note_id: "ACC-2025-0715-RR",
      version_count: 1,
      current_version: { id: "rv-3", version_no: 1, text_sha256: "c40e…88fa", text: RPT_3 },
    },
  ];
}

export const MOCK_MANIFEST = {
  engine_git_sha: "a17c9e4f2b8d6031e5c7a90f4d21b3e8c6f0a95d",
  model_provider: "openrouter",
  model_id: "openai/gpt-5.5",
  prompt_version: "ff-frame-v7",
  schema_version: "frame-schema-v4",
  temperature: 0.0,
  reasoning_effort: "medium",
  manifest_hash: "sha256:2d9f7b1a6c34e0f58a2b9d7c1e4f6083b5a2c9d70e1f4a6b8c3d5e7f9012a4b6c",
  report_manifest: [
    { source_report_id: "report_1", report_version_id: "rv-1", text_sha256: "3f1a…c2e9", chart_date: "2025-01-12" },
    { source_report_id: "report_2", report_version_id: "rv-2", text_sha256: "9b7d…4a11", chart_date: "2025-04-08" },
    { source_report_id: "report_3", report_version_id: "rv-3", text_sha256: "c40e…88fa", chart_date: "2025-07-15" },
  ],
};
