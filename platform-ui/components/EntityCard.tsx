'use client';

import type { ClinicalEntity } from '@/lib/types';

interface EntityCardProps {
  entity: ClinicalEntity;
}

function cleanName(name: string): string {
  let cleaned = name.replace(/^finding_/, '');
  cleaned = cleaned.replace(/_/g, ' ');
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function getCertaintyColor(score: number): string {
  if (score > 0.8) return 'bg-emerald-400';
  if (score >= 0.5) return 'bg-amber-400';
  return 'bg-rose-400';
}

function getTrendInfo(trend: string | null | undefined): { symbol: string; color: string; label: string } {
  switch (trend) {
    case 'worsening':
      return { symbol: '\u2191', color: 'text-rose-400', label: 'Increasing' };
    case 'improving':
      return { symbol: '\u2193', color: 'text-emerald-400', label: 'Decreasing' };
    case 'stable':
      return { symbol: '\u2192', color: 'text-slate-400', label: 'Stable' };
    default:
      return { symbol: '--', color: 'text-slate-600', label: 'Unknown' };
  }
}

function formatDate(iso?: string | null): string {
  if (!iso) return '--';
  try {
    return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return iso;
  }
}

export default function EntityCard({ entity }: EntityCardProps) {
  const certainty = entity.certainty_score ?? 0;
  const trendInfo = getTrendInfo(entity.trend);
  const status = entity.status ?? 'active';

  return (
    <div className={`bg-slate-800/50 border border-slate-700 rounded-lg p-4 ${entity.negated ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between mb-2">
        <h4 className={`text-sm font-semibold text-white ${entity.negated ? 'line-through' : ''}`}>
          {cleanName(entity.canonical_name)}
        </h4>
        <div className="flex items-center gap-2">
          {entity.negated && (
            <span className="text-xs text-rose-400 font-semibold uppercase tracking-wide">Negated</span>
          )}
          {entity.radlex_id ? (
            <span className="text-xs bg-teal-400/10 text-teal-400 px-2 py-0.5 rounded-full font-mono">
              {entity.radlex_id}
            </span>
          ) : (
            <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full">
              Ungrounded
            </span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 w-16">Certainty</span>
          <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${getCertaintyColor(certainty)}`}
              style={{ width: `${certainty * 100}%` }}
            />
          </div>
          <span className="text-xs text-slate-300 font-mono w-10 text-right">
            {certainty.toFixed(2)}
          </span>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <span className="text-slate-500">Status:</span>
            <span
              className={`px-1.5 py-0.5 rounded ${
                status === 'active'
                  ? 'bg-emerald-400/10 text-emerald-400'
                  : status === 'resolved'
                  ? 'bg-slate-600/30 text-slate-400'
                  : 'bg-rose-400/10 text-rose-400'
              }`}
            >
              {status}
            </span>
          </div>

          <div className="flex items-center gap-1">
            <span className="text-slate-500">Trend:</span>
            <span className={`font-bold ${trendInfo.color}`}>{trendInfo.symbol}</span>
            <span className={trendInfo.color}>{trendInfo.label}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 pt-1">
          <div>
            <span className="text-slate-500">First seen</span>
            <div className="text-slate-300 mt-0.5">{formatDate(entity.first_seen)}</div>
          </div>
          <div>
            <span className="text-slate-500">Last seen</span>
            <div className="text-slate-300 mt-0.5">{formatDate(entity.last_seen)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
