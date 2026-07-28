"""Current user + their org memberships."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.deps import SessionDep, UserDep
from app.core.security import list_user_orgs
from app.schemas.dto import MeResponse, OrgRef, UserOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
async def me(user: UserDep, session: SessionDep) -> MeResponse:
    orgs = await list_user_orgs(session, user.id)
    return MeResponse(
        user=UserOut(id=str(user.id), email=user.email, full_name=user.full_name),
        orgs=[OrgRef(**o) for o in orgs],
    )
