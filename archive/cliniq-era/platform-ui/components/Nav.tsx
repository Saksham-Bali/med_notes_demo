'use client';

import { useEffect, useRef, useState } from 'react';
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

    const check = () => {
      getHealth()
        .then(() => {
          if (!cancelled) setHealthy(true);
        })
        .catch(() => {
          if (!cancelled) setHealthy(false);
        });
    };

    check();
    const interval = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setAgentsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const linkClass = (href: string) => {
    const active = pathname === href || (href !== '/' && pathname.startsWith(href));
    return [
      'rounded-full px-3.5 py-2 text-sm tracking-[-0.01em]',
      active
        ? 'bg-black text-[#faf7f1] shadow-sm'
        : 'text-[rgba(17,17,17,0.66)] hover:text-black hover:bg-[rgba(17,17,17,0.05)]',
    ].join(' ');
  };

  return (
    <nav className="sticky top-0 z-50 border-b border-[rgba(17,17,17,0.08)] bg-[rgba(247,244,238,0.86)] backdrop-blur-xl">
      <div className="page-shell">
        <div className="flex h-16 items-center justify-between gap-6">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,17,17,0.12)] bg-white">
                <span className="font-display text-2xl leading-none text-black">C</span>
              </div>
              <div className="leading-none">
                <div className="font-display text-[1.55rem] text-black">ClinIQ</div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.45)]">
                  Review First
                </div>
              </div>
            </Link>

            <div className="hidden md:flex items-center gap-1 rounded-full border border-[rgba(17,17,17,0.08)] bg-white/70 p-1">
              <Link href="/" className={linkClass('/')}>Home</Link>
              <div className="relative" ref={dropdownRef}>
                <button onClick={() => setAgentsOpen((v) => !v)} className={`${linkClass('/agents')} flex items-center gap-1.5`}>
                  Agents
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className={agentsOpen ? 'rotate-180' : ''}>
                    <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                  </svg>
                </button>
                {agentsOpen && (
                  <div className="absolute left-0 top-full mt-2 w-72 rounded-[1.25rem] border border-[rgba(17,17,17,0.1)] bg-[rgba(255,255,255,0.94)] p-2 shadow-[0_24px_60px_rgba(17,17,17,0.12)]">
                    {agents.map((agent) => (
                      <Link
                        key={agent.slug}
                        href={`/agents/${agent.slug}`}
                        onClick={() => setAgentsOpen(false)}
                        className="flex items-center gap-3 rounded-2xl px-3 py-2.5 hover:bg-[rgba(17,17,17,0.04)]"
                      >
                        <span className="font-mono-ui text-[11px] text-[rgba(17,17,17,0.42)] w-5">{agent.number}</span>
                        <span className="text-sm text-black">{agent.fullName}</span>
                        <span className="ml-auto font-mono-ui text-[11px] text-[rgba(17,17,17,0.42)]">:{agent.port}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
              <Link href="/demo" className={linkClass('/demo')}>Demo</Link>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 rounded-full border border-[rgba(17,17,17,0.08)] bg-white/70 px-3 py-2">
              <span className={`h-2.5 w-2.5 rounded-full ${healthy === null ? 'bg-[rgba(17,17,17,0.28)]' : healthy ? 'bg-black' : 'bg-[rgba(17,17,17,0.48)]'}`} />
              <span className="font-mono-ui text-[10px] uppercase tracking-[0.18em] text-[rgba(17,17,17,0.48)]">
                {healthy === null ? 'Checking' : healthy ? 'Online' : 'Offline'}
              </span>
            </div>

            <button
              className="md:hidden flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,17,17,0.1)] bg-white/70 text-black"
              onClick={() => setMobileOpen((v) => !v)}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                {mobileOpen ? (
                  <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                ) : (
                  <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                )}
              </svg>
            </button>
          </div>
        </div>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t border-[rgba(17,17,17,0.08)] bg-[rgba(255,255,255,0.82)]">
          <div className="page-shell py-4 space-y-2">
            <Link href="/" className={`block ${linkClass('/')}`} onClick={() => setMobileOpen(false)}>Home</Link>
            <Link href="/demo" className={`block ${linkClass('/demo')}`} onClick={() => setMobileOpen(false)}>Demo</Link>
            <div className="pt-2">
              <p className="px-3 pb-2 font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">
                Agents
              </p>
              {agents.map((agent) => (
                <Link
                  key={agent.slug}
                  href={`/agents/${agent.slug}`}
                  className="block rounded-full px-3 py-2 text-sm text-[rgba(17,17,17,0.68)] hover:bg-[rgba(17,17,17,0.04)] hover:text-black"
                  onClick={() => setMobileOpen(false)}
                >
                  {agent.number} · {agent.fullName}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
