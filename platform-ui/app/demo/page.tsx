'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import PatientCard from '@/components/PatientCard';
import patientsJson from '@/data/patients.json';
import { getPatients, getPatientState, type PatientSummary } from '@/lib/api';

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

        // Build extras from the patient list data (already has entity counts, dates, regions)
        if (!cancelled) {
          const map: Record<string, PatientExtra> = {};
          for (const p of patientList) {
            map[p.patient_id] = {
              entityCount: p.entity_count,
              firstSeen: p.first_event_date || undefined,
              lastSeen: p.last_event_date || undefined,
              bodyRegions: p.body_regions || [],
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 text-sm text-slate-500 mb-4">
          <Link href="/" className="hover:text-slate-300 transition-colors">Home</Link>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span className="text-slate-300">Demo</span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Patient Explorer</h1>
        <p className="text-slate-400">
          Select a patient to view their clinical summary, timeline, and run extraction workflows.
        </p>
      </div>

      {/* Warning if not seeded */}
      {!loading && !seeded && (
        <div className="bg-amber-400/5 border border-amber-400/20 rounded-xl p-5 mb-8">
          <div className="flex items-start gap-3">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-amber-400 shrink-0 mt-0.5">
              <path d="M10 2l8 15H2L10 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="M10 8v3M10 13v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <div>
              <h3 className="text-sm font-semibold text-amber-400 mb-1">No patient data found</h3>
              <p className="text-sm text-slate-400">
                The fact graph service appears to be empty. Run{' '}
                <code className="text-xs bg-slate-800 px-1.5 py-0.5 rounded font-mono text-slate-300">
                  python scripts/seed_patients.py
                </code>{' '}
                to load patient data, or ensure the orchestrator and fact-graph-service are running.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Patient Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {patients.map((p) => (
            <div key={p.id} className="bg-slate-900 border border-slate-700 rounded-xl p-6 animate-pulse">
              <div className="h-5 bg-slate-800 rounded w-24 mb-2" />
              <div className="h-4 bg-slate-800 rounded w-32 mb-4" />
              <div className="space-y-2">
                <div className="h-3 bg-slate-800 rounded w-full" />
                <div className="h-3 bg-slate-800 rounded w-3/4" />
                <div className="h-3 bg-slate-800 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {patients.map((patient) => (
            <PatientCard
              key={patient.id}
              patient={patient}
              entityCount={extras[patient.id]?.entityCount}
              firstSeen={extras[patient.id]?.firstSeen}
              lastSeen={extras[patient.id]?.lastSeen}
              bodyRegions={extras[patient.id]?.bodyRegions}
            />
          ))}
        </div>
      )}
    </div>
  );
}
