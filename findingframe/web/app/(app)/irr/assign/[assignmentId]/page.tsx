"use client";

import { useMemo, useState } from "react";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { IrrBlindedItem, IrrItemsResponse } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Select,
} from "@/components/ui";
import { ArrowLeft, ArrowRight, Check, EyeOff, ShieldAlert } from "lucide-react";

const ASSERTION_OPTIONS = ["present", "absent", "uncertain", "not_mentioned"];

export default function BlindedWorkbenchPage({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = use(params);
  const q = useQuery({
    queryKey: ["irr", "items", assignmentId],
    queryFn: () => api.irrAssignmentItems(assignmentId),
  });

  if (q.isLoading) return <Loading label="Loading blinded workbench…" />;
  if (q.error) return <ErrorBox message={(q.error as Error).message} />;
  if (!q.data) return null;

  return <Workbench assignmentId={assignmentId} data={q.data} />;
}

function Workbench({ assignmentId, data }: { assignmentId: string; data: IrrItemsResponse }) {
  const qc = useQueryClient();
  const items = data.items;
  const firstUnsubmitted = Math.max(0, items.findIndex((i) => !i.submitted));
  const [idx, setIdx] = useState(firstUnsubmitted === -1 ? 0 : firstUnsubmitted);
  const submittedCount = items.filter((i) => i.submitted).length;

  const item = items[idx];
  const isTrack = data.assignment.unit_of_agreement === "track";

  const submit = useMutation({
    mutationFn: (labels: Record<string, unknown>) =>
      api.irrSubmitRecord(assignmentId, { item_ref: item.item_ref, labels }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["irr", "items", assignmentId] });
      qc.invalidateQueries({ queryKey: ["irr", "mine"] });
      if (idx < items.length - 1) setIdx(idx + 1);
    },
  });

  return (
    <div className="max-w-4xl">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <Link href="/irr/assignments" className="text-2xs text-ink-muted hover:text-ink inline-flex items-center gap-1">
            <ArrowLeft className="w-3 h-3" /> My blinded reads
          </Link>
          <h1 className="text-lg font-semibold text-ink mt-1">{data.assignment.task_name}</h1>
        </div>
        <Badge tone="info" className="inline-flex items-center gap-1 shrink-0">
          <EyeOff className="w-3 h-3" /> blinded read
        </Badge>
      </div>

      {/* blinding assurance banner */}
      <div className="mb-4 rounded-lg border border-info/30 bg-info-soft px-4 py-2.5 text-xs text-info-ink flex items-start gap-2">
        <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          You are seeing only the <span className="font-semibold">source report and candidate
          sentence</span>. The model&apos;s extraction is hidden so your labels are independent — this is
          what makes the agreement statistic valid.
        </span>
      </div>

      {/* progress */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-2xs text-ink-muted mb-1">
          <span>
            Item {idx + 1} of {items.length}
          </span>
          <span>
            {submittedCount}/{data.n_items} submitted
          </span>
        </div>
        <div className="h-2 rounded-full bg-paper-sunk overflow-hidden">
          <div
            className="h-full rounded-full bg-accent transition-all"
            style={{ width: `${data.n_items ? (submittedCount / data.n_items) * 100 : 0}%` }}
          />
        </div>
      </div>

      {items.length === 0 ? (
        <Card className="p-4">
          <EmptyState title="No items in this assignment" description="Nothing to label." />
        </Card>
      ) : (
        <Card className="p-5">
          {isTrack ? (
            <TrackItemForm
              key={item.item_ref}
              item={item}
              submitted={item.submitted}
              onSubmit={(labels) => submit.mutate(labels)}
              pending={submit.isPending}
            />
          ) : (
            <FrameItemForm
              key={item.item_ref}
              item={item}
              slotFields={data.slot_fields}
              submitted={item.submitted}
              onSubmit={(labels) => submit.mutate(labels)}
              pending={submit.isPending}
            />
          )}

          {submit.error && (
            <p className="mt-3 text-2xs text-danger-ink">{(submit.error as ApiError).message}</p>
          )}

          <div className="mt-5 flex items-center justify-between pt-4 border-t border-line">
            <Button variant="ghost" size="sm" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
              <ArrowLeft className="w-4 h-4" /> Prev
            </Button>
            <div className="flex gap-1">
              {items.map((it, i) => (
                <button
                  key={it.item_ref}
                  onClick={() => setIdx(i)}
                  aria-label={`Go to item ${i + 1}`}
                  className={`w-2 h-2 rounded-full ${
                    i === idx ? "bg-accent" : it.submitted ? "bg-good" : "bg-line-strong"
                  }`}
                />
              ))}
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled={idx === items.length - 1}
              onClick={() => setIdx(idx + 1)}
            >
              Next <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function SourcePanel({ item }: { item: IrrBlindedItem }) {
  const [showFull, setShowFull] = useState(false);
  return (
    <div>
      <div className="text-2xs text-ink-muted uppercase tracking-wide mb-1">Candidate sentence (source)</div>
      <p className="text-sm text-ink border-l-2 border-accent pl-3 py-1 bg-accent-soft/40 rounded-r">
        {item.evidence_text || "—"}
      </p>
      {item.full_text && (
        <div className="mt-2">
          <button
            className="text-2xs text-accent hover:underline"
            onClick={() => setShowFull((s) => !s)}
          >
            {showFull ? "Hide" : "View"} full source report
          </button>
          {showFull && (
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-paper-sunk p-3 text-2xs text-ink-soft leading-relaxed font-mono">
              {item.full_text}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function FrameItemForm({
  item,
  slotFields,
  submitted,
  onSubmit,
  pending,
}: {
  item: IrrBlindedItem;
  slotFields: string[];
  submitted?: boolean;
  onSubmit: (labels: Record<string, unknown>) => void;
  pending: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const set = (k: string, v: string) => setValues((p) => ({ ...p, [k]: v }));

  const labels = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const f of slotFields) {
      const v = (values[f] ?? "").trim();
      if (v !== "") out[f] = v;
    }
    return out;
  }, [values, slotFields]);

  return (
    <div className="space-y-4">
      <SourcePanel item={item} />
      {submitted && (
        <Badge tone="good" className="inline-flex items-center gap-1">
          <Check className="w-3 h-3" /> already submitted
        </Badge>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {slotFields.map((f) => (
          <Field key={f} label={f.replace(/_/g, " ")}>
            {f === "assertion" ? (
              <Select value={values[f] ?? ""} onChange={(e) => set(f, e.target.value)}>
                <option value="">—</option>
                {ASSERTION_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                value={values[f] ?? ""}
                placeholder={f === "measurement" ? "e.g. 21 mm" : "your label"}
                onChange={(e) => set(f, e.target.value)}
              />
            )}
          </Field>
        ))}
      </div>
      <Button disabled={Object.keys(labels).length === 0 || pending} loading={pending} onClick={() => onSubmit(labels)}>
        {submitted ? "Resubmit" : "Submit"} label
      </Button>
    </div>
  );
}

function TrackItemForm({
  item,
  submitted,
  onSubmit,
  pending,
}: {
  item: IrrBlindedItem;
  submitted?: boolean;
  onSubmit: (labels: Record<string, unknown>) => void;
  pending: boolean;
}) {
  const [linked, setLinked] = useState<string>("");
  return (
    <div className="space-y-4">
      <div>
        <div className="text-2xs text-ink-muted uppercase tracking-wide mb-1">
          Member evidence sentences (source)
        </div>
        <ul className="space-y-1.5">
          {(item.member_evidence ?? []).map((m, i) => (
            <li key={i} className="text-sm text-ink border-l-2 border-line-strong pl-3">
              {m.evidence_text}
            </li>
          ))}
        </ul>
      </div>
      {submitted && (
        <Badge tone="good" className="inline-flex items-center gap-1">
          <Check className="w-3 h-3" /> already submitted
        </Badge>
      )}
      <Field label="Do these belong to the same longitudinal finding?">
        <Select value={linked} onChange={(e) => setLinked(e.target.value)}>
          <option value="">—</option>
          <option value="true">Yes — same track</option>
          <option value="false">No — different findings</option>
        </Select>
      </Field>
      <Button
        disabled={linked === "" || pending}
        loading={pending}
        onClick={() => onSubmit({ belongs_to_same_track: linked === "true" })}
      >
        {submitted ? "Resubmit" : "Submit"} judgment
      </Button>
    </div>
  );
}
