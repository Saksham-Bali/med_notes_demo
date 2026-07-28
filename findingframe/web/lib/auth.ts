"use client";

import { getSupabase } from "./supabase";
import { IS_MOCK } from "./env";

const MOCK_SESSION_KEY = "ff_mock_session";
const MOCK_TOKEN = "mock-access-token";

export interface AppUser {
  id: string;
  email: string;
  full_name: string | null;
}

/** Access token to attach as `Authorization: Bearer <token>` on API calls. */
export async function getAccessToken(): Promise<string | null> {
  if (IS_MOCK) {
    if (typeof window === "undefined") return MOCK_TOKEN;
    return localStorage.getItem(MOCK_SESSION_KEY) ? MOCK_TOKEN : null;
  }
  const sb = getSupabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function getCurrentUser(): Promise<AppUser | null> {
  if (IS_MOCK) {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(MOCK_SESSION_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AppUser;
    } catch {
      return {
        id: "mock-user",
        email: "reviewer@findingframe.dev",
        full_name: "Demo Reviewer",
      };
    }
  }
  const sb = getSupabase();
  if (!sb) return null;
  const { data } = await sb.auth.getUser();
  if (!data.user) return null;
  return {
    id: data.user.id,
    email: data.user.email ?? "",
    full_name:
      (data.user.user_metadata?.full_name as string | undefined) ?? null,
  };
}

export async function signInWithPassword(
  email: string,
  password: string
): Promise<{ error: string | null }> {
  if (IS_MOCK) {
    const user: AppUser = {
      id: "mock-user",
      email: email || "reviewer@findingframe.dev",
      full_name: "Demo Reviewer",
    };
    localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify(user));
    return { error: null };
  }
  const sb = getSupabase();
  if (!sb) return { error: "Supabase is not configured." };
  const { error } = await sb.auth.signInWithPassword({ email, password });
  return { error: error?.message ?? null };
}

export async function signUpWithPassword(
  email: string,
  password: string,
  fullName: string
): Promise<{ error: string | null; needsConfirmation: boolean }> {
  if (IS_MOCK) {
    const user: AppUser = {
      id: "mock-user",
      email,
      full_name: fullName || "Demo Reviewer",
    };
    localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify(user));
    return { error: null, needsConfirmation: false };
  }
  const sb = getSupabase();
  if (!sb) return { error: "Supabase is not configured.", needsConfirmation: false };
  const { data, error } = await sb.auth.signUp({
    email,
    password,
    options: { data: { full_name: fullName } },
  });
  if (error) return { error: error.message, needsConfirmation: false };
  const needsConfirmation = !data.session;
  return { error: null, needsConfirmation };
}

export async function signOut(): Promise<void> {
  if (IS_MOCK) {
    localStorage.removeItem(MOCK_SESSION_KEY);
    return;
  }
  const sb = getSupabase();
  await sb?.auth.signOut();
}

export function onAuthChange(cb: () => void): () => void {
  if (IS_MOCK) {
    const handler = () => cb();
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }
  const sb = getSupabase();
  if (!sb) return () => {};
  const { data } = sb.auth.onAuthStateChange(() => cb());
  return () => data.subscription.unsubscribe();
}
