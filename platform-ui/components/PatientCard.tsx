'use client';

import Link from 'next/link';

interface PatientMeta {
  id: string;
  display_name: string;
  cancer_type: string;
  reports_count: number;
  description: string;
}

interface PatientCardProps {
  patient: PatientMeta;
  entityCount?: number;
  firstSeen?: string;
  lastSeen?: string;
  bodyRegions?: string[];
}

export default function PatientCard({
  patient,
  entityCount,
  firstSeen,
  lastSeen,
  bodyRegions,
}: PatientCardProps) {
  return (
    <Link href={`/demo/patient/${patient.id}`} className="block group">
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 hover:border-teal-400/50 transition-all duration-200 hover:shadow-lg hover:shadow-teal-400/5 h-full flex flex-col">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-white mb-1">{patient.display_name}</h3>
          <span className="text-sm text-teal-400 font-medium">{patient.cancer_type} Cancer</span>
        </div>

        <div className="space-y-2 text-sm text-slate-400 flex-1">
          <div className="flex items-center justify-between">
            <span>Entities</span>
            <span className="text-slate-200 font-mono">
              {entityCount !== undefined ? entityCount : '--'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Reports</span>
            <span className="text-slate-200 font-mono">{patient.reports_count}</span>
          </div>
          {firstSeen && (
            <div className="flex items-center justify-between">
              <span>First</span>
              <span className="text-slate-300 font-mono text-xs">{firstSeen}</span>
            </div>
          )}
          {lastSeen && (
            <div className="flex items-center justify-between">
              <span>Last</span>
              <span className="text-slate-300 font-mono text-xs">{lastSeen}</span>
            </div>
          )}
          {bodyRegions && bodyRegions.length > 0 && (
            <div className="pt-2">
              <span className="text-xs text-slate-500 block mb-1">Body Regions</span>
              <div className="flex flex-wrap gap-1">
                {bodyRegions.map((r) => (
                  <span key={r} className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                    {r}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 pt-4 border-t border-slate-800">
          <span className="text-sm text-teal-400 group-hover:translate-x-1 transition-transform inline-flex items-center gap-1">
            View Patient
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </div>
    </Link>
  );
}
