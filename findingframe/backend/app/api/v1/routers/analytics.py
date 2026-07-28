"""Org-scoped analytics dashboard endpoints (read-only, under /api/v1/analytics).

Every aggregate is scoped to the caller's active org via the service layer. These are
read-only reporting endpoints, so they do not write to the audit log.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.deps import CtxDep, SessionDep
from app.schemas.dto import (
    AgreementSummary,
    AnalyticsOverview,
    RecistDistribution,
    ReviewThroughput,
)
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def analytics_overview(ctx: CtxDep, session: SessionDep):
    return await analytics.overview(session, org_id=ctx.org_id)


@router.get("/recist-distribution", response_model=RecistDistribution)
async def analytics_recist_distribution(ctx: CtxDep, session: SessionDep):
    return await analytics.recist_distribution(session, org_id=ctx.org_id)


@router.get("/review-throughput", response_model=ReviewThroughput)
async def analytics_review_throughput(ctx: CtxDep, session: SessionDep):
    return await analytics.review_throughput(session, org_id=ctx.org_id)


@router.get("/agreement", response_model=AgreementSummary)
async def analytics_agreement(ctx: CtxDep, session: SessionDep):
    return await analytics.agreement(session, org_id=ctx.org_id)
