"""Async SQLAlchemy 2.0 engine + session factory.

The backend connects as the Postgres superuser (`postgres`) = the tenant boundary.
RLS is defense-in-depth only; org scoping is enforced in the service layer on EVERY query.

The DSN (`settings.database_url`) is an asyncpg URL to Supabase. asyncpg needs:
  * SSL (Supabase requires TLS; dev may use an unverified context),
  * server_settings search_path=ff,public so unqualified names resolve to schema ff.
"""
from __future__ import annotations

import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _ssl_context() -> ssl.SSLContext:
    """A permissive TLS context (dev). Supabase requires SSL; we do not verify the
    server cert here because the direct-host cert chain varies by environment. In
    production, load a CA bundle and set verify_mode=CERT_REQUIRED."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError("FF_DATABASE_URL is not configured")
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            echo=False,
            connect_args={
                "ssl": _ssl_context(),
                "server_settings": {"search_path": f"{settings.db_schema},public"},
            },
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session and commits/rolls back around the request."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
