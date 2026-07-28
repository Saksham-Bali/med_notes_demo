"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AppSettings } from "@/lib/types";
import { Badge, Card, ErrorBox, Loading } from "@/components/ui";
import { cx, shortHash } from "@/lib/format";
import { Check, Cpu, GitCommit, Globe, Lock, Sparkles } from "lucide-react";

export default function SettingsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });

  return (
    <div className="max-w-3xl">
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Settings</h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Active extraction configuration for this org
        </p>
      </div>

      {isLoading && <Loading label="Loading settings…" />}
      {error && <ErrorBox message={(error as Error).message} />}

      {data && (
        <div className="space-y-6">
          {data.read_only && (
            <div className="flex items-center gap-2 rounded-lg border border-line bg-paper-soft px-4 py-2.5 text-xs text-ink-muted">
              <Lock className="w-3.5 h-3.5 text-ink-faint" />
              Read-only. The model and prompt are pinned per run in the reproducibility manifest;
              changes are applied through the extraction engine configuration.
            </div>
          )}

          {/* active model */}
          <Card className="p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-ink-muted uppercase tracking-wide">
              <Cpu className="w-4 h-4 text-accent" /> Active model
            </div>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Detail label="Provider" value={data.llm_provider} mono />
              <Detail label="Model" value={data.llm_model} mono />
              <Detail label="Reasoning effort" value={data.reasoning_effort} />
              <Detail label="Temperature" value={String(data.temperature)} mono />
              {data.prompt_version && <Detail label="Prompt version" value={data.prompt_version} mono />}
              {data.schema_version && <Detail label="Schema version" value={data.schema_version} mono />}
            </div>
          </Card>

          {/* model-agnostic story */}
          <Card className="p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-ink-muted uppercase tracking-wide">
              <Sparkles className="w-4 h-4 text-accent" /> Model-agnostic by design
            </div>
            <p className="mt-2 text-sm text-ink-soft">
              FindingFrame is not tied to any single LLM. Extraction runs through a versioned
              engine adapter, and every run records the exact model, prompt and schema in a
              reproducibility manifest — so the provider can change without touching the
              audit-grade record. Available models:
            </p>
            <ul className="mt-3 space-y-1.5">
              {data.available_models.map((m) => {
                const active = m === data.llm_model;
                return (
                  <li
                    key={m}
                    className={cx(
                      "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-mono",
                      active
                        ? "border-accent/30 bg-accent-soft text-accent-ink"
                        : "border-line bg-paper text-ink-soft"
                    )}
                  >
                    {active ? (
                      <Check className="w-4 h-4 text-accent" />
                    ) : (
                      <span className="w-4 h-4" />
                    )}
                    {m}
                    {active && (
                      <Badge tone="info" className="ml-auto">
                        Active
                      </Badge>
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>

          {/* environment */}
          <Card className="p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-ink-muted uppercase tracking-wide">
              <Globe className="w-4 h-4 text-accent" /> Environment
            </div>
            <div className="mt-3 grid gap-4 sm:grid-cols-3">
              <Detail label="Region" value={data.region} mono />
              <Detail label="Environment" value={data.env} />
              <Detail
                label="Engine git sha"
                value={shortHash(data.engine_git_sha)}
                icon={<GitCommit className="w-3.5 h-3.5 text-ink-faint" />}
                mono
              />
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function Detail({
  label,
  value,
  mono,
  icon,
}: {
  label: string;
  value: string;
  mono?: boolean;
  icon?: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-2xs text-ink-muted uppercase tracking-wide">{label}</div>
      <div className={cx("mt-0.5 text-sm text-ink flex items-center gap-1.5", mono && "font-mono")}>
        {icon}
        {value}
      </div>
    </div>
  );
}
