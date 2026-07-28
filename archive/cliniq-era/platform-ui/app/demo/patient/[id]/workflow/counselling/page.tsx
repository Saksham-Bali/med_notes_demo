'use client';

import { useState, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { submitCounselling, approveCounselling } from '@/lib/api';
import type { BulletPoint, CounsellingFact, WorkflowEnvelope } from '@/lib/types';
import WorkflowStepper from '@/components/WorkflowStepper';

type Step = 'input' | 'processing' | 'review' | 'result';

function getCategoryColor(category: CounsellingFact['category']): string {
  switch (category) {
    case 'CONCERN': return 'bg-amber-400/10 text-amber-400 border-amber-400/20';
    case 'ACTION': return 'bg-teal-400/10 text-teal-400 border-teal-400/20';
    case 'DECISION': return 'bg-blue-400/10 text-blue-400 border-blue-400/20';
    case 'EMOTIONAL': return 'bg-purple-400/10 text-purple-400 border-purple-400/20';
    case 'FOLLOW_UP': return 'bg-orange-400/10 text-orange-400 border-orange-400/20';
  }
}

export default function CounsellingWorkflowPage() {
  const params = useParams();
  const patientId = params.id as string;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>('input');
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [languageHint, setLanguageHint] = useState('hi-IN');
  const [department, setDepartment] = useState('oncology');
  const [error, setError] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState<string>('');
  const [bulletPoints, setBulletPoints] = useState<BulletPoint[]>([]);
  const [counsellingFacts, setCounsellingFacts] = useState<CounsellingFact[]>([]);
  const [approvedBulletIds, setApprovedBulletIds] = useState<Set<string>>(new Set());
  const [approvedFactIds, setApprovedFactIds] = useState<Set<string>>(new Set());
  const [editingBulletId, setEditingBulletId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  const [resultMessage, setResultMessage] = useState('');

  const stepperSteps = [
    { name: 'Voice Transcription', status: step === 'input' ? 'pending' as const : step === 'processing' ? 'running' as const : 'done' as const },
    { name: 'LLM Correction', status: step === 'input' || step === 'processing' ? 'pending' as const : 'done' as const },
    { name: 'Review', status: step === 'review' ? 'running' as const : step === 'result' ? 'done' as const : 'pending' as const },
  ];

  async function handleSubmit() {
    if (!audioFile) return;
    setStep('processing');
    setError(null);

    const formData = new FormData();
    formData.append('audio', audioFile);
    formData.append('patient_id', patientId);
    formData.append('patient_consent', 'true');
    formData.append('consent_timestamp', new Date().toISOString());
    formData.append('language_hint', languageHint);
    formData.append('department', department);
    formData.append('session_type', 'counselling');

    try {
      const result: WorkflowEnvelope = await submitCounselling(formData);
      const data = result.data as {
        session_id: string;
        bullet_points: BulletPoint[];
        counselling_facts: CounsellingFact[];
      };
      setSessionId(data.session_id);

      const bps = data.bullet_points || [];
      setBulletPoints(bps);
      setApprovedBulletIds(new Set(bps.map((bp) => bp.id)));

      const facts = data.counselling_facts || [];
      setCounsellingFacts(facts);
      setApprovedFactIds(new Set(facts.map((f) => f.id)));

      setStep('review');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Processing failed');
      setStep('input');
    }
  }

  function deleteBullet(id: string) {
    setBulletPoints((prev) => prev.filter((bp) => bp.id !== id));
    setApprovedBulletIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
  }

  function startEditBullet(bp: BulletPoint) {
    setEditingBulletId(bp.id);
    setEditText(bp.text);
  }

  function saveEditBullet(id: string) {
    setBulletPoints((prev) => prev.map((bp) => bp.id === id ? { ...bp, text: editText } : bp));
    setEditingBulletId(null);
    setEditText('');
  }

  function toggleFact(id: string) {
    setApprovedFactIds((prev) => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id); else s.add(id);
      return s;
    });
  }

  async function handleConfirm() {
    setError(null);
    try {
      const result = await approveCounselling({
        patient_id: patientId,
        session_id: sessionId,
        approved_fact_ids: Array.from(approvedFactIds),
        approved_bullet_ids: Array.from(approvedBulletIds),
      });
      const data = result.data as { total_ingested?: number; approved_bullets_count?: number; approved_facts_count?: number };
      const total = data.total_ingested ?? 0;
      const bullets = data.approved_bullets_count ?? 0;
      const facts = data.approved_facts_count ?? 0;
      setResultMessage(`Ingested ${total} items (${bullets} bullet points + ${facts} clinical facts)`);
      setStep('result');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Confirmation failed');
    }
  }

  const approvedBulletCount = approvedBulletIds.size;
  const approvedFactCount = approvedFactIds.size;

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
        <span className="text-slate-300">Voice Counselling</span>
      </div>

      <h1 className="text-2xl font-bold text-white mb-2">Add Counselling Session</h1>
      <p className="text-slate-400 mb-6">
        Upload a voice recording. Sarvam AI transcribes it, then the LLM corrects errors and generates bullet points for your review.
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
            <label className="label">Audio Recording</label>
            <div
              className="mt-1 border-2 border-dashed border-slate-600 rounded-xl p-8 text-center cursor-pointer hover:border-teal-400/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              {audioFile ? (
                <div className="space-y-1">
                  <p className="text-white font-medium">{audioFile.name}</p>
                  <p className="text-slate-400 text-sm">{(audioFile.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <svg className="mx-auto text-slate-500" width="40" height="40" viewBox="0 0 40 40" fill="none">
                    <circle cx="20" cy="20" r="18" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M20 12v16M12 20h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  <p className="text-slate-400 text-sm">Click to upload audio (WAV, MP3, M4A, OGG)</p>
                </div>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac"
              className="hidden"
              onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Language</label>
              <select value={languageHint} onChange={(e) => setLanguageHint(e.target.value)} className="select-field">
                <option value="hi-IN">Hindi</option>
                <option value="en-IN">English (India)</option>
                <option value="ta-IN">Tamil</option>
                <option value="te-IN">Telugu</option>
                <option value="kn-IN">Kannada</option>
                <option value="ml-IN">Malayalam</option>
                <option value="mr-IN">Marathi</option>
                <option value="bn-IN">Bengali</option>
                <option value="gu-IN">Gujarati</option>
                <option value="pa-IN">Punjabi</option>
              </select>
            </div>
            <div>
              <label className="label">Department</label>
              <select value={department} onChange={(e) => setDepartment(e.target.value)} className="select-field">
                <option value="oncology">Oncology</option>
                <option value="radiology">Radiology</option>
                <option value="surgery">Surgery</option>
                <option value="palliative">Palliative Care</option>
                <option value="general">General Medicine</option>
              </select>
            </div>
          </div>

          <div className="pt-2">
            <button
              onClick={handleSubmit}
              disabled={!audioFile}
              className="btn-primary inline-flex items-center gap-2"
            >
              Transcribe &amp; Analyse
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
          <h3 className="text-lg font-semibold text-white mb-2">Processing Audio</h3>
          <p className="text-sm text-slate-400">
            Transcribing with Sarvam AI, then correcting and extracting clinical facts...
          </p>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Bullet Points Panel */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-white">
                  Bullet Points
                  <span className="ml-2 text-sm font-normal text-slate-400">({approvedBulletCount} of {bulletPoints.length} kept)</span>
                </h2>
              </div>
              <p className="text-xs text-slate-500 mb-3">
                LLM-corrected summary of the session. Edit or delete any point before confirming.
              </p>

              {bulletPoints.length === 0 ? (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 text-center text-slate-400 text-sm">
                  No bullet points were generated.
                </div>
              ) : (
                <div className="space-y-2">
                  {bulletPoints.map((bp) => (
                    <div key={bp.id} className="bg-slate-900 border border-slate-700 rounded-xl p-4">
                      {editingBulletId === bp.id ? (
                        <div className="space-y-2">
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            rows={3}
                            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-400 resize-none"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveEditBullet(bp.id)}
                              className="px-3 py-1 bg-[#111] text-[#faf7f1] text-xs rounded-lg hover:bg-[#252525] transition-colors"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingBulletId(null)}
                              className="px-3 py-1 bg-slate-700 text-slate-300 text-xs rounded-lg hover:bg-slate-600 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start gap-3">
                          <span className="text-teal-400 mt-0.5 shrink-0">•</span>
                          <p className="text-sm text-slate-200 flex-1">{bp.text}</p>
                          <div className="flex gap-1 shrink-0">
                            <button
                              onClick={() => startEditBullet(bp)}
                              className="text-slate-500 hover:text-teal-400 transition-colors p-1"
                              title="Edit"
                            >
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                <path d="M8.5 1.5l2 2-7 7H1.5V8.5l7-7z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </button>
                            <button
                              onClick={() => deleteBullet(bp.id)}
                              className="text-slate-500 hover:text-rose-400 transition-colors p-1"
                              title="Delete"
                            >
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Clinical Facts Panel */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-white">
                  Clinical Facts
                  <span className="ml-2 text-sm font-normal text-slate-400">({approvedFactCount} of {counsellingFacts.length} approved)</span>
                </h2>
              </div>
              <p className="text-xs text-slate-500 mb-3">
                Structured facts extracted by the LLM. Toggle to approve or reject each.
              </p>

              {counsellingFacts.length === 0 ? (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 text-center text-slate-400 text-sm">
                  No structured clinical facts were extracted.
                </div>
              ) : (
                <div className="space-y-2">
                  {counsellingFacts.map((fact) => {
                    const isApproved = approvedFactIds.has(fact.id);
                    return (
                      <div
                        key={fact.id}
                        className={`border rounded-xl p-4 transition-all duration-200 cursor-pointer ${
                          isApproved
                            ? 'bg-slate-900 border-teal-400/30'
                            : 'bg-slate-900/50 border-slate-700 opacity-60'
                        }`}
                        onClick={() => toggleFact(fact.id)}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`mt-0.5 w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                            isApproved ? 'bg-teal-400 border-teal-400 text-slate-950' : 'border-slate-600'
                          }`}>
                            {isApproved && (
                              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                                <path d="M2.5 6l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded border ${getCategoryColor(fact.category)}`}>
                                {fact.category}
                              </span>
                              <span className="text-xs text-slate-500">
                                {fact.speaker} · {(fact.certainty * 100).toFixed(0)}%
                              </span>
                            </div>
                            <p className="text-sm text-slate-200">{fact.fact}</p>
                            {fact.evidence_text && (
                              <p className="text-xs text-slate-500 italic mt-1 border-l-2 border-slate-700 pl-2">
                                &quot;{fact.evidence_text}&quot;
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Confirm bar */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex items-center justify-between flex-wrap gap-4 sticky bottom-4">
            <span className="text-sm text-slate-300">
              <span className="font-semibold text-white">{approvedBulletCount}</span> bullets +{' '}
              <span className="font-semibold text-white">{approvedFactCount}</span> facts will be ingested
            </span>
            <div className="flex items-center gap-3">
              <button onClick={() => setStep('input')} className="btn-secondary text-sm">
                Back
              </button>
              <button
                onClick={handleConfirm}
                disabled={approvedBulletCount + approvedFactCount === 0}
                className="btn-primary text-sm inline-flex items-center gap-2"
              >
                Confirm &amp; Ingest
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
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
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => {
                setStep('input');
                setAudioFile(null);
                setBulletPoints([]);
                setCounsellingFacts([]);
                setApprovedBulletIds(new Set());
                setApprovedFactIds(new Set());
                setSessionId('');
                setResultMessage('');
              }}
              className="btn-secondary"
            >
              Process Another Recording
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
