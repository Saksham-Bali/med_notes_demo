// When NEXT_PUBLIC_API_URL is unset (undefined), default to the local dev backend.
// When it is explicitly set to an empty string, use same-origin relative calls
// (e.g. behind a reverse proxy that serves the web app and proxies /api on one origin).
const _rawApiUrl = process.env.NEXT_PUBLIC_API_URL;
export const API_URL =
  _rawApiUrl === undefined
    ? "http://localhost:8000"
    : _rawApiUrl.replace(/\/$/, "");

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

/** "mock" runs the whole app against in-memory demo data (no backend, no Supabase). */
export const API_MODE = (process.env.NEXT_PUBLIC_API_MODE || "live").toLowerCase();
export const IS_MOCK = API_MODE === "mock";

export const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
