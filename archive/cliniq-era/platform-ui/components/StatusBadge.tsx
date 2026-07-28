'use client';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusConfig: Record<string, string> = {
  active: 'Active',
  resolved: 'Resolved',
  absent: 'Absent',
  pending: 'Pending',
  success: 'Success',
  error: 'Error',
  running: 'Running',
  completed: 'Completed',
  needs_review: 'Needs Review',
  pending_dependency: 'Pending',
  skipped: 'Skipped',
  healthy: 'Healthy',
  degraded: 'Degraded',
  unreachable: 'Unreachable',
  PASS: 'Pass',
  FAIL: 'Fail',
};

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const label = statusConfig[status] || status;
  const sizeClass = size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3 py-1.5 text-xs';

  return (
    <span className={`inline-flex items-center rounded-full border border-[rgba(17,17,17,0.12)] bg-white text-black uppercase tracking-[0.14em] ${sizeClass}`}>
      {label}
    </span>
  );
}
