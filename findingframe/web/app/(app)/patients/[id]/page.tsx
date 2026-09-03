"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CreateReportInput, Run } from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Select,
  Textarea,
} from "@/components/ui";
import { RunStatusBadge } from "@/components/Badges";
import { Modal } from "@/components/Modal";
import { WorkflowStepper } from "@/components/WorkflowStepper";
import { fmtDate, fmtDateTime, shortHash } from "@/lib/format";
import {
  ClipboardCheck,
  FileStack,
  FileText,
  Play,
  Plus,
  ShieldOff,
  Trash2,
  Upload,
} from "lucide-react";

export default function PatientPage({ params }: { params: { id: string } }) {
  const patientId = params.id;
  const qc = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);

  const patient = useQuery({ queryKey: ["patient", patientId], queryFn: () => api.getPatient(patientId) });
  const reports = useQuery({ queryKey: ["reports", patientId], queryFn: () => api.listReports(patientId) });
  const runs = useQuery({
    queryKey: ["runs", patientId],
    queryFn: () => api.listRuns(patientId),
    refetchInterval: (q) => {
      const data = q.state.data as Run[] | undefined;
      return data?.some((r) => r.status === "queued" || r.status === "running") ? 1500 : false;
    },
  });

  const runExtraction = useMutation({
    mutationFn: () => api.createRun(patientId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs", patientId] });
      qc.invalidateQueries({ queryKey: ["patient", patientId] });
    },
  });

  const deletePii = useMutation({
    mutationFn: () => api.deleteIdentifiers(patientId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", patientId] }),
  });

  const succeededRun = runs.data?.find((r) => r.status === "succeeded");
  const reportCount = reports.data?.length ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link href="/dashboard" className="text-xs text-ink-muted hover:text-ink">
          ← All patients
        </Link>
        <div className="flex items-start justify-between mt-2 gap-4">
          <div>
            <h1 className="text-xl font-semibold text-ink font-mono">
              {patient.data?.subject_code ?? "…"}
            </h1>
            <p className="text-sm text-ink-muted mt-0.5">{patient.data?.cancer_type || "—"}</p>
          </div>
          <div className="flex items-center gap-2">
            {patient.data?.has_identifiers && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (confirm("DPDP erasure: permanently delete this patient's identifiers? Clinical artifacts remain.")) {
                    deletePii.mutate();
                  }
                }}
                loading={deletePii.isPending}
              >
                <ShieldOff className="w-3.5 h-3.5" /> Erase identifiers
              </Button>
            )}
            {succeededRun && (
              <Link href={`/patients/${patientId}/signoff`}>
                <Button variant="secondary" size="sm">
                  <ClipboardCheck className="w-3.5 h-3.5" /> Sign-off & audit
                </Button>
              </Link>
            )}
          </div>
        </div>
        <div className="mt-4">
          <WorkflowStepper
            current={reportCount === 0 ? "upload" : succeededRun ? "review" : "extract"}
            done={reportCount > 0 ? (succeededRun ? ["upload", "extract"] : ["upload"]) : []}
          />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Reports */}
        <Card>
          <div className="flex items-center justify-between px-4 py-3 border-b border-line">
            <div className="flex items-center gap-2">
              <FileStack className="w-4 h-4 text-accent" />
              <h2 className="font-semibold text-ink text-sm">Reports</h2>
              <span className="text-2xs text-ink-faint bg-paper-sunk rounded-full px-2 py-0.5">
                {reportCount}
              </span>
            </div>
            <Button size="sm" onClick={() => setUploadOpen(true)}>
              <Upload className="w-3.5 h-3.5" /> Upload reports
            </Button>
          </div>
          {reports.isLoading && <Loading />}
          {reports.error && <div className="p-4"><ErrorBox message={(reports.error as Error).message} /></div>}
          {reports.data && reports.data.length === 0 && (
            <EmptyState
              icon={<FileText className="w-7 h-7" />}
              title="No reports"
              description="Paste one or more radiology reports to begin."
              action={
                <Button size="sm" onClick={() => setUploadOpen(true)}>
                  <Plus className="w-3.5 h-3.5" /> Upload reports
                </Button>
              }
            />
          )}
          {reports.data && reports.data.length > 0 && (
            <ul className="divide-y divide-line-soft">
              {reports.data.map((r) => (
                <li key={r.id} className="px-4 py-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink">{r.note_type}</div>
                    <div className="text-xs text-ink-muted mt-0.5">
                      {fmtDate(r.report_date)}
                      {r.external_note_id && <span> · {r.external_note_id}</span>}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-2xs text-ink-faint font-mono">
                      v{r.current_version.version_no} · sha {shortHash(r.current_version.text_sha256, 8)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Runs */}
        <Card>
          <div className="flex items-center justify-between px-4 py-3 border-b border-line">
            <div className="flex items-center gap-2">
              <Play className="w-4 h-4 text-accent" />
              <h2 className="font-semibold text-ink text-sm">Extraction runs</h2>
            </div>
            <Button
              size="sm"
              onClick={() => runExtraction.mutate()}
              loading={runExtraction.isPending}
              disabled={reportCount === 0}
            >
              <Play className="w-3.5 h-3.5" /> Run extraction
            </Button>
          </div>
          {runExtraction.error && (
            <div className="p-4"><ErrorBox message={(runExtraction.error as Error).message} /></div>
          )}
          {runs.isLoading && <Loading />}
          {runs.data && runs.data.length === 0 && (
            <EmptyState
              icon={<Play className="w-7 h-7" />}
              title="No runs yet"
              description={
                reportCount === 0
                  ? "Upload reports first, then run extraction."
                  : "Run extraction to build durable frames and tracks."
              }
            />
          )}
          {runs.data && runs.data.length > 0 && (
            <ul className="divide-y divide-line-soft">
              {runs.data.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </ul>
          )}
        </Card>
      </div>

      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} patientId={patientId} />
    </div>
  );
}

function RunRow({ run }: { run: Run }) {
  const inProgress = run.status === "queued" || run.status === "running";
  const total = run.progress_total ?? 0;
  const done = run.progress_done ?? 0;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <li className="px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="text-xs text-ink-muted">{fmtDateTime(run.created_at)}</span>
          </div>
          <div className="text-2xs text-ink-faint font-mono mt-1">
            {run.model_id || "—"} · manifest {shortHash(run.manifest_hash, 10)}
          </div>
        </div>
        {run.status === "succeeded" && (
          <div className="flex shrink-0 items-center gap-2">
            <Link href={`/runs/${run.id}/progression`}>
              <Button size="sm" variant="subtle">
                Trajectory
              </Button>
            </Link>
            <Link href={`/runs/${run.id}/review`}>
              <Button size="sm" variant="subtle">
                Open review →
              </Button>
            </Link>
          </div>
        )}
      </div>
      {inProgress && (
        <div className="mt-2">
          <div className="h-1.5 rounded-full bg-paper-sunk overflow-hidden">
            <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
          </div>
          <div className="text-2xs text-ink-muted mt-1">
            {done}/{total} reports · {pct}%
          </div>
        </div>
      )}
      {run.status === "failed" && run.error && (
        <p className="mt-2 text-2xs text-danger-ink">{run.error}</p>
      )}
    </li>
  );
}

function UploadModal({
  open,
  onClose,
  patientId,
}: {
  open: boolean;
  onClose: () => void;
  patientId: string;
}) {
  const qc = useQueryClient();
  const [reportDate, setReportDate] = useState("");
  const [noteType, setNoteType] = useState("CT chest w/ contrast");
  const [externalId, setExternalId] = useState("");
  const [text, setText] = useState("");

  const upload = useMutation({
    mutationFn: (inputs: CreateReportInput[]) => api.createReports(patientId, inputs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports", patientId] });
      qc.invalidateQueries({ queryKey: ["patient", patientId] });
      setText("");
      setExternalId("");
      onClose();
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    upload.mutate([
      {
        report_date: reportDate || new Date().toISOString().slice(0, 10),
        note_type: noteType,
        external_note_id: externalId || undefined,
        text,
      },
    ]);
  };

  return (
    <Modal open={open} onClose={onClose} title="Upload report" wide>
      <form onSubmit={submit} className="space-y-4">
        {upload.error && <ErrorBox message={(upload.error as Error).message} />}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Report date">
            <Input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} required />
          </Field>
          <Field label="Note type">
            <Select value={noteType} onChange={(e) => setNoteType(e.target.value)}>
              <option>CT chest w/ contrast</option>
              <option>CT abdomen/pelvis</option>
              <option>PET-CT</option>
              <option>MRI</option>
              <option>Radiology report</option>
            </Select>
          </Field>
          <Field label="Accession / external id">
            <Input value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="ACC-…" />
          </Field>
        </div>
        <Field label="Report text" hint="Paste the full radiology report. Addenda create a new version on re-upload.">
          <Textarea
            rows={12}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="CT CHEST WITH CONTRAST&#10;&#10;FINDINGS: …"
            required
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={upload.isPending}>
            <Upload className="w-4 h-4" /> Upload
          </Button>
        </div>
      </form>
    </Modal>
  );
}
