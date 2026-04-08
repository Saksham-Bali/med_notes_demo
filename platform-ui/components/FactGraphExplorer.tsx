'use client';

import type { ClinicalEntity } from '@/lib/types';

interface FactGraphExplorerProps {
  entities: ClinicalEntity[];
}

function cleanName(name: string): string {
  let cleaned = name.replace(/^finding_/, '');
  cleaned = cleaned.replace(/_/g, ' ');
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export default function FactGraphExplorer({ entities }: FactGraphExplorerProps) {
  if (entities.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <p>No entities in the fact graph.</p>
      </div>
    );
  }

  const grounded = entities.filter((e) => e.radlex_id);
  const ungrounded = entities.filter((e) => !e.radlex_id);
  const negated = entities.filter((e) => e.negated);
  const active = entities.filter((e) => (e.status ?? 'active') === 'active');

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-white">{entities.length}</div>
          <div className="text-xs text-slate-400 mt-1">Total Entities</div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-teal-400">{grounded.length}</div>
          <div className="text-xs text-slate-400 mt-1">RadLex Grounded</div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-emerald-400">{active.length}</div>
          <div className="text-xs text-slate-400 mt-1">Active</div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-slate-400">{negated.length}</div>
          <div className="text-xs text-slate-400 mt-1">Negated</div>
        </div>
      </div>

      {ungrounded.length > 0 && (
        <div className="bg-amber-400/5 border border-amber-400/20 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-amber-400 mb-2">
            Ungrounded Entities ({ungrounded.length})
          </h4>
          <div className="flex flex-wrap gap-2">
            {ungrounded.map((e) => (
              <span key={e.entity_id} className="text-xs bg-slate-800 text-slate-300 px-2 py-1 rounded">
                {cleanName(e.canonical_name)}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold text-slate-300 mb-3">All Entities</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left py-2 px-3 text-xs text-slate-500 font-medium">Entity</th>
                <th className="text-left py-2 px-3 text-xs text-slate-500 font-medium">RadLex</th>
                <th className="text-left py-2 px-3 text-xs text-slate-500 font-medium">Region</th>
                <th className="text-left py-2 px-3 text-xs text-slate-500 font-medium">Certainty</th>
                <th className="text-left py-2 px-3 text-xs text-slate-500 font-medium">Trend</th>
                <th className="text-left py-2 px-3 text-xs text-slate-500 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((e) => (
                <tr key={e.entity_id} className="border-b border-slate-800 hover:bg-slate-800/30">
                  <td className={`py-2 px-3 text-slate-200 ${e.negated ? 'line-through opacity-50' : ''}`}>
                    {cleanName(e.canonical_name)}
                  </td>
                  <td className="py-2 px-3">
                    {e.radlex_id ? (
                      <span className="text-xs font-mono text-teal-400">{e.radlex_id}</span>
                    ) : (
                      <span className="text-xs text-slate-600">--</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-xs text-slate-400">
                    {e.body_region ? e.body_region.replace(/_/g, ' ') : '--'}
                  </td>
                  <td className="py-2 px-3 text-xs font-mono text-slate-300">
                    {e.certainty_score !== null && e.certainty_score !== undefined
                      ? e.certainty_score.toFixed(2)
                      : '--'}
                  </td>
                  <td className="py-2 px-3 text-xs">
                    {e.trend === 'improving' && <span className="text-emerald-400">{'\u2193'} Improving</span>}
                    {e.trend === 'worsening' && <span className="text-rose-400">{'\u2191'} Worsening</span>}
                    {e.trend === 'stable' && <span className="text-slate-400">{'\u2192'} Stable</span>}
                    {!e.trend && <span className="text-slate-600">--</span>}
                  </td>
                  <td className="py-2 px-3">
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        (e.status ?? 'active') === 'active'
                          ? 'bg-emerald-400/10 text-emerald-400'
                          : (e.status ?? 'active') === 'resolved'
                          ? 'bg-slate-600/30 text-slate-400'
                          : 'bg-rose-400/10 text-rose-400'
                      }`}
                    >
                      {e.status ?? 'active'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
