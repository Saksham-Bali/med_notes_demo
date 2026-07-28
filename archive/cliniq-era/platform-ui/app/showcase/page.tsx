'use client';

export default function ShowcasePage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="page-shell py-16 sm:py-24">
        <span className="eyebrow">The Problem</span>
        <h1 className="display-title mt-6 max-w-3xl text-[3rem] leading-none text-black sm:text-[4.5rem]">
          Same lesion.<br />Different words.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-[rgba(17,17,17,0.62)]">
          Radiology reports describe the same finding in wildly different language.
          &ldquo;Right upper lobe mass&rdquo; becomes &ldquo;RUL lesion.&rdquo;
          &ldquo;3.2 centimetres&rdquo; becomes &ldquo;3.8.&rdquo;
          No existing automated system reliably says: <em>these are the same entity</em>.
          And nobody is tracking the fact that it grew 18%.
        </p>
      </section>

      {/* The two reports */}
      <section className="page-shell py-8">
        <div className="grid gap-8 lg:grid-cols-2">
          {/* Report 1 */}
          <div className="surface p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,17,17,0.1)] bg-white">
                <span className="font-mono-ui text-xs text-[rgba(17,17,17,0.5)]">01</span>
              </div>
              <div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">January 2024</div>
                <div className="text-sm text-[rgba(17,17,17,0.52)]">CT Chest with Contrast</div>
              </div>
            </div>

            <div className="mt-6 rounded-2xl bg-[rgba(247,244,238,0.6)] border border-[rgba(17,17,17,0.06)] p-5">
              <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.36)] mb-3">Original Report</div>
              <div className="space-y-3 text-sm leading-7 text-[rgba(17,17,17,0.72)]">
                <p>
                  A <mark className="bg-[#111] text-[#faf7f1] px-1 rounded">3.2 cm spiculated mass</mark> is identified
                  in the <mark className="bg-[#111] text-[#faf7f1] px-1 rounded">right upper lobe</mark>.
                  The lesion demonstrates irregular margins and pleural tagging.
                  No evidence of mediastinal or hilar lymphadenopathy.
                </p>
                <p>
                  The remainder of the lungs are clear. No pleural effusion.
                  Cardiac silhouette is normal.
                </p>
              </div>
            </div>

            <div className="mt-4 rounded-2xl bg-white border border-[rgba(17,17,17,0.08)] p-5">
              <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.36)] mb-3">What the System Extracts</div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm font-semibold text-black">Right Upper Lobe Mass</span>
                <span className="font-mono-ui text-xs text-[rgba(17,17,17,0.48)]">RID3874</span>
              </div>
              <div className="flex items-center gap-4 mt-1 text-xs text-[rgba(17,17,17,0.52)]">
                <span>Lung</span>
                <span className="w-px h-3 bg-[rgba(17,17,17,0.12)]" />
                <span>CT Chest</span>
                <span className="w-px h-3 bg-[rgba(17,17,17,0.12)]" />
                <span>3.2 cm</span>
              </div>
            </div>
          </div>

          {/* Report 2 */}
          <div className="surface p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(17,17,17,0.1)] bg-white">
                <span className="font-mono-ui text-xs text-[rgba(17,17,17,0.5)]">02</span>
              </div>
              <div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">September 2024</div>
                <div className="text-sm text-[rgba(17,17,17,0.52)]">CT Chest with Contrast</div>
                <div className="text-xs text-[rgba(17,17,17,0.38)]">+8 months</div>
              </div>
            </div>

            <div className="mt-6 rounded-2xl bg-[rgba(247,244,238,0.6)] border border-[rgba(17,17,17,0.06)] p-5">
              <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.36)] mb-3">Original Report</div>
              <div className="space-y-3 text-sm leading-7 text-[rgba(17,17,17,0.72)]">
                <p>
                  The previously noted <mark className="bg-[#111] text-[#faf7f1] px-1 rounded">RUL lesion</mark> is
                  now <mark className="bg-[#111] text-[#faf7f1] px-1 rounded">3.8 cm</mark> in maximum diameter,
                  representing interval increase from prior study.
                  Persistent irregular margins with continued pleural tagging.
                </p>
                <p>
                  No new nodules identified. Remainder of the study is unchanged.
                </p>
              </div>
            </div>

            <div className="mt-4 rounded-2xl bg-white border border-[rgba(17,17,17,0.08)] p-5">
              <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.36)] mb-3">What the System Extracts</div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm font-semibold text-black">Right Upper Lobe Mass</span>
                <span className="font-mono-ui text-xs text-[rgba(17,17,17,0.48)]">RID3874</span>
              </div>
              <div className="flex items-center gap-4 mt-1 text-xs text-[rgba(17,17,17,0.52)]">
                <span>Lung</span>
                <span className="w-px h-3 bg-[rgba(17,17,17,0.12)]" />
                <span>CT Chest</span>
                <span className="w-px h-3 bg-[rgba(17,17,17,0.12)]" />
                <span>3.8 cm</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* The alignment — same entity */}
      <section className="page-shell py-16">
        <div className="flex flex-col items-center text-center">
          <span className="eyebrow">Entity Resolution</span>
          <h2 className="mt-5 font-display text-[2.5rem] sm:text-[3.5rem] leading-none text-black">
            The system knows they&rsquo;re the same.
          </h2>
          <p className="mt-4 max-w-xl text-base leading-7 text-[rgba(17,17,17,0.58)]">
            &ldquo;Right upper lobe mass&rdquo; and &ldquo;RUL lesion&rdquo; are matched
            via RadLex ontology grounding, anatomical co-location, and measurement proximity.
          </p>
        </div>

        <div className="mt-10 max-w-xl mx-auto">
          <div className="surface p-6">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#111]">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M4 10l4 4 8-8" stroke="#faf7f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <div className="text-sm font-semibold text-black">Entity Matched: Right Upper Lobe Mass</div>
                <div className="text-xs text-[rgba(17,17,17,0.48)] mt-1">RadLex RID3874 &middot; Lung &middot; Chest</div>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-[rgba(17,17,17,0.03)] p-3 text-center">
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.4)]">Jan 2024</div>
                <div className="mt-1 text-sm text-[rgba(17,17,17,0.62)]">&ldquo;right upper lobe mass&rdquo;</div>
                <div className="mt-1 font-mono-ui text-lg font-semibold text-black">3.2 cm</div>
              </div>
              <div className="rounded-xl bg-[rgba(17,17,17,0.03)] p-3 text-center">
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.4)]">Sep 2024</div>
                <div className="mt-1 text-sm text-[rgba(17,17,17,0.62)]">&ldquo;RUL lesion&rdquo;</div>
                <div className="mt-1 font-mono-ui text-lg font-semibold text-black">3.8 cm</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* The growth */}
      <section className="page-shell py-8 pb-16">
        <div className="flex flex-col items-center text-center">
          <span className="eyebrow">Temporal Tracking</span>
          <h2 className="mt-5 font-display text-[2.5rem] sm:text-[3.5rem] leading-none text-black">
            It grew 18%.
          </h2>
          <p className="mt-4 max-w-xl text-base leading-7 text-[rgba(17,17,17,0.58)]">
            The fact graph doesn&rsquo;t just store snapshots. It tracks every measurement
            on a timeline, computes change, and flags progression.
          </p>
        </div>

        <div className="mt-10 max-w-2xl mx-auto space-y-6">
          {/* Measurement trajectory */}
          <div className="surface p-6 sm:p-8">
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.4)] mb-6">Measurement Trajectory</div>

            <div className="flex items-end justify-between px-2">
              <div className="flex flex-col items-center gap-2">
                <div className="font-mono-ui text-lg font-semibold text-black">3.2 cm</div>
                <div className="relative">
                  <div className="w-16 rounded-t-full bg-[rgba(17,17,17,0.12)]" style={{ height: '64px' }} />
                  <div className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.4)]">Jan 2024</div>
                </div>
              </div>

              <div className="flex-1 relative mx-2" style={{ height: '64px' }}>
                <svg width="100%" height="64" className="absolute bottom-0">
                  <line x1="0" y1="48" x2="100%" y2="12" stroke="rgba(17,17,17,0.18)" strokeWidth="1.5" strokeDasharray="4 4" />
                </svg>
              </div>

              <div className="flex flex-col items-center gap-2">
                <div className="font-mono-ui text-2xl font-bold text-black">3.8 cm</div>
                <div className="relative">
                  <div className="w-16 rounded-t-full bg-[#111]" style={{ height: '76px' }} />
                  <div className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.4)]">Sep 2024</div>
                </div>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-center gap-4">
              <div className="rounded-full bg-[rgba(17,17,17,0.05)] px-4 py-2 text-center">
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(17,17,17,0.4)]">Change</div>
                <div className="mt-1 font-mono-ui text-lg font-semibold text-black">+0.6 cm</div>
              </div>
              <div className="rounded-full bg-[#111] px-4 py-2 text-center">
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.2em] text-[rgba(250,247,241,0.6)]">Growth</div>
                <div className="mt-1 font-mono-ui text-2xl font-bold text-[#faf7f1]">+18%</div>
              </div>
            </div>
          </div>

          {/* What this means */}
          <div className="surface p-6">
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.38)]">Why It Matters</div>
                <p className="mt-2 text-sm leading-6 text-[rgba(17,17,17,0.6)]">
                  18% growth over 8 months meets RECIST 1.1 criteria for progressive disease.
                  A radiologist reading the second report in isolation may not have the prior
                  measurement at their fingertips.
                </p>
              </div>
              <div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.38)]">What the System Did</div>
                <p className="mt-2 text-sm leading-6 text-[rgba(17,17,17,0.6)]">
                  The Radiology Extractor grounded both mentions to the same RadLex entity
                  (RID3874). The Fact Graph Engine detected the interval increase and flagged
                  it as WORSENED.
                </p>
              </div>
              <div>
                <div className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-[rgba(17,17,17,0.38)]">Without This System</div>
                <p className="mt-2 text-sm leading-6 text-[rgba(17,17,17,0.6)]">
                  A clinician must manually compare two reports written in different language,
                  calculate growth mentally, and check RECIST criteria — all under time pressure.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <section className="page-shell pb-24 pt-4 text-center">
        <div className="surface p-8 max-w-xl mx-auto">
          <div className="font-display text-3xl text-black">Review before belief.</div>
          <p className="mt-3 text-sm leading-6 text-[rgba(17,17,17,0.56)]">
            Every entity the system proposes must be confirmed by a clinician.
            The automation amplifies judgment — it doesn&rsquo;t replace it.
          </p>
          <a
            href="/demo"
            className="btn-primary mt-6 inline-flex"
          >
            Try the Demo
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>
        </div>
      </section>
    </div>
  );
}
