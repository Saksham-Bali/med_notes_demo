"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AuditFrame,
  AuditPacket,
  AuditTiming,
  RecistAssessment,
  RecistResult,
} from "@/lib/types";
import { Badge, Button, Card, EmptyState, ErrorBox, Loading } from "@/components/ui";
import { ManifestPanel } from "@/components/ManifestPanel";
import { AssertionBadge } from "@/components/Badges";
import { fmtDate, fmtDateTime, fmtDuration, shortHash } from "@/lib/format";
import {
  CheckCircle2,
  Clock,
  Download,
  FileJson,
  GitMerge,
  Link2,
  PenLine,
  ShieldAlert,
  ShieldCheck,
  Signature,
  Table,
} from "lucide-react";

export default function SignoffPage({ params }: { params: { id: string } }) {
  const patientId = params.id;
  const qc = useQueryClient();

  const patient = useQuery({ queryKey: ["patient", patientId], queryFn: () => api.getPatient(patientId) });
  const runs = useQuery({ queryKey: ["runs", patientId], queryFn: () => api.listRuns(patientId) });

  const latestRun = runs.data?.find((r) => r.status === "succeeded");
  const runId = latestRun?.id;

  const packet = useQuery({
    queryKey: ["audit-packet", runId],
    queryFn: () => api.auditPacket(runId as string),
    enabled: Boolean(runId),
  });

  // Signoffs are carried inside the audit packet (there is no GET signoffs endpoint).
  const signoffList = packet.data?.signoffs ?? [];

  const sign = useMutation({
    mutationFn: () => api.signoff(patientId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["audit-packet", runId] });
    },
  });

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const download = (format: "json" | "csv") => {
    if (!packet.data) return;
    if (format === "json") {
      triggerDownload(
        new Blob([JSON.stringify(packet.data, null, 2)], { type: "application/json" }),
        `audit-packet-${patient.data?.subject_code ?? patientId}.json`
      );
    } else {
      triggerDownload(
        new Blob([toCsv(packet.data)], { type: "text/csv" }),
        `audit-facts-${patient.data?.subject_code ?? patientId}.csv`
      );
    }
  };

  const downloadPdf = useMutation({
    mutationFn: () => api.auditPacketPdf(runId as string),
    onSuccess: ({ blob, filename }) =>
      triggerDownload(blob, filename || `audit-packet-${patient.data?.subject_code ?? patientId}.pdf`),
  });

  if (runs.isLoading) return <Loading />;

  if (!runId) {
    return (
      <Card>
        <EmptyState
          icon={<ShieldAlert className="w-8 h-8" />}
          title="No succeeded run to sign off"
          description="Run extraction and review the findings before sign-off."
          action={
            <Link href={`/patients/${patientId}`}>
              <Button variant="secondary">← Back to patient</Button>
            </Link>
          }
        />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/patients/${patientId}`} className="text-xs text-ink-muted hover:text-ink">
          ← {patient.data?.subject_code}
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-accent" />
            <h1 className="text-xl font-semibold text-ink">Sign-off & audit packet</h1>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              size="sm"
              onClick={() => downloadPdf.mutate()}
              loading={downloadPdf.isPending}
              disabled={!packet.data}
            >
              <Download className="w-3.5 h-3.5" /> Download signed audit packet (PDF)
            </Button>
            <Button variant="secondary" size="sm" onClick={() => download("json")} disabled={!packet.data}>
              <FileJson className="w-3.5 h-3.5" /> JSON
            </Button>
            <Button variant="secondary" size="sm" onClick={() => download("csv")} disabled={!packet.data}>
              <Table className="w-3.5 h-3.5" /> CSV
            </Button>
            <Button variant="secondary" onClick={() => sign.mutate()} loading={sign.isPending}>
              <PenLine className="w-4 h-4" /> Sign off
            </Button>
          </div>
        </div>
        {sign.error && <div className="mt-3"><ErrorBox message={(sign.error as Error).message} /></div>}
        {downloadPdf.error && (
          <div className="mt-3"><ErrorBox message={(downloadPdf.error as Error).message} /></div>
        )}
      </div>

      {/* Attested read-time (tamper-evident, from the hash-chained audit_log) */}
      {packet.data?.timing && <AttestedTime timing={packet.data.timing} />}

      {/* Signatures (hash chain) */}
      <Card className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Signature className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold text-ink">Signatures</h2>
          <span className="text-2xs text-ink-muted">hash-chained · append-only</span>
        </div>
        {signoffList.length > 0 ? (
          <ol className="space-y-2">
            {signoffList.map((so, i) => (
              <li key={so.id ?? so.payload_sha256 ?? i} className="flex items-start gap-3 text-xs">
                <CheckCircle2 className="w-4 h-4 text-good shrink-0 mt-0.5" />
                <div className="font-mono">
                  <div className="text-ink">
                    #{i + 1} · {so.signed_by_name || so.signed_by} · {fmtDateTime(so.signed_at)}
                  </div>
                  <div className="text-ink-muted">payload {shortHash(so.payload_sha256, 24)}</div>
                  <div className="text-ink-faint">prev {shortHash(so.prev_signoff_sha256, 24)}</div>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-ink-muted">
            Not yet signed. Sign-off hashes the run manifest + review deltas + link decisions +
            RECIST inputs and chains from the prior signature.
          </p>
        )}
      </Card>

      {packet.isLoading && <Loading label="Assembling audit packet…" />}
      {packet.error && <ErrorBox message={(packet.error as Error).message} />}

      {packet.data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div className="space-y-6">
            <FactsTable packet={packet.data} />
            <DecisionsPanel packet={packet.data} />
            <RecistPanel packet={packet.data} />
          </div>
          <div className="space-y-4">
            <PatientCard packet={packet.data} />
            <ManifestPanel manifest={packet.data.manifest} />
          </div>
        </div>
      )}
    </div>
  );
}

function AttestedTime({ timing }: { timing: AuditTiming }) {
  const active = timing.active_review_seconds ?? timing.elapsed_seconds;
  if (active == null) return null;
  return (
    <div className="rounded-xl border border-good/30 bg-good-soft/60 px-4 py-3 flex items-center gap-3">
      <div className="w-9 h-9 rounded-lg bg-good/15 flex items-center justify-center shrink-0">
        <Clock className="w-5 h-5 text-good-ink" />
      </div>
      <div>
        <div className="text-sm font-semibold text-good-ink">
          Attested review time: {fmtDuration(active)}{" "}
          <span className="font-normal text-good-ink/80">(cryptographically logged)</span>
        </div>
        <div className="text-2xs text-ink-muted mt-0.5">
          Derived from the {timing.source ?? "hash-chained audit_log"}
          {timing.first_action_at && timing.signoff_at
            ? ` · ${fmtDateTime(timing.first_action_at)} → ${fmtDateTime(timing.signoff_at)}`
            : ""}
          . Tamper-evident — not a self-reported estimate.
        </div>
      </div>
    </div>
  );
}

function PatientCard({ packet }: { packet: AuditPacket }) {
  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold text-ink mb-2">Patient (pseudonymized)</h3>
      <dl className="text-xs space-y-1">
        <div className="flex justify-between"><dt className="text-ink-muted">Subject</dt><dd className="font-mono text-ink">{packet.patient.subject_code}</dd></div>
        <div className="flex justify-between"><dt className="text-ink-muted">Cancer</dt><dd className="text-ink text-right">{packet.patient.cancer_type || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-ink-muted">Generated</dt><dd className="text-ink">{fmtDateTime(packet.generated_at)}</dd></div>
        <div className="flex justify-between"><dt className="text-ink-muted">Facts</dt><dd className="text-ink">{packet.frames.length}</dd></div>
      </dl>
    </Card>
  );
}

function FactsTable({ packet }: { packet: AuditPacket }) {
  return (
    <Card>
      <div className="px-4 py-3 border-b border-line">
        <h2 className="text-sm font-semibold text-ink">Every fact with verbatim evidence</h2>
        <p className="text-2xs text-ink-muted mt-0.5">
          Each row anchors to its source sentence. Unverified rows are flagged, never hidden.
        </p>
      </div>
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-2xs uppercase tracking-wide text-ink-faint border-b border-line">
              <th className="px-3 py-2 font-semibold">Date</th>
              <th className="px-3 py-2 font-semibold">Finding</th>
              <th className="px-3 py-2 font-semibold">Assertion</th>
              <th className="px-3 py-2 font-semibold">Meas.</th>
              <th className="px-3 py-2 font-semibold">Evidence (verbatim)</th>
              <th className="px-3 py-2 font-semibold">Gate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {packet.frames.map((f, i) => (
              <tr key={i} className={f.evidence_verified ? "" : "bg-danger-soft/40"}>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-ink-soft">{fmtDate(frameDate(f, packet))}</td>
                <td className="px-3 py-2 text-xs">
                  <div className="text-ink font-medium">{f.display_name || f.finding_type}</div>
                  <div className="text-ink-muted">{[f.anatomy, f.laterality].filter(Boolean).join(" · ")}</div>
                </td>
                <td className="px-3 py-2"><AssertionBadge assertion={f.assertion} /></td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-ink-soft">{f.measurement || "—"}</td>
                <td className="px-3 py-2 evidence text-ink max-w-md">“{f.evidence_text}”</td>
                <td className="px-3 py-2">
                  {f.evidence_verified ? (
                    <Badge tone="good">verified</Badge>
                  ) : (
                    <Badge tone="danger">
                      <ShieldAlert className="w-3 h-3" /> unverified
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function DecisionsPanel({ packet }: { packet: AuditPacket }) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <Card className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <GitMerge className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold text-ink">Human link decisions</h2>
        </div>
        {packet.link_decisions.length > 0 ? (
          <ul className="space-y-2 text-xs">
            {packet.link_decisions.map((d, i) => (
              <li key={d.id ?? d.signature_sha256 ?? i} className="border-b border-line-soft pb-1.5 last:border-0">
                <Badge tone="info">{d.decision}</Badge>
                <span className="font-mono text-ink-muted ml-1.5">{d.primary_track_key}</span>
                {d.rationale && <p className="text-ink-muted mt-0.5">{d.rationale}</p>}
                <p className="font-mono text-2xs text-ink-faint">sig {shortHash(d.signature_sha256, 16)}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-ink-muted">No link decisions recorded.</p>
        )}
      </Card>

      <Card className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <CheckCircle2 className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold text-ink">Reviews ({packet.reviews.length})</h2>
        </div>
        {packet.reviews.length > 0 ? (
          <ul className="space-y-2 text-xs">
            {packet.reviews.map((r, i) => (
              <li key={r.id ?? `${r.track_key}-${i}`} className="border-b border-line-soft pb-1.5 last:border-0">
                <span className="font-mono text-ink-soft">{r.track_key}</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {r.link_correct && <Badge tone="good">link ✓</Badge>}
                  {r.false_split && <Badge tone="danger">false split</Badge>}
                  {r.false_merge && <Badge tone="danger">false merge</Badge>}
                  {r.evidence_valid && <Badge tone="good">evidence ✓</Badge>}
                </div>
                {r.comment && <p className="text-ink-muted mt-0.5">{r.comment}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-ink-muted">No reviews recorded.</p>
        )}
      </Card>
    </div>
  );
}

function RecistPanel({ packet }: { packet: AuditPacket }) {
  // packet.recist may be the RecistResult object, a bare assessments array, or null.
  const r = packet.recist;
  const result: RecistResult | null =
    r && !Array.isArray(r) ? r : null;
  const assessments: RecistAssessment[] = result
    ? result.assessments ?? []
    : Array.isArray(r)
    ? r
    : [];
  const targetSel = packet.target_selection;
  const targetCount = result
    ? result.targets.length
    : Array.isArray(targetSel)
    ? targetSel.length
    : targetSel?.selections?.length ?? 0;
  const overall = assessments.length ? assessments[assessments.length - 1]?.response ?? "—" : "—";

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-2">
        <Link2 className="w-4 h-4 text-accent" />
        <h2 className="text-sm font-semibold text-ink">RECIST (over confirmed tracks)</h2>
      </div>
      {targetCount > 0 ? (
        <div className="text-xs">
          <div className="flex flex-wrap gap-4 mb-2">
            <span>Overall: <strong>{overall}</strong></span>
            {result && <span>Baseline SLD: {result.baseline_sld_mm ?? "—"} mm</span>}
            <span>Target lesions: {targetCount}</span>
          </div>
          {assessments.length > 0 ? (
            <table className="w-full">
              <thead>
                <tr className="text-left text-2xs uppercase text-ink-faint border-b border-line">
                  <th className="py-1">Date</th>
                  <th className="py-1">SLD</th>
                  <th className="py-1">Response</th>
                </tr>
              </thead>
              <tbody>
                {assessments.map((a, i) => (
                  <tr key={i} className="border-b border-line-soft last:border-0">
                    <td className="py-1 text-ink-soft">{fmtDate(a.report_date ?? a.date)}</td>
                    <td className="py-1 font-mono">{a.sld_mm ?? a.sum_longest_diameter_mm ?? "—"} mm</td>
                    <td className="py-1">{a.response ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-ink-muted">
              Baseline signed; no per-timepoint assessments (source reports lack normalized
              measurements). RECIST is never fabricated.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-ink-muted">
          No RECIST computed — confirm track links and select target lesions in the RECIST worksheet.
        </p>
      )}
    </Card>
  );
}

/** Frames don't carry a date; resolve it from the manifest's report_manifest. */
function frameDate(f: AuditFrame, packet: AuditPacket): string | undefined {
  if (f.report_date) return f.report_date;
  if (!f.report_version_id) return undefined;
  const rm = packet.manifest?.report_manifest ?? [];
  const hit = rm.find((r) => r.report_version_id === f.report_version_id);
  return hit?.chart_date;
}

function toCsv(packet: AuditPacket): string {
  const header = [
    "report_date",
    "finding_type",
    "display_name",
    "anatomy",
    "laterality",
    "assertion",
    "measurement",
    "evidence_verified",
    "evidence_text",
  ];
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = packet.frames.map((f) =>
    [
      frameDate(f, packet),
      f.finding_type,
      f.display_name,
      f.anatomy,
      f.laterality,
      f.assertion,
      f.measurement,
      f.evidence_verified,
      f.evidence_text,
    ]
      .map(esc)
      .join(",")
  );
  return [header.join(","), ...rows].join("\n");
}
