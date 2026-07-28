'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { previewDepartmentMerge, confirmFacts } from '@/lib/api';
import type { ClinicalFact, MergeConflict, WorkflowEnvelope } from '@/lib/types';
import ReviewCard from '@/components/ReviewCard';
import WorkflowStepper from '@/components/WorkflowStepper';

type Step = 'input' | 'processing' | 'review' | 'result';

interface DepartmentRow {
  department: string;
  text: string;
  author: string;
  date: string;
}

const DEPARTMENTS = [
  'Cardiology',
  'Neurology',
  'Oncology',
  'Internal Medicine',
  'Surgery',
  'Radiology',
  'Pathology',
];

function emptyRow(): DepartmentRow {
  return { department: 'Internal Medicine', text: '', author: '', date: '' };
}

export default function MergeWorkflowPage() {
  const params = useParams();
  const patientId = params.id as string;

  const [step, setStep] = useState<Step>('input');
  const [rows, setRows] = useState<DepartmentRow[]>([
    { department: 'Cardiology', text: '', author: '', date: '' },
    { department: 'Internal Medicine', text: '', author: '', date: '' },
  ]);
  const [error, setError] = useState<string | null>(null);

  const [envelope, setEnvelope] = useState<WorkflowEnvelope | null>(null);
  const [facts, setFacts] = useState<ClinicalFact[]>([]);
  const [approved, setApproved] = useState<Record<number, boolean>>({});
  const [conflicts, setConflicts] = useState<MergeConflict[]>([]);

  const [resultMessage, setResultMessage] = useState('');
  const [resultDetails, setResultDetails] = useState<Record<string, unknown> | null>(null);

  const stepperSteps = [
    { name: 'Department Merger', status: step === 'input' ? 'pending' as const : step === 'processing' ? 'running' as const : 'done' as const },
    { name: 'Review', status: step === 'review' ? 'running' as const : step === 'result' ? 'done' as const : 'pending' as const },
  ];

  function updateRow(index: number, field: keyof DepartmentRow, value: string) {
    setRows((prev) =>
      prev.map((r, i) => (i === index ? { ...r, [field]: value } : r))
    );
  }

  function addRow() {
    setRows((prev) => [...prev, emptyRow()]);
  }

  function removeRow(index: number) {
    if (rows.length <= 2) return;
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  const canSubmit = rows.every((r) => r.text.trim().length > 0);

  async function handleProcess() {
    setStep('processing');
    setError(null);
    try {
      const result = await previewDepartmentMerge({
        patient_id: patientId,
        department_notes: rows.map((r) => ({
          department: r.department,
          text: r.text,
          date: r.date || new Date().toISOString().split('T')[0],
          author: r.author || undefined,
        })),
      });

      setEnvelope(result);
      const data = result.data || {};

      const extractedFacts = (data.clinical_facts as ClinicalFact[]) || [];
      setFacts(extractedFacts);
      const initialApproved: Record<number, boolean> = {};
      extractedFacts.forEach((_, i) => {
        initialApproved[i] = true;
      });
      setApproved(initialApproved);
      setConflicts((data.conflicts as MergeConflict[]) || []);
      setStep('review');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Processing failed');
      setStep('input');
    }
  }

  function toggleFact(index: number) {
    setApproved((prev) => ({ ...prev, [index]: !prev[index] }));
  }

  function editFact(index: number, edited: ClinicalFact) {
    setFacts((prev) => prev.map((f, i) => (i === index ? edited : f)));
  }

  async function handleSubmit() {
    setError(null);
    const approvedFacts = facts.filter((_, i) => approved[i]);
    try {
      const result = await confirmFacts(patientId, approvedFacts, 'department-merge');
      setResultMessage(`Successfully ingested ${approvedFacts.length} facts`);
      setResultDetails(result.data || null);
      setStep('result');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Confirmation failed');
    }
  }

  const approvedCount = Object.values(approved).filter(Boolean).length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-6 flex-wrap">
        <Link href="/demo" className="hover:text-slate-300 transition-colors">Demo</Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <Link href={`/demo/patient/${patientId}`} className="hover:text-slate-300 transition-colors">
          Patient {patientId}
        </Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-slate-300">Department Merge Workflow</span>
      </div>

      <h1 className="text-2xl font-bold text-white mb-2">Merge Department Notes</h1>
      <p className="text-slate-400 mb-6">
        Combine clinical notes from multiple departments, detect conflicts, and merge into the fact graph.
      </p>

      <div className="mb-8">
        <WorkflowStepper steps={stepperSteps} />
      </div>

      {error && (
        <div className="bg-rose-400/5 border border-rose-400/20 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 text-rose-400 text-sm">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 5v3M8 10v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {error}
          </div>
        </div>
      )}

      {/* Step 1: Input */}
      {step === 'input' && (
        <div className="space-y-4 animate-fade-in">
          {rows.map((row, i) => (
            <div key={i} className="bg-slate-900 border border-slate-700 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-white">Department Note {i + 1}</h3>
                {rows.length > 2 && (
                  <button
                    onClick={() => removeRow(i)}
                    className="text-xs text-rose-400 hover:text-rose-300 transition-colors"
                  >
                    Remove
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                <div>
                  <label className="label">Department</label>
                  <select
                    value={row.department}
                    onChange={(e) => updateRow(i, 'department', e.target.value)}
                    className="select-field"
                  >
                    {DEPARTMENTS.map((d) => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label">Author</label>
                  <input
                    type="text"
                    value={row.author}
                    onChange={(e) => updateRow(i, 'author', e.target.value)}
                    placeholder="Dr. Smith"
                    className="input-field"
                  />
                </div>
                <div>
                  <label className="label">Date</label>
                  <input
                    type="date"
                    value={row.date}
                    onChange={(e) => updateRow(i, 'date', e.target.value)}
                    className="input-field"
                  />
                </div>
              </div>

              <div>
                <label className="label">Clinical Notes</label>
                <textarea
                  value={row.text}
                  onChange={(e) => updateRow(i, 'text', e.target.value)}
                  rows={5}
                  placeholder="Enter department clinical notes..."
                  className="input-field font-mono text-sm"
                />
              </div>
            </div>
          ))}

          <div className="flex items-center gap-3">
            <button onClick={addRow} className="btn-secondary text-sm inline-flex items-center gap-1">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 3v8M3 7h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Add Department
            </button>
            <button
              onClick={handleProcess}
              disabled={!canSubmit}
              className="btn-primary text-sm inline-flex items-center gap-2"
            >
              Merge and Extract
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Processing */}
      {step === 'processing' && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-12 text-center animate-fade-in">
          <div className="inline-block mb-4">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="animate-spin text-teal-400">
              <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="3" strokeDasharray="80" strokeDashoffset="20" strokeLinecap="round" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">Merging Department Notes</h3>
          <p className="text-sm text-slate-400">
            Running parallel extraction and conflict detection...
          </p>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="space-y-6 animate-fade-in">
          {/* Conflicts */}
          {conflicts.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-base font-semibold text-amber-400 flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 1l7 13H1L8 1z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                  <path d="M8 6v3M8 11v1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                </svg>
                Conflicts Detected ({conflicts.length})
              </h2>
              {conflicts.map((c, i) => (
                <div key={i} className="bg-amber-400/5 border border-amber-400/20 rounded-xl p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-1">
                      <h4 className="text-sm font-semibold text-white mb-1">
                        {c.entity.replace(/_/g, ' ')}
                      </h4>
                      <p className="text-sm text-slate-400 mb-2">{c.description}</p>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-slate-500">Departments:</span>
                        {c.departments.map((d) => (
                          <span key={d} className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                            {d}
                          </span>
                        ))}
                      </div>
                      {c.resolution && (
                        <div className="mt-2 text-sm text-emerald-400">
                          <span className="text-xs text-slate-500">Resolution: </span>
                          {c.resolution}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Facts */}
          {facts.length === 0 ? (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-8 text-center">
              <p className="text-slate-400">No clinical facts were extracted.</p>
              <button onClick={() => setStep('input')} className="btn-secondary mt-4">
                Try Again
              </button>
            </div>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-white">
                Review Merged Facts ({facts.length})
              </h2>

              {facts.map((fact, i) => (
                <ReviewCard
                  key={i}
                  fact={fact}
                  approved={approved[i] ?? true}
                  onToggle={() => toggleFact(i)}
                  onEdit={(edited) => editFact(i, edited)}
                />
              ))}

              <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex items-center justify-between flex-wrap gap-4 sticky bottom-4">
                <span className="text-sm text-slate-300">
                  <span className="font-semibold text-white">{approvedCount}</span> of{' '}
                  <span className="font-semibold text-white">{facts.length}</span> facts approved
                </span>
                <div className="flex items-center gap-3">
                  <button onClick={() => setStep('input')} className="btn-secondary text-sm">
                    Back
                  </button>
                  <button
                    onClick={handleSubmit}
                    disabled={approvedCount === 0}
                    className="btn-primary text-sm inline-flex items-center gap-2"
                  >
                    Submit Approved Facts
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Step 4: Result */}
      {step === 'result' && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-8 text-center animate-fade-in">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-400/10 mb-4">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="text-emerald-400">
              <path d="M8 16l5 5 11-12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-white mb-2">{resultMessage}</h2>

          {resultDetails && (
            <div className="mt-4 max-w-sm mx-auto text-left">
              <div className="bg-slate-800/50 rounded-lg p-4 space-y-2 text-sm">
                {Object.entries(resultDetails).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-slate-400">{key.replace(/_/g, ' ')}</span>
                    <span className="text-slate-200 font-mono">{String(val)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => {
                setStep('input');
                setRows([
                  { department: 'Cardiology', text: '', author: '', date: '' },
                  { department: 'Internal Medicine', text: '', author: '', date: '' },
                ]);
                setFacts([]);
                setApproved({});
                setConflicts([]);
                setEnvelope(null);
                setResultMessage('');
                setResultDetails(null);
              }}
              className="btn-secondary"
            >
              Merge More Notes
            </button>
            <Link href={`/demo/patient/${patientId}`} className="btn-primary inline-flex items-center gap-2">
              Back to Patient
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
