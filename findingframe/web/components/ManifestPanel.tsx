"use client";

import type { RunManifest } from "@/lib/types";
import { Card } from "./ui";
import { shortHash } from "@/lib/format";
import { FileCog, Fingerprint } from "lucide-react";

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 border-b border-line-soft last:border-0">
      <span className="text-2xs uppercase tracking-wide text-ink-faint shrink-0">{label}</span>
      <span className={mono ? "font-mono text-xs text-ink-soft text-right break-all" : "text-xs text-ink-soft text-right"}>
        {value}
      </span>
    </div>
  );
}

export function ManifestPanel({ manifest }: { manifest: RunManifest }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-2">
        <FileCog className="w-4 h-4 text-accent" />
        <h3 className="text-sm font-semibold text-ink">Reproducibility manifest</h3>
      </div>
      <p className="text-2xs text-ink-muted mb-3">
        Every run is an immutable artifact. Same inputs + manifest → same output.
      </p>
      <div>
        <Row
          label="Manifest hash"
          value={
            <span className="inline-flex items-center gap-1">
              <Fingerprint className="w-3 h-3 text-ink-faint" />
              {shortHash(manifest.manifest_hash, 20)}
            </span>
          }
          mono
        />
        <Row label="Engine SHA" value={shortHash(manifest.engine_git_sha, 12)} mono />
        <Row label="Model" value={`${manifest.model_provider} · ${manifest.model_id}`} />
        <Row label="Prompt version" value={manifest.prompt_version} mono />
        <Row label="Schema version" value={manifest.schema_version} mono />
        <Row label="Temperature" value={String(manifest.temperature)} />
        {manifest.reasoning_effort && <Row label="Reasoning" value={manifest.reasoning_effort} />}
        <Row label="Reports" value={`${manifest.report_manifest?.length ?? 0} versioned`} />
      </div>
    </Card>
  );
}
