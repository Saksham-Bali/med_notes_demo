"use client";

import { useState } from "react";
import type { TrackEvent } from "@/lib/types";
import { AssertionBadge, GateFailedBadge } from "./Badges";
import { fmtDate } from "@/lib/format";
import { ChevronDown, ChevronRight, FileText, Quote } from "lucide-react";

/** Highlights the verbatim evidence sentence within the full source report. */
function HighlightedReport({ fullText, evidence }: { fullText: string; evidence: string }) {
  const idx = evidence ? fullText.indexOf(evidence) : -1;
  if (idx === -1) {
    return (
      <pre className="whitespace-pre-wrap evidence text-ink-soft">{fullText}</pre>
    );
  }
  return (
    <pre className="whitespace-pre-wrap evidence text-ink-soft">
      {fullText.slice(0, idx)}
      <mark className="bg-accent-soft text-accent-ink rounded px-0.5 ring-1 ring-accent/30">
        {evidence}
      </mark>
      {fullText.slice(idx + evidence.length)}
    </pre>
  );
}

function EventRow({ event }: { event: TrackEvent }) {
  const [open, setOpen] = useState(false);
  const gateFailed = event.evidence_verified === false;
  return (
    <>
      <tr className={gateFailed ? "bg-danger-soft/40" : "hover:bg-paper-soft"}>
        <td className="px-3 py-2 align-top whitespace-nowrap text-xs text-ink-soft font-medium">
          {fmtDate(event.report_date)}
        </td>
        <td className="px-3 py-2 align-top">
          <AssertionBadge assertion={event.assertion} />
          {gateFailed && (
            <span className="ml-1 inline-block align-middle">
              <GateFailedBadge />
            </span>
          )}
        </td>
        <td className="px-3 py-2 align-top">
          <div className="flex items-start gap-1.5 text-ink">
            <Quote className="w-3.5 h-3.5 mt-0.5 shrink-0 text-ink-faint" />
            <span className="evidence text-ink">{event.evidence_text || "— (no evidence span)"}</span>
          </div>
        </td>
        <td className="px-3 py-2 align-top whitespace-nowrap text-xs text-ink-soft">
          {event.measurement || "—"}
        </td>
        <td className="px-3 py-2 align-top whitespace-nowrap text-xs text-ink-muted">
          {[event.anatomy, event.laterality].filter(Boolean).join(" · ") || "—"}
        </td>
        <td className="px-3 py-2 align-top whitespace-nowrap text-right">
          <button
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-ink font-medium"
          >
            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            <FileText className="w-3.5 h-3.5" />
            {open ? "Hide" : "View"} full report
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} className="px-3 pb-3">
            <div className="rounded-lg border border-line bg-paper-soft p-3 max-h-80 overflow-auto scroll-thin">
              <div className="text-2xs uppercase tracking-wide text-ink-faint mb-2 font-semibold">
                Source report — verbatim evidence highlighted
              </div>
              <HighlightedReport fullText={event.full_text} evidence={event.evidence_text} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function EvidenceTable({ events }: { events: TrackEvent[] }) {
  return (
    <div className="overflow-x-auto scroll-thin">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-2xs uppercase tracking-wide text-ink-faint border-b border-line">
            <th className="px-3 py-2 font-semibold">Date</th>
            <th className="px-3 py-2 font-semibold">Assertion</th>
            <th className="px-3 py-2 font-semibold">Evidence (verbatim)</th>
            <th className="px-3 py-2 font-semibold">Measurement</th>
            <th className="px-3 py-2 font-semibold">Anatomy</th>
            <th className="px-3 py-2 font-semibold text-right">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line-soft">
          {events.map((e, i) => (
            <EventRow key={`${e.report_date}-${i}`} event={e} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
