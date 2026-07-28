"use client";

import { Badge, type Tone } from "./ui";
import type { RunStatus } from "@/lib/types";
import { AlertTriangle, ShieldAlert, GitMerge } from "lucide-react";

/** Maps an engine progression label to a display tone + label. */
export function ProgressionBadge({
  progression,
  fallback,
}: {
  progression: string | null | undefined;
  fallback?: string | null;
}) {
  const label = progression || fallback;
  if (!label) return <Badge tone="neutral">not stated</Badge>;
  const p = label.toUpperCase();
  let tone: Tone = "neutral";
  if (["NEW", "WORSENED"].includes(p)) tone = "danger";
  else if (["RESOLVED", "IMPROVED"].includes(p)) tone = "good";
  else if (["STABLE", "PRESENT"].includes(p)) tone = "info";
  else if (["UNCERTAIN", "INDETERMINATE", "NEVER PRESENT", "EMPTY"].includes(p)) tone = "warn";
  else if (["ABSENT THROUGHOUT", "ABSENT", "ACTIVE"].includes(p)) tone = p === "ACTIVE" ? "info" : "quiet";
  return <Badge tone={tone}>{label.replace(/_/g, " ")}</Badge>;
}

export function AssertionBadge({ assertion }: { assertion: string }) {
  const a = assertion.toLowerCase();
  let tone: Tone = "neutral";
  if (a === "present") tone = "info";
  else if (a === "absent") tone = "quiet";
  else if (a === "resolved") tone = "good";
  else if (a === "uncertain") tone = "warn";
  return <Badge tone={tone}>{assertion}</Badge>;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { tone: Tone; label: string }> = {
    queued: { tone: "quiet", label: "Queued" },
    running: { tone: "info", label: "Running" },
    succeeded: { tone: "good", label: "Succeeded" },
    failed: { tone: "danger", label: "Failed" },
  };
  const { tone, label } = map[status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function UnresolvedBadge() {
  return (
    <Badge tone="warn">
      <GitMerge className="w-3 h-3" /> Unresolved link
    </Badge>
  );
}

export function FalseSplitBadge() {
  return (
    <Badge tone="warn">
      <AlertTriangle className="w-3 h-3" /> Possible false split
    </Badge>
  );
}

export function GateFailedBadge() {
  return (
    <Badge tone="danger">
      <ShieldAlert className="w-3 h-3" /> Unverified evidence
    </Badge>
  );
}
