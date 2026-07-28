"""Shared FastAPI dependency aliases for v1 routers."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, OrgContext, get_current_user, get_org_context, require_role
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[CurrentUser, Depends(get_current_user)]
CtxDep = Annotated[OrgContext, Depends(get_org_context)]
# Clinical mutations require an admin or reviewer role in the active org.
ReviewerCtxDep = Annotated[OrgContext, Depends(require_role("admin", "reviewer"))]
