'use client';

import Link from 'next/link';
import AgentCard from '@/components/AgentCard';
import ArchitectureDiagram from '@/components/ArchitectureDiagram';
import { agents } from '@/lib/agents-data';

const principles = [
  {
    id: '01',
    title: 'Quiet Intake',
    copy: 'Reports, scans, notes, and conversations enter through a single restrained workflow.',
  },
  {
    id: '02',
    title: 'Structured Judgment',
    copy: 'Specialized services extract, ground, compare, and validate without hiding uncertainty.',
  },
  {
    id: '03',
    title: 'Human Authority',
    copy: 'Nothing important enters the record until a clinician reviews and confirms it.',
  },
  {
    id: '04',
    title: 'Living Memory',
    copy: 'The fact graph turns fragmented documents into longitudinal patient context.',
  },
];

const techStack = ['FastAPI', 'Next.js', 'Azure OpenAI', 'Sarvam AI', 'SQLite', 'RadLex', 'Review Workflows', 'Fact Graph'];

export default function HomePage() {
  return (
    <div className="paper-grid">
      <section className="page-shell relative overflow-hidden py-16 sm:py-24">
        <div className="grid gap-12 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <div>
            <span className="eyebrow">Clinical Intelligence Platform</span>
            <h1 className="display-title mt-6 max-w-4xl text-[3.6rem] leading-none text-black sm:text-[5.2rem]">
              Minimal surface.
              <br />
              Maximal clinical traceability.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-[rgba(17,17,17,0.66)] sm:text-lg">
              ClinIQ is a review-first workspace for document extraction, longitudinal reasoning,
              and discharge-ready outputs. The interface is deliberately quiet so the medical signal
              stays louder than the software.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href="/demo" className="btn-primary">
                Open Demo
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
              <Link href="/agents/radiology-extractor" className="btn-secondary">
                Inspect Agents
              </Link>
            </div>
          </div>

          <div className="surface p-6 sm:p-8">
            <div className="flex items-center justify-between border-b border-[rgba(17,17,17,0.08)] pb-4">
              <div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.46)]">
                  Operating Premise
                </div>
                <div className="mt-2 font-display text-3xl text-black">Review before belief.</div>
              </div>
              <div className="h-12 w-12 rounded-full border border-[rgba(17,17,17,0.12)] bg-white flex items-center justify-center">
                <span className="font-mono-ui text-xs text-[rgba(17,17,17,0.56)]">10</span>
              </div>
            </div>
            <div className="mt-5 space-y-4 text-sm leading-6 text-[rgba(17,17,17,0.66)]">
              <p>The system is opinionated about confirmation, provenance, and reversibility.</p>
              <p>Every workflow is designed to surface uncertainty instead of smoothing it over.</p>
              <p>That is the personality of the product: calm, strict, and legible.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="page-shell py-6 sm:py-10">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {principles.map((item) => (
            <div key={item.id} className="surface-muted p-6">
              <div className="font-mono-ui text-[11px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.4)]">
                {item.id}
              </div>
              <h2 className="mt-4 text-xl font-semibold text-black">{item.title}</h2>
              <p className="mt-2 text-sm leading-6 text-[rgba(17,17,17,0.64)]">{item.copy}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="page-shell py-12">
        <div className="grid gap-8 lg:grid-cols-[0.34fr_0.66fr] lg:items-start">
          <div>
            <span className="eyebrow">System Map</span>
            <h2 className="mt-5 font-display text-5xl text-black">A thin interface over a dense backend.</h2>
            <p className="mt-4 text-base leading-7 text-[rgba(17,17,17,0.64)]">
              A local Next.js shell sits in front of the orchestrator, which in turn coordinates ten
              specialized services and a persistent fact graph.
            </p>
          </div>
          <div className="surface p-6 sm:p-8">
            <ArchitectureDiagram />
          </div>
        </div>
      </section>

      <section className="page-shell py-12">
        <div className="flex items-end justify-between gap-6 flex-wrap">
          <div>
            <span className="eyebrow">Agent Index</span>
            <h2 className="mt-5 font-display text-5xl text-black">Ten specialists, one record.</h2>
          </div>
          <p className="max-w-xl text-sm leading-6 text-[rgba(17,17,17,0.58)]">
            The stack stays modular underneath, but the interface reads like one instrument rather than ten separate tools.
          </p>
        </div>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard key={agent.slug} agent={agent} />
          ))}
        </div>
      </section>

      <section className="page-shell py-12 pb-24">
        <div className="surface p-8 sm:p-10">
          <div className="grid gap-8 lg:grid-cols-[0.45fr_0.55fr]">
            <div>
              <span className="eyebrow">Stack</span>
              <h2 className="mt-5 font-display text-5xl text-black">Built for clinical review, not dashboard theatre.</h2>
            </div>
            <div className="flex flex-wrap content-start gap-3">
              {techStack.map((tech) => (
                <span
                  key={tech}
                  className="rounded-full border border-[rgba(17,17,17,0.12)] bg-white px-4 py-2 text-sm text-[rgba(17,17,17,0.72)]"
                >
                  {tech}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
