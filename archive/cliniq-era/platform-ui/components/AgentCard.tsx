'use client';

import Link from 'next/link';
import type { AgentInfo } from '@/lib/agents-data';

interface AgentCardProps {
  agent: AgentInfo;
}

export default function AgentCard({ agent }: AgentCardProps) {
  return (
    <Link href={`/agents/${agent.slug}`} className="block group">
      <div className="surface h-full p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-mono-ui text-[11px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.42)]">
              Agent {agent.number}
            </div>
            <h3 className="mt-2 text-lg font-semibold text-black">{agent.fullName}</h3>
          </div>
          <span className="rounded-full border border-[rgba(17,17,17,0.12)] bg-white px-2.5 py-1 font-mono-ui text-[11px] text-[rgba(17,17,17,0.52)]">
            :{agent.port}
          </span>
        </div>

        <p className="mt-4 text-sm leading-6 text-[rgba(17,17,17,0.64)]">
          {agent.purpose.split('.')[0]}.
        </p>

        <div className="mt-6 flex items-center justify-between border-t border-[rgba(17,17,17,0.08)] pt-4">
          <span className="rounded-full bg-[rgba(17,17,17,0.05)] px-3 py-1 text-xs uppercase tracking-[0.14em] text-[rgba(17,17,17,0.48)]">
            {agent.category}
          </span>
          <span className="inline-flex items-center gap-1 text-sm text-black">
            Open
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="transition-transform group-hover:translate-x-1">
              <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </div>
    </Link>
  );
}
