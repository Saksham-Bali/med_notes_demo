'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getAgentBySlug, getCategoryColor, agents } from '@/lib/agents-data';
import StatusBadge from '@/components/StatusBadge';

const categoryColorMap: Record<string, { bg: string; text: string; border: string }> = {
  teal: { bg: 'bg-teal-400/10', text: 'text-teal-400', border: 'border-teal-400/30' },
  amber: { bg: 'bg-amber-400/10', text: 'text-amber-400', border: 'border-amber-400/30' },
  blue: { bg: 'bg-blue-400/10', text: 'text-blue-400', border: 'border-blue-400/30' },
  purple: { bg: 'bg-purple-400/10', text: 'text-purple-400', border: 'border-purple-400/30' },
};

export default function AgentDetailPage() {
  const params = useParams();
  const slug = params.slug as string;
  const agent = getAgentBySlug(slug);

  if (!agent) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white mb-4">Agent Not Found</h1>
          <p className="text-slate-400 mb-6">No agent matches the slug &quot;{slug}&quot;.</p>
          <Link href="/" className="text-teal-400 hover:text-teal-300">
            Back to Home
          </Link>
        </div>
      </div>
    );
  }

  const color = getCategoryColor(agent.category);
  const colors = categoryColorMap[color];

  const currentIndex = agents.findIndex((a) => a.slug === slug);
  const prevAgent = currentIndex > 0 ? agents[currentIndex - 1] : null;
  const nextAgent = currentIndex < agents.length - 1 ? agents[currentIndex + 1] : null;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link href="/" className="hover:text-slate-300 transition-colors">Home</Link>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-slate-300">Agent {agent.number}: {agent.fullName}</span>
      </div>

      {/* Header */}
      <div className={`${colors.bg} border ${colors.border} rounded-xl p-6`}>
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className={`text-sm font-mono font-bold ${colors.text}`}>
                Agent {agent.number}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${colors.bg} ${colors.text}`}>
                {agent.category}
              </span>
              <StatusBadge status={agent.status} />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white">{agent.fullName}</h1>
          </div>
          <div className="text-right">
            <span className="text-xs text-slate-500">Port</span>
            <div className="text-lg font-mono text-slate-300">:{agent.port}</div>
          </div>
        </div>
      </div>

      {/* Purpose */}
      <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Purpose</h2>
        <p className="text-slate-300 leading-relaxed">{agent.purpose}</p>
      </section>

      {/* Pipeline Position */}
      <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
          Pipeline Position
        </h2>
        <p className="text-slate-300 leading-relaxed mb-4">{agent.pipelinePosition}</p>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="bg-slate-800 border border-slate-600 rounded-lg px-4 py-2 text-sm text-slate-400">
            Input Data
          </div>
          <svg width="24" height="12" viewBox="0 0 24 12" fill="none">
            <path d="M0 6h20M16 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-slate-600" />
          </svg>
          <div className={`${colors.bg} border ${colors.border} rounded-lg px-4 py-2 text-sm ${colors.text} font-semibold`}>
            {agent.name}
          </div>
          <svg width="24" height="12" viewBox="0 0 24 12" fill="none">
            <path d="M0 6h20M16 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-slate-600" />
          </svg>
          <div className="bg-slate-800 border border-slate-600 rounded-lg px-4 py-2 text-sm text-slate-400">
            Output
          </div>
        </div>
      </section>

      {/* Prompting Strategy */}
      <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
          Prompting Strategy
        </h2>
        <p className="text-slate-300 leading-relaxed">{agent.promptStrategy}</p>
      </section>

      {/* Input / Output */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            Example Input
          </h2>
          <div className="bg-slate-950 rounded-lg p-4 overflow-x-auto">
            <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">{agent.exampleInput}</pre>
          </div>
          <div className="mt-3">
            <h3 className="text-xs text-slate-500 mb-2">Input Schema</h3>
            <div className="space-y-1">
              {Object.entries(agent.inputSchema).map(([key, val]) => (
                <div key={key} className="flex items-center gap-2 text-xs">
                  <code className="text-teal-400 font-mono">{key}</code>
                  <span className="text-slate-600">:</span>
                  <span className="text-slate-400">{String(val)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            Example Output
          </h2>
          <div className="bg-slate-950 rounded-lg p-4 overflow-x-auto">
            <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">{agent.exampleOutput}</pre>
          </div>
          <div className="mt-3">
            <h3 className="text-xs text-slate-500 mb-2">Output Schema</h3>
            <div className="space-y-1">
              {Object.entries(agent.outputSchema).map(([key, val]) => (
                <div key={key} className="flex items-center gap-2 text-xs">
                  <code className="text-teal-400 font-mono">{key}</code>
                  <span className="text-slate-600">:</span>
                  <span className="text-slate-400">{String(val)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      {/* Failure Modes */}
      <section className="bg-slate-900 border border-slate-700 rounded-xl p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
          Failure Modes & Safeguards
        </h2>
        <ul className="space-y-2">
          {agent.failureModes.map((mode, i) => (
            <li key={i} className="flex items-start gap-3 text-sm text-slate-300">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="mt-0.5 shrink-0 text-amber-400">
                <path d="M8 1l7 13H1L8 1z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                <path d="M8 6v3M8 11v1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
              {mode}
            </li>
          ))}
        </ul>
      </section>

      {/* Source */}
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-slate-500 shrink-0">
          <path d="M5 12l-3-3 3-3M11 4l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-xs text-slate-500">Source:</span>
        <code className="text-xs text-slate-300 font-mono">{agent.sourceLocation}</code>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4">
        {prevAgent ? (
          <Link
            href={`/agents/${prevAgent.slug}`}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M9 3L5 7l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {prevAgent.number} {prevAgent.fullName}
          </Link>
        ) : (
          <div />
        )}
        {nextAgent ? (
          <Link
            href={`/agents/${nextAgent.slug}`}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            {nextAgent.number} {nextAgent.fullName}
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}
