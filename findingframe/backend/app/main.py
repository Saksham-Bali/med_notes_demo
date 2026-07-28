"""FastAPI application entrypoint.

Wires: CORS, request-id + structured logging middleware, typed error handlers, the v1
router (under settings.api_prefix), and a public /health. The backend connects to Postgres
as the superuser and is the explicit tenant boundary — org scoping lives in the service layer.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.api.v1.routers import health as health_router
from app.core.config import settings
from app.core.errors import RequestIdMiddleware, register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine

configure_logging(settings.log_level)
log = get_logger("findingframe.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("startup", env=settings.env, api_prefix=settings.api_prefix)
    yield
    await dispose_engine()
    log.info("shutdown")


app = FastAPI(title="FindingFrame API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)
app.add_middleware(RequestIdMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_prefix)
# Public health check also at the unprefixed root (per BUILD_SPEC).
app.include_router(health_router.router)
