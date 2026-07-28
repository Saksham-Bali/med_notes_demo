'use client';

const agentBoxes = [
  { name: 'OCR', port: 5001 },
  { name: 'SOAP', port: 5002 },
  { name: 'RAD', port: 5003 },
  { name: 'VOICE', port: 5004 },
  { name: 'COUN', port: 5005 },
  { name: 'GRAPH', port: 5006 },
  { name: 'MERGE', port: 5007 },
  { name: 'SUMM', port: 5008 },
  { name: 'QA', port: 5009 },
  { name: 'TRANS', port: 5010 },
];

export default function ArchitectureDiagram() {
  return (
    <div className="space-y-6">
      <div className="rounded-[1.25rem] border border-[rgba(17,17,17,0.1)] bg-white p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">
              Local Shell
            </div>
            <div className="mt-1 text-lg font-semibold text-black">Next.js interface</div>
          </div>
          <div className="font-mono-ui text-xs text-[rgba(17,17,17,0.46)]">:3000</div>
        </div>
      </div>

      <div className="mx-auto h-8 w-px bg-[rgba(17,17,17,0.14)]" />

      <div className="rounded-[1.25rem] border border-[rgba(17,17,17,0.1)] bg-white p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="font-mono-ui text-[10px] uppercase tracking-[0.24em] text-[rgba(17,17,17,0.42)]">
              Coordination Layer
            </div>
            <div className="mt-1 text-lg font-semibold text-black">FastAPI orchestrator</div>
          </div>
          <div className="font-mono-ui text-xs text-[rgba(17,17,17,0.46)]">:8000</div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {['Registry', 'Preview / Confirm', 'Health routing', 'Workflow state'].map((item) => (
            <span key={item} className="rounded-full bg-[rgba(17,17,17,0.05)] px-3 py-1 text-xs text-[rgba(17,17,17,0.52)]">
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="relative pt-4">
        <div className="absolute left-0 right-0 top-0 h-px bg-[rgba(17,17,17,0.12)]" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {agentBoxes.map((agent) => (
            <div key={agent.name} className="rounded-[1.1rem] border border-[rgba(17,17,17,0.1)] bg-white px-4 py-4 text-center">
              <div className="text-sm font-semibold tracking-[0.08em] text-black">{agent.name}</div>
              <div className="mt-1 font-mono-ui text-[11px] text-[rgba(17,17,17,0.42)]">:{agent.port}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
