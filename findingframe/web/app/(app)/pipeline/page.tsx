"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { Badge, Card } from "@/components/ui";
import type { Tone } from "@/components/ui";
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  Check,
  ChevronRight,
  Crosshair,
  FileCheck,
  FileJson,
  FileText,
  GitMerge,
  History,
  Inbox,
  Link2,
  ScanSearch,
  Scissors,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

// ---------------------------------------------------------------------------
// Content model
// ---------------------------------------------------------------------------

type PhaseId = "read" | "link" | "attest";

const PHASES: { id: PhaseId; label: string; kicker: string; tone: Tone }[] = [
  { id: "read", label: "Read the report", kicker: "TMC engine", tone: "info" },
  { id: "link", label: "Link across time", kicker: "TMC engine", tone: "info" },
  { id: "attest", label: "Review, score, attest", kicker: "Product", tone: "good" },
];

type Stage = {
  id: string;
  phase: PhaseId;
  icon: LucideIcon;
  title: string;
  tagline: string;
  input: string;
  output: string;
  overview: string[];
  example: React.ReactNode;
  files: string[];
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PipelinePage() {
  const [activeId, setActiveId] = useState<string>("clean");
  const active = STAGES.find((s) => s.id === activeId) ?? STAGES[0];

  return (
    <div className="pb-16">
      <Hero />

      <div className="grid lg:grid-cols-12 gap-6 mt-8">
        {/* Stage list */}
        <div className="lg:col-span-5 min-w-0 space-y-7">
          {PHASES.map((phase, pi) => (
            <div key={phase.id}>
              <div className="flex items-center gap-2 mb-2.5">
                <span className="text-2xs font-semibold uppercase tracking-widest text-ink-faint">
                  Phase {pi + 1} · {phase.label}
                </span>
                <span className="h-px flex-1 bg-line" />
                <Badge tone={phase.tone}>{phase.kicker}</Badge>
              </div>
              <div className="space-y-2">
                {STAGES.filter((s) => s.phase === phase.id).map((s) => (
                  <div key={s.id}>
                    <StageRow
                      stage={s}
                      index={STAGES.indexOf(s) + 1}
                      active={s.id === activeId}
                      onActivate={() => setActiveId(s.id)}
                    />
                    {/* Inline detail on small screens */}
                    {s.id === activeId && (
                      <div className="lg:hidden mt-2 rise">
                        <StageDetail stage={s} index={STAGES.indexOf(s) + 1} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Sticky detail panel on large screens */}
        <div className="hidden lg:block lg:col-span-7 min-w-0">
          <div className="sticky top-20">
            <div key={active.id} className="rise">
              <StageDetail stage={active} index={STAGES.indexOf(active) + 1} />
            </div>
          </div>
        </div>
      </div>

      <Evaluation />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
  const flow = [
    { value: "1", label: "radiology report" },
    { value: "41", label: "finding frames" },
    { value: "19", label: "machine tracks" },
    { value: "12", label: "confirmed tracks" },
    { value: "4", label: "RECIST timepoints" },
    { value: "1", label: "signed packet" },
  ];
  return (
    <div className="rounded-xl border border-line bg-gradient-to-br from-accent-soft/70 via-paper to-paper shadow-card px-6 py-8 sm:px-10 sm:py-10">
      <p className="text-2xs font-semibold uppercase tracking-widest text-accent-ink mb-2">
        How it works
      </p>
      <h1 className="text-2xl sm:text-3xl font-semibold text-ink tracking-tight max-w-2xl">
        From a raw radiology report to a signed RECIST call
      </h1>
      <p className="mt-2 text-sm text-ink-muted max-w-2xl leading-relaxed">
        Twelve stages. The engine reads each report once, links findings across time, and refuses
        to guess when it cannot. A clinician confirms the links, and the product scores, attests
        and exports the result with a hash chain behind every step. Hover any stage to see what it
        does — with real output, not mock-ups.
      </p>

      <div className="mt-6 flex items-center gap-1.5 overflow-x-auto scroll-thin pb-1">
        {flow.map((f, i) => (
          <div key={f.label} className="flex items-center gap-1.5 shrink-0">
            {i > 0 && <ArrowRight className="w-3.5 h-3.5 text-ink-faint" />}
            <div className="rounded-lg border border-line bg-paper px-3 py-1.5 shadow-card">
              <span className="text-sm font-semibold text-ink">{f.value}</span>{" "}
              <span className="text-xs text-ink-muted">{f.label}</span>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-2xs text-ink-faint">
        Counts from demo patient DEMO-NSCLC-01 — four CT scans through the real engine.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage list row
// ---------------------------------------------------------------------------

function StageRow({
  stage,
  index,
  active,
  onActivate,
}: {
  stage: Stage;
  index: number;
  active: boolean;
  onActivate: () => void;
}) {
  const Icon = stage.icon;
  return (
    <button
      onMouseEnter={onActivate}
      onFocus={onActivate}
      onClick={onActivate}
      className={cx(
        "w-full text-left flex items-center gap-3 rounded-xl border px-4 py-3 transition-all duration-150",
        active
          ? "border-accent/50 bg-paper shadow-pop"
          : "border-line bg-paper/60 hover:border-accent/30 hover:bg-paper"
      )}
    >
      <span
        className={cx(
          "w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-colors",
          active ? "bg-accent text-white" : "bg-paper-sunk text-ink-muted"
        )}
      >
        <Icon className="w-[18px] h-[18px]" />
      </span>
      <span className="w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="text-2xs font-mono text-ink-faint">
            {String(index).padStart(2, "0")}
          </span>
          <span className={cx("text-sm font-semibold", active ? "text-ink" : "text-ink-soft")}>
            {stage.title}
          </span>
        </span>
        <span className="block text-xs text-ink-muted truncate">{stage.tagline}</span>
      </span>
      <ChevronRight
        className={cx(
          "w-4 h-4 shrink-0 transition-all",
          active ? "text-accent translate-x-0.5" : "text-ink-faint"
        )}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function StageDetail({ stage, index }: { stage: Stage; index: number }) {
  const phase = PHASES.find((p) => p.id === stage.phase)!;
  const Icon = stage.icon;
  return (
    <Card className="overflow-hidden">
      <div className="px-6 pt-6 pb-5 border-b border-line bg-gradient-to-br from-paper-soft to-paper">
        <div className="flex items-center gap-2 mb-3">
          <Badge tone={phase.tone}>{phase.kicker}</Badge>
          <span className="text-2xs text-ink-faint">
            Stage {String(index).padStart(2, "0")} of {String(STAGES.length).padStart(2, "0")} ·{" "}
            {phase.label}
          </span>
        </div>
        <div className="flex items-start gap-3">
          <span className="w-10 h-10 rounded-lg bg-accent text-white flex items-center justify-center shrink-0">
            <Icon className="w-5 h-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-ink leading-tight">{stage.title}</h2>
            <p className="text-sm text-ink-muted mt-0.5">{stage.tagline}</p>
          </div>
        </div>
      </div>

      <div className="px-6 py-5 space-y-5">
        <div className="space-y-3">
          {stage.overview.map((p, i) => (
            <p key={i} className="text-sm text-ink-soft leading-relaxed">
              {p}
            </p>
          ))}
        </div>

        <div className="flex items-stretch gap-2">
          <div className="flex-1 rounded-lg border border-line bg-paper-soft px-3 py-2">
            <p className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">In</p>
            <p className="text-xs text-ink-soft mt-0.5">{stage.input}</p>
          </div>
          <div className="self-center text-ink-faint">
            <ArrowRight className="w-4 h-4" />
          </div>
          <div className="flex-1 rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2">
            <p className="text-2xs font-semibold uppercase tracking-wide text-accent-ink">Out</p>
            <p className="text-xs text-ink-soft mt-0.5">{stage.output}</p>
          </div>
        </div>

        <div>
          <p className="text-2xs font-semibold uppercase tracking-widest text-ink-faint mb-2">
            Worked example — real output
          </p>
          {stage.example}
        </div>

        <div className="flex flex-wrap gap-1.5 pt-1 border-t border-line-soft">
          {stage.files.map((f) => (
            <span
              key={f}
              className="font-mono text-2xs text-ink-muted bg-paper-sunk rounded px-1.5 py-0.5 mt-2"
            >
              {f}
            </span>
          ))}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Example building blocks
// ---------------------------------------------------------------------------

function Quote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote className="evidence text-ink-soft border-l-2 border-accent/40 pl-3 py-0.5">
      {children}
    </blockquote>
  );
}

function Slot({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md bg-paper-soft border border-line-soft px-2 py-1">
      <p className="text-2xs uppercase tracking-wide text-ink-faint">{k}</p>
      <p className="font-mono text-xs text-ink">{v}</p>
    </div>
  );
}

function FrameBox({
  type,
  tone,
  chip,
  slots,
  note,
}: {
  type: string;
  tone: Tone;
  chip: string;
  slots: [string, string][];
  note?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-paper p-3 shadow-card">
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono text-xs font-semibold text-ink">{type}</span>
        <Badge tone={tone}>{chip}</Badge>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
        {slots.map(([k, v]) => (
          <Slot key={k} k={k} v={v} />
        ))}
      </div>
      {note && <p className="text-2xs text-ink-muted mt-2">{note}</p>}
    </div>
  );
}

function DarkCode({ children }: { children: string }) {
  return (
    <pre className="rounded-lg bg-ink text-[#d5e0ec] font-mono text-xs leading-relaxed p-4 overflow-x-auto scroll-thin">
      {children}
    </pre>
  );
}

function TrackBox({
  trackKey,
  events,
  points,
  tone = "info",
}: {
  trackKey: string;
  events: string;
  points: string[];
  tone?: Tone;
}) {
  return (
    <div className="rounded-lg border border-line bg-paper p-3 shadow-card">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-mono text-xs font-semibold text-ink break-all">{trackKey}</span>
        <Badge tone={tone}>{events}</Badge>
      </div>
      <div className="mt-2 flex items-center gap-1 flex-wrap">
        {points.map((p, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ArrowRight className="w-3 h-3 text-ink-faint" />}
            <span className="rounded bg-paper-sunk font-mono text-xs text-ink-soft px-1.5 py-0.5">
              {p}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function CheckRow({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="w-4 h-4 rounded-full bg-good-soft text-good-ink flex items-center justify-center shrink-0 mt-0.5">
        <Check className="w-3 h-3" />
      </span>
      <p className="text-xs text-ink-soft">
        <span className="font-mono font-semibold text-ink">{label}</span> — {detail}
      </p>
    </div>
  );
}

function NoteBox({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const tones: Record<Tone, string> = {
    danger: "border-danger/30 bg-danger-soft text-danger-ink",
    warn: "border-warn/30 bg-warn-soft text-warn-ink",
    good: "border-good/30 bg-good-soft text-good-ink",
    info: "border-info/30 bg-info-soft text-info-ink",
    quiet: "border-quiet/30 bg-quiet-soft text-quiet-ink",
    neutral: "border-line bg-paper-soft text-ink-soft",
  };
  return (
    <div className={cx("rounded-lg border px-3 py-2 text-xs leading-relaxed", tones[tone])}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Worked examples (all values are real engine / product output for the demo
// patients DEMO-NSCLC-01 and DEMO-NSCLC-LONG-01)
// ---------------------------------------------------------------------------

function CleanExample() {
  const rows: { text: string; badge: string; tone: Tone }[] = [
    {
      text: "CLINICAL HISTORY: Stage IV non-small cell lung carcinoma. Baseline staging…",
      badge: "scope gate",
      tone: "info",
    },
    {
      text: "TECHNIQUE: Multidetector CT was performed from the thoracic inlet through…",
      badge: "dropped",
      tone: "quiet",
    },
    { text: "COMPARISON: None available.", badge: "dropped", tone: "quiet" },
    {
      text: "FINDINGS: There is a spiculated primary mass in the left lower lobe…",
      badge: "kept",
      tone: "good",
    },
    {
      text: "IMPRESSION: 1. Left lower lobe primary NSCLC, 55 mm. 2. Hepatic metastasis…",
      badge: "kept",
      tone: "good",
    },
  ];
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div
          key={r.text}
          className="flex items-center gap-2 rounded-lg border border-line-soft bg-paper px-3 py-2"
        >
          <p className="evidence text-ink-soft flex-1 truncate">{r.text}</p>
          <Badge tone={r.tone}>{r.badge}</Badge>
        </div>
      ))}
      <p className="text-2xs text-ink-muted pt-1">
        Only FINDINGS, IMPRESSION and CONCLUSION reach the model. The history becomes the clinical
        question; boilerplate never enters the prompt.
      </p>
    </div>
  );
}

function ExtractExample() {
  return (
    <div className="space-y-3">
      <Quote>
        “There is a spiculated primary mass in the left lower lobe measuring 55 mm in greatest
        dimension, consistent with the patient’s known non-small cell lung carcinoma.”
      </Quote>
      <div className="flex justify-center text-ink-faint">
        <ArrowDown className="w-4 h-4" />
      </div>
      <FrameBox
        type="primary_tumor"
        tone="danger"
        chip="critical"
        slots={[
          ["assertion", "present"],
          ["anatomy", "left_lower_lobe"],
          ["laterality", "left"],
          ["measurement", "55 mm"],
          ["uncertainty", "definite"],
          ["evidence span", "[434, 597]"],
        ]}
      />
      <Quote>“No pleural effusion.”</Quote>
      <div className="flex justify-center text-ink-faint">
        <ArrowDown className="w-4 h-4" />
      </div>
      <FrameBox
        type="pleural_effusion"
        tone="quiet"
        chip="absent"
        slots={[
          ["assertion", "absent"],
          ["anatomy", "pleural_space"],
          ["laterality", "bilateral"],
          ["importance", "routine_negative"],
        ]}
        note="There are no negated entities. Absence is a frame on the same track — so a finding that disappears has provenance too."
      />
    </div>
  );
}

function GateExample() {
  return (
    <div className="space-y-2">
      <CheckRow
        label="source_verifiable"
        detail="the evidence text exists verbatim in the report; the span is located byte-exact, with token-boundary protection so a fragment cannot match mid-word."
      />
      <CheckRow
        label="readable_span"
        detail="at least five characters and two tokens; no leading punctuation."
      />
      <CheckRow
        label="concept_supported"
        detail="the evidence mentions the finding type or one of its taxonomy synonyms."
      />
      <CheckRow
        label="assertion_supported"
        detail="“absent” needs negation language (no, without, not seen…); “uncertain” needs hedging (possible, cannot exclude…); “present” must not be negated."
      />
      <NoteBox tone="warn">
        A frame whose span cannot be located is marked <span className="font-mono">
        evidence_verified = false</span> and lands in quarantine (stage 08) for mandatory human
        review. It never blends into the digest.
      </NoteBox>
    </div>
  );
}

function RuleLayerExample() {
  return (
    <div className="space-y-3">
      <Quote>“Heart size is normal.”</Quote>
      <div className="flex justify-center text-ink-faint">
        <ArrowDown className="w-4 h-4" />
      </div>
      <FrameBox
        type="cardiomegaly"
        tone="quiet"
        chip="review_only"
        slots={[
          ["assertion", "absent"],
          ["importance", "review_only"],
        ]}
        note="A broad routine negative is demoted: it can never seed a trusted track or link across scans."
      />
      <div className="rounded-lg border border-line bg-paper p-3 shadow-card">
        <p className="text-2xs uppercase tracking-wide text-ink-faint mb-1.5">
          Anatomy view for linking
        </p>
        <div className="flex items-center gap-2 font-mono text-xs text-ink">
          <span className="rounded bg-paper-sunk px-1.5 py-0.5">left_lower_lobe</span>
          <ArrowRight className="w-3 h-3 text-ink-faint" />
          <span className="rounded bg-accent-soft text-accent-ink px-1.5 py-0.5">thorax</span>
        </div>
        <p className="text-2xs text-ink-muted mt-2">
          The raw wording stays on the frame for review; the collapsed view exists only so the
          linker can compare scans. The whole rule layer is content-addressed with a SHA-256
          fingerprint.
        </p>
      </div>
    </div>
  );
}

function LinkExample() {
  return (
    <div className="space-y-3">
      <TrackBox
        trackKey="primary_tumor | thorax | left"
        events="4 events · active"
        points={["55 mm", "46 mm", "38 mm", "34 mm"]}
        tone="good"
      />
      <div className="flex flex-wrap gap-1.5">
        {["new_track ×1", "exact_key ×3"].map((d) => (
          <span
            key={d}
            className="rounded-md border border-line bg-paper-soft font-mono text-2xs text-ink-soft px-2 py-1"
          >
            {d}
          </span>
        ))}
      </div>
      <p className="text-2xs text-ink-muted">
        Four scans, one track. The lung primary links cleanly because its key never changes — no
        similarity score, no guesswork, and every link decision is recorded on the track.
      </p>
    </div>
  );
}

function SplitExample() {
  return (
    <div className="space-y-2">
      <TrackBox
        trackKey="liver_metastasis | liver_segment_vii | right"
        events="1 event"
        points={["40 mm (2025-01-15)"]}
        tone="warn"
      />
      <TrackBox
        trackKey="liver_metastasis | liver | right"
        events="3 events"
        points={["32 mm", "26 mm", "24 mm"]}
        tone="warn"
      />
      <NoteBox tone="danger">
        Baseline says “hepatic segment VII”; follow-ups say “right hepatic lobe”. The anatomy map
        has no segment-VII-to-liver edge, so one shrinking lesion became two tracks — and{" "}
        <span className="font-mono">false_split_candidates: []</span> stayed empty. The split was
        silent. Stage 10 shows what that does to the response call, and why a human confirms every
        link.
      </NoteBox>
    </div>
  );
}

function ArtifactExample() {
  return (
    <DarkCode>
      {`"link_summary": {
  "input_event_count": 41, "track_count": 19,
  "exact_key": 22, "new_track": 19, "unresolved_link": 0
},
"extraction_provenance": {
  "provider": "openrouter", "model": "deepseek/deepseek-v4-pro",
  "prompt_versions": ["finding_frame_prompt_v7_generalization_contract"]
},
"report_manifest_hash": "sha256:…",   // ordered report texts
"rule_layer_provenance": { "fingerprint_sha256": "…" }`}
    </DarkCode>
  );
}

function DigestExample() {
  const sections: { label: string; count: number; tone: Tone }[] = [
    { label: "Needs attention", count: 2, tone: "danger" },
    { label: "Stable", count: 6, tone: "info" },
    { label: "Resolved / improved", count: 3, tone: "good" },
    { label: "Uncertain", count: 1, tone: "warn" },
    { label: "Routine negatives", count: 7, tone: "quiet" },
  ];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {sections.map((s) => (
          <span
            key={s.label}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-2.5 py-1.5 text-xs text-ink-soft shadow-card"
          >
            {s.label}
            <Badge tone={s.tone}>{s.count}</Badge>
          </span>
        ))}
      </div>
      <NoteBox tone="warn">
        Gate-failed frames sit in a separate quarantine list with the reason attached (e.g.{" "}
        <span className="font-mono">evidence_span_not_located</span>). They demand review; they are
        never folded into the sections above.
      </NoteBox>
      <p className="text-2xs text-ink-muted">
        Every event in every section carries its verbatim evidence and the full source report for
        one-click verification.
      </p>
    </div>
  );
}

function LinkDecisionExample() {
  return (
    <div className="space-y-2">
      <DarkCode>
        {`{
  "decision_type": "merge",
  "primary_track_key": "liver_metastasis|liver|right",
  "related_track_keys": ["liver_metastasis|liver_segment_vii|right"],
  "rationale": "Same segment VII deposit; wording changed between scans.",
  "signature_sha256": "…"   // sha256 of the canonical payload
}`}
      </DarkCode>
      <p className="text-2xs text-ink-muted">
        Decisions are append-only: a correction is a new signed row, never an edit. Replaying them
        over the machine tracks yields the confirmed set that all scoring uses.
      </p>
    </div>
  );
}

function RecistExample() {
  const rows = [
    { date: "2025-01-15", n: "95 · baseline", nc: "SD", c: "95 · baseline", cc: "SD" },
    { date: "2025-03-20", n: "86 · “new lesion”", nc: "PD", c: "78 · −17.9%", cc: "SD" },
    { date: "2025-05-22", n: "78 · −17.9%", nc: "SD", c: "64 · −32.6%", cc: "PR" },
    { date: "2025-07-24", n: "74 · −22.1%", nc: "SD", c: "58 · −38.9%", cc: "PR" },
  ];
  const call = (v: string) => (
    <Badge tone={v === "PD" ? "danger" : v === "PR" ? "good" : "quiet"}>{v}</Badge>
  );
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto scroll-thin rounded-lg border border-line">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-paper-soft text-ink-muted">
              <th className="text-left font-medium px-3 py-2">Timepoint</th>
              <th className="text-left font-medium px-3 py-2">Naive (machine tracks)</th>
              <th className="text-left font-medium px-3 py-2">Confirmed (after 1 merge)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.date} className="border-t border-line-soft">
                <td className="px-3 py-2 font-mono text-ink-soft whitespace-nowrap">{r.date}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className="font-mono text-ink-soft mr-2">{r.n}</span>
                  {call(r.nc)}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className="font-mono text-ink-soft mr-2">{r.c}</span>
                  {call(r.cc)}
                </td>
              </tr>
            ))}
            <tr className="border-t border-line bg-paper-soft">
              <td className="px-3 py-2 font-semibold text-ink">Best overall</td>
              <td className="px-3 py-2">{call("PD")}</td>
              <td className="px-3 py-2">{call("PR")}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <NoteBox tone="good">
        The silent liver split (stage 06) made the naive side see a vanished 40 mm lesion plus a
        “new” one — a false progressive-disease call that could end a working therapy. One signed
        merge flips it to the correct partial response. Same math both sides; only the tracks
        differ.
      </NoteBox>
    </div>
  );
}

function CarryForwardExample() {
  const chips: { label: string; tone: Tone }[] = [
    { label: "carry 0", tone: "quiet" },
    { label: "acknowledge 5", tone: "info" },
    { label: "reopen 3", tone: "warn" },
    { label: "new 3", tone: "good" },
  ];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-lg border border-line bg-paper px-2.5 py-1.5 text-xs text-ink-soft shadow-card">
          11 reports · <span className="font-semibold text-ink">1 LLM call</span>
        </span>
        {chips.map((c) => (
          <span
            key={c.label}
            className="inline-flex items-center rounded-lg border border-line bg-paper px-2.5 py-1.5 shadow-card"
          >
            <Badge tone={c.tone}>{c.label}</Badge>
          </span>
        ))}
      </div>
      <Quote>“The left lower lobe primary mass measures 34 mm, increased from 31 mm.”</Quote>
      <NoteBox tone="danger">
        Report 11: SLD 78 mm is −35% from baseline but{" "}
        <span className="font-semibold">+30% from nadir</span> → PD. The nadir that flips the call
        was measured six scans earlier and rode in on carried state — nothing was re-extracted, and
        the three reopened identities are exactly the ones where the new evidence changes the
        answer.
      </NoteBox>
    </div>
  );
}

function SignoffExample() {
  const links = ["signoff #1", "signoff #2", "signoff #3"];
  const contents = [
    "run manifest",
    "frames + verbatim evidence",
    "signed link decisions",
    "target selection",
    "RECIST timeline",
    "review deltas",
    "chain hashes",
  ];
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5 overflow-x-auto scroll-thin pb-1">
        {links.map((l, i) => (
          <div key={l} className="flex items-center gap-1.5 shrink-0">
            {i > 0 && (
              <span className="font-mono text-2xs text-ink-faint whitespace-nowrap">
                prev_hash →
              </span>
            )}
            <div className="rounded-lg border border-line bg-paper px-3 py-2 shadow-card">
              <p className="text-xs font-semibold text-ink">{l}</p>
              <p className="font-mono text-2xs text-ink-faint">row_sha256: 9f2c…</p>
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {contents.map((c) => (
          <span
            key={c}
            className="rounded-md border border-line bg-paper-soft text-2xs text-ink-soft px-2 py-1"
          >
            {c}
          </span>
        ))}
      </div>
      <p className="text-2xs text-ink-muted">
        A database trigger — not the application — computes every hash under an advisory lock, so
        the app cannot forge or reorder the chain. An independent script recomputes both chains
        from scratch.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evaluation footer
// ---------------------------------------------------------------------------

function Evaluation() {
  const stats = [
    { value: "0.855", label: "Type F1 — 30-patient MIMIC-IV cohort, 300 reports" },
    { value: "0.965", label: "Assertion slot accuracy on held-out patients" },
    { value: "96.3%+", label: "Evidence anchoring on external chest X-ray corpora" },
    { value: "0.027", label: "Type F1 spread across four different LLMs" },
  ];
  return (
    <div className="mt-10 rounded-xl border border-line bg-paper shadow-card px-6 py-6 sm:px-8">
      <p className="text-2xs font-semibold uppercase tracking-widest text-ink-faint mb-1">
        Measured, not promised
      </p>
      <h2 className="text-lg font-semibold text-ink">How well does the extraction hold up?</h2>
      <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border border-line-soft bg-paper-soft px-4 py-3">
            <p className="text-xl font-semibold text-ink tracking-tight">{s.value}</p>
            <p className="text-2xs text-ink-muted mt-1 leading-snug">{s.label}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 text-2xs text-ink-muted leading-relaxed max-w-3xl">
        The chest X-ray transfer used a taxonomy swap only — no retraining. Honest caveats: the
        gold standard is engineering-curated, and the blinded clinician agreement study is designed
        and coded but not yet run. Frame-level scores are criterion-sensitive; the numbers above
        come from the frozen evaluation set, not from demos on this page.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage definitions
// ---------------------------------------------------------------------------

const STAGES: Stage[] = [
  {
    id: "clean",
    phase: "read",
    icon: Scissors,
    title: "Clean & section",
    tagline: "Keep the findings, drop the boilerplate.",
    input: "Raw report text, in chart-date order",
    output: "Extraction text (FINDINGS + IMPRESSION) and a clinical-question scope",
    overview: [
      "The cleaner splits each report on roughly 35 known section-header patterns. It keeps FINDINGS, IMPRESSION and CONCLUSION as the text the model will read, and parses CLINICAL HISTORY or INDICATION separately as the clinical question that scopes the extraction.",
      "TECHNIQUE, COMPARISON and other boilerplate never reach the prompt. When no header matches — plain films, terse addenda — it falls back to the full text rather than lose content.",
    ],
    example: <CleanExample />,
    files: ["tmc/extraction/report_cleaner.py"],
  },
  {
    id: "extract",
    phase: "read",
    icon: ScanSearch,
    title: "Extract finding frames",
    tagline: "One LLM call per report turns prose into structured frames.",
    input: "Cleaned report text + clinical indication",
    output: "Validated FindingFrames — 16 slots each, one assertion per frame",
    overview: [
      "One model call per report, with no cross-report context — a deliberate choice that stops details from one scan bleeding into another. The prompt carries a fixed 20-class oncology checklist with definitions, synonyms and exclusion rules, plus a catch-all slot for anything off the list.",
      "Each frame is one evidence-backed assertion: what was found, where, which side, how sure, how big, and how it changed. Negation is not a special case — “No pleural effusion.” becomes a frame asserting absence, so a clean scan leaves the same paper trail as a worrying one.",
      "Every extraction is disk-cached against the exact text, model and prompt version, keyed by engine commit. That cache is what makes incremental runs (stage 11) nearly free.",
    ],
    example: <ExtractExample />,
    files: [
      "tmc/extraction/finding_frame_extractor.py",
      "tmc/extraction/finding_frame_schema.py",
      "tmc/extraction/finding_type_taxonomy.py",
    ],
  },
  {
    id: "gate",
    phase: "read",
    icon: ShieldCheck,
    title: "Evidence gate",
    tagline: "Every frame must point at the exact bytes that justify it.",
    input: "Candidate frames",
    output: "Frames with byte-exact evidence spans, or a quarantine flag",
    overview: [
      "Four deterministic checks run on every frame — no model involved. The quoted evidence must exist verbatim in the source report, read as a sentence fragment a human can judge, mention the finding concept, and actually support the asserted polarity.",
      "The span is located byte-exact in the original text. This is what makes every claim in the product clickable back to the sentence that produced it.",
    ],
    example: <GateExample />,
    files: ["tmc/extraction/finding_frame_schema.py", "findingframe/worker/persist.py"],
  },
  {
    id: "rules",
    phase: "read",
    icon: Wrench,
    title: "Deterministic rule layer",
    tagline: "Normalize for comparison, rescue known misses, demote weak claims.",
    input: "Gated frames",
    output: "Frames with comparison views, rescued findings, review-only demotions",
    overview: [
      "Regex rescues recover findings the model reliably misses — explicit bone metastases, fractures buried in musculoskeletal reports. A slot normalizer then builds comparison views without touching the raw wording: anatomy collapses to a linkable family, and comparative words map through fixed term tables with a negation window, so “not enlarged” never reads as growth.",
      "A trust policy demotes broad routine negatives to review-only and drops catch-alls that duplicate checklist frames. The entire rule layer — tables plus the source of the branching logic — is hashed into a fingerprint, so anyone can tell which rules produced a given set of tracks.",
    ],
    example: <RuleLayerExample />,
    files: ["tmc/extraction/frame_slot_normalizer.py", "tmc/extraction/rule_layer_provenance.py"],
  },
  {
    id: "linking",
    phase: "link",
    icon: GitMerge,
    title: "Longitudinal linking",
    tagline: "Tracks are computed from a composite key, not guessed.",
    input: "Frames from every report, in date order",
    output: "Tracks — one finding followed across scans, with full link history",
    overview: [
      "Every frame becomes an event keyed finding_type | anatomy | laterality, with per-type defaults (ascites lives in the peritoneum, brain metastases are intracranial) and sub-identity for devices, so sternal wires never merge with a central line.",
      "Events fold onto prior tracks one at a time: an exact key match appends; exactly one compatible match through the anatomy hierarchy merges; anything else starts a new track. No similarity model, no threshold to tune — the same inputs always produce the same tracks.",
      "Each track keeps its full event history, latest status, and a count of every link decision that built it.",
    ],
    example: <LinkExample />,
    files: ["tmc/fact_graph/frame_linker.py", "tmc/fact_graph/frame_adapter.py"],
  },
  {
    id: "refuse",
    phase: "link",
    icon: AlertTriangle,
    title: "Refuse to guess",
    tagline: "Ambiguity becomes a queue item, not a silent choice.",
    input: "Link candidates with more than one plausible home",
    output: "An unresolved-link queue and false-split candidates for review",
    overview: [
      "When two or more prior tracks are compatible with a new event, the linker refuses to pick one. The event is minted as its own unresolved track and pushed to a review queue. A second pass scans finished tracks for pairs that look like one lesion split in two, and flags them.",
      "But some splits are silent. The example below never got flagged — the anatomy map simply had no edge between the two wordings. This failure mode is exactly why the product makes a human confirm links before anything is scored.",
    ],
    example: <SplitExample />,
    files: ["tmc/fact_graph/frame_linker.py"],
  },
  {
    id: "artifact",
    phase: "link",
    icon: FileJson,
    title: "Artifact & provenance",
    tagline: "One JSON that can answer: why should I trust this?",
    input: "Frames, tracks, telemetry from every stage",
    output: "A self-describing pipeline artifact with three provenance anchors",
    overview: [
      "Telemetry wraps every step in spans written to an append-only log, and verifiers assert that every report went through every step and that frame and track counts stay consistent — a run that skips a stage fails loudly.",
      "The artifact records who produced it three ways: extraction provenance (provider, model, prompt versions), a hash over the ordered report texts, and the rule-layer fingerprint. Same reports, same model, same rules — provably the same tracks.",
    ],
    example: <ArtifactExample />,
    files: ["tmc/pipeline/finding_frame_processor.py", "tmc/telemetry/verifiers.py"],
  },
  {
    id: "digest",
    phase: "attest",
    icon: Inbox,
    title: "Digest & quarantine",
    tagline: "Everything the clinician sees links to source; gate failures cannot hide.",
    input: "The engine artifact, persisted by the worker in one transaction",
    output: "A sectioned digest with verbatim evidence, plus a quarantine list",
    overview: [
      "A worker claims the run, executes the engine with retries, and persists frames, tracks and events atomically — a crash mid-run never leaves half a result. From here on, everything lives in the product database.",
      "The digest sorts tracks by what a clinician should do about them: needs attention, stable, resolved, uncertain, routine negatives. Every event carries its verbatim evidence and the full source report for click-through. Frames that failed the evidence gate go to a separate quarantine list — mandatory review, never mixed in.",
    ],
    example: <DigestExample />,
    files: ["findingframe/worker/main.py", "findingframe/backend/app/services/digest.py"],
  },
  {
    id: "confirm",
    phase: "attest",
    icon: Link2,
    title: "Confirm links",
    tagline: "A human turns machine tracks into confirmed tracks — append-only and signed.",
    input: "Machine tracks, the unresolved queue, false-split candidates",
    output: "Confirmed tracks derived by replaying signed decisions",
    overview: [
      "Five decisions: confirm, merge, split, mark unresolved, reject. Each one is appended with a SHA-256 signature over its payload — nothing is edited in place, so the record of who decided what, and when, survives any later change of mind.",
      "Replaying the decisions in order over the machine tracks produces the confirmed set. Rejected and unresolved tracks drop out entirely; scoring never sees them.",
    ],
    example: <LinkDecisionExample />,
    files: ["findingframe/backend/app/services/linking.py"],
  },
  {
    id: "recist",
    phase: "attest",
    icon: Crosshair,
    title: "Targets & RECIST 1.1",
    tagline: "One merge flips a false PD into the correct PR.",
    input: "Confirmed tracks + a human target-lesion selection",
    output: "SLD timeline, per-timepoint CR/PR/SD/PD, and the naive-vs-confirmed contrast",
    overview: [
      "Scoring refuses to run without confirmed tracks and a human target selection — the API returns 422, not a best guess. Selection enforces RECIST 1.1 as written: at most five targets, two per organ; non-nodal lesions need 10 mm longest diameter, nodes 15 mm short axis.",
      "Per timepoint, the sum of longest diameters carries each target's last measurement forward. Any new lesion means progressive disease; +20% from nadir with a 5 mm absolute rise means PD; −30% from baseline means partial response; complete response needs every non-nodal target gone and every node under 10 mm.",
      "The contrast view runs the same arithmetic twice — once over raw machine tracks, once over confirmed ones — so the value of the human decisions is visible, not asserted.",
    ],
    example: <RecistExample />,
    files: ["findingframe/backend/app/services/recist.py"],
  },
  {
    id: "carry",
    phase: "attest",
    icon: History,
    title: "Carry-forward",
    tagline: "Add report 11 without redoing ten reports of confirmed work.",
    input: "A new report on top of a signed-off run",
    output: "An incremental run with prior human work replayed, escalated only where it matters",
    overview: [
      "Adding a report creates an incremental run with the prior run as parent. Only the new report costs an LLM call; the rest serve from the engine cache — the manifest records exactly which was which.",
      "Human decisions reference stable track keys, not database rows, so each confirmed identity replays onto the new run and is classified: carry (nothing changed), acknowledge (the track gained events — the reviewer sees the dates), reopen (a member vanished, went ambiguous, or the new measurement moves the RECIST category on a target), or new.",
      "That reopen rule is the point: the system escalates on decision impact, not on an arbitrary size threshold. The clinician re-attests precisely when new evidence changes the answer.",
    ],
    example: <CarryForwardExample />,
    files: ["findingframe/backend/app/services/carry_forward.py"],
  },
  {
    id: "signoff",
    phase: "attest",
    icon: FileCheck,
    title: "Sign-off, audit chain, export",
    tagline: "Two hash chains the application cannot forge.",
    input: "Everything above, plus the clinician's attestation",
    output: "A hash-chained sign-off and a pseudonymized audit packet (JSON, CSV, PDF)",
    overview: [
      "Sign-off freezes a payload of the run manifest, review deltas, link decisions, target selection and RECIST timeline. A database trigger — not the application — computes its hash and chains it to the previous sign-off for that patient. The append-only audit log gets the same treatment for every action along the way.",
      "The audit packet exports the whole story — every frame with its verbatim evidence and gate status, every signed decision, every hash — pseudonymized to a subject code. A standalone script recomputes both chains from scratch and reports pass or fail.",
    ],
    example: <SignoffExample />,
    files: [
      "findingframe/backend/app/services/signoff.py",
      "findingframe/backend/app/services/export.py",
      "findingframe/infra/scripts/verify_chain.py",
    ],
  },
];
