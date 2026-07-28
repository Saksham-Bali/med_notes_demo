"use client";

import { cx } from "@/lib/format";
import { Check } from "lucide-react";

export type StepId = "upload" | "extract" | "review" | "links" | "recist" | "signoff";

const STEPS: { id: StepId; label: string }[] = [
  { id: "upload", label: "Upload" },
  { id: "extract", label: "Extract" },
  { id: "review", label: "Review" },
  { id: "links", label: "Confirm links" },
  { id: "recist", label: "RECIST" },
  { id: "signoff", label: "Sign-off" },
];

export function WorkflowStepper({ current, done = [] }: { current: StepId; done?: StepId[] }) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto scroll-thin py-1">
      {STEPS.map((s, i) => {
        const isDone = done.includes(s.id);
        const isCurrent = s.id === current;
        return (
          <div key={s.id} className="flex items-center gap-1 shrink-0">
            <div
              className={cx(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                isCurrent
                  ? "bg-accent text-white"
                  : isDone
                  ? "bg-good-soft text-good-ink"
                  : "bg-paper-sunk text-ink-muted"
              )}
            >
              <span
                className={cx(
                  "w-4 h-4 rounded-full flex items-center justify-center text-2xs",
                  isCurrent ? "bg-white/25" : isDone ? "bg-good/20" : "bg-line-strong text-ink"
                )}
              >
                {isDone ? <Check className="w-2.5 h-2.5" /> : i + 1}
              </span>
              {s.label}
            </div>
            {i < STEPS.length - 1 && <span className="w-4 h-px bg-line-strong" />}
          </div>
        );
      })}
    </div>
  );
}
