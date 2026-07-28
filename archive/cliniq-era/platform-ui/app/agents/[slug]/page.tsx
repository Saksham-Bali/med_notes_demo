'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import StatusBadge from '@/components/StatusBadge';
import { agents, getAgentBySlug } from '@/lib/agents-data';

export default function AgentDetailPage() {
  const params = useParams();
  const slug = params.slug as string;
  const agent = getAgentBySlug(slug);

  if (!agent) {
    return (
      <div className="page-shell py-16">
        <div className="surface p-10 text-center">
          <h1 className="font-display text-5xl text-black">Agent not found</h1>
          <p className="mt-4 text-[rgba(17,17,17,0.6)]">No agent matches “{slug}”.</p>
          <Link href="/" className="btn-secondary mt-6">Back Home</Link>
        </div>
      </div>
    );
  }

  const index = agents.findIndex((item) => item.slug === slug);
  const previous = index > 0 ? agents[index - 1] : null;
  const next = index < agents.length - 1 ? agents[index + 1] : null;

  return (
    <div className="page-shell py-10 space-y-6">
      <div className="flex items-center gap-2 text-sm text-[rgba(17,17,17,0.46)]">
        <Link href="/" className="hover:text-black">Home</Link>
        <span>·</span>
        <span className="text-black">{agent.fullName}</span>
      </div>

      <div className="surface p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">
              Agent {agent.number}
            </div>
            <h1 className="mt-3 font-display text-5xl text-black sm:text-6xl">{agent.fullName}</h1>
          </div>
          <div className="space-y-2">
            <StatusBadge status={agent.status} size="md" />
            <div className="rounded-full border border-[rgba(17,17,17,0.1)] bg-white px-3 py-1 font-mono-ui text-xs text-[rgba(17,17,17,0.52)]">
              Port :{agent.port}
            </div>
          </div>
        </div>
        <p className="mt-5 max-w-3xl text-base leading-7 text-[rgba(17,17,17,0.62)]">{agent.purpose}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="surface p-6">
          <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.42)]">Pipeline Position</div>
          <p className="mt-3 text-sm leading-6 text-[rgba(17,17,17,0.64)]">{agent.pipelinePosition}</p>
          <div className="mt-4 rounded-2xl bg-white p-4 text-sm text-black">{agent.promptStrategy}</div>
        </section>

        <section className="surface p-6">
          <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.42)]">Failure Modes</div>
          <ul className="mt-3 space-y-3 text-sm leading-6 text-[rgba(17,17,17,0.64)]">
            {agent.failureModes.map((mode, idx) => (
              <li key={idx} className="border-l border-[rgba(17,17,17,0.12)] pl-4">{mode}</li>
            ))}
          </ul>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="surface p-6">
          <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.42)]">Example Input</div>
          <pre className="mt-4 overflow-x-auto rounded-2xl bg-white p-4 text-xs leading-6 text-[rgba(17,17,17,0.76)]">{agent.exampleInput}</pre>
          <div className="mt-4 space-y-2">
            {Object.entries(agent.inputSchema).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-xs">
                <code className="font-mono-ui text-black">{key}</code>
                <span className="text-[rgba(17,17,17,0.42)]">:</span>
                <span className="text-[rgba(17,17,17,0.58)]">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="surface p-6">
          <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.42)]">Example Output</div>
          <pre className="mt-4 overflow-x-auto rounded-2xl bg-white p-4 text-xs leading-6 text-[rgba(17,17,17,0.76)]">{agent.exampleOutput}</pre>
          <div className="mt-4 space-y-2">
            {Object.entries(agent.outputSchema).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-xs">
                <code className="font-mono-ui text-black">{key}</code>
                <span className="text-[rgba(17,17,17,0.42)]">:</span>
                <span className="text-[rgba(17,17,17,0.58)]">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="surface p-5">
        <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.42)]">Source</div>
        <code className="mt-2 block text-sm text-black">{agent.sourceLocation}</code>
      </div>

      <div className="flex items-center justify-between gap-4">
        {previous ? (
          <Link href={`/agents/${previous.slug}`} className="btn-secondary">
            ← {previous.fullName}
          </Link>
        ) : <span />}
        {next ? (
          <Link href={`/agents/${next.slug}`} className="btn-secondary">
            {next.fullName} →
          </Link>
        ) : <span />}
      </div>
    </div>
  );
}
