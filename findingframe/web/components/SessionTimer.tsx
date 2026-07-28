"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtDuration } from "@/lib/format";
import { Clock, Pause, Play } from "lucide-react";

/**
 * Visible review-session timer. POSTs a review-session on mount (start) and PATCHes
 * it on unmount / pagehide (end: active_seconds, tracks_reviewed). Active seconds
 * only accrue while running, so it measures genuine review time for the ROI story.
 */
export function SessionTimer({
  runId,
  patientId,
  tracksReviewed,
}: {
  runId: string;
  patientId?: string;
  tracksReviewed: number;
}) {
  const [seconds, setSeconds] = useState(0);
  const [running, setRunning] = useState(true);
  const sessionId = useRef<string | null>(null);
  const secondsRef = useRef(0);
  const reviewedRef = useRef(tracksReviewed);
  reviewedRef.current = tracksReviewed;

  // start session once
  useEffect(() => {
    let active = true;
    api.startSession(runId, patientId).then((s) => {
      if (active) sessionId.current = s.id;
    });
    const end = () => {
      if (sessionId.current) {
        api.endSession(sessionId.current, secondsRef.current, reviewedRef.current).catch(() => {});
      }
    };
    window.addEventListener("pagehide", end);
    return () => {
      window.removeEventListener("pagehide", end);
      end();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  // tick
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      secondsRef.current += 1;
      setSeconds(secondsRef.current);
    }, 1000);
    return () => clearInterval(t);
  }, [running]);

  return (
    <div className="inline-flex items-center gap-2 rounded-lg border border-line bg-paper px-3 py-1.5 shadow-card">
      <Clock className="w-4 h-4 text-accent" />
      <span className="font-mono text-sm tabular-nums text-ink">{fmtDuration(seconds)}</span>
      <span className="text-2xs text-ink-muted">review time</span>
      <button
        onClick={() => setRunning((v) => !v)}
        className="ml-1 text-ink-muted hover:text-ink"
        title={running ? "Pause" : "Resume"}
      >
        {running ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}
