"""Append-only audit log.

The per-org hash chain (prev_hash, row_hash) is computed by the DB trigger
ff.chain_audit() on INSERT — it is race-safe (advisory lock) and tamper-evident. We MUST
NOT set the hash columns here; we only insert the meaningful columns. org_id is NOT NULL.

DPDP: never write plaintext patient identifiers into before/after (callers redact).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_var
from app.db.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one audit row inside the caller's transaction. The DB trigger fills the hash
    chain columns."""
    if org_id is None:
        raise ValueError("audit rows require an org_id (audit_log.org_id is NOT NULL)")
    row = AuditLog(
        org_id=org_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        request_id=request_id_var.get() or None,
    )
    session.add(row)
    await session.flush()
    return row
