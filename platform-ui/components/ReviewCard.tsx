'use client';

import { useState } from 'react';
import type { ClinicalFact } from '@/lib/types';

interface ReviewCardProps {
  fact: ClinicalFact;
  approved: boolean;
  onToggle: () => void;
  onEdit: (edited: ClinicalFact) => void;
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

function getCertaintyLabel(score: number): string {
  if (score > 0.9) return 'confirmed';
  if (score > 0.7) return 'probable';
  if (score > 0.5) return 'possible';
  return 'uncertain';
}

function getTemporalBadge(change?: string): { bg: string; text: string } | null {
  if (!change) return null;
  switch (change) {
    case 'NEW':
      return { bg: 'bg-teal-400/10 text-teal-400', text: 'NEW' };
    case 'STABLE':
      return { bg: 'bg-slate-600/30 text-slate-400', text: 'STABLE' };
    case 'WORSENED':
      return { bg: 'bg-rose-400/10 text-rose-400', text: 'WORSENED' };
    case 'IMPROVED':
      return { bg: 'bg-emerald-400/10 text-emerald-400', text: 'IMPROVED' };
    case 'RESOLVED':
      return { bg: 'bg-purple-400/10 text-purple-400', text: 'RESOLVED' };
    case 'ABSENT':
      return { bg: 'bg-slate-600/30 text-slate-500', text: 'ABSENT' };
    default:
      return { bg: 'bg-slate-600/30 text-slate-400', text: change };
  }
}

export default function ReviewCard({ fact, approved, onToggle, onEdit }: ReviewCardProps) {
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(fact.entity_name);
  const [editCertainty, setEditCertainty] = useState(fact.certainty);
  const [editBodyRegion, setEditBodyRegion] = useState(fact.body_region || '');

  const temporal = getTemporalBadge(fact.temporal_change);

  function handleSave() {
    onEdit({
      ...fact,
      entity_name: editName,
      certainty: editCertainty,
      body_region: editBodyRegion || undefined,
    });
    setEditing(false);
  }

  function handleCancel() {
    setEditName(fact.entity_name);
    setEditCertainty(fact.certainty);
    setEditBodyRegion(fact.body_region || '');
    setEditing(false);
  }

  return (
    <div
      className={`border rounded-xl p-5 transition-all duration-200 ${
        approved
          ? 'bg-slate-900 border-teal-400/30'
          : 'bg-slate-900/50 border-slate-700 opacity-60'
      }`}
    >
      <div className="flex items-start gap-3">
        <button
          onClick={onToggle}
          className={`mt-0.5 w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors ${
            approved
              ? 'bg-teal-400 border-teal-400 text-slate-950'
              : 'border-slate-600 hover:border-slate-400'
          }`}
        >
          {approved && (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M2.5 6l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-base font-semibold text-white">
                {cleanName(fact.entity_name)}
              </h3>
              {fact.radlex_id ? (
                <span className="text-xs bg-teal-400/10 text-teal-400 px-2 py-0.5 rounded-full font-mono">
                  RadLex: {fact.radlex_id}
                </span>
              ) : (
                <span className="text-xs bg-amber-400/10 text-amber-400 px-2 py-0.5 rounded-full">
                  Ungrounded
                </span>
              )}
            </div>
            <button
              onClick={() => setEditing(!editing)}
              className="text-xs text-slate-400 hover:text-teal-400 transition-colors flex items-center gap-1 shrink-0"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M8.5 1.5l2 2-7 7H1.5V8.5l7-7z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Edit
            </button>
          </div>

          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 w-16 shrink-0">Certainty</span>
              <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${getCertaintyColor(fact.certainty)}`}
                  style={{ width: `${fact.certainty * 100}%` }}
                />
              </div>
              <span className="text-xs text-slate-300 font-mono w-24 text-right">
                {fact.certainty.toFixed(2)} ({getCertaintyLabel(fact.certainty)})
              </span>
            </div>

            <div className="flex items-center flex-wrap gap-3 text-xs">
              {fact.body_region && (
                <div className="flex items-center gap-1">
                  <span className="text-slate-500">Body Region:</span>
                  <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded">{fact.body_region}</span>
                </div>
              )}

              {temporal && (
                <div className="flex items-center gap-1">
                  <span className="text-slate-500">Temporal:</span>
                  <span className={`px-2 py-0.5 rounded ${temporal.bg}`}>{temporal.text}</span>
                </div>
              )}

              <div className="flex items-center gap-1">
                <span className="text-slate-500">Negated:</span>
                <span className={fact.negated ? 'text-rose-400' : 'text-slate-400'}>
                  {fact.negated ? 'Yes' : 'No'}
                </span>
              </div>
            </div>

            {(fact.evidence || fact.source_text) && (
              <div className="bg-slate-800/60 rounded-lg px-3 py-2 text-sm text-slate-300 italic border-l-2 border-slate-600">
                &quot;{fact.evidence || fact.source_text}&quot;
              </div>
            )}
          </div>

          {editing && (
            <div className="mt-4 pt-4 border-t border-slate-700 space-y-3">
              <div>
                <label className="text-xs text-slate-500 block mb-1">Entity Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-400"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-500 block mb-1">Certainty (0-1)</label>
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    value={editCertainty}
                    onChange={(e) => setEditCertainty(parseFloat(e.target.value) || 0)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-400"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-500 block mb-1">Body Region</label>
                  <input
                    type="text"
                    value={editBodyRegion}
                    onChange={(e) => setEditBodyRegion(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-400"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  className="px-4 py-1.5 bg-teal-500 text-white text-sm rounded-lg hover:bg-teal-600 transition-colors"
                >
                  Save
                </button>
                <button
                  onClick={handleCancel}
                  className="px-4 py-1.5 bg-slate-700 text-slate-300 text-sm rounded-lg hover:bg-slate-600 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
