"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { signOut } from "@/lib/auth";
import { useUser } from "./AuthGuard";
import { IS_MOCK } from "@/lib/env";
import { cx } from "@/lib/format";
import { Activity, BarChart3, ClipboardCheck, LogOut, Settings, ShieldCheck, Workflow } from "lucide-react";

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();

  const onSignOut = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <header className="sticky top-0 z-30 bg-paper/90 backdrop-blur border-b border-line">
      <div className="mx-auto max-w-7xl px-5 h-14 flex items-center gap-4">
        <Link href="/dashboard" className="flex items-center gap-2 group">
          <span className="w-7 h-7 rounded-lg bg-accent text-white flex items-center justify-center">
            <ShieldCheck className="w-4 h-4" />
          </span>
          <span className="font-semibold text-ink tracking-tight">
            FindingFrame
          </span>
          <span className="text-2xs text-ink-faint hidden sm:inline">audit-grade oncology review</span>
        </Link>

        <nav className="flex items-center gap-1 ml-2 overflow-x-auto scroll-thin">
          <NavLink href="/dashboard" active={pathname?.startsWith("/dashboard") ?? false}>
            <Activity className="w-4 h-4" /> Patients
          </NavLink>
          <NavLink href="/analytics" active={pathname?.startsWith("/analytics") ?? false}>
            <BarChart3 className="w-4 h-4" /> Analytics
          </NavLink>
          <NavLink href="/pipeline" active={pathname?.startsWith("/pipeline") ?? false}>
            <Workflow className="w-4 h-4" /> Pipeline
          </NavLink>
          <NavLink href="/irr" active={pathname?.startsWith("/irr") ?? false}>
            <ClipboardCheck className="w-4 h-4" /> Validation
          </NavLink>
          <NavLink href="/settings" active={pathname?.startsWith("/settings") ?? false}>
            <Settings className="w-4 h-4" /> Settings
          </NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {IS_MOCK && (
            <span className="text-2xs font-semibold text-warn-ink bg-warn-soft border border-warn/20 rounded-md px-2 py-0.5">
              MOCK MODE
            </span>
          )}
          {user && (
            <span className="text-xs text-ink-muted hidden sm:inline">
              {user.full_name || user.email}
            </span>
          )}
          <button
            onClick={onSignOut}
            className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink"
          >
            <LogOut className="w-3.5 h-3.5" /> Sign out
          </button>
        </div>
      </div>
    </header>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cx(
        "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors shrink-0 whitespace-nowrap",
        active ? "bg-accent-soft text-accent-ink" : "text-ink-soft hover:bg-paper-sunk"
      )}
    >
      {children}
    </Link>
  );
}
