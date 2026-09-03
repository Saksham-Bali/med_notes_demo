"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api";
import { ProgressionStory } from "@/components/ProgressionStory";
import { Button, Card, EmptyState, ErrorBox, Loading } from "@/components/ui";
import { Link2 } from "lucide-react";

export default function ProgressionPage({ params }: { params: { id: string } }) {
  const runId = params.id;

  const progression = useQuery({
    queryKey: ["recist-progression", runId],
    queryFn: () => api.getRecistProgression(runId),
    retry: false,
  });
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.getRun(runId) });
  const patient = useQuery({
    queryKey: ["patient", run.data?.patient_id],
    queryFn: () => api.getPatient(run.data!.patient_id),
    enabled: Boolean(run.data?.patient_id),
  });

  if (progression.isLoading) return <Loading label="Loading trajectory…" />;

  const err = progression.error as ApiError | undefined;
  // 422 is the honest "not enough human input yet" answer, not a failure.
  if (err?.status === 422) {
    return (
      <Card>
        <EmptyState
          icon={<Link2 className="w-8 h-8" />}
          title="No trajectory yet"
          description={
            err.message ||
            "A trajectory needs human-confirmed tracks and a target-lesion selection. Confirm the links, then pick target lesions."
          }
          action={
            <Link href={`/runs/${runId}/recist`}>
              <Button>Go to the RECIST worksheet</Button>
            </Link>
          }
        />
      </Card>
    );
  }
  if (err) return <ErrorBox message={err.message} />;
  if (!progression.data) return null;

  return (
    <div className="space-y-5">
      <Link href={`/runs/${runId}/review`} className="text-xs text-ink-muted hover:text-ink">
        ← Review workbench
      </Link>
      <ProgressionStory
        progression={progression.data}
        subjectCode={patient.data?.subject_code ?? null}
        reviewHref={`/runs/${runId}/review`}
      />
    </div>
  );
}
