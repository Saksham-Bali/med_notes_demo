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
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((step, index) => {
        const active = step.status === 'running' || step.status === 'done';
        return (
          <div key={index} className="flex items-center gap-2">
            <div className={`flex items-center gap-2 rounded-full border px-3 py-2 ${
              active
                ? 'border-black bg-black text-[#faf7f1]'
                : 'border-[rgba(17,17,17,0.12)] bg-white text-[rgba(17,17,17,0.5)]'
            }`}>
              <div className={`flex h-5 w-5 items-center justify-center rounded-full ${
                active ? 'bg-white text-black' : 'bg-[rgba(17,17,17,0.06)] text-[rgba(17,17,17,0.5)]'
              }`}>
                {step.status === 'done' ? (
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2.5 6l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : step.status === 'running' ? (
                  <div className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                ) : step.status === 'error' ? (
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M3 3l6 6M9 3L3 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                ) : (
                  <span className="font-mono-ui text-[10px]">{index + 1}</span>
                )}
              </div>
              <span className="text-sm">{step.name}</span>
            </div>
            {index < steps.length - 1 && <div className="h-px w-6 bg-[rgba(17,17,17,0.12)]" />}
          </div>
        );
      })}
    </div>
  );
}
