'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { previewRadiology, confirmFacts } from '@/lib/api';
import type { ClinicalFact, WorkflowEnvelope } from '@/lib/types';
import ReviewCard from '@/components/ReviewCard';
import WorkflowStepper from '@/components/WorkflowStepper';

type Step = 'input' | 'processing' | 'review' | 'result';

export default function RadiologyWorkflowPage() {
  const params = useParams();
  const patientId = params.id as string;

  const [step, setStep] = useState<Step>('input');
  const [reportText, setReportText] = useState('');
  const [modality, setModality] = useState('CT');
  const [bodyRegion, setBodyRegion] = useState('chest');
  const [reportDate, setReportDate] = useState('');
  const [error, setError] = useState<string | null>(null);

  const [envelope, setEnvelope] = useState<WorkflowEnvelope | null>(null);
  const [facts, setFacts] = useState<ClinicalFact[]>([]);
  const [approved, setApproved] = useState<Record<number, boolean>>({});

  const [resultMessage, setResultMessage] = useState('');
  const [resultDetails, setResultDetails] = useState<Record<string, unknown> | null>(null);

  const stepperSteps = [
    { name: 'Radiology Extractor', status: step === 'input' ? 'pending' as const : step === 'processing' ? 'running' as const : 'done' as const },
    { name: 'Entity Grounding', status: step === 'input' || step === 'processing' ? 'pending' as const : 'done' as const },
    { name: 'Review', status: step === 'review' ? 'running' as const : step === 'result' ? 'done' as const : 'pending' as const },
  ];

  async function handleExtract() {
    setStep('processing');
    setError(null);
    try {
      const result = await previewRadiology({
        patient_id: patientId,
        report_text: reportText,
        modality,
        body_region: bodyRegion,
        report_date: reportDate || undefined,
      });
      setEnvelope(result);
      const extractedFacts = (result.data?.clinical_facts as ClinicalFact[]) || [];
      setFacts(extractedFacts);
      const initialApproved: Record<number, boolean> = {};
      extractedFacts.forEach((_, i) => {
        initialApproved[i] = true;
      });
      setApproved(initialApproved);
      setStep('review');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Extraction failed');
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
      const result = await confirmFacts(patientId, approvedFacts, 'radiology-report');
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
        <span className="text-slate-300">Radiology Workflow</span>
      </div>

      <h1 className="text-2xl font-bold text-white mb-2">Add Radiology Report</h1>
      <p className="text-slate-400 mb-6">
        Extract RadLex-grounded clinical findings from a radiology report.
      </p>

      {/* Stepper */}
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
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-5 animate-fade-in">
          <div>
            <label className="label">Report Text</label>
            <textarea
              value={reportText}
              onChange={(e) => setReportText(e.target.value)}
              rows={12}
              placeholder="Paste the radiology report text here...&#10;&#10;Example:&#10;FINDINGS: There is a 2.3 cm nodule in the right upper lobe. Moderate left-sided pleural effusion. No pneumothorax. The heart is normal in size. Mediastinal lymphadenopathy is present."
              className="input-field font-mono text-sm"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="label">Modality</label>
              <select value={modality} onChange={(e) => setModality(e.target.value)} className="select-field">
                <option value="CT">CT</option>
                <option value="MRI">MRI</option>
                <option value="PET">PET</option>
                <option value="X-Ray">X-Ray</option>
                <option value="Ultrasound">Ultrasound</option>
              </select>
            </div>
            <div>
              <label className="label">Body Region</label>
              <select value={bodyRegion} onChange={(e) => setBodyRegion(e.target.value)} className="select-field">
                <option value="chest">Chest</option>
                <option value="abdomen">Abdomen</option>
                <option value="brain">Brain</option>
                <option value="pelvis">Pelvis</option>
                <option value="spine">Spine</option>
                <option value="neck">Neck</option>
                <option value="extremities">Extremities</option>
              </select>
            </div>
            <div>
              <label className="label">Report Date</label>
              <input
                type="date"
                value={reportDate}
                onChange={(e) => setReportDate(e.target.value)}
                className="input-field"
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              onClick={handleExtract}
              disabled={!reportText.trim()}
              className="btn-primary inline-flex items-center gap-2"
            >
              Extract Findings
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
          <h3 className="text-lg font-semibold text-white mb-2">Processing Report</h3>
          <p className="text-sm text-slate-400">
            Running radiology extraction and entity grounding...
          </p>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="space-y-4 animate-fade-in">
          {envelope && envelope.steps && envelope.steps.length > 0 && (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Workflow Steps
              </h3>
              <div className="flex flex-wrap gap-2">
                {envelope.steps.map((s, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      s.status === 'success' ? 'bg-emerald-400' :
                      s.status === 'needs_review' ? 'bg-amber-400' :
                      s.status === 'error' ? 'bg-rose-400' : 'bg-slate-600'
                    }`} />
                    <span className="text-slate-300">{s.agent}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {facts.length === 0 ? (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-8 text-center">
              <p className="text-slate-400">No clinical facts were extracted from this report.</p>
              <button onClick={() => setStep('input')} className="btn-secondary mt-4">
                Try Again
              </button>
            </div>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-white">
                Review Extracted Facts ({facts.length})
              </h2>
              <p className="text-sm text-slate-400">
                Review each extracted clinical fact. Toggle the checkbox to approve or reject.
                Click Edit to modify entity details before ingestion.
              </p>

              {facts.map((fact, i) => (
                <ReviewCard
                  key={i}
                  fact={fact}
                  approved={approved[i] ?? true}
                  onToggle={() => toggleFact(i)}
                  onEdit={(edited) => editFact(i, edited)}
                />
              ))}

              {/* Summary bar */}
              <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex items-center justify-between flex-wrap gap-4 sticky bottom-4">
                <span className="text-sm text-slate-300">
                  <span className="font-semibold text-white">{approvedCount}</span> of{' '}
                  <span className="font-semibold text-white">{facts.length}</span> facts approved
                </span>
                <div className="flex items-center gap-3">
                  <button onClick={() => setStep('input')} className="btn-secondary text-sm">
                    Back to Input
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
                setReportText('');
                setFacts([]);
                setApproved({});
                setEnvelope(null);
                setResultMessage('');
                setResultDetails(null);
              }}
              className="btn-secondary"
            >
              Process Another Report
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
