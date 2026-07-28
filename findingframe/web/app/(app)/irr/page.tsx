"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type {
  IrrDisagreement,
  IrrKappaGroup,
  IrrKappaResult,
  IrrTask,
  IrrUnit,
  Patient,
  Run,
} from "@/lib/types";
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
  type Tone,
} from "@/components/ui";
import { Modal } from "@/components/Modal";
import { cx, fmtDate } from "@/lib/format";
import {
  ClipboardCheck,
  EyeOff,
  GitCompareArrows,
  Plus,
  Users,
} from "lucide-react";

// Landis-Koch band -> visual tone
function bandTone(band: string): Tone {
  switch (band) {
    case "almost perfect":
    case "substantial":
      return "good";
    case "moderate":
      return "info";
    case "fair":
      return "warn";
    case "slight":
    case "poor":
      return "danger";
    default:
      return "quiet";
  }
}

function fmtK(v: number | null): string {
  return v == null ? "—" : v.toFixed(3);
}

export default function IrrPage() {
  const tasks = useQuery({ queryKey: ["irr", "tasks"], queryFn: api.irrListTasks });
  const [selected, setSelected] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  const activeId = selected ?? tasks.data?.[0]?.id ?? null;

  return (
    <div>
      <div className="mb-4 rounded-lg border border-warn/30 bg-warn-soft px-4 py-2.5 text-xs text-warn-ink flex items-start gap-2">
        <span className="font-semibold shrink-0">Synthetic pilot data</span>
        <span className="text-warn-ink/90">
          The κ values below demonstrate the inter-rater methodology on synthetic reader
          annotations. They are <span className="font-semibold">not clinician-validated</span> —
          the real Tata Memorial / NCG reader study is pending (see the IRR protocol).
        </span>
      </div>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5 text-accent" /> Clinical validation — inter-rater reliability
          </h1>
          <p className="text-sm text-ink-muted mt-0.5 max-w-3xl">
            Blinded, double-read Cohen&apos;s κ. Two readers in an independence group label the same
            sampled items <span className="font-medium text-ink-soft">without seeing the model&apos;s
            extraction</span> — the chance-corrected agreement between them is the validation
            statistic. This is <span className="font-medium">not</span> the production review workflow
            (which is anchored on the model and cannot be pooled into κ).
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link
            href="/irr/assignments"
            className="text-xs font-medium text-ink-soft hover:text-ink inline-flex items-center gap-1.5 px-3 py-2 rounded-lg hover:bg-paper-sunk"
          >
            <EyeOff className="w-4 h-4" /> My blinded reads
          </Link>
          <Button onClick={() => setNewOpen(true)}>
            <Plus className="w-4 h-4" /> New IRR task
          </Button>
        </div>
      </div>

      {tasks.isLoading && <Loading label="Loading IRR tasks…" />}
      {tasks.error && <ErrorBox message={(tasks.error as Error).message} />}

      {!tasks.isLoading && !tasks.error && (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <div className="space-y-2">
            {(tasks.data ?? []).length === 0 ? (
              <Card className="p-4">
                <EmptyState
                  icon={<ClipboardCheck className="w-6 h-6" />}
                  title="No IRR tasks yet"
                  description="Create a blinded pilot over an extraction run, assign two readers to an independence group, and κ appears here once they submit."
                />
              </Card>
            ) : (
              (tasks.data ?? []).map((t) => (
                <TaskListCard
                  key={t.id}
                  task={t}
                  active={t.id === activeId}
                  onClick={() => setSelected(t.id)}
                />
              ))
            )}
          </div>

          <div>{activeId ? <TaskDetail taskId={activeId} /> : null}</div>
        </div>
      )}

      <NewTaskModal open={newOpen} onClose={() => setNewOpen(false)} onCreated={(id) => setSelected(id)} />
    </div>
  );
}

function TaskListCard({ task, active, onClick }: { task: IrrTask; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "w-full text-left rounded-xl border p-3.5 transition-colors",
        active ? "border-accent bg-accent-soft" : "border-line bg-paper hover:bg-paper-sunk"
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-ink truncate">{task.name}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <Badge tone="neutral">{task.unit_of_agreement}</Badge>
        <Badge tone="quiet">{task.n_items} items</Badge>
        <Badge tone={task.n_annotators && task.n_annotators >= 2 ? "good" : "warn"}>
          {task.n_annotators ?? 0} readers
        </Badge>
      </div>
      <div className="mt-1.5 text-2xs text-ink-muted">{fmtDate(task.created_at)}</div>
    </button>
  );
}

function TaskDetail({ taskId }: { taskId: string }) {
  const task = useQuery({ queryKey: ["irr", "task", taskId], queryFn: () => api.irrGetTask(taskId) });
  const kappa = useQuery({ queryKey: ["irr", "kappa", taskId], queryFn: () => api.irrKappa(taskId) });

  if (task.isLoading || kappa.isLoading) return <Loading label="Loading task…" />;
  if (task.error) return <ErrorBox message={(task.error as Error).message} />;
  const t = task.data;
  if (!t) return null;

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-ink">{t.name}</h2>
            {t.description && <p className="text-sm text-ink-muted mt-0.5">{t.description}</p>}
          </div>
          <Badge tone="info" className="inline-flex items-center gap-1">
            <EyeOff className="w-3 h-3" /> blinded
          </Badge>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-2xs">
          <Meta label="Unit" value={t.unit_of_agreement} />
          <Meta label="Protocol" value={t.protocol_id} />
          <Meta label="Sampled items" value={String(t.n_items)} />
          <Meta label="Run" value={t.run_id ? t.run_id.slice(0, 8) : "—"} />
        </div>
        {t.sampling && Object.keys(t.sampling).length > 0 && (
          <p className="mt-2 text-2xs text-ink-faint">
            {String((t.sampling as Record<string, unknown>).strategy ?? "")}
          </p>
        )}
      </Card>

      <AssignmentsPanel task={t} />
      <KappaPanel data={kappa.data} error={kappa.error as Error | null} />
      <DisagreementsPanel taskId={taskId} />
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-paper-sunk border border-line px-2 py-1">
      <span className="text-ink-faint uppercase tracking-wide">{label}</span>
      <span className="font-medium text-ink-soft">{value}</span>
    </span>
  );
}

// ---- assignments ----------------------------------------------------------
function AssignmentsPanel({ task }: { task: IrrTask }) {
  const qc = useQueryClient();
  const [annotatorId, setAnnotatorId] = useState("");
  const [group, setGroup] = useState("pilot_pair_1");

  const assign = useMutation({
    mutationFn: () =>
      api.irrCreateAssignment(task.id, { annotator_id: annotatorId.trim(), independence_group: group.trim() }),
    onSuccess: () => {
      setAnnotatorId("");
      qc.invalidateQueries({ queryKey: ["irr", "task", task.id] });
      qc.invalidateQueries({ queryKey: ["irr", "kappa", task.id] });
      qc.invalidateQueries({ queryKey: ["irr", "tasks"] });
    },
  });

  const assignments = task.assignments ?? [];

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2">
        <Users className="w-4 h-4 text-accent" />
        <h3 className="text-sm font-semibold text-ink">Reader assignments</h3>
      </div>
      {assignments.length === 0 ? (
        <p className="mt-2 text-sm text-ink-muted">
          No readers assigned. Assign exactly two readers to a shared independence group to form a
          blinded pair.
        </p>
      ) : (
        <div className="mt-3 divide-y divide-line">
          {assignments.map((a) => (
            <div key={a.id} className="flex items-center gap-3 py-2">
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-ink truncate">
                  {a.annotator_name || a.annotator_id}
                </div>
                <div className="text-2xs text-ink-muted">
                  group <span className="font-mono">{a.independence_group ?? "—"}</span> · {a.n_records} records
                </div>
              </div>
              {a.model_output_visible ? (
                <Badge tone="danger">anchored</Badge>
              ) : (
                <Badge tone="info" className="inline-flex items-center gap-1">
                  <EyeOff className="w-3 h-3" /> blinded
                </Badge>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 pt-3 border-t border-line">
        <div className="text-2xs text-ink-muted uppercase tracking-wide mb-2">Assign a reader</div>
        <div className="grid gap-2 sm:grid-cols-[1fr_180px_auto] items-end">
          <Field label="Annotator user id (org member)">
            <Input
              placeholder="auth user uuid"
              value={annotatorId}
              onChange={(e) => setAnnotatorId(e.target.value)}
            />
          </Field>
          <Field label="Independence group">
            <Input value={group} onChange={(e) => setGroup(e.target.value)} />
          </Field>
          <Button
            variant="secondary"
            disabled={!annotatorId.trim() || !group.trim() || assign.isPending}
            loading={assign.isPending}
            onClick={() => assign.mutate()}
          >
            Assign
          </Button>
        </div>
        {assign.error && (
          <p className="mt-2 text-2xs text-danger-ink">{(assign.error as ApiError).message}</p>
        )}
        <p className="mt-2 text-2xs text-ink-faint">
          Assignments are blinded (model_output_visible=false) by construction. Two readers sharing an
          independence group form the pair a κ is computed over.
        </p>
      </div>
    </Card>
  );
}

// ---- kappa table ----------------------------------------------------------
function KappaPanel({ data, error }: { data?: IrrKappaResult; error: Error | null }) {
  if (error) return <ErrorBox message={error.message} />;
  if (!data) return null;

  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink">Cohen&apos;s κ (per slot)</h3>
        <Badge tone={data.available ? "good" : "quiet"}>
          {data.available ? "Available" : "Not yet available"}
        </Badge>
      </div>

      {!data.available ? (
        <p className="mt-2 text-sm text-ink-muted">{data.reason ?? "Not enough annotation data yet."}</p>
      ) : (
        <div className="mt-4 space-y-6">
          {data.groups
            .filter((g) => g.slots.length > 0)
            .map((g) => (
              <KappaGroupTable key={g.independence_group ?? "none"} group={g} />
            ))}
          <div className="pt-3 border-t border-line flex flex-wrap gap-1.5">
            {data.landis_koch.map((b) => (
              <span
                key={b.label}
                className="text-2xs text-ink-muted inline-flex items-center gap-1"
              >
                <Badge tone={bandTone(b.label)}>{b.label}</Badge>
                <span className="text-ink-faint">{b.range}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function KappaGroupTable({ group }: { group: IrrKappaGroup }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-semibold text-ink">
          group <span className="font-mono">{group.independence_group}</span>
        </span>
        <span className="text-2xs text-ink-muted">
          {group.readers.map((r) => r.annotator_name || r.annotator_id.slice(0, 8)).join(" vs ")} ·{" "}
          {group.n_common_items ?? 0} common items
        </span>
        {group.anchored_warning && <Badge tone="danger">anchored — not valid IRR</Badge>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-2xs text-ink-muted uppercase tracking-wide text-left border-b border-line">
              <th className="py-1.5 pr-3 font-semibold">Slot</th>
              <th className="py-1.5 pr-3 font-semibold text-right">n</th>
              <th className="py-1.5 pr-3 font-semibold text-right">Agree</th>
              <th className="py-1.5 pr-3 font-semibold text-right">κ</th>
              <th className="py-1.5 pr-3 font-semibold text-right">95% CI</th>
              <th className="py-1.5 font-semibold">Band</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {group.slots.map((s) => (
              <tr key={s.slot} className={cx(s.slot.startsWith("full_frame") && "bg-paper-sunk")}>
                <td className="py-1.5 pr-3 font-medium text-ink">{s.slot}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-ink-soft">{s.n}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-ink-soft">
                  {s.observed_agreement == null ? "—" : `${(s.observed_agreement * 100).toFixed(1)}%`}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums font-semibold text-ink">
                  {fmtK(s.kappa)}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-2xs text-ink-muted">
                  {s.ci_low == null ? "—" : `[${fmtK(s.ci_low)}, ${fmtK(s.ci_high)}]`}
                </td>
                <td className="py-1.5">
                  <Badge tone={bandTone(s.band)}>{s.band}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---- disagreements / adjudication -----------------------------------------
function DisagreementsPanel({ taskId }: { taskId: string }) {
  const dis = useQuery({
    queryKey: ["irr", "disagreements", taskId],
    queryFn: () => api.irrDisagreements(taskId),
  });

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2">
        <GitCompareArrows className="w-4 h-4 text-accent" />
        <h3 className="text-sm font-semibold text-ink">Adjudication worklist</h3>
        {dis.data && <Badge tone={dis.data.count > 0 ? "warn" : "good"}>{dis.data.count} disagreements</Badge>}
      </div>
      <p className="text-2xs text-ink-muted mt-0.5">
        Items where the two blinded readers disagree. A senior adjudicator (seeing both reads
        and the evidence — this step is not blinded) resolves each into consensus gold.
      </p>

      {dis.isLoading && <Loading label="Loading disagreements…" />}
      {dis.error && <ErrorBox message={(dis.error as Error).message} />}
      {dis.data && dis.data.count === 0 && (
        <p className="mt-3 text-sm text-ink-muted">No disagreements — readers agree on every scored item.</p>
      )}
      {dis.data && dis.data.count > 0 && (
        <div className="mt-3 space-y-3">
          {dis.data.disagreements.map((d) => (
            <DisagreementRow key={`${d.independence_group}-${d.item_ref}`} taskId={taskId} d={d} />
          ))}
        </div>
      )}
    </Card>
  );
}

function DisagreementRow({ taskId, d }: { taskId: string; d: IrrDisagreement }) {
  const qc = useQueryClient();
  const [source, setSource] = useState<"a" | "b">("a");
  const [emitGold, setEmitGold] = useState(true);

  const adjudicate = useMutation({
    mutationFn: () =>
      api.irrAdjudicate(taskId, {
        item_ref: d.item_ref,
        resolves_assignment_ids: d.resolves_assignment_ids,
        consensus: (source === "a" ? d.reader_a.labels : d.reader_b.labels) as Record<string, unknown>,
        emit_gold: emitGold,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["irr", "disagreements", taskId] });
    },
  });

  return (
    <div className="rounded-lg border border-line p-3">
      <div className="text-2xs text-ink-faint font-mono mb-1">{d.item_ref.slice(0, 8)}…</div>
      {d.evidence_text && (
        <p className="text-xs text-ink-soft italic mb-2 border-l-2 border-line-strong pl-2">
          “{d.evidence_text}”
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <ReaderLabels title={d.reader_a.annotator_name || "Reader A"} labels={d.reader_a.labels} highlight={d.differing_slots} />
        <ReaderLabels title={d.reader_b.annotator_name || "Reader B"} labels={d.reader_b.labels} highlight={d.differing_slots} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-2xs text-ink-muted">differs on:</span>
        {d.differing_slots.map((s) => (
          <Badge key={s} tone="warn">{s}</Badge>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 pt-2 border-t border-line">
        <span className="text-2xs text-ink-muted">consensus =</span>
        <Select value={source} onChange={(e) => setSource(e.target.value as "a" | "b")} className="w-auto">
          <option value="a">Reader A&apos;s labels</option>
          <option value="b">Reader B&apos;s labels</option>
        </Select>
        <label className="text-2xs text-ink-soft inline-flex items-center gap-1">
          <input type="checkbox" checked={emitGold} onChange={(e) => setEmitGold(e.target.checked)} />
          promote to gold
        </label>
        <Button size="sm" variant="secondary" loading={adjudicate.isPending} onClick={() => adjudicate.mutate()}>
          Adjudicate
        </Button>
        {adjudicate.isSuccess && <Badge tone="good">resolved</Badge>}
        {adjudicate.error && <span className="text-2xs text-danger-ink">{(adjudicate.error as Error).message}</span>}
      </div>
    </div>
  );
}

function ReaderLabels({
  title,
  labels,
  highlight,
}: {
  title: string;
  labels: Record<string, unknown>;
  highlight: string[];
}) {
  return (
    <div className="rounded-md bg-paper-sunk border border-line p-2">
      <div className="text-2xs font-semibold text-ink-soft mb-1">{title}</div>
      <dl className="space-y-0.5">
        {Object.entries(labels).map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-2 text-2xs">
            <dt className="text-ink-faint">{k}</dt>
            <dd className={cx("font-medium", highlight.includes(k) ? "text-warn-ink" : "text-ink-soft")}>
              {String(v)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ---- new task modal -------------------------------------------------------
function NewTaskModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [patientId, setPatientId] = useState("");
  const [runId, setRunId] = useState("");
  const [unit, setUnit] = useState<IrrUnit>("frame");
  const [sampleSize, setSampleSize] = useState(15);
  const [name, setName] = useState("IRR Pilot — stratified sample");

  const patients = useQuery({ queryKey: ["patients"], queryFn: api.listPatients, enabled: open });
  const runs = useQuery({
    queryKey: ["runs", patientId],
    queryFn: () => api.listRuns(patientId),
    enabled: open && !!patientId,
  });

  const succeededRuns = useMemo(
    () => (runs.data ?? []).filter((r: Run) => r.status === "succeeded"),
    [runs.data]
  );

  const create = useMutation({
    mutationFn: () =>
      api.irrCreateTask({
        name: name.trim(),
        unit_of_agreement: unit,
        run_id: runId,
        sample_size: sampleSize,
      }),
    onSuccess: (t: IrrTask) => {
      qc.invalidateQueries({ queryKey: ["irr", "tasks"] });
      onCreated(t.id);
      onClose();
    },
  });

  return (
    <Modal open={open} onClose={onClose} title="New IRR task" wide>
      <div className="space-y-3">
        <Field label="Task name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Patient" hint="Pick the patient whose run you want to sample from">
          <Select
            value={patientId}
            onChange={(e) => {
              setPatientId(e.target.value);
              setRunId("");
            }}
          >
            <option value="">Select a patient…</option>
            {(patients.data ?? []).map((p: Patient) => (
              <option key={p.id} value={p.id}>
                {p.subject_code}
                {p.cancer_type ? ` · ${p.cancer_type}` : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Extraction run">
          <Select value={runId} onChange={(e) => setRunId(e.target.value)} disabled={!patientId}>
            <option value="">{patientId ? "Select a run…" : "Pick a patient first"}</option>
            {succeededRuns.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id.slice(0, 8)} · {fmtDate(r.created_at)} · {r.model_id ?? ""}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Unit of agreement">
            <Select value={unit} onChange={(e) => setUnit(e.target.value as IrrUnit)}>
              <option value="frame">frame (all slots per frame)</option>
              <option value="slot">slot</option>
              <option value="track">track (linking judgment)</option>
            </Select>
          </Field>
          <Field label="Sample size">
            <Input
              type="number"
              min={1}
              max={1000}
              value={sampleSize}
              onChange={(e) => setSampleSize(Number(e.target.value))}
            />
          </Field>
        </div>

        {create.error && <ErrorBox message={(create.error as ApiError).message} />}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!runId || !name.trim() || create.isPending} loading={create.isPending} onClick={() => create.mutate()}>
            Create task &amp; sample
          </Button>
        </div>
        <p className="text-2xs text-ink-faint">
          Sampling is stratified per protocol (50% standard / 25% unresolved-link|false-split /
          25% low-confidence|gate-adjacent). After creating, assign two readers and open the blinded
          workbench from <Link href="/irr/assignments" className="text-accent underline">My assignments</Link>.
        </p>
      </div>
    </Modal>
  );
}
