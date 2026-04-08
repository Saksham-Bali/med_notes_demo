'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getPatientState, getPatientTimeline } from '@/lib/api';
import type { PatientState, PatientTimeline as PTL } from '@/lib/types';
import ClinicalSummary from '@/components/ClinicalSummary';
import PatientTimeline from '@/components/PatientTimeline';
import patientsJson from '@/data/patients.json';

type Tab = 'summary' | 'timeline' | 'add';

interface PatientMeta {
  id: string;
  display_name: string;
  cancer_type: string;
  reports_count: number;
  description: string;
}

const workflowCards = [
  {
    title: 'Add Radiology Report',
    description: 'Extract RadLex-grounded findings from imaging reports with hybrid rule+LLM extraction.',
    href: 'workflow/radiology',
    available: true,
  },
  {
    title: 'Add Handwritten Note',
    description: 'OCR processing and SOAP extraction from scanned clinical notes.',
    href: 'workflow/note',
    available: true,
  },
  {
    title: 'Add Counselling Session',
    description: 'Process audio recordings of clinical counselling sessions.',
    href: 'workflow/counselling',
    available: true,
  },
  {
    title: 'Merge Department Notes',
    description: 'Combine notes from multiple departments with conflict detection and resolution.',
    href: 'workflow/merge',
    available: true,
  },
  {
    title: 'Generate Discharge Summary',
    description: 'Create NABH-compliant discharge summary with QA validation and translation.',
    href: 'workflow/summary',
    available: true,
  },
];

export default function PatientDetailPage() {
  const params = useParams();
  const patientId = params.id as string;
  const [tab, setTab] = useState<Tab>('summary');
  const [state, setState] = useState<PatientState | null>(null);
  const [timeline, setTimeline] = useState<PTL | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const patients = patientsJson as PatientMeta[];
  const meta = patients.find((p) => p.id === patientId);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [s, t] = await Promise.all([
          getPatientState(patientId),
          getPatientTimeline(patientId),
        ]);
        if (!cancelled) {
          setState(s);
          setTimeline(t);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load patient data');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [patientId]);

  const tabs: { key: Tab; label: string }[] = [
    { key: 'summary', label: 'Clinical Summary' },
    { key: 'timeline', label: 'Event Timeline' },
    { key: 'add', label: 'Add New Data' },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-6">
        <Link href="/" className="hover:text-slate-300 transition-colors">Home</Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <Link href="/demo" className="hover:text-slate-300 transition-colors">Demo</Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-slate-300">{meta?.display_name || `Patient ${patientId}`}</span>
      </div>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-1">
          {meta?.display_name || `Patient ${patientId}`}
        </h1>
        {meta && (
          <p className="text-slate-400">
            {meta.cancer_type} Cancer -- {meta.description}
          </p>
        )}
        <div className="flex items-center gap-4 mt-3 text-sm text-slate-500">
          <span>ID: <code className="font-mono text-slate-300">{patientId}</code></span>
          {state && (
            <span>{state.entities.length} entities</span>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-800 mb-6">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                tab === t.key
                  ? 'text-teal-400 border-teal-400'
                  : 'text-slate-400 border-transparent hover:text-white hover:border-slate-600'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {error && (
        <div className="bg-rose-400/5 border border-rose-400/20 rounded-xl p-5 mb-6">
          <div className="flex items-center gap-2 text-rose-400">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 5v3M8 10v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span className="text-sm">{error}</span>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-slate-900 border border-slate-700 rounded-xl p-6 animate-pulse">
              <div className="h-4 bg-slate-800 rounded w-48 mb-3" />
              <div className="h-3 bg-slate-800 rounded w-full mb-2" />
              <div className="h-3 bg-slate-800 rounded w-3/4" />
            </div>
          ))}
        </div>
      ) : (
        <>
          {tab === 'summary' && (
            <ClinicalSummary entities={state?.entities || []} />
          )}

          {tab === 'timeline' && (
            <PatientTimeline events={timeline?.events || []} />
          )}

          {tab === 'add' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {workflowCards.map((card) => (
                <div key={card.title} className="relative">
                  {card.available ? (
                    <Link
                      href={`/demo/patient/${patientId}/${card.href}`}
                      className="block group"
                    >
                      <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 hover:border-teal-400/50 transition-all h-full">
                        <h3 className="text-base font-semibold text-white mb-2">{card.title}</h3>
                        <p className="text-sm text-slate-400 leading-relaxed mb-4">{card.description}</p>
                        <span className="text-sm text-teal-400 group-hover:translate-x-1 transition-transform inline-flex items-center gap-1">
                          Start Workflow
                          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </span>
                      </div>
                    </Link>
                  ) : (
                    <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 opacity-60 h-full">
                      <h3 className="text-base font-semibold text-white mb-2">{card.title}</h3>
                      <p className="text-sm text-slate-400 leading-relaxed mb-4">{card.description}</p>
                      <span className="text-xs bg-slate-800 text-slate-500 px-2 py-1 rounded">
                        Coming Soon
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
