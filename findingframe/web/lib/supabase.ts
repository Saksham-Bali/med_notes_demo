"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { HAS_SUPABASE, SUPABASE_ANON_KEY, SUPABASE_URL } from "./env";

let _client: SupabaseClient | null = null;

/**
 * Browser Supabase client (auth only). Returns null when Supabase env is not
 * configured (e.g. pure mock mode), so callers can degrade gracefully.
 */
export function getSupabase(): SupabaseClient | null {
  if (!HAS_SUPABASE) return null;
  if (_client) return _client;
  _client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return _client;
}
