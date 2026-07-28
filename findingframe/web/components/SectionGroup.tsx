"use client";

import type { SectionKey } from "@/lib/types";
import { SECTION_META } from "@/lib/types";
import { cx } from "@/lib/format";

const dot: Record<string, string> = {
  danger: "bg-danger",
  warn: "bg-warn",
  good: "bg-good",
  info: "bg-info",
  quiet: "bg-quiet",
};

export function SectionHeader({
  section,
  count,
  action,
}: {
  section: SectionKey;
  count: number;
  action?: React.ReactNode;
}) {
  const meta = SECTION_META[section];
  return (
    <div className="flex items-center gap-2.5 pt-2">
      <span className={cx("w-2 h-2 rounded-full", dot[meta.tone])} />
      <h2 className="text-sm font-bold text-ink">{meta.label}</h2>
      <span className="text-xs text-ink-muted">{meta.description}</span>
      <span className="text-2xs font-semibold text-ink-faint bg-paper-sunk rounded-full px-2 py-0.5">
        {count}
      </span>
      {action && <div className="ml-auto">{action}</div>}
    </div>
  );
}
