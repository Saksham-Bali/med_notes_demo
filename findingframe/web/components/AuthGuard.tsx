"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, onAuthChange, type AppUser } from "@/lib/auth";
import { Loading } from "./ui";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "authed" | "anon">("loading");

  useEffect(() => {
    let active = true;
    const check = async () => {
      const user = await getCurrentUser();
      if (!active) return;
      if (user) setState("authed");
      else {
        setState("anon");
        router.replace("/login");
      }
    };
    check();
    const unsub = onAuthChange(check);
    return () => {
      active = false;
      unsub();
    };
  }, [router]);

  if (state !== "authed") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loading label="Checking session…" />
      </div>
    );
  }
  return <>{children}</>;
}

export function useUser(): AppUser | null {
  const [user, setUser] = useState<AppUser | null>(null);
  useEffect(() => {
    let active = true;
    getCurrentUser().then((u) => active && setUser(u));
    const unsub = onAuthChange(() => getCurrentUser().then((u) => active && setUser(u)));
    return () => {
      active = false;
      unsub();
    };
  }, []);
  return user;
}
