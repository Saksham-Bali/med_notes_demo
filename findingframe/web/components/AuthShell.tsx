"use client";

import { IS_MOCK } from "@/lib/env";
import { ShieldCheck } from "lucide-react";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Brand / trust panel */}
      <div className="hidden lg:flex flex-col justify-between bg-ink text-white p-12">
        <div className="flex items-center gap-2">
          <span className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
            <ShieldCheck className="w-5 h-5" />
          </span>
          <span className="font-semibold tracking-tight text-lg">FindingFrame</span>
        </div>
        <div className="max-w-md">
          <h1 className="text-2xl font-semibold leading-snug">
            Audit-grade oncology radiology review.
          </h1>
          <p className="mt-4 text-white/70 leading-relaxed">
            Every fact traceable to its source sentence. RECIST 1.1 progression computed
            deterministically over clinician-confirmed lesion identity. Gate-failed evidence
            quarantined for mandatory review.
          </p>
          <ul className="mt-6 space-y-2 text-sm text-white/60">
            <li>· 100% source-linked — verbatim evidence on every finding</li>
            <li>· Human-confirmed track linking before any RECIST</li>
            <li>· Immutable runs · reproducibility manifest · hash-chained sign-off</li>
          </ul>
        </div>
        <p className="text-2xs text-white/40">
          Reviewer accelerator · human-in-the-loop · provenance-complete.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <span className="w-8 h-8 rounded-lg bg-accent text-white flex items-center justify-center">
              <ShieldCheck className="w-5 h-5" />
            </span>
            <span className="font-semibold tracking-tight text-lg text-ink">FindingFrame</span>
          </div>
          <h2 className="text-xl font-semibold text-ink">{title}</h2>
          <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>
          {IS_MOCK && (
            <div className="mt-4 rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-xs text-warn-ink">
              Running in <strong>mock mode</strong> — any email/password works and loads a demo
              patient. No backend required.
            </div>
          )}
          <div className="mt-6">{children}</div>
          <div className="mt-6 text-sm text-ink-muted">{footer}</div>
        </div>
      </div>
    </div>
  );
}
