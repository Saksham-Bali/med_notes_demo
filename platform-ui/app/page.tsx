'use client';

import Link from 'next/link';
import ArchitectureDiagram from '@/components/ArchitectureDiagram';
import AgentCard from '@/components/AgentCard';
import { agents } from '@/lib/agents-data';

const howItWorks = [
  {
    step: '01',
    title: 'Data Input',
    description:
      'Upload radiology reports, handwritten notes, counselling recordings, or department notes.',
    color: 'teal',
  },
  {
    step: '02',
    title: 'AI Processing',
    description:
      '10 specialized agents extract, ground, and validate clinical entities.',
    color: 'blue',
  },
  {
    step: '03',
    title: 'Human Review',
    description:
      'Clinicians review each extracted entity before it enters the patient record.',
    color: 'amber',
  },
  {
    step: '04',
    title: 'Living Record',
    description:
      'The Fact Graph builds a longitudinal, ontology-grounded patient timeline.',
    color: 'purple',
  },
];

const stepColors: Record<string, { border: string; num: string; dot: string }> = {
  teal: { border: 'border-teal-400/30', num: 'text-teal-400', dot: 'bg-teal-400' },
  blue: { border: 'border-blue-400/30', num: 'text-blue-400', dot: 'bg-blue-400' },
  amber: { border: 'border-amber-400/30', num: 'text-amber-400', dot: 'bg-amber-400' },
  purple: { border: 'border-purple-400/30', num: 'text-purple-400', dot: 'bg-purple-400' },
};

const techStack = [
  'FastAPI',
  'Next.js',
  'Azure OpenAI',
  'Docker',
  'RadLex',
  'SQLite',
  'Sarvam AI',
  'Tailwind CSS',
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-teal-400/5 via-transparent to-transparent" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16 relative">
          <div className="max-w-3xl">
            <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight">
              Clinical Intelligence
              <br />
              <span className="text-teal-400">Platform</span>
            </h1>
            <p className="mt-4 text-lg text-slate-400 leading-relaxed max-w-2xl">
              AI-powered clinical document processing with human-in-the-loop verification.
              Extract, ground, and validate clinical entities from radiology reports,
              handwritten notes, and counselling sessions.
            </p>
            <div className="mt-8 flex items-center gap-4">
              <Link
                href="/demo"
                className="inline-flex items-center gap-2 bg-teal-500 hover:bg-teal-400 text-white font-semibold px-6 py-3 rounded-lg transition-colors"
              >
                Try the Demo
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
              <Link
                href="/agents/radiology-extractor"
                className="inline-flex items-center gap-2 text-slate-300 hover:text-white font-medium px-6 py-3 rounded-lg border border-slate-700 hover:border-slate-500 transition-colors"
              >
                Explore Agents
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-6">
          How It Works
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {howItWorks.map((item) => {
            const colors = stepColors[item.color];
            return (
              <div
                key={item.step}
                className={`bg-slate-900 border ${colors.border} rounded-xl p-5 relative`}
              >
                <div className="flex items-center gap-2 mb-3">
                  <div className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
                  <span className={`text-xs font-mono font-bold ${colors.num}`}>
                    Step {item.step}
                  </span>
                </div>
                <h3 className="text-base font-semibold text-white mb-2">{item.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{item.description}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Architecture Diagram */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-6">
          System Architecture
        </h2>
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 sm:p-8">
          <ArchitectureDiagram />
        </div>
      </section>

      {/* Agent Grid */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-6">
          10 Specialized Agents
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard key={agent.slug} agent={agent} />
          ))}
        </div>
      </section>

      {/* Technology Stack */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 pb-24">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-6">
          Technology Stack
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {techStack.map((tech) => (
            <span
              key={tech}
              className="bg-slate-900 border border-slate-700 text-slate-300 text-sm px-4 py-2 rounded-lg"
            >
              {tech}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
