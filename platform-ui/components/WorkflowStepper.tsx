'use client';

interface StepInfo {
  name: string;
  status: 'pending' | 'running' | 'done' | 'error' | 'skipped';
}

interface WorkflowStepperProps {
  steps: StepInfo[];
}

export default function WorkflowStepper({ steps }: WorkflowStepperProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {steps.map((step, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                step.status === 'done'
                  ? 'bg-emerald-400/20 text-emerald-400'
                  : step.status === 'running'
                  ? 'bg-teal-400/20 text-teal-400 animate-pulse'
                  : step.status === 'error'
                  ? 'bg-rose-400/20 text-rose-400'
                  : step.status === 'skipped'
                  ? 'bg-slate-700 text-slate-500'
                  : 'bg-slate-800 text-slate-500'
              }`}
            >
              {step.status === 'done' ? (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3.5 7l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : step.status === 'running' ? (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="animate-spin">
                  <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="20" strokeDashoffset="5" />
                </svg>
              ) : step.status === 'error' ? (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M4.5 4.5l5 5M9.5 4.5l-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
              )}
            </div>
            <span
              className={`text-sm font-medium ${
                step.status === 'done'
                  ? 'text-emerald-400'
                  : step.status === 'running'
                  ? 'text-teal-400'
                  : step.status === 'error'
                  ? 'text-rose-400'
                  : 'text-slate-500'
              }`}
            >
              {step.name}
            </span>
          </div>

          {i < steps.length - 1 && (
            <div className={`w-8 h-px ${step.status === 'done' ? 'bg-emerald-400/40' : 'bg-slate-700'}`} />
          )}
        </div>
      ))}
    </div>
  );
}
