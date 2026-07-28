#!/usr/bin/env python3
"""Seed the SYNTHETIC "money patient" (DEMO-NSCLC-01) into the demo DB as a completed run.

Idempotent, offline (reads the frozen engine artifact in infra/seed_data/ — no live LLM
key needed). Reuses the same demo org as seed_demo.py ("Tata Memorial (Demo)") and mirrors
its frames/tracks/track_events + succeeded extraction_run insert pattern.

Unlike seed_demo.py this does NOT TRUNCATE — it seeds a SECOND patient alongside the
existing demo patient. Idempotency is by (org_id, subject_code): if DEMO-NSCLC-01 already
exists in the org, the script is a no-op.

Run:  backend/.venv/bin/python infra/scripts/seed_money_patient.py

Prereqs: run infra/scripts/seed_demo.py first (creates the org + demo user), and
infra/scripts/build_money_patient.py once (creates the frozen artifact).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_ENV = FF_ROOT / "backend" / ".env"
TMC_DIR = FF_ROOT.parent / "tmc"
SEED_DATA_DIR = INFRA_DIR / "seed_data"

# reuse helpers + constants from the existing seed script
sys.path.insert(0, str(SCRIPT_DIR))
import seed_demo  # noqa: E402
from seed_demo import (  # noqa: E402
    _sha256,
    build_pg_dsn,
    clinical_section_for,
    load_env_file,
    progression_for,
    report_range_for,
)

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

DEMO_ORG_NAME = seed_demo.DEMO_ORG_NAME
DEMO_EMAIL = seed_demo.DEMO_EMAIL
MODEL_PROVIDER = "openrouter"
REASONING_EFFORT = "medium"

REPORTS_PATH = SEED_DATA_DIR / "money_patient_reports.json"
ARTIFACT_PATH = SEED_DATA_DIR / "money_patient_artifact.json"


def _parse_dt(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def main() -> int:
    print("=== FindingFrame money-patient seed (SYNTHETIC) ===")
    if not REPORTS_PATH.exists() or not ARTIFACT_PATH.exists():
        print(f"ERROR: frozen data missing. Run build_money_patient.py first.\n"
              f"  {REPORTS_PATH}\n  {ARTIFACT_PATH}", file=sys.stderr)
        return 1

    reports_doc = json.loads(REPORTS_PATH.read_text())
    artifact = json.loads(ARTIFACT_PATH.read_text())
    subject_code = reports_doc["subject_code"]
    cancer_type = reports_doc["cancer_type"]
    reports = reports_doc["reports"]
    tracks = artifact["tracks"]
    manifest = artifact.get("manifest", {})
    engine_git_sha = manifest.get("engine_git_sha", "")
    model_id = manifest.get("model_id", "deepseek/deepseek-v4-pro")
    prompt_version = manifest.get("prompt_version", "unknown")
    schema_version = manifest.get("schema_version", "unknown")

    env = load_env_file(BACKEND_ENV)
    database_url = env.get("FF_DATABASE_URL", "")
    if not database_url:
        print(f"ERROR: FF_DATABASE_URL missing from {BACKEND_ENV}", file=sys.stderr)
        return 1
    dsn = build_pg_dsn(database_url)

    with psycopg.connect(dsn, autocommit=False, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # -- org (reuse; create if missing) --------------------------------
            cur.execute("select id from ff.orgs where name = %s", (DEMO_ORG_NAME,))
            row = cur.fetchone()
            if row:
                org_id = row["id"]
                print(f"Org exists: {DEMO_ORG_NAME} ({org_id})")
            else:
                cur.execute(
                    "insert into ff.orgs (name, region) values (%s, %s) returning id",
                    (DEMO_ORG_NAME, "ap-southeast-1"),
                )
                org_id = cur.fetchone()["id"]
                print(f"Created org: {DEMO_ORG_NAME} ({org_id})")

            # -- created_by user: prefer the demo user, else any org admin -----
            cur.execute("select id from auth.users where email = %s", (DEMO_EMAIL,))
            row = cur.fetchone()
            if row:
                user_id = row["id"]
            else:
                cur.execute(
                    "select user_id from ff.memberships where org_id = %s "
                    "order by role limit 1",
                    (org_id,),
                )
                m = cur.fetchone()
                if not m:
                    print("ERROR: no demo user/membership found. Run seed_demo.py first.",
                          file=sys.stderr)
                    return 1
                user_id = m["user_id"]
            print(f"Using created_by user {user_id}")

            # -- idempotency: skip if patient already present ------------------
            cur.execute(
                "select id from ff.patients where org_id = %s and subject_code = %s",
                (org_id, subject_code),
            )
            existing = cur.fetchone()
            if existing:
                print(f"Patient {subject_code} already seeded ({existing['id']}); "
                      "idempotent no-op.")
                conn.rollback()
                _verify(dsn, org_id, existing["id"], subject_code)
                return 0

            # -- patient -------------------------------------------------------
            cur.execute(
                "insert into ff.patients (org_id, subject_code, cancer_type, created_by) "
                "values (%s, %s, %s, %s) returning id",
                (org_id, subject_code, cancer_type, user_id),
            )
            patient_id = cur.fetchone()["id"]
            print(f"Created patient {subject_code} ({patient_id})")

            # -- reports + report_versions ------------------------------------
            report_version_map: dict[str, dict] = {}
            for r in sorted(reports, key=lambda x: x["chart_date"]):
                sid = r["source_report_id"]
                chart_date = _parse_dt(r["chart_date"])
                cur.execute(
                    "insert into ff.reports (org_id, patient_id, report_date, note_type, "
                    "external_note_id, created_by) values (%s,%s,%s,%s,%s,%s) returning id",
                    (org_id, patient_id, chart_date, r["note_type"], r["note_id"], user_id),
                )
                report_id = cur.fetchone()["id"]
                sha = _sha256(r["text"])
                cur.execute(
                    "insert into ff.report_versions (report_id, org_id, version_no, text, "
                    "text_sha256, is_addendum, created_by) values (%s,%s,1,%s,%s,false,%s) "
                    "returning id",
                    (report_id, org_id, r["text"], sha, user_id),
                )
                version_id = cur.fetchone()["id"]
                report_version_map[sid] = {
                    "report_version_id": version_id, "text_sha256": sha,
                    "chart_date": chart_date,
                }
            print(f"Inserted {len(report_version_map)} reports + report_versions")

            # -- extraction run (succeeded, full manifest) --------------------
            report_manifest = [
                {
                    "source_report_id": sid,
                    "report_version_id": str(v["report_version_id"]),
                    "text_sha256": v["text_sha256"],
                    "chart_date": v["chart_date"].isoformat(),
                }
                for sid, v in sorted(report_version_map.items(),
                                     key=lambda kv: (kv[1]["chart_date"], kv[0]))
            ]
            manifest_payload = json.dumps(
                {
                    "engine_git_sha": engine_git_sha,
                    "model_provider": MODEL_PROVIDER,
                    "model_id": model_id,
                    "prompt_version": prompt_version,
                    "schema_version": schema_version,
                    "temperature": 0.0,
                    "reasoning_effort": REASONING_EFFORT,
                    "reports": report_manifest,
                },
                sort_keys=True,
            )
            manifest_hash = _sha256(manifest_payload)
            cur.execute(
                "insert into ff.extraction_runs (org_id, patient_id, status, engine_git_sha, "
                "model_provider, model_id, prompt_version, schema_version, temperature, "
                "reasoning_effort, manifest_hash, report_manifest, attempts, progress_total, "
                "progress_done, created_by, started_at, finished_at) values "
                "(%s,%s,'succeeded',%s,%s,%s,%s,%s,0.0,%s,%s,%s::jsonb,1,%s,%s,%s,now(),now()) "
                "returning id",
                (org_id, patient_id, engine_git_sha, MODEL_PROVIDER, model_id, prompt_version,
                 schema_version, REASONING_EFFORT, manifest_hash, json.dumps(report_manifest),
                 len(report_manifest), len(report_manifest), user_id),
            )
            run_id = cur.fetchone()["id"]
            print(f"Created extraction_run {run_id} "
                  f"(status=succeeded, manifest_hash={manifest_hash[:12]}...)")

            # -- tracks + frames + track_events -------------------------------
            n_tracks = n_frames = n_events = 0
            for track_key in sorted(tracks):
                track = tracks[track_key]
                section = clinical_section_for(track)
                progression, progression_detail = progression_for(track)
                # Surface the two liver tracks (same lesion under two labels) as a
                # false-split candidate so the review UI proactively offers the merge.
                is_liver = track.get("finding_type") == "liver_metastasis"
                false_split = bool(track.get("contains_compatible_merges", False)) or is_liver
                cur.execute(
                    "insert into ff.tracks (run_id, org_id, patient_id, track_key, finding_type, "
                    "anatomy, laterality, latest_status, progression, progression_detail, "
                    "event_count, report_range, unresolved_link, false_split_candidate, "
                    "clinical_section) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "returning id",
                    (run_id, org_id, patient_id, track_key, track.get("finding_type"),
                     track.get("anatomy"), track.get("laterality"), track.get("latest_status"),
                     progression, progression_detail, track.get("event_count", 0),
                     report_range_for(track), bool(track.get("unresolved_link", False)),
                     false_split, section),
                )
                track_id = cur.fetchone()["id"]
                n_tracks += 1

                for ev in track.get("events", []):
                    sid = ev.get("source_report_id")
                    rv = report_version_map.get(sid)
                    report_version_id = rv["report_version_id"] if rv else None
                    span_start = ev.get("evidence_span_start")
                    span_end = ev.get("evidence_span_end")
                    evidence_verified = (
                        span_start is not None and span_end is not None
                        and span_start >= 0 and span_end >= 0
                    )
                    event_date = _parse_dt(ev.get("report_date"))
                    measurement = ev.get("measurement")
                    cur.execute(
                        "insert into ff.frames (run_id, org_id, patient_id, report_version_id, "
                        "source_report_id, frame_index, track_key, finding_type, finding_surface, "
                        "assertion, anatomy, laterality, uncertainty, temporal_change, measurement, "
                        "clinical_importance, evidence_text, evidence_span_start, evidence_span_end, "
                        "evidence_verified, review_only, lesion_key) values "
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s) "
                        "returning id",
                        (run_id, org_id, patient_id, report_version_id, sid,
                         ev.get("frame_index"), ev.get("track_key", track_key),
                         ev.get("finding_type"), ev.get("finding_surface"),
                         ev.get("assertion", "present"), ev.get("anatomy"), ev.get("laterality"),
                         ev.get("uncertainty"), ev.get("temporal_change"),
                         json.dumps(measurement) if measurement is not None else None,
                         ev.get("clinical_importance"), ev.get("evidence_text", ""),
                         span_start if span_start is not None else -1,
                         span_end if span_end is not None else -1,
                         evidence_verified, bool(ev.get("review_only", False)),
                         ev.get("lesion_key")),
                    )
                    frame_id = cur.fetchone()["id"]
                    n_frames += 1
                    cur.execute(
                        "insert into ff.track_events (track_id, frame_id, org_id, "
                        "report_version_id, event_date, assertion, evidence_text, temporal_change, "
                        "measurement) values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                        (track_id, frame_id, org_id, report_version_id, event_date,
                         ev.get("assertion", "present"), ev.get("evidence_text", ""),
                         ev.get("temporal_change"),
                         json.dumps(measurement) if measurement is not None else None),
                    )
                    n_events += 1
            print(f"Inserted {n_tracks} tracks, {n_frames} frames, {n_events} track_events")
        conn.commit()

    _verify(dsn, org_id, patient_id, subject_code)
    print("\n=== Seeded (SYNTHETIC money patient) ===")
    print(f"  org:     {DEMO_ORG_NAME} ({org_id})")
    print(f"  patient: {subject_code} ({patient_id})")
    print(f"  run:     {run_id}")
    print("Done.")
    return 0


def _verify(dsn: str, org_id, patient_id, subject_code: str) -> None:
    print("\n=== Verification ===")
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for table in ("reports", "extraction_runs", "tracks", "frames"):
                cur.execute(f"select count(*) c from ff.{table} where patient_id = %s",
                            (patient_id,))
                print(f"  ff.{table} (patient {subject_code}): {cur.fetchone()['c']}")
            cur.execute(
                "select count(*) c from ff.track_events te join ff.tracks t on t.id = te.track_id "
                "where t.patient_id = %s", (patient_id,))
            print(f"  ff.track_events (patient {subject_code}): {cur.fetchone()['c']}")
            cur.execute(
                "select track_key, finding_type, latest_status, false_split_candidate, event_count "
                "from ff.tracks where patient_id = %s and finding_type = 'liver_metastasis' "
                "order by track_key", (patient_id,))
            print("  liver_metastasis tracks (the split):")
            for r in cur.fetchall():
                print(f"    {r['track_key']}  status={r['latest_status']} "
                      f"false_split={r['false_split_candidate']} events={r['event_count']}")


if __name__ == "__main__":
    raise SystemExit(main())
