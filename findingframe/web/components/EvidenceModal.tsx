"use client";

import type { Track } from "@/lib/types";
import { Modal } from "./Modal";
import { EvidenceTable } from "./EvidenceTable";
import { ProgressionBadge } from "./Badges";

/** One-motion jump from a target row/track to its highlighted verbatim evidence. */
export function EvidenceModal({
  track,
  onClose,
}: {
  track: Track | null;
  onClose: () => void;
}) {
  return (
    <Modal open={Boolean(track)} onClose={onClose} title="Source evidence" wide>
      {track && (
        <div>
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <h3 className="text-sm font-semibold text-ink">{track.display_name}</h3>
            <ProgressionBadge progression={track.progression} fallback={track.latest_status} />
            <span className="text-2xs font-mono text-ink-muted">{track.track_key}</span>
          </div>
          <p className="text-2xs text-ink-muted mb-2">
            Expand any row to see the verbatim sentence highlighted in the full source report.
          </p>
          <div className="rounded-lg border border-line overflow-hidden">
            <EvidenceTable events={track.events} />
          </div>
        </div>
      )}
    </Modal>
  );
}
