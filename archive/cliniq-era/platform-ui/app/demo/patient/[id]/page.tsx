'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import ClinicalSummary from '@/components/ClinicalSummary';
import PatientTimeline from '@/components/PatientTimeline';
import patientsJson from '@/data/patients.json';
import { getPatientState, getPatientTimeline } from '@/lib/api';
import type { PatientState, PatientTimeline as Timeline } from '@/lib/types';

type Tab = 'summary' | 'timeline' | 'add';

interface PatientMeta {
  id: string;
  display_name: string;
  cancer_type: string;
  reports_count: number;
  description: string;
}

const workflowCards = [
  { title: 'Radiology report', description: 'Extract grounded findings from imaging text.', href: 'workflow/radiology' },
  { title: 'Handwritten note', description: 'OCR, SOAP extraction, and review.', href: 'workflow/note' },
  { title: 'Counselling session', description: 'Audio transcription and clinician approval.', href: 'workflow/counselling' },
  { title: 'Department merge', description: 'Combine departmental notes with conflict handling.', href: 'workflow/merge' },
  { title: 'Discharge summary', description: 'Generate, validate, and translate summary output.', href: 'workflow/summary' },
];

export default function PatientDetailPage() {
  const params = useParams();
  const patientId = params.id as string;
  const [tab, setTab] = useState<Tab>('summary');
  const [state, setState] = useState<PatientState | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const meta = (patientsJson as PatientMeta[]).find((patient) => patient.id === patientId);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [patientState, patientTimeline] = await Promise.all([
          getPatientState(patientId),
          getPatientTimeline(patientId),
        ]);
        if (!cancelled) {
          setState(patientState);
          setTimeline(patientTimeline);
        }
      } catch (eventualError) {
        if (!cancelled) {
          setError(eventualError instanceof Error ? eventualError.message : 'Failed to load patient data');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  const tabs: { key: Tab; label: string }[] = [
    { key: 'summary', label: 'Clinical Summary' },
    { key: 'timeline', label: 'Timeline' },
    { key: 'add', label: 'Workflows' },
  ];

  return (
    <div className="page-shell py-10">
      <div className="flex items-center gap-2 text-sm text-[rgba(17,17,17,0.46)]">
        <Link href="/" className="hover:text-black">Home</Link>
        <span>·</span>
        <Link href="/demo" className="hover:text-black">Demo</Link>
        <span>·</span>
        <span className="text-black">{meta?.display_name || patientId}</span>
      </div>

      <div className="mt-6 surface p-6 sm:p-8">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-start">
          <div>
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">
              Longitudinal Record
            </div>
            <h1 className="mt-3 font-display text-5xl text-black">
              {meta?.display_name || `Patient ${patientId}`}
            </h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-[rgba(17,17,17,0.6)]">
              {meta ? `${meta.cancer_type} cancer · ${meta.description}` : 'Patient-specific state, timelines, and workflow entry points.'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <div className="surface-muted p-4">
              <div className="text-[rgba(17,17,17,0.42)] text-xs uppercase tracking-[0.18em]">Patient ID</div>
              <div className="mt-1 font-mono-ui text-black">{patientId}</div>
            </div>
            <div className="surface-muted p-4">
              <div className="text-[rgba(17,17,17,0.42)] text-xs uppercase tracking-[0.18em]">Entities</div>
              <div className="mt-1 font-mono-ui text-black">{state?.entities.length ?? '—'}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.key}
            onClick={() => setTab(item.key)}
            className={`rounded-full px-4 py-2 text-sm ${
              tab === item.key
                ? 'bg-black text-[#faf7f1]'
                : 'border border-[rgba(17,17,17,0.1)] bg-white/70 text-[rgba(17,17,17,0.58)]'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-6 surface p-5">
          <p className="text-sm text-black">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="mt-6 space-y-4">
          {[1, 2, 3].map((item) => (
            <div key={item} className="surface animate-pulse p-6">
              <div className="h-4 w-40 rounded bg-[rgba(17,17,17,0.08)]" />
              <div className="mt-3 h-3 w-full rounded bg-[rgba(17,17,17,0.06)]" />
              <div className="mt-2 h-3 w-3/4 rounded bg-[rgba(17,17,17,0.06)]" />
            </div>
          ))}
        </div>
      ) : (
        <>
          {tab === 'summary' && (
            <div className="mt-6">
              <ClinicalSummary entities={state?.entities || []} />
            </div>
          )}

          {tab === 'timeline' && (
            <div className="mt-6">
              <PatientTimeline events={timeline?.events || []} />
            </div>
          )}

          {tab === 'add' && (
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {workflowCards.map((card) => (
                <Link key={card.title} href={`/demo/patient/${patientId}/${card.href}`} className="block group">
                  <div className="surface h-full p-5">
                    <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.42)]">
                      Workflow
                    </div>
                    <h3 className="mt-3 text-lg font-semibold text-black">{card.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-[rgba(17,17,17,0.6)]">{card.description}</p>
                    <div className="mt-5 border-t border-[rgba(17,17,17,0.08)] pt-4 text-sm text-black inline-flex items-center gap-1">
                      Open
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="transition-transform group-hover:translate-x-1">
                        <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
