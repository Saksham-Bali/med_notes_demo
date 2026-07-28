"use client";

import { forwardRef } from "react";
import type { Review, ReviewInput, Track } from "@/lib/types";
import { EvidenceTable } from "./EvidenceTable";
import { ReviewForm } from "./ReviewForm";
import { FalseSplitBadge, ProgressionBadge, UnresolvedBadge } from "./Badges";
import { Badge } from "./ui";
import { cx } from "@/lib/format";
import { CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";

export const TrackCard = forwardRef<
  HTMLDivElement,
  {
    track: Track;
    index?: number;
    selected?: boolean;
    reviewOpen?: boolean;
    existingReview?: Review;
    submitting?: boolean;
    onSelect?: () => void;
    onToggleReview?: () => void;
    onSubmitReview?: (input: ReviewInput) => void;
  }
>(function TrackCard(
  {
    track,
    selected,
    reviewOpen,
    existingReview,
    submitting,
    onSelect,
    onToggleReview,
    onSubmitReview,
  },
  ref
) {
  const reviewed = Boolean(existingReview);
  return (
    <div
      ref={ref}
      onClick={onSelect}
      className={cx(
        "rounded-xl border bg-paper shadow-card scroll-mt-24 transition-shadow",
        selected ? "border-accent ring-2 ring-accent/25" : "border-line",
        track.false_split_candidate || track.unresolved_link ? "border-l-4 border-l-warn" : ""
      )}
    >
      <div className="flex items-start justify-between gap-3 px-4 pt-3.5 pb-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-ink truncate">{track.display_name}</h3>
            <ProgressionBadge progression={track.progression} fallback={track.latest_status} />
            {reviewed && (
              <span className="inline-flex items-center gap-1 text-2xs font-semibold text-good">
                <CheckCircle2 className="w-3.5 h-3.5" /> reviewed
              </span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 flex-wrap text-2xs text-ink-muted">
            <span className="font-mono">{track.finding_type}</span>
            {track.anatomy && <span>· {track.anatomy}</span>}
            {track.laterality && <span>· {track.laterality}</span>}
            {track.measurement_trend && (
              <Badge tone="neutral" className="normal-case tracking-normal">
                {track.measurement_trend}
              </Badge>
            )}
          </div>
          {track.progression_detail && (
            <p className="mt-1 text-xs text-ink-muted">{track.progression_detail}</p>
          )}
          <div className="mt-2 flex gap-1.5 flex-wrap">
            {track.unresolved_link && <UnresolvedBadge />}
            {track.false_split_candidate && <FalseSplitBadge />}
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleReview?.();
          }}
          className="shrink-0 inline-flex items-center gap-1 text-xs font-medium text-accent hover:text-accent-ink"
        >
          {reviewOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          Review
        </button>
      </div>

      <div className="border-t border-line-soft">
        <EvidenceTable events={track.events} />
      </div>

      {reviewOpen && (
        <div className="px-4 pb-4 pt-1">
          <ReviewForm
            track={track}
            existing={existingReview}
            submitting={submitting}
            onSubmit={(input) => onSubmitReview?.(input)}
          />
        </div>
      )}
    </div>
  );
});
