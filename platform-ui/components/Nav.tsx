'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { agents } from '@/lib/agents-data';
import { getHealth } from '@/lib/api';

export default function Nav() {
  const pathname = usePathname();
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [agentsOpen, setAgentsOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then(() => {
        if (!cancelled) setHealthy(true);
      })
      .catch(() => {
        if (!cancelled) setHealthy(false);
      });
    const interval = setInterval(() => {
      getHealth()
        .then(() => setHealthy(true))
        .catch(() => setHealthy(false));
    }, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setAgentsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const linkClass = (href: string) => {
    const active = pathname === href || (href !== '/' && pathname.startsWith(href));
    return `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      active ? 'text-teal-400 bg-slate-800' : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
    }`;
  };

  return (
    <nav className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="text-teal-400">
                <rect x="2" y="2" width="24" height="24" rx="6" stroke="currentColor" strokeWidth="2" />
                <path d="M9 14h10M14 9v10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span className="text-xl font-bold text-white">
                Clin<span className="text-teal-400">IQ</span>
              </span>
            </Link>

            <div className="hidden md:flex items-center gap-1">
              <Link href="/" className={linkClass('/')}>
                Home
              </Link>

              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setAgentsOpen(!agentsOpen)}
                  className={`${linkClass('/agents')} flex items-center gap-1`}
                >
                  Agents
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    fill="none"
                    className={`transition-transform ${agentsOpen ? 'rotate-180' : ''}`}
                  >
                    <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>

                {agentsOpen && (
                  <div className="absolute top-full left-0 mt-1 w-72 bg-slate-900 border border-slate-700 rounded-lg shadow-xl py-2 max-h-[70vh] overflow-y-auto">
                    {agents.map((agent) => (
                      <Link
                        key={agent.slug}
                        href={`/agents/${agent.slug}`}
                        onClick={() => setAgentsOpen(false)}
                        className="flex items-center gap-3 px-4 py-2.5 hover:bg-slate-800 transition-colors"
                      >
                        <span className="text-xs font-mono text-slate-500 w-5">{agent.number}</span>
                        <span className="text-sm text-slate-200">{agent.fullName}</span>
                        <span className="text-xs text-slate-500 ml-auto">:{agent.port}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>

              <Link href="/demo" className={linkClass('/demo')}>
                Demo
              </Link>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthy === null ? 'bg-slate-600' : healthy ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              <span className="hidden sm:inline">
                {healthy === null ? 'Checking...' : healthy ? 'Orchestrator Online' : 'Orchestrator Offline'}
              </span>
            </div>

            <button
              className="md:hidden p-2 text-slate-400 hover:text-white"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                {mobileOpen ? (
                  <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                ) : (
                  <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                )}
              </svg>
            </button>
          </div>
        </div>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t border-slate-800 bg-slate-950 px-4 py-3 space-y-1">
          <Link href="/" className={`block ${linkClass('/')}`} onClick={() => setMobileOpen(false)}>
            Home
          </Link>
          <Link href="/demo" className={`block ${linkClass('/demo')}`} onClick={() => setMobileOpen(false)}>
            Demo
          </Link>
          <div className="pt-2 border-t border-slate-800 mt-2">
            <p className="text-xs text-slate-500 px-3 py-1 uppercase tracking-wider">Agents</p>
            {agents.map((agent) => (
              <Link
                key={agent.slug}
                href={`/agents/${agent.slug}`}
                className="block px-3 py-2 text-sm text-slate-300 hover:text-white"
                onClick={() => setMobileOpen(false)}
              >
                {agent.number} - {agent.fullName}
              </Link>
            ))}
          </div>
        </div>
      )}
    </nav>
  );
}
