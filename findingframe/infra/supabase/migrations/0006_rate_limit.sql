-- Shared LLM token-bucket coordination table. Previously created lazily by the worker,
-- but the least-privilege ff_app role (0005) has no CREATE on schema ff (by design) — so
-- DDL must live in a migration (owned by postgres), with ff_app granted read/write access.

begin;

create table if not exists ff.llm_rate_limit (
  bucket_key   text primary key,
  window_start timestamptz not null default now(),
  count        int not null default 0
);

grant select, insert, update on ff.llm_rate_limit to ff_app;

commit;
