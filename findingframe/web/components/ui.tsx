"use client";

import { cx } from "@/lib/format";
import { Loader2 } from "lucide-react";
import Link from "next/link";

// ---- Button ---------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
type ButtonSize = "sm" | "md";

const btnBase =
  "inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap";

const btnVariants: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-ink shadow-sm",
  secondary: "bg-paper text-ink border border-line-strong hover:bg-paper-soft",
  ghost: "text-ink-soft hover:bg-paper-sunk",
  danger: "bg-danger text-white hover:bg-danger-ink shadow-sm",
  subtle: "bg-accent-soft text-accent-ink hover:bg-accent/15",
};

const btnSizes: Record<ButtonSize, string> = {
  sm: "text-xs px-2.5 py-1.5",
  md: "text-sm px-3.5 py-2",
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      className={cx(btnBase, btnVariants[variant], btnSizes[size], className)}
      {...props}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "primary",
  size = "md",
  className,
  children,
  href,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: React.ReactNode;
  href: string;
}) {
  return (
    <Link href={href} className={cx(btnBase, btnVariants[variant], btnSizes[size], className)}>
      {children}
    </Link>
  );
}

// ---- Card -----------------------------------------------------------------

export function Card({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cx("bg-paper rounded-xl border border-line shadow-card", className)}>
      {children}
    </div>
  );
}

// ---- Badge ----------------------------------------------------------------

export type Tone = "danger" | "warn" | "good" | "info" | "quiet" | "neutral";

const toneClasses: Record<Tone, string> = {
  danger: "bg-danger-soft text-danger-ink border-danger/20",
  warn: "bg-warn-soft text-warn-ink border-warn/20",
  good: "bg-good-soft text-good-ink border-good/20",
  info: "bg-info-soft text-info-ink border-info/20",
  quiet: "bg-quiet-soft text-quiet-ink border-quiet/20",
  neutral: "bg-paper-sunk text-ink-soft border-line-strong",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide",
        toneClasses[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

// ---- Spinner / states -----------------------------------------------------

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("w-5 h-5 animate-spin text-ink-faint", className)} />;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted py-10 justify-center">
      <Spinner /> {label}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="text-center py-12 px-6">
      {icon && <div className="mx-auto mb-3 text-ink-faint flex justify-center">{icon}</div>}
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description && <p className="mt-1 text-sm text-ink-muted max-w-md mx-auto">{description}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger-ink">
      {message}
    </div>
  );
}

// ---- Form controls --------------------------------------------------------

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-ink-soft mb-1">{label}</span>
      {children}
      {hint && <span className="block text-2xs text-ink-muted mt-1">{hint}</span>}
    </label>
  );
}

const inputBase =
  "w-full rounded-lg border border-line-strong bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/50";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputBase, props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputBase, "font-mono text-xs leading-relaxed", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(inputBase, "pr-8", props.className)} />;
}
