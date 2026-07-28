'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import PatientCard from '@/components/PatientCard';
import patientsJson from '@/data/patients.json';
import { getPatients, type PatientSummary } from '@/lib/api';

interface PatientMeta {
  id: string;
  display_name: string;
  cancer_type: string;
  reports_count: number;
  description: string;
}

interface PatientExtra {
  entityCount?: number;
  firstSeen?: string;
  lastSeen?: string;
  bodyRegions?: string[];
}

export default function DemoPage() {
  const patients = patientsJson as PatientMeta[];
  const [extras, setExtras] = useState<Record<string, PatientExtra>>({});
  const [loading, setLoading] = useState(true);
  const [seeded, setSeeded] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setLoading(true);
      try {
        const patientList: PatientSummary[] = await getPatients();

        if (!patientList || patientList.length === 0) {
          setSeeded(false);
          setLoading(false);
          return;
        }

        if (!cancelled) {
          const map: Record<string, PatientExtra> = {};
          for (const patient of patientList) {
            map[patient.patient_id] = {
              entityCount: patient.entity_count,
              firstSeen: patient.first_event_date || undefined,
              lastSeen: patient.last_event_date || undefined,
              bodyRegions: patient.body_regions || [],
            };
          }
          setExtras(map);
          setSeeded(true);
        }
      } catch {
        setSeeded(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadData();
    return () => {
      cancelled = true;
    };
  }, [patients]);

  return (
    <div className="page-shell py-10 sm:py-14">
      <div className="flex items-center gap-2 text-sm text-[rgba(17,17,17,0.46)]">
        <Link href="/" className="hover:text-black">Home</Link>
        <span>·</span>
        <span className="text-black">Demo</span>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-[0.42fr_0.58fr]">
        <div>
          <span className="eyebrow">Patient Explorer</span>
          <h1 className="mt-5 font-display text-5xl text-black sm:text-6xl">Choose a seeded patient and step into the record.</h1>
          <p className="mt-4 max-w-lg text-base leading-7 text-[rgba(17,17,17,0.62)]">
            This demo sits directly on top of the live fact graph service. It is less a dashboard
            and more a quiet index into patient state, workflows, and approvals.
          </p>
        </div>

        {!loading && !seeded ? (
          <div className="surface p-6">
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.42)]">
              Seed Required
            </div>
            <h2 className="mt-3 text-xl font-semibold text-black">No patient data found</h2>
            <p className="mt-2 text-sm leading-6 text-[rgba(17,17,17,0.62)]">
              The fact graph appears empty. Seed patients first or make sure the orchestrator and fact graph
              are reachable through the current tunnel.
            </p>
          </div>
        ) : (
          <div className="surface p-6">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="surface-muted p-4">
                <div className="font-display text-3xl text-black">{patients.length}</div>
                <div className="mt-1 text-xs uppercase tracking-[0.18em] text-[rgba(17,17,17,0.44)]">Patients</div>
              </div>
              <div className="surface-muted p-4">
                <div className="font-display text-3xl text-black">
                  {Object.values(extras).reduce((acc, item) => acc + (item.entityCount || 0), 0) || '—'}
                </div>
                <div className="mt-1 text-xs uppercase tracking-[0.18em] text-[rgba(17,17,17,0.44)]">Entities</div>
              </div>
              <div className="surface-muted p-4">
                <div className="font-display text-3xl text-black">Live</div>
                <div className="mt-1 text-xs uppercase tracking-[0.18em] text-[rgba(17,17,17,0.44)]">Source</div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {patients.map((patient) => (
          <div key={patient.id} className={loading ? 'animate-pulse' : ''}>
            <PatientCard
              patient={patient}
              entityCount={extras[patient.id]?.entityCount}
              firstSeen={extras[patient.id]?.firstSeen}
              lastSeen={extras[patient.id]?.lastSeen}
              bodyRegions={extras[patient.id]?.bodyRegions}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
