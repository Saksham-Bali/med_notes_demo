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
      <div className="surface h-full p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">
              Patient
            </div>
            <h3 className="mt-2 text-xl font-semibold text-black">{patient.display_name}</h3>
            <p className="mt-1 text-sm text-[rgba(17,17,17,0.56)]">{patient.cancer_type} cancer</p>
          </div>
          <span className="rounded-full border border-[rgba(17,17,17,0.1)] bg-white px-3 py-1 font-mono-ui text-[11px] text-[rgba(17,17,17,0.46)]">
            {patient.id}
          </span>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
          <div className="surface-muted p-3">
            <div className="text-[rgba(17,17,17,0.42)]">Entities</div>
            <div className="mt-1 font-mono-ui text-black">{entityCount ?? '--'}</div>
          </div>
          <div className="surface-muted p-3">
            <div className="text-[rgba(17,17,17,0.42)]">Reports</div>
            <div className="mt-1 font-mono-ui text-black">{patient.reports_count}</div>
          </div>
        </div>

        {(firstSeen || lastSeen) && (
          <div className="mt-4 space-y-1 text-xs text-[rgba(17,17,17,0.5)]">
            {firstSeen && <div>First event: {firstSeen}</div>}
            {lastSeen && <div>Latest event: {lastSeen}</div>}
          </div>
        )}

        {bodyRegions && bodyRegions.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {bodyRegions.slice(0, 4).map((region) => (
              <span
                key={region}
                className="rounded-full border border-[rgba(17,17,17,0.08)] bg-white px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] text-[rgba(17,17,17,0.48)]"
              >
                {region.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        )}

        <div className="mt-5 border-t border-[rgba(17,17,17,0.08)] pt-4">
          <span className="inline-flex items-center gap-1 text-sm text-black">
            Open chart
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="transition-transform group-hover:translate-x-1">
              <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </div>
    </Link>
  );
}
