'use client';

import { useState } from 'react';
import type { ClinicalEntity } from '@/lib/types';

interface ClinicalSummaryProps {
  entities: ClinicalEntity[];
}

// ── helpers ──────────────────────────────────────────────────

function cleanName(name: string): string {
  let cleaned = name.replace(/^finding_/, '');
  cleaned = cleaned.replace(/_/g, ' ');
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function regionLabel(region: string): string {
  return region.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(iso?: string | null): string {
  if (!iso) return '';
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

function certaintyWord(score: number | null | undefined): string {
  if (score == null) return '';
  if (score >= 0.9) return 'confirmed';
  if (score >= 0.7) return 'likely';
  if (score >= 0.5) return 'suspected';
  return 'uncertain';
}

function trendPhrase(entity: ClinicalEntity): string {
  const traj = entity.certainty_trajectory || [];
  if (traj.length < 2) return '';
  const first = traj[0].certainty;
  const last = traj[traj.length - 1].certainty;
  const delta = last - first;
  if (delta > 0.05) return ', increasing certainty over time';
  if (delta < -0.05) return ', decreasing certainty over time';
  return ', stable over follow-up';
}

function temporalSpan(entity: ClinicalEntity): string {
  const first = entity.first_seen || entity.first_documented;
  const last = entity.last_seen || entity.last_documented;
  if (!first) return '';
  const f = formatDate(first);
  const l = formatDate(last);
  if (f === l) return ` (${f})`;
  return ` (${f} – ${l})`;
}

/** Entities with multiple events = tracked over time = clinically significant */
function isSignificant(entity: ClinicalEntity): boolean {
  return (entity.event_count || 0) > 1;
}

/** Build a clinical sentence for one entity */
function entityToSentence(entity: ClinicalEntity): string {
  const name = cleanName(entity.canonical_name);
  const cert = entity.certainty_score;
  const status = entity.status;
  const events = entity.event_count || 1;

  if (status === 'absent' || entity.negated) {
    const traj = entity.certainty_trajectory || [];
    if (traj.length >= 2) {
      return `${name} was previously documented but has since been excluded${temporalSpan(entity)}.`;
    }
    return `No evidence of ${name.toLowerCase()}.`;
  }

  const certPhrase = cert != null ? `${certaintyWord(cert)} ` : '';
  const site = entity.anatomical_site ? ` in the ${entity.anatomical_site}` : '';
  const radlex = entity.radlex_id ? ` [${entity.radlex_id}]` : '';
  const trend = trendPhrase(entity);
  const dates = temporalSpan(entity);
  const eventNote = events > 1 ? `, documented across ${events} reports` : '';

  if (status === 'uncertain') {
    return `${name}${radlex}${site} is of uncertain significance (certainty ${cert?.toFixed(2) || 'N/A'})${dates}${eventNote}${trend}.`;
  }

  return `${certPhrase}${name}${radlex}${site}${dates}${eventNote}${trend}.`.replace(/^./, (c) => c.toUpperCase());
}

// ── components ───────────────────────────────────────────────

function RegionSection({
  region,
  entities,
}: {
  region: string;
  entities: ClinicalEntity[];
}) {
  const [showMinor, setShowMinor] = useState(false);

  const active = entities.filter((e) => e.status === 'active' && !e.negated);
  const uncertain = entities.filter((e) => e.status === 'uncertain');
  const absent = entities.filter((e) => e.status === 'absent' || e.negated);

  // Split active into significant (multi-event) and incidental (single-event)
  const significant = active.filter(isSignificant);
  const incidental = active.filter((e) => !isSignificant(e));

  const significantSentences = significant.map(entityToSentence);
  const incidentalSentences = incidental.map(entityToSentence);
  const uncertainSentences = uncertain.map(entityToSentence);

  // If no significant findings, show all active
  const hasSignificant = significant.length > 0;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl overflow-hidden">
      {/* Region header */}
      <div className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-teal-400" />
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
            {regionLabel(region)}
          </h3>
          <div className="flex items-center gap-2 text-xs">
            {significant.length > 0 && (
              <span className="bg-emerald-400/10 text-emerald-400 px-2 py-0.5 rounded-full">
                {significant.length} tracked
              </span>
            )}
            {incidental.length > 0 && (
              <span className="bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full">
                {incidental.length} incidental
              </span>
            )}
            {uncertain.length > 0 && (
              <span className="bg-amber-400/10 text-amber-400 px-2 py-0.5 rounded-full">
                {uncertain.length} uncertain
              </span>
            )}
            {absent.length > 0 && (
              <span className="bg-slate-800 text-slate-500 px-2 py-0.5 rounded-full">
                {absent.length} excluded
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Narrative content */}
      <div className="px-5 pb-5 space-y-3">
        {/* Key tracked findings (multi-event, actively monitored) */}
        {significantSentences.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-2">
              Key Findings (tracked across multiple reports)
            </h4>
            <div className="bg-slate-950/50 rounded-lg p-4 text-sm text-slate-300 leading-relaxed space-y-1.5">
              {significantSentences.map((sentence, i) => (
                <p key={i}>{sentence}</p>
              ))}
            </div>
          </div>
        )}

        {/* Uncertain findings */}
        {uncertainSentences.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-2">
              Uncertain / Under Evaluation
            </h4>
            <div className="bg-slate-950/50 rounded-lg p-4 text-sm text-slate-400 leading-relaxed space-y-1.5">
              {uncertainSentences.map((sentence, i) => (
                <p key={i}>{sentence}</p>
              ))}
            </div>
          </div>
        )}

        {/* If no significant findings, show all active as the main section */}
        {!hasSignificant && incidentalSentences.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Documented Findings
            </h4>
            <div className="bg-slate-950/50 rounded-lg p-4 text-sm text-slate-300 leading-relaxed space-y-1.5">
              {incidentalSentences.map((sentence, i) => (
                <p key={i}>{sentence}</p>
              ))}
            </div>
          </div>
        )}

        {/* Incidental findings — collapsed, shown only on demand */}
        {hasSignificant && incidental.length > 0 && (
          <div>
            <button
              onClick={() => setShowMinor(!showMinor)}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                className={`transition-transform ${showMinor ? 'rotate-90' : ''}`}
              >
                <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              {incidental.length} incidental finding{incidental.length !== 1 ? 's' : ''} (single report, not tracked)
            </button>
            {showMinor && (
              <div className="bg-slate-950/30 rounded-lg p-4 mt-2 text-sm text-slate-500 leading-relaxed space-y-1">
                {incidentalSentences.map((sentence, i) => (
                  <p key={i}>{sentence}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Absent/excluded — just a count, expandable */}
        {absent.length > 0 && (
          <p className="text-xs text-slate-600">
            {absent.length} finding{absent.length !== 1 ? 's' : ''} previously documented but now excluded.
          </p>
        )}
      </div>
    </div>
  );
}

// ── main component ───────────────────────────────────────────

export default function ClinicalSummary({ entities }: ClinicalSummaryProps) {
  if (entities.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="mx-auto mb-3 text-slate-600">
          <circle cx="24" cy="24" r="18" stroke="currentColor" strokeWidth="2" />
          <path d="M24 16v8M24 28v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <p>No clinical entities found for this patient.</p>
        <p className="text-sm mt-1">
          Process some reports through the workflow to populate the fact graph.
        </p>
      </div>
    );
  }

  // Group by body region
  const grouped: Record<string, ClinicalEntity[]> = {};
  for (const entity of entities) {
    const region = entity.body_region || 'unspecified';
    if (!grouped[region]) grouped[region] = [];
    grouped[region].push(entity);
  }

  const sortedRegions = Object.keys(grouped).sort((a, b) => {
    if (a === 'unspecified') return 1;
    if (b === 'unspecified') return -1;
    // Sort by number of significant (tracked) entities, not total
    const sigA = grouped[a].filter((e) => e.status !== 'absent' && isSignificant(e)).length;
    const sigB = grouped[b].filter((e) => e.status !== 'absent' && isSignificant(e)).length;
    return sigB - sigA;
  });

  // Overall stats
  const active = entities.filter((e) => e.status === 'active' && !e.negated);
  const tracked = active.filter(isSignificant);
  const incidental = active.filter((e) => !isSignificant(e));
  const uncertainCount = entities.filter((e) => e.status === 'uncertain').length;
  const absentCount = entities.filter((e) => e.status === 'absent' || e.negated).length;

  return (
    <div className="space-y-4">
      {/* Overall summary */}
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3">Clinical Overview</h3>
        <p className="text-sm text-slate-300 leading-relaxed">
          <strong className="text-white">{tracked.length} actively tracked findings</strong> across{' '}
          {sortedRegions.length} body regions, each documented in multiple imaging studies.
          {incidental.length > 0 && (
            <> An additional {incidental.length} incidental findings were noted in single reports.</>
          )}
          {absentCount > 0 && (
            <> {absentCount} previously documented findings have since been excluded.</>
          )}
        </p>
        <div className="flex items-center gap-4 mt-3 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-slate-400">Tracked: {tracked.length}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-slate-600" />
            <span className="text-slate-400">Incidental: {incidental.length}</span>
          </div>
          {uncertainCount > 0 && (
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-amber-400" />
              <span className="text-slate-400">Uncertain: {uncertainCount}</span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-slate-800" />
            <span className="text-slate-400">Excluded: {absentCount}</span>
          </div>
        </div>
      </div>

      {/* Per-region narratives */}
      {sortedRegions.map((region) => (
        <RegionSection key={region} region={region} entities={grouped[region]} />
      ))}
    </div>
  );
}
