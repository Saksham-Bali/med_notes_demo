"""Public health check: reports engine SHA and DB reachability."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.v1.deps import SessionDep
from app.engine.adapter import get_engine
from app.schemas.dto import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDep) -> HealthResponse:
    db_ok = "ok"
    try:
        await session.execute(text("select 1"))
    except Exception:
        db_ok = "error"
    try:
        engine_sha = get_engine().manifest_base().engine_git_sha or "unknown"
    except Exception:
        engine_sha = "unknown"
    status = "ok" if db_ok == "ok" else "degraded"
    return HealthResponse(status=status, engine_sha=engine_sha, db=db_ok)
