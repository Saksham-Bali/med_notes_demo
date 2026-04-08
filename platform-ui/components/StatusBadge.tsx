'use client';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-emerald-400/10', text: 'text-emerald-400', label: 'Active' },
  resolved: { bg: 'bg-slate-400/10', text: 'text-slate-400', label: 'Resolved' },
  absent: { bg: 'bg-rose-400/10', text: 'text-rose-400', label: 'Absent' },
  pending: { bg: 'bg-amber-400/10', text: 'text-amber-400', label: 'Pending' },
  success: { bg: 'bg-emerald-400/10', text: 'text-emerald-400', label: 'Success' },
  error: { bg: 'bg-rose-400/10', text: 'text-rose-400', label: 'Error' },
  running: { bg: 'bg-blue-400/10', text: 'text-blue-400', label: 'Running' },
  completed: { bg: 'bg-emerald-400/10', text: 'text-emerald-400', label: 'Completed' },
  needs_review: { bg: 'bg-amber-400/10', text: 'text-amber-400', label: 'Needs Review' },
  pending_dependency: { bg: 'bg-slate-400/10', text: 'text-slate-400', label: 'Pending' },
  skipped: { bg: 'bg-slate-600/20', text: 'text-slate-500', label: 'Skipped' },
  healthy: { bg: 'bg-emerald-400/10', text: 'text-emerald-400', label: 'Healthy' },
  degraded: { bg: 'bg-amber-400/10', text: 'text-amber-400', label: 'Degraded' },
  unreachable: { bg: 'bg-rose-400/10', text: 'text-rose-400', label: 'Unreachable' },
  PASS: { bg: 'bg-emerald-400/10', text: 'text-emerald-400', label: 'PASS' },
  FAIL: { bg: 'bg-rose-400/10', text: 'text-rose-400', label: 'FAIL' },
};

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    bg: 'bg-slate-400/10',
    text: 'text-slate-400',
    label: status,
  };

  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';

  return (
    <span className={`inline-flex items-center rounded-full font-medium ${config.bg} ${config.text} ${sizeClass}`}>
      {config.label}
    </span>
  );
}
