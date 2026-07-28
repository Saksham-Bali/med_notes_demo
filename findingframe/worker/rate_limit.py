"""Shared LLM rate limiter (token bucket) backed by Postgres.

The engine ships an in-process limiter that does NOT survive multiple worker processes.
This is a fixed-window limiter shared across all workers via a small counter row, guarded
by a transaction-scoped advisory lock so concurrent workers cannot over-spend the budget.

BUILD_SPEC explicitly sanctions "a Postgres counter table or advisory lock". We lazily
create ``ff.llm_rate_limit`` (a runtime coordination table, not migration-owned).
"""
from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger

log = get_logger("findingframe.worker.ratelimit")

_BUCKET = "llm_global"
_WINDOW_SECONDS = 60
_LOCK_KEY = 918273645  # fixed advisory-lock key for the limiter critical section

_DDL = """
create table if not exists ff.llm_rate_limit (
  bucket_key   text primary key,
  window_start timestamptz not null default now(),
  count        int not null default 0
)
"""


async def ensure_table(sm: async_sessionmaker) -> None:
    """No-op. ``ff.llm_rate_limit`` is created by migration 0006 (owned by postgres);
    the least-privilege ff_app role has no CREATE on schema ff, so runtime DDL is not
    attempted. Kept for call-site compatibility."""
    return None


async def acquire(sm: async_sessionmaker, *, limit_per_min: int) -> None:
    """Block until a token is available in the current 60s window, then consume it."""
    while True:
        wait_s = await _try_acquire(sm, limit_per_min=limit_per_min)
        if wait_s <= 0:
            return
        await asyncio.sleep(min(wait_s, _WINDOW_SECONDS))


async def _try_acquire(sm: async_sessionmaker, *, limit_per_min: int) -> float:
    """Returns 0 if a token was consumed, else seconds to wait before retrying."""
    async with sm() as s:
        await s.execute(text("select pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
        row = (
            await s.execute(
                text(
                    "select window_start, count from ff.llm_rate_limit "
                    "where bucket_key = :b for update"
                ),
                {"b": _BUCKET},
            )
        ).first()
        now = dt.datetime.now(dt.timezone.utc)
        if row is None:
            await s.execute(
                text(
                    "insert into ff.llm_rate_limit (bucket_key, window_start, count) "
                    "values (:b, :now, 1)"
                ),
                {"b": _BUCKET, "now": now},
            )
            await s.commit()
            return 0.0

        window_start, count = row
        elapsed = (now - window_start).total_seconds()
        if elapsed >= _WINDOW_SECONDS:
            await s.execute(
                text(
                    "update ff.llm_rate_limit set window_start = :now, count = 1 "
                    "where bucket_key = :b"
                ),
                {"b": _BUCKET, "now": now},
            )
            await s.commit()
            return 0.0
        if count < limit_per_min:
            await s.execute(
                text("update ff.llm_rate_limit set count = count + 1 where bucket_key = :b"),
                {"b": _BUCKET},
            )
            await s.commit()
            return 0.0
        await s.commit()
        return _WINDOW_SECONDS - elapsed
