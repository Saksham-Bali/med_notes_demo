"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api";
import type {
  ConfirmedTrack,
  RecistAssessment,
  RecistResponse,
  RecistResult,
  TargetLesionSelection,
  Track,
} from "@/lib/types";
import { Badge, Button, Card, EmptyState, ErrorBox, Input, Loading, Select } from "@/components/ui";
import { RecistChart } from "@/components/RecistChart";
import { ContrastCard } from "@/components/ContrastCard";
import { cx, fmtDate, pct } from "@/lib/format";
import { AlertTriangle, Link2, Ruler, Target } from "lucide-react";

function parseMm(measurement?: string | null): number | "" {
  if (!measurement) return "";
  const m = measurement.match(/(\d+(?:\.\d+)?)\s*mm/i);
  return m ? Number(m[1]) : "";
}

const responseTone: Record<RecistResponse, "danger" | "good" | "info" | "warn"> = {
  PD: "danger",
  CR: "good",
  PR: "good",
  SD: "info",
};

export default function RecistPage({ params }: { params: { id: string } }) {
  const runId = params.id;
  const qc = useQueryClient();

  const router = useRouter();
  const confirmed = useQuery({
    queryKey: ["confirmed-tracks", runId],
    queryFn: () => api.confirmedTracks(runId),
  });
  const contrast = useQuery({
    queryKey: ["recist-contrast", runId],
    queryFn: () => api.getRecistContrast(runId),
    retry: false,
  });
  // Digest tracks carry full source text for the one-motion evidence jump.
  const digest = useQuery({ queryKey: ["digest", runId], queryFn: () => api.getDigest(runId) });
  const trackByKey = useMemo(() => {
    const m = new Map<string, Track>();
    if (digest.data) {
      for (const list of Object.values(digest.data.sections)) {
        for (const t of list) m.set(t.track_key, t);
      }
    }
    for (const t of confirmed.data ?? []) if (!m.has(t.track_key)) m.set(t.track_key, t);
    return m;
  }, [confirmed.data, digest.data]);

  // Any human-confirmed track is an eligible target. Measurements may be absent
  // in the source (the reviewer enters the baseline mm), so we do NOT gate on them.
  const eligible = useMemo(
    () => (confirmed.data ?? []).filter((t) => t.confirmed),
    [confirmed.data]
  );

  const baselineVersions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const t of confirmed.data ?? []) {
      for (const e of t.events) {
        if (e.report_version_id) seen.set(e.report_version_id, e.report_date);
      }
    }
    return Array.from(seen.entries())
      .map(([id, date]) => ({ id, date }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [confirmed.data]);

  const [baselineRv, setBaselineRv] = useState<string>("");
  const [selection, setSelection] = useState<Record<string, { organ: string; baseline_mm: number | "" }>>({});
  const [recist, setRecist] = useState<RecistResult | null>(null);

  const effectiveBaseline = baselineRv || baselineVersions[0]?.id || "";

  const selectedKeys = Object.keys(selection);
  const organCounts = selectedKeys.reduce<Record<string, number>>((acc, k) => {
    const organ = selection[k].organ || "unspecified";
    acc[organ] = (acc[organ] ?? 0) + 1;
    return acc;
  }, {});
  const totalSelected = selectedKeys.length;
  const overFive = totalSelected > 5;
  const overPerOrgan = Object.entries(organCounts).some(([, n]) => n > 2);

  const toggle = (t: ConfirmedTrack) => {
    setSelection((s) => {
      const next = { ...s };
      if (next[t.confirmed_track_key]) {
        delete next[t.confirmed_track_key];
      } else {
        const baselineEvent =
          t.events.find((e) => e.report_version_id === effectiveBaseline) ?? t.events[0];
        next[t.confirmed_track_key] = {
          organ: (t.anatomy || "").split(/\s+/).slice(-1)[0] || t.finding_type,
          baseline_mm: parseMm(baselineEvent?.measurement),
        };
      }
      return next;
    });
  };

  const submit = useMutation({
    mutationFn: async () => {
      const selections: TargetLesionSelection[] = selectedKeys.map((k) => ({
        confirmed_track_key: k,
        organ: selection[k].organ || "unspecified",
        baseline_mm: Number(selection[k].baseline_mm) || 0,
      }));
      await api.setTargetLesions(runId, {
        baseline_report_version_id: effectiveBaseline,
        selections,
      });
      return api.getRecist(runId);
    },
    onSuccess: (r) => {
      setRecist(r);
      qc.invalidateQueries({ queryKey: ["confirmed-tracks", runId] });
    },
  });

  const err = submit.error as ApiError | undefined;
  const is422 = err?.status === 422;

  if (confirmed.isLoading) return <Loading label="Loading confirmed tracks…" />;
  if (confirmed.error) return <ErrorBox message={(confirmed.error as Error).message} />;

  const noConfirmed = eligible.length === 0;

  return (
    <div className="space-y-5">
      <div>
        <Link href={`/runs/${runId}/review`} className="text-xs text-ink-muted hover:text-ink">
          ← Review workbench
        </Link>
        <div className="flex items-center gap-2 mt-2">
          <Ruler className="w-5 h-5 text-accent" />
          <h1 className="text-xl font-semibold text-ink">RECIST 1.1 worksheet</h1>
        </div>
        <p className="text-sm text-ink-muted mt-1 max-w-3xl">
          Select up to 5 target lesions (max 2 per organ) from <strong>human-confirmed</strong>{" "}
          tracks. SLD and response are then computed deterministically — never from unconfirmed
          linking.
        </p>
      </div>

      {/* Money moment: automated vs human-confirmed RECIST. */}
      {contrast.data && (
        <ContrastCard
          contrast={contrast.data}
          trackLookup={(k) => trackByKey.get(k)}
          onConfirmLinks={() => router.push(`/runs/${runId}/review`)}
        />
      )}

      {noConfirmed && (
        <Card>
          <EmptyState
            icon={<Link2 className="w-8 h-8" />}
            title="Confirm track links first"
            description="No confirmed, measurable tracks are available. Confirm track identity in the review workbench before selecting target lesions."
            action={
              <Link href={`/runs/${runId}/review`}>
                <Button>
                  <Link2 className="w-4 h-4" /> Go confirm links
                </Button>
              </Link>
            }
          />
        </Card>
      )}

      {!noConfirmed && (
        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          {/* Target selection */}
          <div className="space-y-4">
            <Card>
              <div className="px-4 py-3 border-b border-line flex items-center gap-2">
                <Target className="w-4 h-4 text-accent" />
                <h2 className="font-semibold text-ink text-sm">Eligible confirmed tracks</h2>
                <span
                  className={cx(
                    "ml-auto text-xs font-semibold",
                    overFive ? "text-danger-ink" : "text-ink-muted"
                  )}
                >
                  {totalSelected}/5 selected
                </span>
              </div>
              <ul className="divide-y divide-line-soft">
                {eligible.map((t) => {
                  const sel = selection[t.confirmed_track_key];
                  return (
                    <li key={t.confirmed_track_key} className="px-4 py-3">
                      <label className="flex items-start gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={Boolean(sel)}
                          onChange={() => toggle(t)}
                          className="mt-1 accent-accent"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-ink">{t.display_name}</div>
                          <div className="text-2xs text-ink-muted font-mono">{t.confirmed_track_key}</div>
                          <div className="text-2xs text-ink-muted mt-0.5">
                            {t.measurement_trend || "measurable"}
                          </div>
                        </div>
                      </label>
                      {sel && (
                        <div className="mt-2 ml-7 grid grid-cols-2 gap-2 max-w-sm">
                          <label className="text-2xs text-ink-soft">
                            Organ
                            <Input
                              value={sel.organ}
                              onChange={(e) =>
                                setSelection((s) => ({
                                  ...s,
                                  [t.confirmed_track_key]: { ...s[t.confirmed_track_key], organ: e.target.value },
                                }))
                              }
                              className="mt-0.5 py-1 text-xs"
                            />
                          </label>
                          <label className="text-2xs text-ink-soft">
                            Baseline (mm)
                            <Input
                              type="number"
                              value={sel.baseline_mm}
                              onChange={(e) =>
                                setSelection((s) => ({
                                  ...s,
                                  [t.confirmed_track_key]: {
                                    ...s[t.confirmed_track_key],
                                    baseline_mm: e.target.value === "" ? "" : Number(e.target.value),
                                  },
                                }))
                              }
                              className="mt-0.5 py-1 text-xs"
                            />
                          </label>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>

            {(overFive || overPerOrgan) && (
              <div className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-2.5 text-sm text-danger-ink flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                {overFive && <span>RECIST 1.1 allows at most 5 target lesions. </span>}
                {overPerOrgan && <span>At most 2 target lesions per organ.</span>}
              </div>
            )}

            {is422 && (
              <div className="rounded-lg border border-warn/30 bg-warn-soft px-4 py-2.5 text-sm text-warn-ink flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                {err?.message || "Confirm track links and select targets before computing RECIST."}
              </div>
            )}
            {err && !is422 && <ErrorBox message={err.message} />}
          </div>

          {/* Baseline + compute */}
          <div className="space-y-4">
            <Card className="p-4 space-y-3">
              <h3 className="text-sm font-semibold text-ink">Baseline & compute</h3>
              <label className="block text-xs text-ink-soft">
                Baseline study
                <Select
                  value={effectiveBaseline}
                  onChange={(e) => setBaselineRv(e.target.value)}
                  className="mt-1"
                >
                  {baselineVersions.map((b) => (
                    <option key={b.id} value={b.id}>
                      {fmtDate(b.date)}
                    </option>
                  ))}
                </Select>
              </label>
              <Button
                className="w-full"
                onClick={() => submit.mutate()}
                loading={submit.isPending}
                disabled={totalSelected === 0 || overFive || overPerOrgan}
              >
                <Ruler className="w-4 h-4" /> Compute RECIST
              </Button>
              <p className="text-2xs text-ink-muted">
                Selection is signed and appended. Recompute is idempotent server-side.
              </p>
            </Card>
          </div>
        </div>
      )}

      {recist && <RecistResultCard recist={recist} />}
    </div>
  );
}

function assessmentDate(a: RecistAssessment): string {
  return a.report_date ?? a.date ?? "";
}
function assessmentSld(a: RecistAssessment): number | undefined {
  return a.sld_mm ?? a.sum_longest_diameter_mm;
}

function RecistResultCard({ recist }: { recist: RecistResult }) {
  const assessments = recist.assessments ?? [];
  const hasAssessments = assessments.length > 0;
  const overall = hasAssessments ? assessments[assessments.length - 1]?.response ?? null : null;
  const latestSld = hasAssessments ? assessmentSld(assessments[assessments.length - 1]) : undefined;

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
        <h2 className="font-semibold text-ink">SLD timeline & response</h2>
        {overall && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-ink-muted">Overall (latest)</span>
            <Badge tone={responseTone[overall]} className="text-xs">
              {overall}
            </Badge>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-center mb-4">
        <Stat label="Baseline SLD" value={`${recist.baseline_sld_mm ?? "—"} mm`} />
        <Stat label="Latest SLD" value={latestSld != null ? `${latestSld} mm` : "—"} />
        <Stat label="Target lesions" value={String(recist.targets.length)} />
      </div>

      {hasAssessments ? (
        <>
          <RecistChart assessments={assessments} baselineSld={recist.baseline_sld_mm ?? 0} />
          <div className="mt-5 overflow-x-auto scroll-thin">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-2xs uppercase tracking-wide text-ink-faint border-b border-line">
                  <th className="px-3 py-2 font-semibold">Timepoint</th>
                  <th className="px-3 py-2 font-semibold">SLD</th>
                  <th className="px-3 py-2 font-semibold">Δ baseline</th>
                  <th className="px-3 py-2 font-semibold">Δ nadir</th>
                  <th className="px-3 py-2 font-semibold">Response</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {assessments.map((a, i) => (
                  <tr key={`${assessmentDate(a)}-${i}`}>
                    <td className="px-3 py-2 text-ink-soft">{fmtDate(assessmentDate(a))}</td>
                    <td className="px-3 py-2 font-mono">{assessmentSld(a) ?? "—"} mm</td>
                    <td className="px-3 py-2 font-mono text-ink-muted">{pct(a.pct_change_from_baseline)}</td>
                    <td className="px-3 py-2 font-mono text-ink-muted">{pct(a.pct_change_from_nadir)}</td>
                    <td className="px-3 py-2">
                      {a.response && <Badge tone={responseTone[a.response]}>{a.response}</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-line bg-paper-soft px-4 py-6 text-center">
          <p className="text-sm font-semibold text-ink">Baseline recorded — no follow-up SLD yet</p>
          <p className="mt-1 text-xs text-ink-muted max-w-xl mx-auto">
            Target lesions are confirmed and the baseline SLD ({recist.baseline_sld_mm ?? "—"} mm) is
            signed, but no per-timepoint assessments were computed — the source reports for this
            patient lack normalized measurements. RECIST is never fabricated; assessments appear once
            measurable follow-ups exist.
          </p>
        </div>
      )}

      <ul className="mt-3 text-2xs text-ink-muted space-y-1">
        <li>· SLD = sum of longest diameters of confirmed target lesions.</li>
        <li>· Computed deterministically over human-confirmed tracks only.</li>
      </ul>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-paper-soft py-3">
      <div className="text-lg font-semibold text-ink font-mono">{value}</div>
      <div className="text-2xs text-ink-muted uppercase tracking-wide">{label}</div>
    </div>
  );
}
