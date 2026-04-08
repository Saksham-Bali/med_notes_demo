'use client';

const agentBoxes = [
  { name: 'OCR', port: 5001, color: 'teal' },
  { name: 'SOAP', port: 5002, color: 'teal' },
  { name: 'RAD', port: 5003, color: 'teal' },
  { name: 'VOI', port: 5004, color: 'teal' },
  { name: 'COUN', port: 5005, color: 'teal' },
  { name: 'FG', port: 5006, color: 'amber' },
  { name: 'DEPT', port: 5007, color: 'blue' },
  { name: 'SUMM', port: 5008, color: 'blue' },
  { name: 'QA', port: 5009, color: 'purple' },
  { name: 'TRANS', port: 5010, color: 'purple' },
];

const colorMap: Record<string, { bg: string; border: string; text: string }> = {
  teal: { bg: 'bg-teal-400/10', border: 'border-teal-400/40', text: 'text-teal-400' },
  amber: { bg: 'bg-amber-400/10', border: 'border-amber-400/40', text: 'text-amber-400' },
  blue: { bg: 'bg-blue-400/10', border: 'border-blue-400/40', text: 'text-blue-400' },
  purple: { bg: 'bg-purple-400/10', border: 'border-purple-400/40', text: 'text-purple-400' },
};

export default function ArchitectureDiagram() {
  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      {/* Frontend Layer */}
      <div className="border border-slate-600 rounded-xl p-4 bg-slate-800/30">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 rounded-full bg-teal-400" />
          <span className="text-sm font-semibold text-slate-200">Frontend</span>
          <span className="text-xs text-slate-500 font-mono ml-auto">Next.js 14</span>
        </div>
        <p className="text-xs text-slate-400 pl-4">
          Patient dashboard, workflow forms, human-in-the-loop review interface
        </p>
      </div>

      {/* Connector */}
      <div className="flex justify-center">
        <div className="w-px h-6 bg-slate-600" />
      </div>

      {/* Orchestrator Layer */}
      <div className="border border-slate-600 rounded-xl p-4 bg-slate-800/30">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-sm font-semibold text-slate-200">Orchestrator</span>
          <span className="text-xs text-slate-500 font-mono ml-auto">FastAPI :8000</span>
        </div>
        <div className="flex flex-wrap gap-3 pl-4">
          <span className="text-xs bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md">
            Workflow Engine
          </span>
          <span className="text-xs bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md">
            Agent Registry
          </span>
          <span className="text-xs bg-slate-700 text-slate-300 px-2.5 py-1 rounded-md">
            Error Handler
          </span>
        </div>
      </div>

      {/* Connectors */}
      <div className="flex justify-center items-center gap-1">
        <div className="flex-1 h-px bg-slate-700" />
        <div className="flex gap-1">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="w-px h-6 bg-slate-600" />
          ))}
        </div>
        <div className="flex-1 h-px bg-slate-700" />
      </div>

      {/* Agent Grid */}
      <div className="grid grid-cols-5 sm:grid-cols-5 gap-2 sm:gap-3">
        {agentBoxes.map((agent) => {
          const colors = colorMap[agent.color];
          return (
            <div
              key={agent.name}
              className={`${colors.bg} border ${colors.border} rounded-lg p-2 sm:p-3 text-center transition-all hover:scale-105`}
            >
              <div className={`text-xs sm:text-sm font-bold ${colors.text}`}>
                {agent.name}
              </div>
              <div className="text-[10px] sm:text-xs text-slate-500 font-mono mt-0.5">
                :{agent.port}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center justify-center gap-4 pt-2 text-xs text-slate-500">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded bg-teal-400/30 border border-teal-400/50" />
          <span>Input Agents</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded bg-amber-400/30 border border-amber-400/50" />
          <span>Core</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded bg-blue-400/30 border border-blue-400/50" />
          <span>Processing</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded bg-purple-400/30 border border-purple-400/50" />
          <span>Output</span>
        </div>
      </div>
    </div>
  );
}
