"""FindingFrame extraction worker (separate process; imports the backend ``app``).

Loop:
  1. Claim one queued run with FOR UPDATE SKIP LOCKED (survives restarts, safe for N workers).
  2. Load the run's report versions, run the engine (rate-limited + retry/backoff on transient
     LLM errors).
  3. Persist frames/tracks/track_events + flip status->succeeded ATOMICALLY.
  4. On failure: status->failed, error, attempts++.
Everything the worker does writes an audit_log row.

Run:  backend/.venv/bin/python -m worker.main        (from the findingframe/ repo root)
"""
from __future__ import annotations

import worker._bootstrap  # noqa: F401  (adds backend/ to sys.path so `import app` works)

import asyncio
import datetime as dt
import json
import signal
import time
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models import ExtractionRun, Patient, ReportVersion
from app.db.session import dispose_engine, get_sessionmaker
from app.engine import adapter as engine_adapter
from app.engine.adapter import get_engine
from app.engine.types import ReportInput
from app.services import audit, carry_forward
from worker import persist, rate_limit

log = get_logger("findingframe.worker")

_TRANSIENT_HINTS = ("429", "500", "502", "503", "504", "timeout", "timed out",
                    "rate limit", "temporarily", "connection reset")
_MAX_LLM_RETRIES = 3
_stop = False


def _handle_signal(*_a):
    global _stop
    _stop = True
    log.info("stop_requested")


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(h in msg for h in _TRANSIENT_HINTS)


async def claim_run(sm: async_sessionmaker) -> uuid.UUID | None:
    """Atomically claim one queued run (FOR UPDATE SKIP LOCKED). Returns its id or None."""
    async with sm() as s:
        row = (
            await s.execute(
                text(
                    """
                    select id from ff.extraction_runs
                    where status = 'queued'
                    order by created_at
                    for update skip locked
                    limit 1
                    """
                )
            )
        ).first()
        if row is None:
            return None
        run_id = row[0]
        await s.execute(
            text(
                """
                update ff.extraction_runs
                set status='running', locked_by=:worker, locked_at=now(),
                    started_at=coalesce(started_at, now()),
                    attempts = attempts + 1,
                    checkpoint = jsonb_set(coalesce(checkpoint,'{}'::jsonb),
                                           '{phase}', '"running"'::jsonb)
                where id = :id
                """
            ),
            {"worker": settings.worker_id, "id": run_id},
        )
        run = await s.get(ExtractionRun, run_id)
        await audit.record(
            s,
            org_id=run.org_id,
            actor_id=None,
            action="run.claim",
            entity_type="run",
            entity_id=str(run_id),
            after={"worker": settings.worker_id, "attempts": run.attempts},
        )
        await s.commit()
        return run_id


async def _load_inputs(sm: async_sessionmaker, run: ExtractionRun) -> list[ReportInput]:
    """Rebuild engine ReportInputs from the run's frozen report_manifest."""
    inputs: list[ReportInput] = []
    async with sm() as s:
        for entry in run.report_manifest or []:
            rvid = entry.get("report_version_id")
            if not rvid:
                continue
            version = await s.get(ReportVersion, uuid.UUID(str(rvid)))
            if version is None:
                continue
            inputs.append(
                ReportInput(
                    source_report_id=entry.get("source_report_id") or f"report_{len(inputs)+1}",
                    text=version.text,
                    chart_date=dt.datetime.fromisoformat(entry["chart_date"])
                    if entry.get("chart_date")
                    else dt.datetime.now(dt.timezone.utc),
                    report_version_id=str(version.id),
                    text_sha256=version.text_sha256,
                )
            )
    return inputs


def _run_engine(subject_code: str, inputs: list[ReportInput], run_id: str):
    """Blocking engine call (runs in a thread). Retries transient LLM errors with backoff."""
    last: Exception | None = None
    for attempt in range(1, _MAX_LLM_RETRIES + 1):
        try:
            return get_engine().process_patient(subject_code, inputs, run_id=run_id)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not _is_transient(exc) or attempt == _MAX_LLM_RETRIES:
                raise
            backoff = 2.0 ** attempt
            log.warning("engine_transient_retry", attempt=attempt, backoff=backoff, error=str(exc))
            time.sleep(backoff)
    raise last  # pragma: no cover


async def process_run(sm: async_sessionmaker, run_id: uuid.UUID) -> None:
    async with sm() as s:
        run = await s.get(ExtractionRun, run_id)
        patient = await s.get(Patient, run.patient_id)
    subject_code = patient.subject_code
    org_id = run.org_id
    started = time.time()

    try:
        inputs = await _load_inputs(sm, run)
        if not inputs:
            raise RuntimeError("run has no loadable report versions")

        # Shared LLM budget: consume one token per report before the (bursty) engine call.
        for _ in inputs:
            await rate_limit.acquire(sm, limit_per_min=settings.llm_rate_limit_per_min)

        artifact = await asyncio.to_thread(_run_engine, subject_code, inputs, str(run_id))
        provenance = engine_adapter.extraction_provenance(artifact, run.report_manifest or [])

        # Persist + flip to succeeded atomically.
        async with sm() as s:
            counts = await persist.persist_artifact(
                s,
                run_id=run_id,
                org_id=org_id,
                patient_id=run.patient_id,
                report_manifest=run.report_manifest or [],
                artifact=artifact,
            )
            latency_ms = int((time.time() - started) * 1000)
            await s.execute(
                text(
                    """
                    update ff.extraction_runs set
                      status='succeeded', finished_at=now(), error=null,
                      progress_done=:total, progress_total=:total, latency_ms=:lat,
                      manifest_hash=coalesce(manifest_hash, :mh),
                      engine_git_sha=coalesce(engine_git_sha, :sha),
                      model_id=coalesce(model_id, :model),
                      extraction_provenance = :prov::jsonb,
                      checkpoint = jsonb_set(coalesce(checkpoint,'{}'::jsonb),
                                             '{phase}', '"persisted"'::jsonb)
                    where id = :id
                    """
                ),
                {
                    "total": len(inputs),
                    "lat": latency_ms,
                    "mh": artifact.manifest.manifest_hash,
                    "sha": artifact.manifest.engine_git_sha,
                    "model": artifact.manifest.model_id,
                    "prov": json.dumps(provenance),
                    "id": run_id,
                },
            )
            await audit.record(
                s,
                org_id=org_id,
                actor_id=None,
                action="run.succeeded",
                entity_type="run",
                entity_id=str(run_id),
                after={
                    **counts,
                    "latency_ms": latency_ms,
                    "llm_calls": provenance.get("llm_calls"),
                    "reports_total": provenance.get("reports_total"),
                },
            )
            await s.commit()
        log.info("run_succeeded", run_id=str(run_id), llm_calls=provenance.get("llm_calls"),
                 reports_total=provenance.get("reports_total"), **counts)

        # An incremental run extends a record a clinician already confirmed. Replay the
        # confirmations that still stand, so the reviewer is asked only about what this
        # report actually changed. Anything re-opened or new is left for them.
        if run.parent_run_id:
            async with sm() as s:
                result = await carry_forward.apply_carry_forward(
                    s, org_id=org_id, run_id=run_id, applied_by=run.created_by
                )
                await audit.record(
                    s,
                    org_id=org_id,
                    actor_id=None,
                    action="run.carry_forward",
                    entity_type="run",
                    entity_id=str(run_id),
                    after={
                        "parent_run_id": str(run.parent_run_id),
                        "counts": result["counts"],
                        "carried_link_decisions": result["carried_link_decisions"],
                        "carried_target_selection": result["carried_target_selection"],
                        "recist_call_before": result["recist_call_before"],
                        "recist_call_after": result["recist_call_after"],
                    },
                )
                await s.commit()
            log.info("run_carried_forward", run_id=str(run_id), **result["counts"])

    except Exception as exc:  # noqa: BLE001
        log.error("run_failed", run_id=str(run_id), error=str(exc), exc_type=type(exc).__name__)
        async with sm() as s:
            await s.execute(
                text(
                    """
                    update ff.extraction_runs
                    set status='failed', error=:err, finished_at=now(), locked_by=null
                    where id = :id
                    """
                ),
                {"err": str(exc)[:2000], "id": run_id},
            )
            await audit.record(
                s,
                org_id=org_id,
                actor_id=None,
                action="run.failed",
                entity_type="run",
                entity_id=str(run_id),
                after={"error": str(exc)[:500]},
            )
            await s.commit()


async def run_loop() -> None:
    configure_logging(settings.log_level)
    sm = get_sessionmaker()
    await rate_limit.ensure_table(sm)
    log.info("worker_started", worker_id=settings.worker_id,
             poll_interval_s=settings.worker_poll_interval_s)
    while not _stop:
        try:
            run_id = await claim_run(sm)
        except Exception as exc:  # noqa: BLE001 — never die on a claim error
            log.error("claim_error", error=str(exc))
            run_id = None
        if run_id is None:
            await asyncio.sleep(settings.worker_poll_interval_s)
            continue
        await process_run(sm, run_id)
    await dispose_engine()
    log.info("worker_stopped")


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
