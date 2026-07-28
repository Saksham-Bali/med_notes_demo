"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CreatePatientInput } from "@/lib/types";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Loading } from "@/components/ui";
import { RunStatusBadge } from "@/components/Badges";
import { Modal } from "@/components/Modal";
import { fmtDate } from "@/lib/format";
import { FileText, Plus, Stethoscope, UserPlus } from "lucide-react";

export default function DashboardPage() {
  const [open, setOpen] = useState(false);
  const { data: patients, isLoading, error } = useQuery({
    queryKey: ["patients"],
    queryFn: api.listPatients,
  });

  return (
    <div>
      <div className="flex items-end justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-ink">Patients</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            Pseudonymized cohort · longitudinal radiology review
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <UserPlus className="w-4 h-4" /> New patient
        </Button>
      </div>

      {isLoading && <Loading label="Loading patients…" />}
      {error && <ErrorBox message={(error as Error).message} />}

      {patients && patients.length === 0 && (
        <Card>
          <EmptyState
            icon={<Stethoscope className="w-8 h-8" />}
            title="No patients yet"
            description="Create a pseudonymized patient to begin uploading radiology reports and running extraction."
            action={
              <Button onClick={() => setOpen(true)}>
                <Plus className="w-4 h-4" /> New patient
              </Button>
            }
          />
        </Card>
      )}

      {patients && patients.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {patients.map((p) => (
            <Link key={p.id} href={`/patients/${p.id}`}>
              <Card className="p-4 h-full hover:shadow-pop hover:border-line-strong transition-all">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-mono text-sm font-semibold text-ink">{p.subject_code}</div>
                    <div className="text-xs text-ink-muted mt-0.5">{p.cancer_type || "—"}</div>
                  </div>
                  {p.latest_run && <RunStatusBadge status={p.latest_run.status} />}
                </div>
                <DemoLabel subjectCode={p.subject_code} />
                <div className="mt-4 flex items-center gap-4 text-xs text-ink-muted">
                  <span className="inline-flex items-center gap-1">
                    <FileText className="w-3.5 h-3.5" />
                    {p.report_count ?? 0} report{(p.report_count ?? 0) === 1 ? "" : "s"}
                  </span>
                  {p.created_at && <span>· added {fmtDate(p.created_at)}</span>}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <NewPatientModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

/** Descriptor for the two seeded demo patients — the visual heroes of the demo. */
function DemoLabel({ subjectCode }: { subjectCode: string }) {
  if (subjectCode === "DEMO-NSCLC-01") {
    return (
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Badge tone="warn">Synthetic</Badge>
        <span className="text-2xs text-ink-muted">PD→PR money moment</span>
      </div>
    );
  }
  if (subjectCode === "10000935") {
    return (
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Badge tone="info">Real</Badge>
        <span className="text-2xs text-ink-muted">MIMIC-derived</span>
      </div>
    );
  }
  return null;
}

function NewPatientModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [form, setForm] = useState<CreatePatientInput>({ subject_code: "", cancer_type: "" });
  const [withPii, setWithPii] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      api.createPatient({
        subject_code: form.subject_code,
        cancer_type: form.cancer_type || undefined,
        identifiers: withPii ? form.identifiers : undefined,
      }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["patients"] });
      onClose();
      router.push(`/patients/${p.id}`);
    },
  });

  return (
    <Modal open={open} onClose={onClose} title="New patient">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
        className="space-y-4"
      >
        {create.error && <ErrorBox message={(create.error as Error).message} />}
        <Field label="Subject code" hint="A pseudonymous code — never real PII.">
          <Input
            value={form.subject_code}
            onChange={(e) => setForm((f) => ({ ...f, subject_code: e.target.value }))}
            placeholder="TMC-0418"
            required
          />
        </Field>
        <Field label="Cancer type">
          <Input
            value={form.cancer_type ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, cancer_type: e.target.value }))}
            placeholder="Non-small-cell lung carcinoma"
          />
        </Field>

        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input
            type="checkbox"
            checked={withPii}
            onChange={(e) => setWithPii(e.target.checked)}
            className="accent-accent"
          />
          Add identifiers (encrypted at rest; DPDP-deletable)
        </label>

        {withPii && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-lg border border-line bg-paper-soft p-3">
            <Field label="MRN">
              <Input
                onChange={(e) =>
                  setForm((f) => ({ ...f, identifiers: { ...f.identifiers, mrn: e.target.value } }))
                }
              />
            </Field>
            <Field label="Name">
              <Input
                onChange={(e) =>
                  setForm((f) => ({ ...f, identifiers: { ...f.identifiers, name: e.target.value } }))
                }
              />
            </Field>
            <Field label="DOB">
              <Input
                type="date"
                onChange={(e) =>
                  setForm((f) => ({ ...f, identifiers: { ...f.identifiers, dob: e.target.value } }))
                }
              />
            </Field>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create patient
          </Button>
        </div>
      </form>
    </Modal>
  );
}
