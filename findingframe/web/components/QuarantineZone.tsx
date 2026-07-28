"use client";

import { useState } from "react";
import type { GateFailedFrame } from "@/lib/types";
import { AssertionBadge } from "./Badges";
import { fmtDate } from "@/lib/format";
import { ChevronDown, ChevronRight, FileText, ShieldAlert } from "lucide-react";

function GateRow({ frame }: { frame: GateFailedFrame }) {
  const [open, setOpen] = useState(false);
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
    </div>
  );
}

export function QuarantineZone({ frames }: { frames: GateFailedFrame[] }) {
  if (!frames.length) return null;
  return (
    <section className="rounded-xl border-2 border-danger/40 bg-danger-soft/50 p-4">
      <div className="flex items-center gap-2 mb-1">
        <ShieldAlert className="w-5 h-5 text-danger" />
        <h2 className="text-base font-bold text-danger-ink">
          Requires review — unverified evidence
        </h2>
        <span className="ml-auto text-xs font-semibold text-danger-ink">
          {frames.length} quarantined
        </span>
      </div>
      <p className="text-xs text-danger-ink/80 mb-3 max-w-3xl">
        These findings failed the evidence gate: their source sentence could not be located
        verbatim in the report. They are <strong>never silently included</strong> — a clinician
        must verify or reject each before it can enter the signed record.
      </p>
      <div className="space-y-2">
        {frames.map((f, i) => (
          <GateRow key={f.frame_id ?? i} frame={f} />
        ))}
      </div>
    </section>
  );
}
