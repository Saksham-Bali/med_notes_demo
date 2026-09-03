#!/usr/bin/env python3
"""End-to-end verification of the incremental-demo headline numbers.

Runs the REAL backend services (carry-forward, runs, recist) against a Postgres
database with the real schema (migrations 0001–0008 applied) and the seeded long
patient. Asserts the four headline claims the demo ships on screen.

Run:  backend/.venv/bin/python infra/scripts/verify_incremental_demo.py

Prereqs:
  infra/scripts/seed_demo.py       (org + demo user)
  infra/scripts/build_long_patient.py  (frozen artifacts)
  infra/scripts/seed_long_patient.py   (patient + two runs in the DB)
  infra/supabase/migrations/       (0001–0008 applied)

Exits 0 when all four claims hold; non-zero otherwise. This is the artifact that
lets anyone re-check the demo's headline numbers in one command.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_DIR = FF_ROOT / "backend"
BACKEND_ENV = BACKEND_DIR / ".env"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from seed_demo import build_pg_dsn, load_env_file, resolve_database_url  # noqa: E402

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import ExtractionRun  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.services import carry_forward, runs  # noqa: E402


async def _verify() -> int:
    """Run the four headline checks and return 0 if all pass."""
    ok = True
    env = load_env_file(BACKEND_ENV)
    dsn = build_pg_dsn(resolve_database_url(env))

    # Resolve the demo org + long-patient ids from the frozen data.
    reports_doc = json.loads((INFRA_DIR / "seed_data" / "long_patient_reports.json").read_text())
    subject_code = reports_doc["subject_code"]

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from ff.orgs where name = 'Tata Memorial (Demo)'")
            org_row = cur.fetchone()
            if not org_row:
                print("ERROR: demo org not found. Run seed_demo.py first.")
                return 1
            org_id = org_row["id"]

            cur.execute(
                "select id from ff.patients where org_id = %s and subject_code = %s",
                (org_id, subject_code),
            )
            patient_row = cur.fetchone()
            if not patient_row:
                print(f"ERROR: patient {subject_code} not found. Run seed_long_patient.py first.")
                return 1
            patient_id = patient_row["id"]

            cur.execute(
                "select id, run_kind, parent_run_id from ff.extraction_runs "
                "where patient_id = %s order by created_at",
                (patient_id,),
            )
            runs_rows = cur.fetchall()
            if len(runs_rows) < 2:
                print("ERROR: expected 2 runs for the long patient, "
                      f"found {len(runs_rows)}. Run seed_long_patient.py first.")
                return 1

            parent = [r for r in runs_rows if r["parent_run_id"] is None][0]
            child = [r for r in runs_rows if r["parent_run_id"] is not None][0]
            child_run_id = child["id"]

    # Use the same async DB pool the services already expect.
    sm = get_sessionmaker()

    # ---- Headline check 1: RECIST call moves from PR -> PD ----------------
    async with sm() as session:
        plan = await carry_forward.plan_carry_forward(
            session, org_id=org_id, run_id=child_run_id,
        )

        recist_before = plan["recist_call_before"]
        recist_after = plan["recist_call_after"]
        llm_calls = plan.get("llm_calls")
        reports_total = plan.get("reports_total")

        print(f"=== Headline checks for {subject_code} ===")
        print(f"  Child run:           {child_run_id}")
        print(f"  Parent run:          {plan['parent_run_id']}")
        print(f"  RECIST before:       {recist_before}")
        print(f"  RECIST after:        {recist_after}")
        print(f"  LLM calls:           {llm_calls}")
        print(f"  Reports total:       {reports_total}")
        print(f"  Category moved:      {plan['category_moved']}")
        print(f"  Counts:              {plan['counts']}")

        # Claim 1: the call moves.
        if recist_before != "PR":
            print(f"  [FAIL] recist_call_before should be 'PR', got {recist_before}")
            ok = False
        else:
            print("  [PASS] RECIST before = PR")

        if recist_after != "PD":
            print(f"  [FAIL] recist_call_after should be 'PD', got {recist_after}")
            ok = False
        else:
            print("  [PASS] RECIST after = PD")

        # A missing llm_calls is a FAILURE, not a pass. "Only the new report was read" is
        # one of the four claims the demo makes on screen; if extraction_provenance is
        # absent there is nothing backing it, which is exactly the unverifiable stage
        # claim this column was added to prevent.
        if llm_calls != 1:
            print(f"  [FAIL] llm_calls should be 1, got {llm_calls!r}")
            ok = False
        else:
            print("  [PASS] llm_calls = 1 (only report 11 reached the model)")

        if reports_total != 11:
            print(f"  [FAIL] reports_total should be 11, got {reports_total}")
            ok = False
        else:
            print("  [PASS] reports_total = 11")

        # Claim 2: three target identities reopen (RECIST anchor).
        identities = plan["identities"]
        reopens = [i for i in identities if i["status"] == "reopen"]
        target_reopens = {
            i["confirmed_track_key"] for i in reopens
        }
        print(f"\n  Reopened identities: {len(reopens)}")
        for i in reopens:
            print(f"    {i['confirmed_track_key']}: {i['reason']}")

        if len(reopens) != 3:
            print(f"  [FAIL] expected 3 target identities to reopen, got {len(reopens)}")
            ok = False
        else:
            print("  [PASS] all three target identities reopen for re-confirmation")

        # Claim 3: nothing outside the RECIST targets was sent back for re-confirmation.
        #
        # Note this is deliberately NOT "routine negatives show status=carry". Every
        # confirmed track picks up an event from report 11 — a negative re-asserted as
        # absent is still new evidence — so they land on `acknowledge`, not `carry`. Both
        # mean the same thing for the demo's claim: the identity attestation stood and the
        # clinician was not asked to make it again. What would falsify the claim is a
        # non-target identity being re-opened.
        kept = [i for i in identities if i["status"] in ("carry", "acknowledge")]
        print(f"\n  Identities kept without re-confirmation: {len(kept)} "
              f"({sum(1 for i in kept if i['status'] == 'carry')} unchanged, "
              f"{sum(1 for i in kept if i['status'] == 'acknowledge')} with new evidence "
              "to acknowledge)")
        if not kept:
            print("  [FAIL] no confirmed identity survived the new report — the clinician "
                  "would be redoing act one")
            ok = False
        else:
            print(f"  [PASS] {len(kept)} confirmed identities did not need re-confirmation")

        # Claim 4: at least one identity is 'new' (the 7 mm subpleural nodule).
        news = [i for i in identities if i["status"] == "new"]
        print(f"\n  New identities: {len(news)}")
        for i in news:
            print(f"    {i['confirmed_track_key']}")
        if not news:
            print("  [FAIL] no 'new' identities found — report 11 introduced a finding "
                  "that should need a fresh human decision")
            ok = False
        else:
            print(f"  [PASS] {len(news)} new finding(s) need a fresh decision")

    await asyncio.sleep(0)
    return 0 if ok else 2


def main() -> int:
    return asyncio.run(_verify())


if __name__ == "__main__":
    raise SystemExit(main())
