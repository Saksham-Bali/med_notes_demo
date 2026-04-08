'use client';

import { useState } from 'react';
import type { TimelineEvent } from '@/lib/types';

interface PatientTimelineProps {
  events: TimelineEvent[];
}

// ── helpers ──────────────────────────────────────────────────

function cleanName(name: string): string {
  if (!name) return '';
  let cleaned = name.replace(/^finding_/, '');
  cleaned = cleaned.replace(/_/g, ' ');
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

function getModalityColor(modality?: string | null): string {
  if (!modality) return 'bg-slate-700 text-slate-400';
  switch (modality.toUpperCase()) {
    case 'CT': return 'bg-blue-400/10 text-blue-400';
    case 'MRI': return 'bg-purple-400/10 text-purple-400';
    case 'PET': return 'bg-amber-400/10 text-amber-400';
    case 'X-RAY': case 'XR': return 'bg-teal-400/10 text-teal-400';
    case 'US': case 'ULTRASOUND': return 'bg-emerald-400/10 text-emerald-400';
    case 'RR': return 'bg-indigo-400/10 text-indigo-400';
    default: return 'bg-slate-700 text-slate-400';
  }
}

function modalityLabel(modality?: string | null): string {
  if (!modality) return 'Unknown';
  switch (modality.toUpperCase()) {
    case 'CT': return 'CT Scan';
    case 'MRI': return 'MRI';
    case 'PET': return 'PET Scan';
    case 'RR': return 'Radiology Report';
    case 'OTHER': return 'Clinical Study';
    default: return modality;
  }
}

function certaintyLabel(cert: number | null | undefined): string {
  if (cert == null) return '';
  if (cert >= 0.9) return 'confirmed';
  if (cert >= 0.7) return 'likely';
  if (cert >= 0.5) return 'suspected';
  return 'uncertain';
}

function certaintyColor(cert: number | null | undefined): string {
  if (cert == null) return 'text-slate-500';
  if (cert >= 0.9) return 'text-emerald-400';
  if (cert >= 0.7) return 'text-blue-400';
  if (cert >= 0.5) return 'text-amber-400';
  return 'text-slate-500';
}

/** Build a clinical sentence for one finding within a report */
function findingToPhrase(event: TimelineEvent): string {
  const name = cleanName(event.canonical_name || event.entity_name || '');
  const cert = event.certainty;
  const meas = event.measurement;
  const negated = event.is_negated;

  if (negated) {
    return `no ${name.toLowerCase()}`;
  }

  let phrase = name.toLowerCase();

  // Add measurement if present
  if (meas && typeof meas === 'object') {
    const raw = (meas as Record<string, unknown>).raw_text;
    const val = (meas as Record<string, unknown>).value;
    const unit = (meas as Record<string, unknown>).unit;
    if (raw && raw !== 'None' && raw !== 'null') {
      phrase += ` (${raw})`;
    } else if (val != null && unit) {
      phrase += ` (${val} ${unit})`;
    }
  }

  // Add certainty qualifier for non-confirmed findings
  if (cert != null && cert < 0.9) {
    phrase = `${certaintyLabel(cert)} ${phrase}`;
  }

  return phrase;
}

// ── types ────────────────────────────────────────────────────

interface ReportGroup {
  reportId: string;
  modality: string;
  events: TimelineEvent[];
  positiveFindings: TimelineEvent[];
  negativeFindings: TimelineEvent[];
  measurementFindings: TimelineEvent[];
}

interface DateGroup {
  date: string;
  dateFormatted: string;
  reports: ReportGroup[];
  totalFindings: number;
}

// ── components ───────────────────────────────────────────────

function ReportCard({ report }: { report: ReportGroup }) {
  const [expanded, setExpanded] = useState(false);

  const positivePhrases = report.positiveFindings.map(findingToPhrase);
  const negativePhrases = report.negativeFindings.map(findingToPhrase);

  // Build a narrative summary for the report
  const summaryParts: string[] = [];
  if (positivePhrases.length > 0) {
    // Show first few inline, rest on expand
    const shown = positivePhrases.slice(0, 4);
    const remaining = positivePhrases.length - shown.length;
    summaryParts.push(shown.join(', '));
    if (remaining > 0 && !expanded) {
      summaryParts[summaryParts.length - 1] += `, and ${remaining} more`;
    }
  }

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg overflow-hidden">
      {/* Report header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-slate-800/60 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-xs px-2 py-0.5 rounded shrink-0 ${getModalityColor(report.modality)}`}>
            {modalityLabel(report.modality)}
          </span>
          <span className="text-xs text-slate-500 font-mono shrink-0">
            {report.reportId}
          </span>
          <span className="text-xs text-slate-400">
            {report.positiveFindings.length} finding{report.positiveFindings.length !== 1 ? 's' : ''}
            {report.negativeFindings.length > 0 && (
              <>, {report.negativeFindings.length} excluded</>
            )}
          </span>
        </div>
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          className={`text-slate-500 transition-transform shrink-0 ${expanded ? 'rotate-180' : ''}`}
        >
          <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {/* Report content */}
      <div className="px-4 pb-3">
        {/* Narrative summary */}
        <p className="text-sm text-slate-300 leading-relaxed">
          {positivePhrases.length > 0 ? (
            expanded ? (
              <>
                <span className="text-slate-400">Findings: </span>
                {positivePhrases.join('; ')}.
              </>
            ) : (
              <>
                <span className="text-slate-400">Findings: </span>
                {summaryParts.join('. ')}.
              </>
            )
          ) : (
            <span className="text-slate-500 italic">No positive findings in this report.</span>
          )}
        </p>

        {/* Expanded: show negatives + measurements */}
        {expanded && (
          <div className="mt-3 space-y-2">
            {/* Measurements table */}
            {report.measurementFindings.length > 0 && (
              <div>
                <h5 className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1.5">
                  Measurements
                </h5>
                <div className="grid gap-1">
                  {report.measurementFindings.map((ev, i) => {
                    const meas = ev.measurement as Record<string, unknown> | undefined;
                    return (
                      <div key={i} className="flex items-center gap-3 text-xs">
                        <span className="text-slate-300 min-w-[140px]">
                          {cleanName(ev.canonical_name || ev.entity_name || '')}
                        </span>
                        <span className="text-teal-400 font-mono">
                          {meas?.raw_text && meas.raw_text !== 'None'
                            ? String(meas.raw_text)
                            : meas?.value != null
                              ? `${meas.value} ${meas.unit || ''}`
                              : '—'}
                        </span>
                        {meas?.normalized_mm != null && (
                          <span className="text-slate-500">({String(meas.normalized_mm)} mm)</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Negative findings */}
            {negativePhrases.length > 0 && (
              <div>
                <h5 className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">
                  Excluded
                </h5>
                <p className="text-xs text-slate-500 leading-relaxed">
                  {negativePhrases.join(', ')}.
                </p>
              </div>
            )}

            {/* Per-finding detail list */}
            <div>
              <h5 className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1.5">
                All Findings ({report.events.length})
              </h5>
              <div className="grid gap-0.5">
                {report.events.map((ev, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs py-0.5">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      ev.is_negated ? 'bg-slate-600' : 'bg-emerald-400'
                    }`} />
                    <span className={ev.is_negated ? 'text-slate-500 line-through' : 'text-slate-300'}>
                      {cleanName(ev.canonical_name || ev.entity_name || '')}
                    </span>
                    <span className={`font-mono ${certaintyColor(ev.certainty)}`}>
                      {ev.certainty?.toFixed(2)}
                    </span>
                    {ev.certainty_label && (
                      <span className="text-slate-600">{ev.certainty_label}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DateSection({ group }: { group: DateGroup }) {
  return (
    <div className="relative pl-10">
      {/* Timeline dot */}
      <div className="absolute left-[13px] top-3 w-3 h-3 rounded-full bg-teal-500 border-2 border-slate-900 z-10" />

      <div className="space-y-2">
        {/* Date header */}
        <div className="flex items-center gap-3 pt-1">
          <span className="text-sm font-semibold text-white">{group.dateFormatted}</span>
          <span className="text-xs text-slate-500">
            {group.reports.length} report{group.reports.length !== 1 ? 's' : ''} · {group.totalFindings} findings
          </span>
        </div>

        {/* Report cards */}
        {group.reports.map((report) => (
          <ReportCard key={report.reportId} report={report} />
        ))}
      </div>
    </div>
  );
}

// ── main component ───────────────────────────────────────────

export default function PatientTimeline({ events }: PatientTimelineProps) {
  const [showAll, setShowAll] = useState(false);

  if (!events || events.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="mx-auto mb-3 text-slate-600">
          <rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" strokeWidth="2" />
          <path d="M6 18h36" stroke="currentColor" strokeWidth="2" />
          <circle cx="14" cy="14" r="1.5" fill="currentColor" />
          <circle cx="20" cy="14" r="1.5" fill="currentColor" />
          <circle cx="26" cy="14" r="1.5" fill="currentColor" />
        </svg>
        <p>No timeline events found.</p>
      </div>
    );
  }

  // Group events: date → report → events
  const dateMap = new Map<string, Map<string, TimelineEvent[]>>();
  for (const event of events) {
    const dateKey = (event.date || event.timestamp || '').slice(0, 10);
    if (!dateMap.has(dateKey)) dateMap.set(dateKey, new Map());
    const reportMap = dateMap.get(dateKey)!;
    const reportKey = event.source_report_id || 'unknown';
    if (!reportMap.has(reportKey)) reportMap.set(reportKey, []);
    reportMap.get(reportKey)!.push(event);
  }

  // Build structured date groups
  const dateGroups: DateGroup[] = [];
  for (const [dateKey, reportMap] of Array.from(dateMap)) {
    const reports: ReportGroup[] = [];
    let totalFindings = 0;

    for (const [reportId, reportEvents] of Array.from(reportMap)) {
      const positiveFindings = reportEvents.filter((e) => !e.is_negated);
      const negativeFindings = reportEvents.filter((e) => e.is_negated);
      const measurementFindings = reportEvents.filter((e) => {
        if (!e.measurement || typeof e.measurement !== 'object') return false;
        const m = e.measurement as Record<string, unknown>;
        return (m.raw_text && m.raw_text !== 'None' && m.raw_text !== 'null') || m.value != null;
      });

      // Determine dominant modality for this report
      const modalities = reportEvents.map((e) => e.modality || 'OTHER');
      const modality = modalities.find((m) => m !== 'OTHER') || modalities[0] || 'OTHER';

      totalFindings += positiveFindings.length;

      reports.push({
        reportId,
        modality,
        events: reportEvents,
        positiveFindings,
        negativeFindings,
        measurementFindings,
      });
    }

    dateGroups.push({
      date: dateKey,
      dateFormatted: formatDate(dateKey),
      reports,
      totalFindings,
    });
  }

  // Sort by date descending (most recent first)
  dateGroups.sort((a, b) => b.date.localeCompare(a.date));

  // Stats
  const totalPositive = events.filter((e) => !e.is_negated).length;
  const totalNegated = events.filter((e) => e.is_negated).length;
  const withMeasurements = events.filter((e) => {
    if (!e.measurement || typeof e.measurement !== 'object') return false;
    const m = e.measurement as Record<string, unknown>;
    return (m.raw_text && m.raw_text !== 'None') || m.value != null;
  }).length;

  // Show limited dates by default
  const INITIAL_DATES = 8;
  const visibleGroups = showAll ? dateGroups : dateGroups.slice(0, INITIAL_DATES);
  const hiddenCount = dateGroups.length - INITIAL_DATES;

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-2">Timeline Overview</h3>
        <p className="text-sm text-slate-300 leading-relaxed">
          <strong className="text-white">{events.length} events</strong> across{' '}
          <strong className="text-white">{dateGroups.length} imaging sessions</strong> spanning{' '}
          {dateGroups.length > 0 && (
            <>
              {dateGroups[dateGroups.length - 1].dateFormatted} to {dateGroups[0].dateFormatted}
            </>
          )}.
          {' '}{totalPositive} positive findings, {totalNegated} excluded,
          {withMeasurements > 0 && <> {withMeasurements} with quantitative measurements.</>}
        </p>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-[18px] top-0 bottom-0 w-px bg-slate-700" />

        <div className="space-y-6">
          {visibleGroups.map((group) => (
            <DateSection key={group.date} group={group} />
          ))}
        </div>

        {/* Show more / less */}
        {hiddenCount > 0 && (
          <div className="relative pl-10 pt-4">
            <div className="absolute left-[15px] top-5 w-2 h-2 rounded-full bg-slate-700 z-10" />
            <button
              onClick={() => setShowAll(!showAll)}
              className="text-sm text-teal-400 hover:text-teal-300 transition-colors flex items-center gap-1.5"
            >
              {showAll ? (
                <>Show less</>
              ) : (
                <>{hiddenCount} older session{hiddenCount !== 1 ? 's' : ''} — click to show</>
              )}
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                className={`transition-transform ${showAll ? 'rotate-180' : ''}`}
              >
                <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
