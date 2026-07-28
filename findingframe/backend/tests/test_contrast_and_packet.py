"""Tests for the demo-critical additions:

- naive-vs-confirmed RECIST contrast on SYNTHETIC money-patient-shaped tracks (offline, pure);
- tamper-evident ROI timing computation (DB-integration, skips if the DB is unreachable);
- the PDF audit-packet renderer returns a non-empty application/pdf document (offline).
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import ExtractionRun, Org
from app.db.session import _ssl_context
from app.services import metrics, patients as patients_svc, recist, sessions as sessions_svc
from app.services import signoff as signoff_svc
from app.services.export import packet_to_pdf

# --- SYNTHETIC money-patient track shape ------------------------------------
LUNG = "primary_tumor|thorax|left"
LIVER_B1 = "liver_metastasis|liver_segment_vii|right"  # baseline-only (segment VII label)
LIVER_B2 = "liver_metastasis|liver|right"  # follow-ups (broad "liver" label) + merged key
DATES = ["2025-01-15", "2025-03-20", "2025-05-22", "2025-07-24"]


def _ev(date: str, mm: float, assertion: str = "present") -> dict:
    return {"date": date, "assertion": assertion, "measurement": {"normalized_mm": mm}}


def _machine_tracks() -> dict:
    return {
        LUNG: {
            "finding_type": "primary_tumor",
            "anatomy": "thorax",
            "laterality": "left",
            "events": [_ev(d, mm) for d, mm in zip(DATES, [55, 46, 38, 34])],
        },
        LIVER_B1: {
            "finding_type": "liver_metastasis",
            "anatomy": "liver_segment_vii",
            "laterality": "right",
            "events": [_ev(DATES[0], 40)],
        },
        LIVER_B2: {
            "finding_type": "liver_metastasis",
            "anatomy": "liver",
            "laterality": "right",
            "events": [_ev(d, mm) for d, mm in zip(DATES[1:], [32, 26, 24])],
        },
    }


def _confirmed_by_key() -> dict:
    """After the human merge: lung stands alone, the two liver tracks fold into one."""
    return {
        LUNG: {
            "confirmed_track_key": LUNG,
            "finding_type": "primary_tumor",
            "anatomy": "thorax",
            "laterality": "left",
            "member_track_keys": [LUNG],
            "events": [_ev(d, mm) for d, mm in zip(DATES, [55, 46, 38, 34])],
        },
        LIVER_B2: {
            "confirmed_track_key": LIVER_B2,
            "finding_type": "liver_metastasis",
            "anatomy": "liver",
            "laterality": "right",
            "member_track_keys": [LIVER_B1, LIVER_B2],
            "events": [_ev(d, mm) for d, mm in zip(DATES, [40, 32, 26, 24])],
        },
    }


def _selections() -> list[dict]:
    return [
        {"confirmed_track_key": LUNG, "organ": "lung", "baseline_mm": 55},
        {"confirmed_track_key": LIVER_B2, "organ": "liver", "baseline_mm": 40},
    ]


# --- contrast: naive PD vs confirmed PR (the money moment) -------------------
def test_naive_side_fires_false_pd_from_split():
    member_map = {LUNG: [LUNG], LIVER_B2: [LIVER_B1, LIVER_B2]}
    naive = recist.build_naive_side(_selections(), member_map, _machine_tracks())
    assert naive["classification"] == "PD"
    assert naive["new_lesion"] is True
    # the follow-up liver track is the false "new lesion"
    assert LIVER_B2 in naive["rationale"]
    # naive targets are MACHINE tracks: lung + the baseline (segment VII) liver track
    keys = {t["track_key"] for t in naive["target_tracks"]}
    assert keys == {LUNG, LIVER_B1}
    assert all(t["source"] == "machine" for t in naive["target_tracks"])


def test_confirmed_side_is_partial_response():
    confirmed = recist.build_confirmed_side(_selections(), _confirmed_by_key())
    assert confirmed["classification"] == "PR"
    assert confirmed["new_lesion"] is False
    keys = {t["track_key"] for t in confirmed["target_tracks"]}
    assert keys == {LUNG, LIVER_B2}
    # SLD timeline: 95 -> 78 -> 64 -> 58
    slds = [row["sld_mm"] for row in confirmed["sld_timeline"]]
    assert slds == [95, 78, 64, 58]


def test_contrast_discrepancy_pd_vs_pr():
    naive = recist.build_naive_side(
        _selections(), {LUNG: [LUNG], LIVER_B2: [LIVER_B1, LIVER_B2]}, _machine_tracks()
    )
    confirmed = recist.build_confirmed_side(_selections(), _confirmed_by_key())
    assert naive["classification"] == "PD"
    assert confirmed["classification"] == "PR"
    assert naive["classification"] != confirmed["classification"]


def test_naive_without_merge_matches_confirmed():
    """A single-member (no false split) target selection does not manufacture a new lesion."""
    machine = {LUNG: _machine_tracks()[LUNG]}
    sel = [{"confirmed_track_key": LUNG, "organ": "lung", "baseline_mm": 55}]
    naive = recist.build_naive_side(sel, {LUNG: [LUNG]}, machine)
    assert naive["new_lesion"] is False
    # 55 -> 34 is -38% => PR, no false PD
    assert naive["classification"] == "PR"


# --- best-overall ranking ---------------------------------------------------
def test_best_overall_progression_trumps():
    assert recist.best_overall(["SD", "PD", "SD"]) == "PD"


def test_best_overall_takes_best_response_when_no_pd():
    assert recist.best_overall(["SD", "PR", "SD"]) == "PR"
    assert recist.best_overall(["SD", "PR", "CR"]) == "CR"
    assert recist.best_overall([]) == "NE"


# --- compute_timeline reuse -------------------------------------------------
def test_compute_timeline_new_lesion_forces_pd():
    d0 = dt.datetime.fromisoformat("2025-01-15")
    d1 = dt.datetime.fromisoformat("2025-03-20")
    targets = [{"track_key": "t1", "organ": "liver", "is_nodal": False,
                "baseline_mm": 40, "series": [(d0, 40.0), (d1, 30.0)]}]
    rows = recist.compute_timeline(targets, {d1})
    assert rows[0]["classification"] == "SD"
    assert rows[1]["new_lesion"] is True
    assert rows[1]["classification"] == "PD"


# --- PDF renderer -----------------------------------------------------------
def _minimal_packet() -> dict:
    return {
        "patient": {"id": str(uuid.uuid4()), "subject_code": "DEMO-NSCLC-01", "cancer_type": "lung"},
        "manifest": {
            "run_id": str(uuid.uuid4()), "manifest_hash": "abc123", "engine_git_sha": "e04d3c6d9c79",
            "model_provider": "openrouter", "model_id": "deepseek/deepseek-v4-pro",
            "prompt_version": "p1", "schema_version": "s1", "status": "succeeded",
        },
        "timing": {
            "first_action_at": "2026-07-17T10:00:00+00:00", "signoff_at": "2026-07-17T10:07:30+00:00",
            "elapsed_seconds": 450.0, "active_review_seconds": 300, "source": "hash-chained audit_log",
        },
        "frames": [
            {"finding_type": "liver_metastasis", "anatomy": "liver", "laterality": "right",
             "assertion": "present", "evidence_text": "40 mm lesion in segment VII",
             "evidence_verified": True, "track_key": LIVER_B1, "source_report_id": "report_1",
             "temporal_change": None},
            {"finding_type": "indeterminate_nodule", "anatomy": "lung", "laterality": "right",
             "assertion": "uncertain", "evidence_text": "6 mm nodule, too small to characterize",
             "evidence_verified": False, "track_key": "x", "source_report_id": "report_2",
             "temporal_change": None},
        ],
        "recist": [
            {"assessment_date": "2025-01-15T00:00:00+00:00", "sld_mm": 95.0,
             "pct_from_baseline": 0.0, "new_lesion": False, "classification": "SD"},
            {"assessment_date": "2025-05-22T00:00:00+00:00", "sld_mm": 64.0,
             "pct_from_baseline": -32.6, "new_lesion": False, "classification": "PR"},
        ],
        "recist_contrast": {
            "run_id": str(uuid.uuid4()),
            "naive": {"classification": "PD"},
            "confirmed": {"classification": "PR"},
            "discrepancy": True,
            "discrepancy_note": "Naive PD vs confirmed PR — one merge flips the response.",
        },
        "link_decisions": [
            {"decision": "merge", "primary_track_key": LIVER_B2,
             "related_track_keys": [LIVER_B1], "resulting_track_key": LIVER_B2,
             "rationale": "same lesion", "signature_sha256": "deadbeef" * 8},
        ],
        "signoffs": [
            {"id": str(uuid.uuid4()), "payload_sha256": "aa" * 32, "prev_signoff_sha256": None,
             "row_sha256": "bb" * 32, "signed_by": str(uuid.uuid4()),
             "signed_at": "2026-07-17T10:07:30+00:00", "scope": "patient"},
        ],
    }


def test_packet_to_pdf_returns_nonempty_pdf():
    pdf = packet_to_pdf(_minimal_packet())
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000
    assert pdf[:5] == b"%PDF-"


def test_packet_to_pdf_handles_empty_sections():
    packet = _minimal_packet()
    packet["recist"] = []
    packet["link_decisions"] = []
    packet["signoffs"] = []
    packet["recist_contrast"] = {"naive": None, "confirmed": None, "discrepancy": False,
                                 "discrepancy_note": "no selection"}
    pdf = packet_to_pdf(packet)
    assert pdf[:5] == b"%PDF-"


# --- ROI timing (DB-integration; skips cleanly if the DB is unreachable) ----
@pytest_asyncio.fixture()
async def db_session():
    if not settings.database_url:
        pytest.skip("FF_DATABASE_URL not configured; skipping timing DB test")
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={
            "ssl": _ssl_context(),
            "server_settings": {"search_path": f"{settings.db_schema},public"},
        },
    )
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    session = sm()
    try:
        await session.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        await session.close()
        await engine.dispose()
        pytest.skip(f"DB unreachable, skipping timing DB test: {exc}")
    try:
        yield session
    finally:
        await session.rollback()  # never commit — leave the live DB untouched
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_compute_timing_measures_active_and_elapsed(db_session):
    session = db_session
    # A real user id is required (reviewer_id / signed_by FK auth.users). The least-privilege
    # ff_app role cannot read the auth schema; probe in a SAVEPOINT so a permission error
    # doesn't abort the outer transaction, and skip if no user is reachable.
    try:
        async with session.begin_nested():
            actor_id = (
                await session.execute(text("select id from auth.users limit 1"))
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        actor_id = None
    if actor_id is None:
        pytest.skip("no auth.users row reachable (ff_app) to author a review session / sign-off")

    suffix = uuid.uuid4().hex[:8]
    org = Org(name=f"Timing Org {suffix}", region="ap-southeast-1")
    session.add(org)
    await session.flush()
    patient = await patients_svc.create_patient(
        session, org_id=org.id, created_by=actor_id, subject_code=f"TIMING-{suffix}",
        cancer_type="lung",
    )
    run = ExtractionRun(
        org_id=org.id, patient_id=patient.id, status="succeeded", created_by=actor_id,
        progress_total=1, progress_done=1,
    )
    session.add(run)
    await session.flush()

    # a review session with measured active time
    rs = await sessions_svc.start_session(
        session, org_id=org.id, patient_id=patient.id, reviewer_id=actor_id, run_id=run.id
    )
    await sessions_svc.end_session(
        session, org_id=org.id, session_id=rs.id, active_seconds=300, tracks_reviewed=4
    )
    # a sign-off (chained by the DB trigger) closes the window
    await signoff_svc.create_signoff(
        session, org_id=org.id, patient_id=patient.id, signed_by=actor_id, run_id=run.id
    )

    timing = await metrics.compute_timing(
        session, org_id=org.id, run_id=run.id, patient_id=patient.id
    )
    assert timing["source"] == "hash-chained audit_log"
    assert timing["active_review_seconds"] == 300
    assert timing["first_action_at"] is not None  # review-session start
    assert timing["signoff_at"] is not None
    assert timing["elapsed_seconds"] is not None
    assert timing["elapsed_seconds"] >= 0
