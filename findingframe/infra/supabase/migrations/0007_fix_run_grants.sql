-- The worker writes the reproducibility manifest on the running->succeeded transition
-- (a run is enqueued before extraction knows the engine sha / cost). Postgres requires
-- column-UPDATE privilege for every column in the SET clause, so ff_app needs update on
-- the manifest columns. Immutability is still enforced by ff.guard_extraction_run_update
-- (0003): once status='succeeded', the manifest columns cannot change, and success
-- requires them to be non-null. So this grant does not weaken the freeze — the trigger does.

begin;
grant update (manifest_hash, engine_git_sha, model_id, model_provider,
              prompt_version, schema_version, temperature, reasoning_effort, report_manifest)
  on ff.extraction_runs to ff_app;
commit;
