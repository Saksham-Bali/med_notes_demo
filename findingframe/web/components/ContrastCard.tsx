"use client";

import { useState } from "react";
import type {
  ContrastArm,
  ContrastTimepoint,
  RecistAssessment,
  RecistClassification,
  RecistContrast,
  Track,
} from "@/lib/types";
import { Badge, type Tone } from "./ui";
import { RecistChart } from "./RecistChart";
import { EvidenceModal } from "./EvidenceModal";
import { cx, pct } from "@/lib/format";
import { AlertTriangle, ArrowRight, FileSearch, Sparkles } from "lucide-react";

function classTone(c: RecistClassification): Tone {
  const u = String(c).toUpperCase();
  if (u === "PD") return "danger";
  if (u === "PR" || u === "CR") return "good";
  if (u === "SD") return "info";
  return "quiet"; // NE / unknown
}

function toAssessments(tl: ContrastTimepoint[]): RecistAssessment[] {
  return tl.map((t) => ({
    report_date: t.assessment_date,
    sld_mm: t.sld_mm,
    response: (["PD", "PR", "CR", "SD"].includes(String(t.classification).toUpperCase())
      ? (String(t.classification).toUpperCase() as RecistAssessment["response"])
      : null),
    pct_from_baseline: t.pct_from_baseline,
    pct_from_nadir: t.pct_from_nadir,
  }));
}

function lastPctFromBaseline(arm: ContrastArm): number | null {
  const last = arm.sld_timeline[arm.sld_timeline.length - 1];
  return last ? last.pct_from_baseline : null;
}

function Arm({
  title,
  subtitle,
  arm,
  tone,
  trackLookup,
  onOpenTrack,
}: {
  title: string;
  subtitle: string;
  arm: ContrastArm;
  tone: "danger" | "good";
  trackLookup?: (key: string) => Track | undefined;
  onOpenTrack?: (t: Track) => void;
}) {
  const baseline = arm.sld_timeline[0]?.baseline_sld_mm ?? 0;
  const border = tone === "danger" ? "border-danger/40" : "border-good/40";
  const headBg = tone === "danger" ? "bg-danger-soft" : "bg-good-soft";
  const headText = tone === "danger" ? "text-danger-ink" : "text-good-ink";
  return (
    <div className={cx("rounded-xl border-2 bg-paper overflow-hidden", border)}>
      <div className={cx("px-4 py-2.5", headBg)}>
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className={cx("text-2xs font-bold uppercase tracking-wide", headText)}>{title}</div>
            <div className="text-xs text-ink-muted">{subtitle}</div>
          </div>
          <div className="text-right">
            <div className={cx("text-2xl font-bold leading-none", headText)}>{arm.classification}</div>
            <div className="text-2xs text-ink-muted mt-0.5">{pct(lastPctFromBaseline(arm))} vs baseline</div>
          </div>
        </div>
      </div>
      <div className="p-3">
        {arm.new_lesion && (
          <div className="mb-2 inline-flex items-center gap-1 text-2xs font-semibold text-danger-ink bg-danger-soft rounded-md px-2 py-0.5">
            <AlertTriangle className="w-3 h-3" /> new lesion asserted
          </div>
        )}
        <RecistChart assessments={toAssessments(arm.sld_timeline)} baselineSld={baseline} />
        <div className="mt-2 space-y-1">
          {arm.target_tracks.map((t) => {
            const track = trackLookup?.(t.track_key);
            const clickable = Boolean(track && onOpenTrack);
            return (
              <button
                key={`${t.track_key}-${t.source}`}
                type="button"
                disabled={!clickable}
                onClick={() => track && onOpenTrack?.(track)}
                className={cx(
                  "w-full flex items-center justify-between gap-2 text-left text-2xs rounded-md px-2 py-1 border",
                  clickable
                    ? "border-line hover:bg-accent-soft hover:border-accent/40 cursor-pointer"
                    : "border-line-soft"
                )}
              >
                <span className="font-mono text-ink-soft truncate">{t.track_key}</span>
                <span className="flex items-center gap-1.5 shrink-0">
                  <span className="text-ink-muted">{t.organ} · {t.baseline_mm}mm</span>
                  {clickable && <FileSearch className="w-3 h-3 text-accent" />}
                </span>
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-2xs text-ink-muted leading-relaxed">{arm.rationale}</p>
      </div>
    </div>
  );
}

export function ContrastCard({
  contrast,
  trackLookup,
  onConfirmLinks,
}: {
  contrast: RecistContrast;
  trackLookup?: (key: string) => Track | undefined;
  onConfirmLinks?: () => void;
}) {
  const [modalTrack, setModalTrack] = useState<Track | null>(null);
  const { naive, confirmed, discrepancy, discrepancy_note } = contrast;

  return (
    <section
      className={cx(
        "rounded-2xl border-2 p-4 sm:p-5",
        discrepancy ? "border-accent bg-accent-soft/40" : "border-line bg-paper"
      )}
    >
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className={cx("w-5 h-5", discrepancy ? "text-accent" : "text-ink-muted")} />
        <h2 className="text-base font-bold text-ink">RECIST response — automated vs. your confirmed linking</h2>
      </div>

      {discrepancy && confirmed ? (
        <>
          <div className="flex items-center justify-center gap-3 my-3 flex-wrap">
            <Badge tone={classTone(naive.classification)} className="text-sm px-3 py-1">
              Automated: {naive.classification}
              {naive.new_lesion ? " (false new lesion)" : ""}
            </Badge>
            <ArrowRight className="w-5 h-5 text-accent" />
            <Badge tone={classTone(confirmed.classification)} className="text-sm px-3 py-1">
              After your confirmed merge: {confirmed.classification} ({pct(lastPctFromBaseline(confirmed))})
            </Badge>
          </div>
          <p className="text-center text-sm font-semibold text-accent-ink mb-4">
            One human merge flips {naive.classification} → {confirmed.classification}.
          </p>

          <div className="grid gap-4 lg:grid-cols-2">
            <Arm
              title="Automated linking (machine)"
              subtitle="Deterministic linker output, unconfirmed"
              arm={naive}
              tone="danger"
              trackLookup={trackLookup}
              onOpenTrack={setModalTrack}
            />
            <Arm
              title="After your confirmed links"
              subtitle="Human-confirmed lesion identity"
              arm={confirmed}
              tone="good"
              trackLookup={trackLookup}
              onOpenTrack={setModalTrack}
            />
          </div>

          <div className="mt-4 rounded-lg border border-accent/30 bg-paper px-4 py-3 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-accent shrink-0 mt-0.5" />
            <p className="text-xs text-ink-soft">{discrepancy_note}</p>
          </div>
        </>
      ) : (
        <div className="mt-2">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-ink-muted">Automated linking:</span>
            <Badge tone={classTone(naive.classification)}>{naive.classification}</Badge>
            {naive.new_lesion && <Badge tone="danger">new lesion asserted</Badge>}
          </div>
          <Arm
            title="Automated linking (machine)"
            subtitle="Deterministic linker output, unconfirmed"
            arm={naive}
            tone="danger"
            trackLookup={trackLookup}
            onOpenTrack={setModalTrack}
          />
          {!confirmed && (
            <div className="mt-3 rounded-lg border border-warn/30 bg-warn-soft px-4 py-3 text-xs text-warn-ink flex items-center justify-between gap-3">
              <span>
                No human link decisions yet — this is the <strong>unconfirmed</strong> machine call. Confirm
                track links to compute the audit-grade, human-confirmed RECIST.
              </span>
              {onConfirmLinks && (
                <button
                  onClick={onConfirmLinks}
                  className="shrink-0 inline-flex items-center gap-1 font-semibold text-accent-ink hover:underline"
                >
                  Confirm links <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <EvidenceModal track={modalTrack} onClose={() => setModalTrack(null)} />
    </section>
  );
}
