"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { RecistClass, RecistDistribution, ReviewThroughput } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorBox, Loading } from "@/components/ui";
import { cx, fmtDuration } from "@/lib/format";
import {
  Activity,
  BarChart3,
  ClipboardCheck,
  Layers,
  ShieldAlert,
  Timer,
  Users,
} from "lucide-react";

export default function AnalyticsPage() {
  const overview = useQuery({ queryKey: ["analytics", "overview"], queryFn: api.analyticsOverview });
  const recist = useQuery({ queryKey: ["analytics", "recist"], queryFn: api.recistDistribution });
  const throughput = useQuery({ queryKey: ["analytics", "throughput"], queryFn: api.reviewThroughput });

  const loading = overview.isLoading || recist.isLoading || throughput.isLoading;
  const error = overview.error || recist.error || throughput.error;

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Analytics</h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Org-scoped aggregates · read straight from the durable clinical record and the
          hash-chained audit trail
        </p>
      </div>

      {loading && <Loading label="Loading analytics…" />}
      {error && <ErrorBox message={(error as Error).message} />}

      {!loading && !error && overview.data && (
        <div className="space-y-6">
          {/* KPI stat tiles */}
          <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
            <StatTile
              icon={<Users className="w-4 h-4" />}
              label="Patients"
              value={overview.data.patients.toLocaleString()}
              sub={`${overview.data.reports_total.toLocaleString()} reports · ${overview.data.avg_reports_per_patient.toFixed(
                1
              )} avg/patient`}
            />
            <StatTile
              icon={<Activity className="w-4 h-4" />}
              label="Extraction runs"
              value={overview.data.runs.toLocaleString()}
              sub={statusSummary(overview.data.runs_by_status)}
            />
            <StatTile
              icon={<ShieldAlert className="w-4 h-4" />}
              label="Gate-failed rate"
              value={`${(overview.data.gate_failed_rate * 100).toFixed(1)}%`}
              sub={`${overview.data.frames_gate_failed} of ${overview.data.frames_total} frames quarantined`}
              tone={overview.data.gate_failed_rate > 0 ? "danger" : "good"}
            />
            <StatTile
              icon={<Timer className="w-4 h-4" />}
              label="Avg attested review"
              value={
                throughput.data && throughput.data.patients_reviewed > 0
                  ? fmtDuration(throughput.data.avg_review_seconds_per_patient)
                  : "—"
              }
              sub="per patient · from review_sessions"
            />
          </div>

          {/* secondary counts */}
          <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
            <MiniStat icon={<Layers className="w-4 h-4" />} label="Tracks" value={overview.data.tracks_total} />
            <MiniStat icon={<BarChart3 className="w-4 h-4" />} label="Frames" value={overview.data.frames_total} />
            <MiniStat
              icon={<ClipboardCheck className="w-4 h-4" />}
              label="Reviews"
              value={throughput.data?.reviews_total ?? 0}
            />
            <MiniStat
              icon={<ShieldAlert className="w-4 h-4" />}
              label="Corrections"
              value={throughput.data?.corrections ?? 0}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {recist.data && <RecistPanel data={recist.data} />}
            {throughput.data && <ThroughputPanel data={throughput.data} />}
          </div>

          <AgreementPanel />
        </div>
      )}
    </div>
  );
}

function statusSummary(byStatus: Record<string, number>): string {
  const parts = Object.entries(byStatus).map(([s, n]) => `${n} ${s}`);
  return parts.length ? parts.join(" · ") : "no runs yet";
}

// ---- stat tiles -----------------------------------------------------------

function StatTile({
  icon,
  label,
  value,
  sub,
  tone = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "danger" | "good";
}) {
  const accent =
    tone === "danger" ? "text-danger" : tone === "good" ? "text-good" : "text-accent";
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-ink-muted uppercase tracking-wide">
        <span className={accent}>{icon}</span>
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-ink tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-2xs text-ink-muted">{sub}</div>}
    </Card>
  );
}

function MiniStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <Card className="p-3 flex items-center gap-3">
      <span className="text-ink-faint">{icon}</span>
      <div>
        <div className="text-lg font-semibold text-ink tabular-nums leading-none">
          {value.toLocaleString()}
        </div>
        <div className="text-2xs text-ink-muted mt-0.5">{label}</div>
      </div>
    </Card>
  );
}

// ---- RECIST distribution --------------------------------------------------

const RECIST_ORDER: RecistClass[] = ["CR", "PR", "SD", "PD", "NE"];
const RECIST_COLOR: Record<RecistClass, string> = {
  CR: "#1e5e40",
  PR: "#2f855a",
  SD: "#1b64c9",
  PD: "#c0362c",
  NE: "#94a3b8",
};
const RECIST_LABEL: Record<RecistClass, string> = {
  CR: "Complete",
  PR: "Partial",
  SD: "Stable",
  PD: "Progressive",
  NE: "Not eval.",
};

function RecistPanel({ data }: { data: RecistDistribution }) {
  const counts = RECIST_ORDER.map((k) => ({ k, n: data.by_assessment[k] ?? 0 }));
  const max = Math.max(1, ...counts.map((c) => c.n));

  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink">RECIST distribution</h2>
        <span className="text-2xs text-ink-muted">
          {data.total_assessments} timepoint{data.total_assessments === 1 ? "" : "s"} ·{" "}
          {data.runs_assessed} run{data.runs_assessed === 1 ? "" : "s"}
        </span>
      </div>
      <p className="text-2xs text-ink-muted mt-0.5">
        Response calls across confirmed RECIST assessments
      </p>

      {data.total_assessments === 0 ? (
        <EmptyState
          title="No RECIST assessments yet"
          description="RECIST is computed only over human-confirmed tracks with a target-lesion selection."
        />
      ) : (
        <>
          <div className="mt-5 flex items-end justify-between gap-3 h-40">
            {counts.map(({ k, n }) => (
              <div key={k} className="flex-1 flex flex-col items-center justify-end h-full">
                <div className="text-xs font-semibold text-ink tabular-nums mb-1">{n}</div>
                <div
                  className="w-full rounded-t-md transition-all"
                  style={{
                    height: `${(n / max) * 100}%`,
                    minHeight: n > 0 ? 6 : 2,
                    backgroundColor: n > 0 ? RECIST_COLOR[k] : "#e2e8f0",
                  }}
                  aria-label={`${RECIST_LABEL[k]}: ${n}`}
                />
                <div className="mt-2 text-2xs font-semibold text-ink-soft">{k}</div>
                <div className="text-2xs text-ink-faint">{RECIST_LABEL[k]}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-3 border-t border-line text-2xs text-ink-muted">
            Best overall response per run:{" "}
            {RECIST_ORDER.filter((k) => (data.by_run_best_overall[k] ?? 0) > 0)
              .map((k) => `${data.by_run_best_overall[k]} ${k}`)
              .join(" · ") || "—"}
          </div>
        </>
      )}
    </Card>
  );
}

// ---- throughput + correction ---------------------------------------------

function ThroughputPanel({ data }: { data: ReviewThroughput }) {
  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink">Review throughput</h2>
        <span className="text-2xs text-ink-muted">{data.source}</span>
      </div>

      {data.reviews_total === 0 && data.review_sessions === 0 ? (
        <EmptyState
          title="No review activity yet"
          description="Attested review time and correction rate appear once clinicians review a run."
        />
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <div className="text-2xs text-ink-muted uppercase tracking-wide">Correction rate</div>
              <div className="mt-1 text-2xl font-semibold text-ink tabular-nums">
                {(data.correction_rate * 100).toFixed(1)}%
              </div>
              <div className="text-2xs text-ink-muted mt-0.5">
                {data.corrections} of {data.reviews_total} reviews needed a fix
              </div>
              <div className="mt-2 h-2 rounded-full bg-paper-sunk overflow-hidden">
                <div
                  className="h-full rounded-full bg-warn"
                  style={{ width: `${Math.min(100, data.correction_rate * 100)}%` }}
                />
              </div>
            </div>
            <div>
              <div className="text-2xs text-ink-muted uppercase tracking-wide">
                Attested review time
              </div>
              <div className="mt-1 text-2xl font-semibold text-ink tabular-nums">
                {fmtDuration(data.total_active_review_seconds)}
              </div>
              <div className="text-2xs text-ink-muted mt-0.5">
                {data.tracks_reviewed} tracks · {data.review_sessions} session
                {data.review_sessions === 1 ? "" : "s"} · {data.patients_reviewed} patient
                {data.patients_reviewed === 1 ? "" : "s"}
              </div>
            </div>
          </div>

          <div className="mt-5">
            <div className="text-2xs text-ink-muted uppercase tracking-wide mb-2">
              Reviewer leaderboard
            </div>
            {data.reviewer_leaderboard.length === 0 ? (
              <p className="text-xs text-ink-muted">No reviewers yet.</p>
            ) : (
              <div className="divide-y divide-line">
                {data.reviewer_leaderboard.map((r) => (
                  <div key={r.reviewer_id} className="flex items-center gap-3 py-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-ink truncate">{r.name}</div>
                      <div className="text-2xs text-ink-muted">
                        {r.reviews} review{r.reviews === 1 ? "" : "s"} ·{" "}
                        {fmtDuration(r.active_seconds)} active
                      </div>
                    </div>
                    <Badge tone={r.corrections > 0 ? "warn" : "good"}>
                      {(r.correction_rate * 100).toFixed(0)}% corrected
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

// ---- agreement (best-effort) ---------------------------------------------

function AgreementPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "agreement"],
    queryFn: api.agreement,
  });
  if (isLoading || !data) return null;

  return (
    <Card className={cx("p-5", data.available ? "" : "bg-paper-soft")}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink">Inter-rater agreement</h2>
        <Badge tone={data.available ? "good" : "quiet"}>
          {data.available ? "Available" : "Not yet available"}
        </Badge>
      </div>
      {data.available ? (
        <div className="mt-3 text-sm text-ink-soft">
          {data.items_annotated ?? 0} items annotated · {data.items_adjudicated ?? 0} adjudicated.
          {data.note && <span className="block text-2xs text-ink-muted mt-1">{data.note}</span>}
        </div>
      ) : (
        <p className="mt-2 text-sm text-ink-muted">
          {data.reason ??
            "Inter-rater agreement becomes available once annotators submit independent blinded labels."}
        </p>
      )}
    </Card>
  );
}
