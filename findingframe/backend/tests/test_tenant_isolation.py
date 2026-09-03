"""Tenant-isolation (IDOR) tests.

The backend connects to Postgres as the superuser, so it BYPASSES RLS — tenant isolation
rests entirely on app-level org scoping in the service layer. This module proves it: it
creates two orgs A and B, each with a patient + extraction run (and a review session in B),
then asserts that a caller scoped to org A cannot read or write ANY of org B's resources.

Every service function that takes an id is exercised. The expectation is a 404 (NotFound)
for id-addressed resources and an empty result for list/latest queries — never another
org's data. A positive control (org B reaching its OWN run) confirms the failure is caused
by org scoping, not by missing rows.

This talks to the real Supabase DB the same way infra/scripts/seed_demo.py does (service
layer needs an AsyncSession). Everything is created inside ONE transaction that is rolled
back on teardown, so the live demo data is never mutated. The whole module skips cleanly if
the DB is unreachable, keeping the offline unit suite green.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.errors import NotFound
from app.db.models import ExtractionRun, Org, ReviewSession
from app.db.session import _is_local, _ssl_context
from app.services import (
    digest,
    export,
    linking,
    patients as patients_svc,
    recist,
    reports as reports_svc,
    reviews as reviews_svc,
    runs as runs_svc,
    sessions as sessions_svc,
    signoff as signoff_svc,
)


class Tenant:
    """Handle to one org's fixture rows."""

    def __init__(self, org_id: uuid.UUID, patient_id: uuid.UUID, run_id: uuid.UUID) -> None:
        self.org_id = org_id
        self.patient_id = patient_id
        self.run_id = run_id


class TwoTenants:
    def __init__(self, a: Tenant, b: Tenant, session, actor_id, b_session_id) -> None:
        self.a = a
        self.b = b
        self.session = session
        self.actor_id = actor_id  # a real auth.users id, or None
        self.b_session_id = b_session_id  # a ReviewSession in org B, or None


async def _make_tenant(session, name: str, subject: str, actor_id) -> Tenant:
    org = Org(name=name, region="ap-southeast-1")
    session.add(org)
    await session.flush()
    patient = await patients_svc.create_patient(
        session,
        org_id=org.id,
        created_by=actor_id,
        subject_code=subject,
        cancer_type="gastric",
    )
    run = ExtractionRun(
        org_id=org.id,
        patient_id=patient.id,
        status="queued",
        created_by=actor_id,
        progress_total=0,
        progress_done=0,
    )
    session.add(run)
    await session.flush()
    return Tenant(org_id=org.id, patient_id=patient.id, run_id=run.id)


@pytest_asyncio.fixture()
async def tenants():
    if not settings.database_url:
        pytest.skip("FF_DATABASE_URL not configured; skipping tenant-isolation tests")
    # A dedicated engine per test (NullPool) avoids reusing asyncpg connections across
    # pytest-asyncio's per-test event loops (which would raise), and keeps us off the
    # shared app engine entirely.
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={
            # Match app.db.session: a loopback scratch Postgres has no TLS and rejects
            # the upgrade, so demanding SSL would skip these tests everywhere but the
            # live database -- which is the one place you least want to run them.
            **({} if _is_local(settings.database_url) else {"ssl": _ssl_context()}),
            "server_settings": {"search_path": f"{settings.db_schema},public"},
        },
    )
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    session = sm()
    # Skip the whole module if the DB is unreachable (keeps the offline suite green).
    try:
        await session.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        await session.close()
        await engine.dispose()
        pytest.skip(f"DB unreachable, skipping tenant-isolation tests: {exc}")

    try:
        # A real user id lets us build a ReviewSession (reviewer_id FKs auth.users).
        # The least-privilege ff_app role cannot read the auth schema; a failed statement
        # aborts the transaction, so probe inside a SAVEPOINT and fall back to actor_id=None
        # (the isolation assertions below all tolerate a missing real user).
        try:
            async with session.begin_nested():
                actor_id = (
                    await session.execute(text("select id from auth.users limit 1"))
                ).scalar_one_or_none()
        except Exception:  # noqa: BLE001
            actor_id = None

        suffix = uuid.uuid4().hex[:8]
        a = await _make_tenant(session, f"IDOR Org A {suffix}", f"IDOR-A-{suffix}", actor_id)
        b = await _make_tenant(session, f"IDOR Org B {suffix}", f"IDOR-B-{suffix}", actor_id)

        b_session_id = None
        if actor_id is not None:
            rs = ReviewSession(
                org_id=b.org_id,
                patient_id=b.patient_id,
                run_id=b.run_id,
                reviewer_id=actor_id,
            )
            session.add(rs)
            await session.flush()
            b_session_id = rs.id

        yield TwoTenants(a, b, session, actor_id, b_session_id)
    finally:
        await session.rollback()  # never commit — leave the live DB untouched
        await session.close()
        await engine.dispose()


# --- positive control -------------------------------------------------------
@pytest.mark.asyncio
async def test_own_org_can_read_its_run(tenants: TwoTenants):
    run = await runs_svc.get_run(
        tenants.session, org_id=tenants.b.org_id, run_id=tenants.b.run_id
    )
    assert run.id == tenants.b.run_id


# --- patient-addressed services ---------------------------------------------
@pytest.mark.asyncio
async def test_cannot_read_other_org_patient(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await patients_svc.get_patient(s, org_id=a.org_id, patient_id=b.patient_id)
    with pytest.raises(NotFound):
        await patients_svc.get_patient_detail(s, org_id=a.org_id, patient_id=b.patient_id)
    # list is org-scoped: B's patient must not appear in A's list
    a_patients = await patients_svc.list_patients(s, org_id=a.org_id)
    assert all(p.id != b.patient_id for p in a_patients)


@pytest.mark.asyncio
async def test_cannot_read_or_write_other_org_reports(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await reports_svc.list_reports(s, org_id=a.org_id, patient_id=b.patient_id)
    with pytest.raises(NotFound):
        await reports_svc.add_reports(
            s,
            org_id=a.org_id,
            patient_id=b.patient_id,
            created_by=tenants.actor_id,
            items=[{"report_date": "2026-01-01T00:00:00+00:00", "text": "x"}],
        )


@pytest.mark.asyncio
async def test_cannot_erase_other_org_identifiers(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await patients_svc.delete_identifiers(s, org_id=a.org_id, patient_id=b.patient_id)


@pytest.mark.asyncio
async def test_cannot_signoff_or_read_signoffs_across_org(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await signoff_svc.create_signoff(
            s, org_id=a.org_id, patient_id=b.patient_id, signed_by=tenants.actor_id
        )
    # read: org-scoped query returns none of B's signoffs
    rows = await signoff_svc.list_signoffs(s, org_id=a.org_id, patient_id=b.patient_id)
    assert rows == []


# --- run-addressed services -------------------------------------------------
@pytest.mark.asyncio
async def test_cannot_read_other_org_run(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await runs_svc.get_run(s, org_id=a.org_id, run_id=b.run_id)
    # list runs for B's patient under org A must be empty
    listed = await runs_svc.list_runs(s, org_id=a.org_id, patient_id=b.patient_id)
    assert listed == []


@pytest.mark.asyncio
async def test_cannot_read_other_org_digest(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await digest.build_digest(s, org_id=a.org_id, run_id=b.run_id)


@pytest.mark.asyncio
async def test_cannot_read_or_write_other_org_reviews(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await reviews_svc.list_reviews(s, org_id=a.org_id, run_id=b.run_id)
    with pytest.raises(NotFound):
        await reviews_svc.create_review(
            s,
            org_id=a.org_id,
            run_id=b.run_id,
            reviewer_id=tenants.actor_id or uuid.uuid4(),
            data={"track_key": "t1"},
        )


@pytest.mark.asyncio
async def test_cannot_read_or_write_other_org_link_decisions(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await linking.list_link_decisions(s, org_id=a.org_id, run_id=b.run_id)
    with pytest.raises(NotFound):
        await linking.derive_confirmed_tracks(s, org_id=a.org_id, run_id=b.run_id)
    with pytest.raises(NotFound):
        await linking.create_link_decision(
            s,
            org_id=a.org_id,
            run_id=b.run_id,
            decided_by=tenants.actor_id or uuid.uuid4(),
            data={"decision": "confirm", "primary_track_key": "t1"},
        )


@pytest.mark.asyncio
async def test_cannot_read_or_write_other_org_recist(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await recist.compute_recist(s, org_id=a.org_id, run_id=b.run_id)
    with pytest.raises(NotFound):
        await recist.create_target_selection(
            s,
            org_id=a.org_id,
            run_id=b.run_id,
            selected_by=tenants.actor_id or uuid.uuid4(),
            baseline_report_version_id=None,
            selections=[{"confirmed_track_key": "t1", "organ": "liver", "baseline_mm": 20}],
        )
    # latest_target_selection is org-scoped -> None for a foreign run
    latest = await recist.latest_target_selection(s, org_id=a.org_id, run_id=b.run_id)
    assert latest is None


@pytest.mark.asyncio
async def test_cannot_read_other_org_audit_packet(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await export.build_audit_packet(s, org_id=a.org_id, run_id=b.run_id)


@pytest.mark.asyncio
async def test_audit_log_is_org_scoped(tenants: TwoTenants):
    s, a = tenants.session, tenants.a
    rows = await export.list_audit(s, org_id=a.org_id)
    assert all(r.org_id == a.org_id for r in rows)


# --- review-session-addressed services --------------------------------------
@pytest.mark.asyncio
async def test_cannot_start_or_end_session_across_org(tenants: TwoTenants):
    s, a, b = tenants.session, tenants.a, tenants.b
    with pytest.raises(NotFound):
        await sessions_svc.start_session(
            s, org_id=a.org_id, patient_id=b.patient_id, reviewer_id=tenants.actor_id or uuid.uuid4()
        )
    if tenants.b_session_id is not None:
        with pytest.raises(NotFound):
            await sessions_svc.end_session(
                s,
                org_id=a.org_id,
                session_id=tenants.b_session_id,
                active_seconds=1,
                tracks_reviewed=1,
            )
