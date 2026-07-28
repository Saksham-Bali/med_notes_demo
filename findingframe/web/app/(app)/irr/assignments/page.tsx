"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import type { IrrMyAssignment } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorBox, Loading } from "@/components/ui";
import { ClipboardCheck, EyeOff } from "lucide-react";

export default function MyAssignmentsPage() {
  const q = useQuery({ queryKey: ["irr", "mine"], queryFn: api.irrMyAssignments });

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink flex items-center gap-2">
          <ClipboardCheck className="w-5 h-5 text-accent" /> My blinded reads
        </h1>
        <p className="text-sm text-ink-muted mt-0.5">
          IRR annotation assignments assigned to you. Each is a blinded read: you label the sampled
          items from the source report only, without seeing the model&apos;s extraction.
        </p>
      </div>

      {q.isLoading && <Loading label="Loading assignments…" />}
      {q.error && <ErrorBox message={(q.error as Error).message} />}

      {!q.isLoading && !q.error && (
        <div className="space-y-2 max-w-3xl">
          {(q.data?.assignments ?? []).length === 0 ? (
            <Card className="p-4">
              <EmptyState
                icon={<ClipboardCheck className="w-6 h-6" />}
                title="No assignments"
                description="When an admin assigns you to an IRR task, your blinded reads appear here."
              />
            </Card>
          ) : (
            (q.data?.assignments ?? []).map((a: IrrMyAssignment) => (
              <Link key={a.id} href={`/irr/assign/${a.id}`}>
                <Card className="p-4 hover:bg-paper-sunk transition-colors">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink truncate">{a.task_name}</div>
                      <div className="text-2xs text-ink-muted mt-0.5">
                        {a.unit_of_agreement} · group{" "}
                        <span className="font-mono">{a.independence_group ?? "—"}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {!a.model_output_visible && (
                        <Badge tone="info" className="inline-flex items-center gap-1">
                          <EyeOff className="w-3 h-3" /> blinded
                        </Badge>
                      )}
                      <Badge tone={a.n_records >= a.n_items && a.n_items > 0 ? "good" : "warn"}>
                        {a.n_records}/{a.n_items} done
                      </Badge>
                    </div>
                  </div>
                </Card>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}
