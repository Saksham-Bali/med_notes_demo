"use client";

import { useState } from "react";
import Link from "next/link";
import type { DeltaIdentity, IdentityStatus, RunDelta } from "@/lib/types";
import { IDENTITY_META } from "@/lib/types";
import { Badge } from "./ui";
import { fmtDate } from "@/lib/format";
import { ArrowRight, ChevronDown, ChevronRight, GitCommitVertical } from "lucide-react";

const ORDER: IdentityStatus[] = ["reopen", "new", "acknowledge", "carry"];

function responseTone(call: string | null) {
  if (call === "PD") return "danger" as const;
  if (call === "PR" || call === "CR") return "good" as const;
  if (call === "SD") return "info" as const;
  return "quiet" as const;
}

function Count({ status, n }: { status: IdentityStatus; n: number }) {
  const meta = IDENTITY_META[status];
  return (
    <div className="rounded-lg border border-line bg-paper px-3 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-ink tabular-nums">{n}</span>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
      <p className="mt-1 text-2xs text-ink-muted leading-snug">{meta.description}</p>
    </div>
  );
}

function Group({ status, items }: { status: IdentityStatus; items: DeltaIdentity[] }) {
  const [open, setOpen] = useState(status === "reopen" || status === "new");
  if (!items.length) return null;
  const meta = IDENTITY_META[status];
  return (
    <div className="rounded-lg border border-line bg-paper">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <Badge tone={meta.tone}>{meta.label}</Badge>
        <span className="text-xs text-ink-muted">{items.length}</span>
      </button>
      {open && (
        <ul className="border-t border-line divide-y divide-line">
          {items.map((it) => (
            <li key={it.confirmed_track_key} className="px-3 py-2">
              <p className="font-mono text-2xs text-ink-soft break-all">
                {it.confirmed_track_key}
              </p>
              <p className="mt-0.5 text-xs text-ink-muted">{it.reason}</p>
              {it.review_only && (
                <span className="mt-0.5 inline-block text-2xs uppercase tracking-wide text-ink-muted">
                  review-only fragment
                </span>
              )}
              {it.gained_event_dates.length > 0 && (
                <p className="mt-0.5 text-2xs text-ink-muted">
                  new evidence: {it.gained_event_dates.map((d) => fmtDate(d)).join(", ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RunDeltaPanel({ delta, runId }: { delta: RunDelta; runId: string }) {
  const grouped = ORDER.map((status) => ({
    status,
    items: delta.identities.filter((i) => i.status === status),
  }));
  const added = delta.reports_added?.length ?? 0;
  // Split so the headline count cannot read as "3 new lesions" when they are fragments.
  const newFragments = delta.identities.filter((i) => i.status === "new" && i.review_only).length;
  const reviewed = (delta.counts.reopen ?? 0) + (delta.counts.new ?? 0);
  const untouched = (delta.counts.carry ?? 0) + (delta.counts.acknowledge ?? 0);

  return (
    <section className="rounded-2xl border-2 border-accent bg-accent-soft/40 p-4">
      <div className="flex items-center gap-2">
        <GitCommitVertical className="w-5 h-5 text-accent-ink" />
        <h2 className="text-base font-bold text-accent-ink">
          {added === 1 ? "One new report" : `${added} new reports`} — what changed
        </h2>
        {delta.llm_calls !== null && (
          <span className="ml-auto text-xs font-semibold text-accent-ink tabular-nums">
            {delta.llm_calls} of {delta.reports_total} reports read
          </span>
        )}
      </div>

      <p className="mt-1 max-w-3xl text-xs text-ink-soft">
        This record was already reviewed and signed. {untouched} confirmed{" "}
        {untouched === 1 ? "identity" : "identities"} stood without re-confirmation;{" "}
        {reviewed === 0 ? "nothing" : reviewed} {reviewed === 1 ? "item" : "items"} need a
        human
        {newFragments > 0 && (
          <>
            {" "}
            (of which {newFragments} {newFragments === 1 ? "is a" : "are"} review-only
            catch-all {newFragments === 1 ? "fragment" : "fragments"}, not a lesion tracked
            across scans)
          </>
        )}
        . The rest of the history was not re-read — its frames came back from the
        content-addressed extraction cache, and the longitudinal state was recomputed from
        scratch over every stored frame, which costs milliseconds.
      </p>

      {(delta.recist_call_before || delta.recist_call_after) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-2xs uppercase tracking-wide text-ink-muted">RECIST</span>
          <Badge tone={responseTone(delta.recist_call_before)}>
            before: {delta.recist_call_before ?? "—"}
          </Badge>
          <ArrowRight className="w-4 h-4 text-ink-muted" />
          <Badge tone={responseTone(delta.recist_call_after)}>
            after: {delta.recist_call_after ?? "—"}
          </Badge>
          {delta.category_moved && (
            <span className="text-2xs font-semibold text-warn-ink">
              the call moved, so the lesions that drove it are re-confirmed rather than assumed
            </span>
          )}
          <Link
            href={`/runs/${runId}/progression`}
            className="ml-auto text-xs font-semibold text-accent-ink underline underline-offset-2 hover:text-accent"
          >
            See what moved →
          </Link>
        </div>
      )}

      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {ORDER.map((s) => (
          <Count key={s} status={s} n={delta.counts[s] ?? 0} />
        ))}
      </div>

      <div className="mt-3 space-y-2">
        {grouped.map(({ status, items }) => (
          <Group key={status} status={status} items={items} />
        ))}
      </div>
    </section>
  );
}
