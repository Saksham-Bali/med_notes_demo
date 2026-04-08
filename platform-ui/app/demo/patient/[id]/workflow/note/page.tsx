'use client';

import { useState, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { previewHandwrittenNote, confirmFacts } from '@/lib/api';
import type { ClinicalFact, WorkflowEnvelope } from '@/lib/types';
import ReviewCard from '@/components/ReviewCard';
import WorkflowStepper from '@/components/WorkflowStepper';

type Step = 'input' | 'processing' | 'review' | 'result';

export default function NoteWorkflowPage() {
  const params = useParams();
  const patientId = params.id as string;

  const [step, setStep] = useState<Step>('input');
  const [file, setFile] = useState<File | null>(null);
  const [department, setDepartment] = useState('Internal Medicine');
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [envelope, setEnvelope] = useState<WorkflowEnvelope | null>(null);
  const [facts, setFacts] = useState<ClinicalFact[]>([]);
  const [approved, setApproved] = useState<Record<number, boolean>>({});
  const [ocrText, setOcrText] = useState('');
  const [ocrConfidence, setOcrConfidence] = useState<number | null>(null);
  const [soapData, setSoapData] = useState<Record<string, string> | null>(null);

  const [resultMessage, setResultMessage] = useState('');
  const [resultDetails, setResultDetails] = useState<Record<string, unknown> | null>(null);

  const stepperSteps = [
    { name: 'OCR', status: step === 'input' ? 'pending' as const : step === 'processing' ? 'running' as const : 'done' as const },
    { name: 'SOAP Extraction', status: step === 'input' || step === 'processing' ? 'pending' as const : 'done' as const },
    { name: 'Review', status: step === 'review' ? 'running' as const : step === 'result' ? 'done' as const : 'pending' as const },
  ];

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith('image/')) {
      setFile(f);
    }
  }, []);

  async function handleProcess() {
    if (!file) return;
    setStep('processing');
    setError(null);
    try {
      const formData = new FormData();
      formData.append('image', file);
      formData.append('patient_id', patientId);
      formData.append('department', department);

      const result = await previewHandwrittenNote(formData);
      setEnvelope(result);

      const data = result.data || {};
      setOcrText((data.raw_text as string) || '');
      setOcrConfidence(typeof data.confidence === 'number' ? data.confidence : null);
      setSoapData((data.soap as Record<string, string>) || null);

      const extractedFacts = (data.clinical_facts as ClinicalFact[]) || [];
      setFacts(extractedFacts);
      const initialApproved: Record<number, boolean> = {};
      extractedFacts.forEach((_, i) => {
        initialApproved[i] = true;
      });
      setApproved(initialApproved);
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
      const result = await confirmFacts(patientId, approvedFacts, 'handwritten-note');
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
        <span className="text-slate-300">Handwritten Note Workflow</span>
      </div>

      <h1 className="text-2xl font-bold text-white mb-2">Add Handwritten Note</h1>
      <p className="text-slate-400 mb-6">
        Upload a scanned clinical note for OCR and SOAP extraction.
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
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-5 animate-fade-in">
          <div>
            <label className="label">Upload Image</label>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                dragging
                  ? 'border-teal-400 bg-teal-400/5'
                  : file
                  ? 'border-emerald-400/50 bg-emerald-400/5'
                  : 'border-slate-600 hover:border-slate-500'
              }`}
            >
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              {file ? (
                <div>
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="mx-auto mb-2 text-emerald-400">
                    <path d="M8 16l5 5 11-12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <p className="text-sm text-emerald-400 font-medium">{file.name}</p>
                  <p className="text-xs text-slate-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <div>
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="mx-auto mb-2 text-slate-500">
                    <path d="M16 8v16M8 16h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <p className="text-sm text-slate-400">
                    Drag and drop an image here, or click to browse
                  </p>
                  <p className="text-xs text-slate-600 mt-1">PNG, JPG, or TIFF</p>
                </div>
              )}
            </div>
          </div>

          <div>
            <label className="label">Department</label>
            <select value={department} onChange={(e) => setDepartment(e.target.value)} className="select-field max-w-xs">
              <option value="Internal Medicine">Internal Medicine</option>
              <option value="Cardiology">Cardiology</option>
              <option value="Neurology">Neurology</option>
              <option value="Oncology">Oncology</option>
              <option value="Surgery">Surgery</option>
              <option value="Radiology">Radiology</option>
              <option value="Pathology">Pathology</option>
            </select>
          </div>

          <div className="pt-2">
            <button
              onClick={handleProcess}
              disabled={!file}
              className="btn-primary inline-flex items-center gap-2"
            >
              Process Note
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
          <h3 className="text-lg font-semibold text-white mb-2">Processing Note</h3>
          <p className="text-sm text-slate-400">
            Running OCR and SOAP extraction...
          </p>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="space-y-6 animate-fade-in">
          {/* OCR + SOAP panels */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-white">OCR Extracted Text</h3>
                {ocrConfidence !== null && (
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    ocrConfidence > 0.8 ? 'bg-emerald-400/10 text-emerald-400' :
                    ocrConfidence > 0.5 ? 'bg-amber-400/10 text-amber-400' :
                    'bg-rose-400/10 text-rose-400'
                  }`}>
                    Confidence: {(ocrConfidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <div className="bg-slate-950 rounded-lg p-4 max-h-64 overflow-y-auto">
                <pre className="text-sm text-slate-300 font-mono whitespace-pre-wrap">
                  {ocrText || 'No text extracted'}
                </pre>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-700 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-white mb-3">SOAP Structure</h3>
              {soapData ? (
                <div className="space-y-3 max-h-64 overflow-y-auto">
                  {['subjective', 'objective', 'assessment', 'plan'].map((key) => (
                    <div key={key}>
                      <span className="text-xs font-semibold uppercase tracking-wider text-teal-400">
                        {key}
                      </span>
                      <p className="text-sm text-slate-300 mt-1">
                        {soapData[key] || '--'}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">No SOAP data available</p>
              )}
            </div>
          </div>

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
                Review Extracted Facts ({facts.length})
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
                setFile(null);
                setFacts([]);
                setApproved({});
                setEnvelope(null);
                setOcrText('');
                setOcrConfidence(null);
                setSoapData(null);
                setResultMessage('');
                setResultDetails(null);
              }}
              className="btn-secondary"
            >
              Process Another Note
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
