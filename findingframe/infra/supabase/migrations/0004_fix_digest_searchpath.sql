-- Fix: hash-chain triggers call pgcrypto digest(), which on Supabase lives in the
-- `extensions` schema, not on the trigger's search_path (ff,public). Every audit_log /
-- signoff insert therefore failed with "function digest(bytea, unknown) does not exist",
-- which cascaded to all mutating endpoints (each writes an audit row).
-- Pin the functions' search_path to include extensions.

begin;
alter function ff.chain_signoff() set search_path = ff, extensions, public, pg_temp;
alter function ff.chain_audit()   set search_path = ff, extensions, public, pg_temp;
commit;
