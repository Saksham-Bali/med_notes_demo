"""Auth: verify Supabase ES256 user JWTs via JWKS, resolve org membership, ensure a
profile row exists on first call.

The backend connects to Postgres as the superuser (tenant boundary); RLS is not relied on.
Org scoping is enforced in the service layer. This module resolves *which* org the caller
acts in and their role, and refuses requests without a valid JWT."""
from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Forbidden, Unauthorized
from app.db.models import Membership, Org, Profile
from app.db.session import get_session

# Single cached JWKS client (fetches + caches signing keys, refreshes on rotation).
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = settings.jwks_url_resolved
        if not url:
            raise Unauthorized("JWKS URL is not configured", code="auth_misconfigured")
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True)
    return _jwks_client


@dataclasses.dataclass
class CurrentUser:
    id: uuid.UUID
    email: str | None
    full_name: str | None = None


@dataclasses.dataclass
class OrgContext:
    """The org the caller acts in + their role there."""

    user: CurrentUser
    org_id: uuid.UUID
    role: str


def _decode_token(token: str) -> dict:
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp"]},
        )
    except Unauthorized:
        raise
    except jwt.PyJWTError as exc:
        raise Unauthorized(f"Invalid token: {exc}", code="invalid_token") from exc
    except Exception as exc:  # JWKS fetch / network problems
        raise Unauthorized("Could not verify token", code="auth_unavailable") from exc


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Missing bearer token", code="missing_token")
    token = authorization.split(" ", 1)[1].strip()
    claims = _decode_token(token)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise Unauthorized("Token missing subject", code="invalid_token") from exc
    email = claims.get("email")
    full_name = (claims.get("user_metadata") or {}).get("full_name") or claims.get("name")

    await _ensure_profile(session, user_id, full_name)
    return CurrentUser(id=user_id, email=email, full_name=full_name)


async def _ensure_profile(session: AsyncSession, user_id: uuid.UUID, full_name: str | None) -> None:
    """Create the profile row on first call (idempotent). profiles.id FKs auth.users(id),
    which exists because the JWT was issued by Supabase for this user."""
    existing = await session.get(Profile, user_id)
    if existing is None:
        # Use ON CONFLICT to tolerate races between concurrent first requests.
        await session.execute(
            text(
                "insert into ff.profiles (id, full_name) values (:id, :full_name) "
                "on conflict (id) do nothing"
            ),
            {"id": user_id, "full_name": full_name},
        )
        await session.flush()


async def get_org_context(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    x_org_id: Annotated[str | None, Header()] = None,
) -> OrgContext:
    """Resolve the caller's active org. If X-Org-Id is supplied it must be one the user
    belongs to; otherwise default to their single membership."""
    rows = (
        await session.execute(
            select(Membership.org_id, Membership.role).where(Membership.user_id == user.id)
        )
    ).all()
    if not rows:
        raise Forbidden("User has no org membership", code="no_membership")

    if x_org_id:
        try:
            requested = uuid.UUID(x_org_id)
        except ValueError as exc:
            raise Forbidden("Invalid X-Org-Id", code="invalid_org") from exc
        for org_id, role in rows:
            if org_id == requested:
                return OrgContext(user=user, org_id=org_id, role=role)
        raise Forbidden("Not a member of the requested org", code="not_org_member")

    org_id, role = rows[0]
    return OrgContext(user=user, org_id=org_id, role=role)


def require_role(*allowed: str):
    """Dependency factory: caller's role in the active org must be in ``allowed``."""

    async def _dep(ctx: Annotated[OrgContext, Depends(get_org_context)]) -> OrgContext:
        if ctx.role not in allowed:
            raise Forbidden(
                f"Requires role in {allowed}; you are '{ctx.role}'", code="insufficient_role"
            )
        return ctx

    return _dep


async def list_user_orgs(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(Org.id, Org.name, Membership.role)
            .join(Membership, Membership.org_id == Org.id)
            .where(Membership.user_id == user_id)
        )
    ).all()
    return [{"id": str(oid), "name": name, "role": role} for oid, name, role in rows]
