'use client';

import Link from 'next/link';
import type { AgentInfo } from '@/lib/agents-data';
import { getCategoryColor } from '@/lib/agents-data';

interface AgentCardProps {
  agent: AgentInfo;
}

const categoryBg: Record<string, string> = {
  teal: 'bg-teal-400/10 border-teal-400/30 hover:border-teal-400/60',
  amber: 'bg-amber-400/10 border-amber-400/30 hover:border-amber-400/60',
  blue: 'bg-blue-400/10 border-blue-400/30 hover:border-blue-400/60',
  purple: 'bg-purple-400/10 border-purple-400/30 hover:border-purple-400/60',
};

const categoryText: Record<string, string> = {
  teal: 'text-teal-400',
  amber: 'text-amber-400',
  blue: 'text-blue-400',
  purple: 'text-purple-400',
};

export default function AgentCard({ agent }: AgentCardProps) {
  const color = getCategoryColor(agent.category);

  return (
    <Link href={`/agents/${agent.slug}`} className="block group">
      <div
        className={`rounded-xl border p-5 transition-all duration-200 ${categoryBg[color]} hover:shadow-lg hover:shadow-slate-900/50`}
      >
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-mono font-bold ${categoryText[color]}`}>
              {agent.number}
            </span>
            <span className="text-sm font-semibold text-white">{agent.fullName}</span>
          </div>
          <span className="text-xs font-mono text-slate-500">:{agent.port}</span>
        </div>

        <p className="text-sm text-slate-400 leading-relaxed mb-4 line-clamp-2">
          {agent.purpose.split('.')[0]}.
        </p>

        <div className="flex items-center justify-between">
          <span
            className={`text-xs px-2 py-0.5 rounded-full capitalize ${
              color === 'teal'
                ? 'bg-teal-400/10 text-teal-400'
                : color === 'amber'
                ? 'bg-amber-400/10 text-amber-400'
                : color === 'blue'
                ? 'bg-blue-400/10 text-blue-400'
                : 'bg-purple-400/10 text-purple-400'
            }`}
          >
            {agent.category}
          </span>
          <span className={`text-sm ${categoryText[color]} group-hover:translate-x-1 transition-transform inline-flex items-center gap-1`}>
            Learn More
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </div>
    </Link>
  );
}
