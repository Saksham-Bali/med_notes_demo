"""Aggregate all v1 routers into a single APIRouter."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import (
    analytics,
    health,
    irr,
    me,
    patients,
    reports,
    runs,
    sessions,
    settings,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(patients.router)
api_router.include_router(reports.router)
api_router.include_router(runs.router)
api_router.include_router(sessions.router)
api_router.include_router(analytics.router)
api_router.include_router(irr.router)
api_router.include_router(settings.router)
