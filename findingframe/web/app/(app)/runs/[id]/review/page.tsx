"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Review, ReviewInput, SectionKey, Track } from "@/lib/types";
import { SECTION_ORDER } from "@/lib/types";
import { Button, Card, ErrorBox, Loading } from "@/components/ui";
import { TrackCard } from "@/components/TrackCard";
import { SectionHeader } from "@/components/SectionGroup";
import { QuarantineZone } from "@/components/QuarantineZone";
import { ContrastCard } from "@/components/ContrastCard";
import { LinkConfirmation } from "@/components/LinkConfirmation";
import { ManifestPanel } from "@/components/ManifestPanel";
import { SessionTimer } from "@/components/SessionTimer";
import { cx } from "@/lib/format";
import { CheckCheck, Keyboard, ListChecks, Link2, Ruler } from "lucide-react";

type Tab = "review" | "links";

export default function ReviewPage({ params }: { params: { id: string } }) {
  const runId = params.id;
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("review");

  const digest = useQuery({ queryKey: ["digest", runId], queryFn: () => api.getDigest(runId) });
  const reviews = useQuery({ queryKey: ["reviews", runId], queryFn: () => api.listReviews(runId) });
  const contrast = useQuery({
    queryKey: ["recist-contrast", runId],
    queryFn: () => api.getRecistContrast(runId),
    retry: false,
  });

  const createReview = useMutation({
    mutationFn: (input: ReviewInput) => api.createReview(runId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reviews", runId] }),
  });

  // Flat ordered track list across sections (for keyboard nav).
  const ordered = useMemo(() => {
    if (!digest.data) return [] as { track: Track; section: SectionKey }[];
    const out: { track: Track; section: SectionKey }[] = [];
    for (const section of SECTION_ORDER) {
      for (const track of digest.data.sections[section] ?? []) out.push({ track, section });
    }
    return out;
  }, [digest.data]);

  const reviewsByKey = useMemo(() => {
    const m = new Map<string, Review>();
    for (const r of reviews.data ?? []) m.set(r.track_key, r);
    return m;
  }, [reviews.data]);

  // Lookup for the one-motion jump from a contrast target row to its evidence.
  const trackByKey = useMemo(() => {
    const m = new Map<string, Track>();
    for (const { track } of ordered) m.set(track.track_key, track);
    return m;
  }, [ordered]);

  const [selected, setSelected] = useState(0);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Keyboard nav: j/k move, c toggle review form.
  const onKey = useCallback(
    (e: KeyboardEvent) => {
      if (tab !== "review") return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      if (e.key === "j") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, ordered.length - 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setSelected((s) => Math.max(s - 1, 0));
      } else if (e.key === "c") {
        e.preventDefault();
        const key = ordered[selected]?.track.track_key;
        if (key) setOpenKey((k) => (k === key ? null : key));
      }
    },
    [ordered, selected, tab]
  );

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  useEffect(() => {
    cardRefs.current[selected]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selected]);

  const batchVerifyNegatives = () => {
    const negs = digest.data?.sections.routine_negatives ?? [];
    for (const t of negs) {
      createReview.mutate({
        track_key: t.track_key,
        reviewed_value: { finding_type: t.finding_type, progression: t.progression },
        link_correct: true,
        type_correct: true,
        progression_correct: true,
        latest_status_correct: true,
        false_merge: false,
        false_split: false,
        evidence_valid: true,
        clinically_significant: false,
        comment: "Batch-verified routine negative.",
      });
    }
  };

  if (digest.isLoading) return <Loading label="Loading digest…" />;
  if (digest.error) return <ErrorBox message={(digest.error as Error).message} />;
  if (!digest.data) return null;

  const d = digest.data;
  const reviewedCount = reviews.data?.length ?? 0;
  const gateCount = d.gate_failed.length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <Link href={`/patients/${d.patient.id}`} className="text-xs text-ink-muted hover:text-ink">
          ← {d.patient.subject_code}
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-2">
          <div>
            <h1 className="text-xl font-semibold text-ink">Review workbench</h1>
            <p className="text-sm text-ink-muted mt-0.5">
              {d.patient.subject_code} · {d.report_count} reports · {ordered.length} tracks ·{" "}
              {reviewedCount} reviewed
            </p>
          </div>
          <div className="flex items-center gap-3">
            <SessionTimer runId={runId} patientId={d.patient.id} tracksReviewed={reviewedCount} />
            <Link href={`/runs/${runId}/recist`}>
              <Button variant="secondary" size="sm">
                <Ruler className="w-3.5 h-3.5" /> RECIST worksheet →
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Gate-failed quarantine — the FIRST thing on the page (trust signal), never hidden. */}
      <QuarantineZone frames={d.gate_failed} />

      {/* Money moment: automated vs human-confirmed RECIST, when a discrepancy exists. */}
      {contrast.data && contrast.data.discrepancy && (
        <ContrastCard
          contrast={contrast.data}
          trackLookup={(k) => trackByKey.get(k)}
          onConfirmLinks={() => setTab("links")}
        />
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-line">
        <TabButton active={tab === "review"} onClick={() => setTab("review")}>
          <ListChecks className="w-4 h-4" /> Findings review
        </TabButton>
        <TabButton active={tab === "links"} onClick={() => setTab("links")}>
          <Link2 className="w-4 h-4" /> Confirm track links
          {(() => {
            const n = ordered.filter(
              (o) => o.track.unresolved_link || o.track.false_split_candidate
            ).length;
            return n > 0 ? (
              <span className="ml-1 text-2xs bg-warn text-white rounded-full px-1.5">{n}</span>
            ) : null;
          })()}
        </TabButton>
      </div>

      {tab === "links" ? (
        <LinkConfirmation runId={runId} digest={d} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div className="space-y-6">
            {SECTION_ORDER.map((section) => {
              const tracks = d.sections[section] ?? [];
              if (tracks.length === 0) return null;
              return (
                <section key={section} className="space-y-3">
                  <SectionHeader
                    section={section}
                    count={tracks.length}
                    action={
                      section === "routine_negatives" ? (
                        <Button
                          size="sm"
                          variant="subtle"
                          onClick={batchVerifyNegatives}
                          loading={createReview.isPending}
                        >
                          <CheckCheck className="w-3.5 h-3.5" /> Batch-verify all
                        </Button>
                      ) : undefined
                    }
                  />
                  {tracks.map((track) => {
                    const flatIndex = ordered.findIndex((o) => o.track.track_key === track.track_key);
                    return (
                      <TrackCard
                        key={track.track_key}
                        ref={(el) => {
                          cardRefs.current[flatIndex] = el;
                        }}
                        track={track}
                        selected={flatIndex === selected}
                        reviewOpen={openKey === track.track_key}
                        existingReview={reviewsByKey.get(track.track_key)}
                        submitting={createReview.isPending}
                        onSelect={() => setSelected(flatIndex)}
                        onToggleReview={() =>
                          setOpenKey((k) => (k === track.track_key ? null : track.track_key))
                        }
                        onSubmitReview={(input) => {
                          createReview.mutate(input);
                        }}
                      />
                    );
                  })}
                </section>
              );
            })}
          </div>

          {/* Sidebar */}
          <div className="space-y-4">
            <Card className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Keyboard className="w-4 h-4 text-accent" />
                <h3 className="text-sm font-semibold text-ink">Keyboard</h3>
              </div>
              <ul className="space-y-1.5 text-xs text-ink-soft">
                <li className="flex items-center gap-2"><kbd>j</kbd> / <kbd>k</kbd> next / previous track</li>
                <li className="flex items-center gap-2"><kbd>c</kbd> open / close review form</li>
              </ul>
            </Card>

            <Card className="p-4">
              <h3 className="text-sm font-semibold text-ink mb-2">Provenance summary</h3>
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Tracks</dt>
                  <dd className="text-ink font-medium">{ordered.length}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Reviewed</dt>
                  <dd className="text-ink font-medium">{reviewedCount}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className={cx(gateCount ? "text-danger-ink font-semibold" : "text-ink-muted")}>
                    Quarantined
                  </dt>
                  <dd className={cx(gateCount ? "text-danger-ink font-semibold" : "text-ink")}>
                    {gateCount}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 text-2xs text-ink-muted leading-relaxed">
                100% source-linked. Gate-failed facts are quarantined above for mandatory review —
                never silently included.
              </p>
            </Card>

            {d.manifest && <ManifestPanel manifest={d.manifest} />}
          </div>
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
        active
          ? "border-accent text-accent-ink"
          : "border-transparent text-ink-muted hover:text-ink"
      )}
    >
      {children}
    </button>
  );
}
