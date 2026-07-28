'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { generateSummary } from '@/lib/api';
import type { WorkflowEnvelope } from '@/lib/types';
import StatusBadge from '@/components/StatusBadge';

export default function SummaryWorkflowPage() {
  const params = useParams();
  const patientId = params.id as string;

  const [physician, setPhysician] = useState('');
  const [admissionDate, setAdmissionDate] = useState('');
  const [dischargeDate, setDischargeDate] = useState('');
  const [department, setDepartment] = useState('Oncology');
  const [language, setLanguage] = useState('en');
  const [template, setTemplate] = useState('nabh_standard');
  const [includeRecist, setIncludeRecist] = useState(false);
  const [generateAudio, setGenerateAudio] = useState(false);
  const [generatePdf, setGeneratePdf] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WorkflowEnvelope | null>(null);

  function validDate(d: string): string | undefined {
    if (!d) return undefined;
    // Must be YYYY-MM-DD with a 4-digit year
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return undefined;
    const parsed = new Date(d);
    if (isNaN(parsed.getTime())) return undefined;
    return d;
  }

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const envelope = await generateSummary({
        patient_id: patientId,
        admission_date: validDate(admissionDate),
        discharge_date: validDate(dischargeDate),
        attending_physician: physician || undefined,
        department: department || undefined,
        include_recist: includeRecist,
        template,
        target_language: language,
        generate_audio: generateAudio,
        generate_pdf: generatePdf,
      });
      setResult(envelope);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Summary generation failed');
    } finally {
      setLoading(false);
    }
  }

  const data = result?.data || {};

  // The orchestrator nests results: data.generator, data.qa, data.translation, data.discharge_summary
  const qaResult = (data.qa as Record<string, unknown>)?.result as Record<string, unknown> | undefined;
  const qaVerdict = (qaResult?.verdict as string) || undefined;
  const qaScore = qaResult?.score as number | undefined;
  const qaIssues = (qaResult?.issues as { type: string; severity: string; message: string }[]) || [];

  // Structured discharge summary — could be at data.discharge_summary or data.generator.result.discharge_summary
  const generatorResult = (data.generator as Record<string, unknown>)?.result as Record<string, unknown> | undefined;
  const rawDS = data.discharge_summary;
  const dischargeSummary = (typeof rawDS === 'object' && rawDS !== null ? rawDS : generatorResult?.discharge_summary) as Record<string, unknown> | undefined;

  // Prose version (brief_summary from the structured object, or the prose_version field)
  const summaryText = (generatorResult?.prose_version as string)
    || (typeof rawDS === 'string' ? rawDS : '')
    || '';

  // Translation artifacts
  const translationResult = (data.translation as Record<string, unknown>)?.result as Record<string, unknown> | undefined;
  const audioUrl = translationResult?.audio_url as string | undefined;
  const pdfUrl = translationResult?.pdf_url as string | undefined;

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
        <span className="text-slate-300">Discharge Summary</span>
      </div>

      <h1 className="text-2xl font-bold text-white mb-2">Generate Discharge Summary</h1>
      <p className="text-slate-400 mb-6">
        Create an NABH-compliant discharge summary from the patient&apos;s fact graph data.
      </p>

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form */}
        <div className="lg:col-span-1">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 space-y-4 sticky top-24">
            <h2 className="text-sm font-semibold text-white">Configuration</h2>

            <div>
              <label className="label">Attending Physician</label>
              <input
                type="text"
                value={physician}
                onChange={(e) => setPhysician(e.target.value)}
                placeholder="Dr. Sharma"
                className="input-field"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Admission Date</label>
                <input
                  type="date"
                  value={admissionDate}
                  onChange={(e) => setAdmissionDate(e.target.value)}
                  className="input-field"
                />
              </div>
              <div>
                <label className="label">Discharge Date</label>
                <input
                  type="date"
                  value={dischargeDate}
                  onChange={(e) => setDischargeDate(e.target.value)}
                  className="input-field"
                />
              </div>
            </div>

            <div>
              <label className="label">Department</label>
              <select value={department} onChange={(e) => setDepartment(e.target.value)} className="select-field">
                <option value="Oncology">Oncology</option>
                <option value="Cardiology">Cardiology</option>
                <option value="Neurology">Neurology</option>
                <option value="Internal Medicine">Internal Medicine</option>
                <option value="Surgery">Surgery</option>
              </select>
            </div>

            <div>
              <label className="label">Target Language</label>
              <select value={language} onChange={(e) => setLanguage(e.target.value)} className="select-field">
                <option value="en">English</option>
                <option value="hi">Hindi</option>
                <option value="mr">Marathi</option>
                <option value="ta">Tamil</option>
                <option value="te">Telugu</option>
              </select>
            </div>

            <div>
              <label className="label">Template</label>
              <select value={template} onChange={(e) => setTemplate(e.target.value)} className="select-field">
                <option value="nabh_standard">NABH Standard</option>
              </select>
            </div>

            <div className="space-y-2 pt-2">
              <label className="flex items-center gap-3 cursor-pointer">
                <button
                  type="button"
                  onClick={() => setIncludeRecist(!includeRecist)}
                  className={`w-9 h-5 rounded-full transition-colors relative ${
                    includeRecist ? 'bg-[#111]' : 'bg-[rgba(17,17,17,0.14)]'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      includeRecist ? 'translate-x-4' : ''
                    }`}
                  />
                </button>
                <span className="text-sm text-slate-300">Include RECIST</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <button
                  type="button"
                  onClick={() => setGenerateAudio(!generateAudio)}
                  className={`w-9 h-5 rounded-full transition-colors relative ${
                    generateAudio ? 'bg-[#111]' : 'bg-[rgba(17,17,17,0.14)]'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      generateAudio ? 'translate-x-4' : ''
                    }`}
                  />
                </button>
                <span className="text-sm text-slate-300">Generate Audio</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <button
                  type="button"
                  onClick={() => setGeneratePdf(!generatePdf)}
                  className={`w-9 h-5 rounded-full transition-colors relative ${
                    generatePdf ? 'bg-[#111]' : 'bg-[rgba(17,17,17,0.14)]'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      generatePdf ? 'translate-x-4' : ''
                    }`}
                  />
                </button>
                <span className="text-sm text-slate-300">Generate PDF</span>
              </label>
            </div>

            <button
              onClick={handleGenerate}
              disabled={loading}
              className="btn-primary w-full inline-flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="animate-spin">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="24" strokeDashoffset="6" strokeLinecap="round" />
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  Generate Summary
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Result */}
        <div className="lg:col-span-2">
          {!result && !loading && (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-12 text-center">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="mx-auto mb-3 text-slate-600">
                <rect x="8" y="6" width="32" height="36" rx="4" stroke="currentColor" strokeWidth="2" />
                <path d="M16 16h16M16 22h16M16 28h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <p className="text-slate-500">
                Configure the summary parameters and click Generate Summary.
              </p>
            </div>
          )}

          {loading && (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-12 text-center animate-fade-in">
              <div className="inline-block mb-4">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="animate-spin text-teal-400">
                  <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="3" strokeDasharray="80" strokeDashoffset="20" strokeLinecap="round" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">Generating Summary</h3>
              <p className="text-sm text-slate-400">
                Running Summary Generator, QA Agent, and Translation Layer...
              </p>
            </div>
          )}

          {result && (
            <div className="space-y-4 animate-fade-in">
              {/* Status message */}
              {result.message && (
                <div className={`border rounded-xl p-4 ${
                  result.status === 'completed' ? 'bg-emerald-400/5 border-emerald-400/20' :
                  result.status === 'needs_review' ? 'bg-amber-400/5 border-amber-400/20' :
                  'bg-slate-800 border-slate-700'
                }`}>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={result.status} size="md" />
                    <span className="text-sm text-slate-300">{result.message}</span>
                  </div>
                </div>
              )}

              {/* QA Verdict */}
              {qaVerdict && (
                <div className={`border rounded-xl p-5 ${
                  qaVerdict === 'PASS'
                    ? 'bg-emerald-400/5 border-emerald-400/20'
                    : 'bg-rose-400/5 border-rose-400/20'
                }`}>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <h3 className="text-sm font-semibold text-white">QA Validation</h3>
                      <StatusBadge status={qaVerdict} size="md" />
                    </div>
                    {qaScore !== undefined && (
                      <span className="text-sm text-slate-300 font-mono">
                        Score: {qaScore}/100
                      </span>
                    )}
                  </div>

                  {qaIssues.length > 0 && (
                    <div className="space-y-2">
                      {qaIssues.map((issue, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm">
                          <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${
                            issue.severity === 'high'
                              ? 'bg-rose-400/10 text-rose-400'
                              : issue.severity === 'medium'
                              ? 'bg-amber-400/10 text-amber-400'
                              : 'bg-slate-700 text-slate-400'
                          }`}>
                            {issue.severity}
                          </span>
                          <span className="text-slate-300">{issue.message}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Workflow Steps */}
              {result.steps && result.steps.length > 0 && (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                    Workflow Steps
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {result.steps.map((s, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-xs">
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          s.status === 'success' ? 'bg-[#111]' :
                          s.status === 'needs_review' ? 'bg-[rgba(17,17,17,0.55)]' :
                          s.status === 'error' ? 'bg-[rgba(17,17,17,0.85)]' :
                          s.status === 'skipped' ? 'bg-[rgba(17,17,17,0.15)]' : 'bg-[rgba(17,17,17,0.15)]'
                        }`} />
                        <span className="text-slate-300">{s.agent}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary Text */}
              {(summaryText || dischargeSummary) && (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-white">Discharge Summary</h3>
                    <button
                      onClick={() => {
                        const text = summaryText || JSON.stringify(dischargeSummary, null, 2);
                        navigator.clipboard.writeText(text);
                      }}
                      className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1.5 bg-slate-800 px-3 py-1.5 rounded-lg"
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
                        <path d="M8 4V2.5A1.5 1.5 0 006.5 1h-4A1.5 1.5 0 001 2.5v4A1.5 1.5 0 002.5 8H4" stroke="currentColor" strokeWidth="1.2" />
                      </svg>
                      Copy to Clipboard
                    </button>
                  </div>

                  {dischargeSummary && (
                    <div className="space-y-4 mb-4">
                      {Object.entries(dischargeSummary).map(([key, value]) => {
                        if (!value || (Array.isArray(value) && value.length === 0)) return null;
                        const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                        return (
                          <div key={key} className="border-b border-slate-800 pb-3">
                            <h4 className="text-xs font-semibold text-teal-400 uppercase tracking-wider mb-1">{label}</h4>
                            {typeof value === 'string' ? (
                              <p className="text-sm text-slate-300 leading-relaxed">{value}</p>
                            ) : Array.isArray(value) ? (
                              <ul className="list-disc list-inside text-sm text-slate-300 space-y-0.5">
                                {value.map((item, i) => (
                                  <li key={i}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>
                                ))}
                              </ul>
                            ) : typeof value === 'object' && value !== null ? (
                              <pre className="text-xs text-slate-400 bg-slate-950 rounded p-2 overflow-x-auto">{JSON.stringify(value, null, 2)}</pre>
                            ) : (
                              <p className="text-sm text-slate-300">{String(value)}</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {summaryText && !dischargeSummary && (
                    <div className="prose prose-invert prose-sm max-w-none">
                      <div className="bg-slate-950 rounded-lg p-5 text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-mono">
                        {summaryText}
                      </div>
                    </div>
                  )}

                  {summaryText && dischargeSummary && (
                    <details className="mt-4">
                      <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300">
                        View raw prose version
                      </summary>
                      <div className="bg-slate-950 rounded-lg p-4 mt-2 text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-mono">
                        {summaryText}
                      </div>
                    </details>
                  )}
                </div>
              )}

              {/* Downloads */}
              {(audioUrl || pdfUrl) && (
                <div className="bg-slate-900 border border-slate-700 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-white mb-3">Downloads</h3>
                  <div className="flex items-center gap-3">
                    {pdfUrl && (
                      <a
                        href={pdfUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-secondary text-sm inline-flex items-center gap-2"
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M7 2v8M4 7l3 3 3-3M3 11h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        Download PDF
                      </a>
                    )}
                    {audioUrl && (
                      <a
                        href={audioUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-secondary text-sm inline-flex items-center gap-2"
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M7 2v8M4 7l3 3 3-3M3 11h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        Download Audio
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Back button */}
              <div className="pt-2">
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
      </div>
    </div>
  );
}
