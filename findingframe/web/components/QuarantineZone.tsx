"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { GateFailedFrame, Review, ReviewInput } from "@/lib/types";
import { api } from "@/lib/api";
import { AssertionBadge } from "./Badges";
import { Button } from "./ui";
import { fmtDate } from "@/lib/format";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  ShieldAlert,
  X,
} from "lucide-react";

/** A quarantine decision is a review whose whole point is the evidence verdict. */
function gateReview(frame: GateFailedFrame, evidenceValid: boolean): ReviewInput {
  return {
    track_key: frame.track_key || frame.finding_type,
    // Snapshot exactly what the reviewer had in front of them, not the state at sign-off.
    reviewed_value: {
      quarantined_frame: {
        frame_id: frame.frame_id,
        finding_type: frame.finding_type,
        assertion: frame.assertion,
        evidence_text: frame.evidence_text,
        report_version_id: frame.report_version_id,
        reason: frame.reason,
      },
    },
    link_correct: true,
    type_correct: true,
    progression_correct: true,
    latest_status_correct: true,
    false_merge: false,
    false_split: false,
    evidence_valid: evidenceValid,
    clinically_significant: evidenceValid,
    comment: evidenceValid
      ? "Quarantined finding verified against the source report by a reviewer."
      : "Quarantined finding rejected: evidence not supported by the source report.",
  };
}

function GateRow({
  frame,
  runId,
  decided,
  onDecided,
}: {
  frame: GateFailedFrame;
  runId: string;
  decided?: boolean;
  onDecided: (frameId: string, verdict: "verified" | "rejected") => void;
}) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const key = frame.frame_id ?? frame.evidence_text;

  const decide = useMutation({
    mutationFn: (evidenceValid: boolean): Promise<Review> =>
      api.createReview(runId, gateReview(frame, evidenceValid)),
    onSuccess: (_r, evidenceValid) => {
      onDecided(key, evidenceValid ? "verified" : "rejected");
      qc.invalidateQueries({ queryKey: ["reviews", runId] });
      qc.invalidateQueries({ queryKey: ["digest", runId] });
    },
  });

  return (
    <div className="rounded-lg border border-danger/25 bg-paper">
      <div className="flex items-start justify-between gap-3 px-3 py-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-ink">
              {frame.display_name || frame.finding_type}
            </span>
            <AssertionBadge assertion={frame.assertion} />
            <span className="text-2xs text-ink-muted">{fmtDate(frame.report_date)}</span>
          </div>
          <p className="mt-1 evidence text-danger-ink">“{frame.evidence_text}”</p>
          {frame.reason && <p className="mt-1 text-2xs text-ink-muted">{frame.reason}</p>}
        </div>
        <button
          onClick={() => setOpen((v) => !v)}
          className="shrink-0 inline-flex items-center gap-1 text-xs text-accent hover:text-accent-ink font-medium"
        >
          {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          <FileText className="w-3.5 h-3.5" /> Source
        </button>
      </div>

      {open && (
        <div className="px-3 pb-3">
          <div className="rounded-lg border border-line bg-paper-soft p-3 max-h-72 overflow-auto scroll-thin">
            <pre className="whitespace-pre-wrap evidence text-ink-soft">{frame.full_text}</pre>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 border-t border-danger/15 px-3 py-2">
        {decided ? (
          <span className="text-2xs font-semibold uppercase tracking-wide text-ink-muted">
            decision recorded
          </span>
        ) : (
          <>
            <Button
              size="sm"
              variant="secondary"
              loading={decide.isPending && decide.variables === true}
              onClick={() => decide.mutate(true)}
            >
              <Check className="w-3.5 h-3.5" /> Verify against source
            </Button>
            <Button
              size="sm"
              variant="danger"
              loading={decide.isPending && decide.variables === false}
              onClick={() => decide.mutate(false)}
            >
              <X className="w-3.5 h-3.5" /> Reject
            </Button>
            <span className="ml-auto text-2xs text-ink-muted">
              Read the source before deciding.
            </span>
          </>
        )}
      </div>

      {decide.isError && (
        <p className="px-3 pb-2 text-2xs text-danger-ink">
          Could not record the decision. Try again.
        </p>
      )}
    </div>
  );
}

export function QuarantineZone({ frames, runId }: { frames: GateFailedFrame[]; runId: string }) {
  const [decided, setDecided] = useState<Record<string, "verified" | "rejected">>({});
  if (!frames.length) return null;

  const outstanding = frames.filter((f) => !decided[f.frame_id ?? f.evidence_text]).length;

  return (
    <section className="rounded-xl border-2 border-danger/40 bg-danger-soft/50 p-4">
      <div className="flex items-center gap-2 mb-1">
        <ShieldAlert className="w-5 h-5 text-danger" />
        <h2 className="text-base font-bold text-danger-ink">
          Requires review — unverified evidence
        </h2>
        <span className="ml-auto text-xs font-semibold text-danger-ink">
          {outstanding} of {frames.length} outstanding
        </span>
      </div>
      <p className="text-xs text-danger-ink/80 mb-3 max-w-3xl">
        These findings failed the evidence gate: their source sentence could not be located
        verbatim in the report. They are <strong>never silently included</strong> — a clinician
        must verify or reject each before it can enter the signed record.
      </p>
      <div className="space-y-2">
        {frames.map((f, i) => {
          const key = f.frame_id ?? f.evidence_text;
          return (
            <GateRow
              key={f.frame_id ?? i}
              frame={f}
              runId={runId}
              decided={Boolean(decided[key])}
              onDecided={(k, verdict) => setDecided((d) => ({ ...d, [k]: verdict }))}
            />
          );
        })}
      </div>
    </section>
  );
}
