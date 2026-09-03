"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Digest, LinkDecisionInput, LinkDecisionKind, Track } from "@/lib/types";
import { Badge, Button, Card, EmptyState, Input } from "./ui";
import { EvidenceTable } from "./EvidenceTable";
import { FalseSplitBadge, ProgressionBadge, UnresolvedBadge } from "./Badges";
import { fmtDateTime, shortHash } from "@/lib/format";
import { CheckCircle2, GitMerge, Link2, Scissors, ShieldCheck, XCircle } from "lucide-react";

const DECISION_LABELS: Record<LinkDecisionKind, string> = {
  confirm: "Confirm identity",
  merge: "Merge tracks",
  split: "Keep split",
  mark_unresolved: "Leave unresolved",
  reject: "Reject track",
};

export function LinkConfirmation({ runId, digest }: { runId: string; digest: Digest }) {
  const qc = useQueryClient();
  const allTracks = useMemo(
    () => Object.values(digest.sections).flat(),
    [digest]
  );
  const uncertain = allTracks.filter((t) => t.unresolved_link || t.false_split_candidate);
  const settled = allTracks.filter((t) => !t.unresolved_link && !t.false_split_candidate);

  const decisions = useQuery({
    queryKey: ["link-decisions", runId],
    queryFn: () => api.listLinkDecisions(runId),
  });
  const confirmed = useQuery({
    queryKey: ["confirmed-tracks", runId],
    queryFn: () => api.confirmedTracks(runId),
  });

  const decide = useMutation({
    mutationFn: (input: LinkDecisionInput) => api.createLinkDecision(runId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["link-decisions", runId] });
      qc.invalidateQueries({ queryKey: ["confirmed-tracks", runId] });
      // RECIST is computed only over confirmed tracks, so a link decision can change the
      // response category. Without this the contrast card keeps showing the pre-merge
      // call and the reviewer sees a stale verdict next to the decision that changed it.
      qc.invalidateQueries({ queryKey: ["recist-contrast", runId] });
      qc.invalidateQueries({ queryKey: ["run-delta", runId] });
    },
  });

  const decidedKeys = new Set((decisions.data ?? []).map((d) => d.primary_track_key));

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        <div className="rounded-xl border border-warn/30 bg-warn-soft/40 p-4">
          <div className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-warn-ink" />
            <h2 className="font-bold text-warn-ink">Confirm track identity first</h2>
          </div>
          <p className="text-xs text-warn-ink/80 mt-1 max-w-3xl">
            Track linking is the weakest step (false splits fabricate "new lesions", and in RECIST
            1.1 a new lesion = unconditional PD). RECIST renders <strong>only</strong> over
            human-confirmed tracks. Resolve every flagged pair below before selecting target lesions.
          </p>
        </div>

        <section>
          <h3 className="text-sm font-bold text-ink mb-2">
            Needs decision <span className="text-ink-faint font-normal">({uncertain.length})</span>
          </h3>
          {uncertain.length === 0 && (
            <Card>
              <EmptyState
                icon={<CheckCircle2 className="w-7 h-7 text-good" />}
                title="No unresolved links"
                description="The linker produced no unresolved-link or false-split candidates for this run."
              />
            </Card>
          )}
          <div className="space-y-3">
            {uncertain.map((t) => (
              <LinkDecisionCard
                key={t.track_key}
                track={t}
                candidates={allTracks.filter((x) => x.track_key !== t.track_key)}
                decided={decidedKeys.has(t.track_key)}
                onDecide={(input) => decide.mutate(input)}
                submitting={decide.isPending}
              />
            ))}
          </div>
        </section>

        {settled.length > 0 && (
          <section>
            <h3 className="text-sm font-bold text-ink mb-2">
              Auto-linked <span className="text-ink-faint font-normal">({settled.length})</span>
            </h3>
            <p className="text-xs text-ink-muted mb-2">
              Exact composite-key matches — you can still confirm or reject each.
            </p>
            <div className="space-y-3">
              {settled.map((t) => (
                <LinkDecisionCard
                  key={t.track_key}
                  track={t}
                  candidates={allTracks.filter((x) => x.track_key !== t.track_key)}
                  decided={decidedKeys.has(t.track_key)}
                  onDecide={(input) => decide.mutate(input)}
                  submitting={decide.isPending}
                  compact
                />
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Sidebar: confirmed + decision log */}
      <div className="space-y-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-4 h-4 text-good" />
            <h3 className="text-sm font-semibold text-ink">Confirmed tracks</h3>
          </div>
          {confirmed.data && confirmed.data.length > 0 ? (
            <ul className="space-y-1.5">
              {confirmed.data.map((t) => (
                <li key={t.confirmed_track_key} className="flex items-center gap-2 text-xs">
                  {t.confirmed ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-good shrink-0" />
                  ) : (
                    <span className="w-3.5 h-3.5 rounded-full border border-line-strong shrink-0" />
                  )}
                  <span className="text-ink-soft truncate">{t.display_name}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-ink-muted">No decisions recorded yet.</p>
          )}
        </Card>

        <Card className="p-4">
          <h3 className="text-sm font-semibold text-ink mb-2">Decision log (signed)</h3>
          {decisions.data && decisions.data.length > 0 ? (
            <ul className="space-y-2">
              {decisions.data.map((d) => (
                <li key={d.id} className="text-2xs border-b border-line-soft pb-1.5 last:border-0">
                  <div className="flex items-center gap-1.5">
                    <Badge tone="info">{DECISION_LABELS[d.decision]}</Badge>
                    <span className="text-ink-muted">{fmtDateTime(d.decided_at ?? d.created_at)}</span>
                  </div>
                  <div className="font-mono text-ink-faint mt-0.5 truncate">{d.primary_track_key}</div>
                  <div className="font-mono text-ink-faint">sig {shortHash(d.signature_sha256 ?? d.payload_sha256, 12)}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-ink-muted">Append-only. Each decision is hashed.</p>
          )}
        </Card>
      </div>
    </div>
  );
}

function LinkDecisionCard({
  track,
  candidates,
  decided,
  onDecide,
  submitting,
  compact,
}: {
  track: Track;
  candidates: Track[];
  decided: boolean;
  onDecide: (input: LinkDecisionInput) => void;
  submitting?: boolean;
  compact?: boolean;
}) {
  const [mergeTarget, setMergeTarget] = useState<string>("");
  const [rationale, setRationale] = useState("");
  const [showMerge, setShowMerge] = useState(false);

  const fire = (decision: LinkDecisionKind, related?: string[]) =>
    onDecide({
      decision,
      primary_track_key: track.track_key,
      related_track_keys: related,
      rationale: rationale || undefined,
    });

  return (
    <Card className={compact ? "border-line" : "border-l-4 border-l-warn"}>
      <div className="px-4 pt-3 pb-2 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-sm font-semibold text-ink">{track.display_name}</h4>
            <ProgressionBadge progression={track.progression} fallback={track.latest_status} />
            {decided && (
              <span className="inline-flex items-center gap-1 text-2xs font-semibold text-good">
                <CheckCircle2 className="w-3.5 h-3.5" /> decided
              </span>
            )}
          </div>
          <div className="text-2xs font-mono text-ink-muted mt-1">{track.track_key}</div>
          <div className="mt-1.5 flex gap-1.5 flex-wrap">
            {track.unresolved_link && <UnresolvedBadge />}
            {track.false_split_candidate && <FalseSplitBadge />}
          </div>
        </div>
      </div>

      {!compact && (
        <div className="border-t border-line-soft">
          <EvidenceTable events={track.events} />
        </div>
      )}

      <div className="px-4 py-3 border-t border-line-soft space-y-2">
        {showMerge && (
          <div className="flex items-center gap-2">
            <select
              value={mergeTarget}
              onChange={(e) => setMergeTarget(e.target.value)}
              className="flex-1 rounded-lg border border-line-strong bg-paper px-2 py-1.5 text-xs"
            >
              <option value="">Merge into…</option>
              {candidates.map((c) => (
                <option key={c.track_key} value={c.track_key}>
                  {c.display_name} — {c.track_key}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={!mergeTarget}
              loading={submitting}
              onClick={() => {
                onDecide({
                  decision: "merge",
                  primary_track_key: mergeTarget,
                  related_track_keys: [track.track_key],
                  resulting_track_key: mergeTarget,
                  rationale: rationale || undefined,
                });
                setShowMerge(false);
              }}
            >
              Confirm merge
            </Button>
          </div>
        )}
        <Input
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Rationale (recorded in the signed decision)…"
          className="text-xs py-1.5"
        />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => fire("confirm")} loading={submitting}>
            <CheckCircle2 className="w-3.5 h-3.5" /> Confirm identity
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setShowMerge((v) => !v)}>
            <GitMerge className="w-3.5 h-3.5" /> Merge…
          </Button>
          <Button size="sm" variant="secondary" onClick={() => fire("split")} loading={submitting}>
            <Scissors className="w-3.5 h-3.5" /> Keep split
          </Button>
          <Button size="sm" variant="ghost" onClick={() => fire("mark_unresolved")}>
            Leave unresolved
          </Button>
          <Button size="sm" variant="ghost" onClick={() => fire("reject")}>
            <XCircle className="w-3.5 h-3.5" /> Reject
          </Button>
        </div>
      </div>
    </Card>
  );
}
