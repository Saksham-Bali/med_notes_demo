#!/usr/bin/env python3
"""Seed the SYNTHETIC "dynamicity" patient (DEMO-NSCLC-LONG-01) into the demo DB.

Idempotent, offline (reads frozen engine artifacts from infra/seed_data/ — no live LLM
key needed). Reuses the demo org and user from seed_demo.py ("Tata Memorial (Demo)").

Two runs are seeded:
  - A parent ``full`` run over reports 1–10, with the clinician's act-one work already
    recorded: link decisions confirming each target track, a target lesion selection naming
    the three lesions, quarantine clearance, and a sign-off.
  - An ``incremental`` run over all 11 reports, pointing at the parent via ``parent_run_id``.
    Tracks/events are fresh (recomputed by the engine for the full history), but the
    clinician's confirmations that still stand are carried forward by track key.

Run:  backend/.venv/bin/python infra/scripts/seed_long_patient.py

Prereqs: run infra/scripts/seed_demo.py first (creates the org + demo user), and
infra/scripts/build_long_patient.py once (creates the frozen artifacts).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_ENV = FF_ROOT / "backend" / ".env"
SEED_DATA_DIR = INFRA_DIR / "seed_data"

sys.path.insert(0, str(SCRIPT_DIR))
import seed_demo  # noqa: E402
from seed_demo import (  # noqa: E402
    _sha256,
    build_pg_dsn,
    resolve_database_url,
    clinical_section_for,
    load_env_file,
    progression_for,
    report_range_for,
)

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg[binary]"], check=True)
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore

DEMO_ORG_NAME = seed_demo.DEMO_ORG_NAME
DEMO_EMAIL = seed_demo.DEMO_EMAIL
MODEL_PROVIDER = "openrouter"
REASONING_EFFORT = "medium"

REPORTS_PATH = SEED_DATA_DIR / "long_patient_reports.json"
ARTIFACT_PATH = SEED_DATA_DIR / "long_patient_artifact.json"
BASELINE_ARTIFACT_PATH = SEED_DATA_DIR / "long_patient_artifact_baseline.json"

# Target lesion targets (matching the authored series from long_patient_reports.py).
TARGET_LUNG = "primary_tumor|thorax|left"
TARGET_LIVER = "liver_metastasis|liver|not_applicable"
TARGET_LUNG_METS = "lung_metastasis|thorax|right"
TARGET_KEYS = [TARGET_LUNG, TARGET_LIVER, TARGET_LUNG_METS]

# Stable machine track keys the engine produces for the routine negatives.
# These vary by LLM extraction so they are read from the artifact or kept as a set.
NEGATIVE_TRACK_KEYS_BY_TYPE: dict[str, list[str]] = {
    "ascites|peritoneum|not_applicable": [],
    "bone_metastasis|bone|not_applicable": [],
    "pleural_effusion|pleural_space|bilateral": [],
    "pneumothorax|pleural_space|not_applicable": [],
    "lymph_node_metastasis|lymph_node|not_applicable": [],
}


def _parse_dt(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _insert_missing_act_one_reviews(cur, org_id, patient_id, run_id, user_id, now) -> int:
    """Record a slot review for every confirmed track on a run that lacks one.

    Confirming identity and reviewing the frame's slots are different acts, and it is the
    REVIEW that puts the "reviewed" tick on a track card. Without these the workbench shows
    a fully-reviewed run as entirely outstanding.

    review_only tracks are skipped: the engine mints a per-report key for them so they
    never link across timepoints, and they are surfaced through the quarantine queue
    instead. Returns the number of rows inserted.
    """
    # EVERY track, including the per-report catch-all fragments. Act one is a full pass:
    # the reviewer read all of it. Reviewing only the eight linkable tracks left 37
    # fragments looking untouched, so the workbench showed a completed run as mostly
    # outstanding. Identity confirmation (link_decisions) still applies only to the
    # linkable tracks -- a per-report fragment has no longitudinal identity to attest.
    cur.execute(
        "select track_key from ff.tracks where run_id = %s order by track_key", (run_id,)
    )
    confirmable = [r["track_key"] for r in cur.fetchall()]
    cur.execute("select track_key from ff.reviews where run_id = %s", (run_id,))
    already = {r["track_key"] for r in cur.fetchall()}

    inserted = 0
    for track_key in confirmable:
        if track_key in already:
            continue
        cur.execute(
            "insert into ff.reviews (org_id, patient_id, run_id, track_key, reviewer_id, "
            "reviewed_value, link_correct, type_correct, progression_correct, "
            "latest_status_correct, false_merge, false_split, evidence_valid, "
            "clinically_significant, comment, review_kind, created_at) "
            "values (%s,%s,%s,%s,%s,%s::jsonb,true,true,true,true,false,false,true,%s,%s,"
            "'review',%s)",
            (org_id, patient_id, run_id, track_key, user_id,
             json.dumps({"seeded_act_one": True, "track_key": track_key}),
             track_key in TARGET_KEYS,
             "Reviewed against the source evidence during the initial pass.",
             now),
        )
        inserted += 1
    return inserted


def _carry_forward(org_id, run_id, applied_by) -> dict:
    """Run the real carry-forward service against this database and commit.

    Imported lazily and run in its own event loop so the seed stays a plain synchronous
    psycopg script everywhere else.
    """
    import asyncio
    import sys as _sys

    backend = str(FF_ROOT / "backend")
    if backend not in _sys.path:
        _sys.path.insert(0, backend)
    from app.db.session import get_sessionmaker  # noqa: PLC0415
    from app.services import carry_forward as cf  # noqa: PLC0415

    async def _run() -> dict:
        sm = get_sessionmaker()
        async with sm() as session:
            out = await cf.apply_carry_forward(
                session, org_id=org_id, run_id=run_id, applied_by=applied_by
            )
            await session.commit()
            return out

    return asyncio.run(_run())


def main() -> int:
    print("=== FindingFrame long-patient seed (SYNTHETIC) ===")
    for p in (REPORTS_PATH, ARTIFACT_PATH, BASELINE_ARTIFACT_PATH):
        if not p.exists():
            print(f"ERROR: frozen data missing: {p}\n  Run build_long_patient.py first.",
                  file=sys.stderr)
            return 1

    reports_doc = json.loads(REPORTS_PATH.read_text())
    artifact = json.loads(ARTIFACT_PATH.read_text())
    baseline_artifact = json.loads(BASELINE_ARTIFACT_PATH.read_text())
    subject_code = reports_doc["subject_code"]
    cancer_type = reports_doc["cancer_type"]
    reports = reports_doc["reports"]
    tracks = artifact["tracks"]
    baseline_tracks = baseline_artifact["tracks"]
    manifest = artifact.get("manifest", {})
    baseline_manifest = baseline_artifact.get("manifest", {})
    engine_git_sha = manifest.get("engine_git_sha", "")
    model_id = manifest.get("model_id", "deepseek/deepseek-v4-pro")
    prompt_version = manifest.get("prompt_version", "unknown")
    schema_version = manifest.get("schema_version", "unknown")

    env = load_env_file(BACKEND_ENV)
    database_url = resolve_database_url(env)
    if not database_url:
        print(f"ERROR: FF_DATABASE_URL missing from {BACKEND_ENV}", file=sys.stderr)
        return 1
    dsn = build_pg_dsn(database_url)

    with psycopg.connect(dsn, autocommit=False, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # -- org -----------------------------------------------------------
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

            # -- user ----------------------------------------------------------
            # Resolve the reviewer from ff.memberships, NOT auth.users. The least-privilege
            # ff_app role the product connects as has no rights on the `auth` schema at all
            # (it is Supabase-owned), so querying auth.users there does not return empty --
            # it raises `permission denied for schema auth` and aborts the transaction,
            # which a fallback placed after it can never catch. ff.memberships is in our own
            # schema, is what the app authorises against anyway, and seed_demo.py populates
            # it alongside the auth user.
            cur.execute(
                "select user_id from ff.memberships where org_id = %s order by role limit 1",
                (org_id,),
            )
            m = cur.fetchone()
            if not m:
                print("ERROR: no demo user in this org. Run seed_demo.py first.", file=sys.stderr)
                return 1
            user_id = m["user_id"]

            # -- idempotency ---------------------------------------------------
            cur.execute(
                "select id from ff.patients where org_id = %s and subject_code = %s",
                (org_id, subject_code),
            )
            existing = cur.fetchone()
            if existing:
                # Top up rather than no-op. An earlier revision of this script created both
                # runs but recorded no slot reviews and never applied carry-forward, so the
                # review workbench showed ten reports of settled work as outstanding. A
                # plain no-op leaves that broken forever, because the clinical tables are
                # append-only and cannot simply be re-seeded. Everything below is an INSERT
                # of something missing, so it is safe to re-run and safe under the triggers.
                patient_id = existing["id"]
                print(f"Patient {subject_code} already seeded ({patient_id}); topping up.")
                cur.execute(
                    "select id, run_kind from ff.extraction_runs where patient_id = %s "
                    "order by created_at",
                    (patient_id,),
                )
                runs = cur.fetchall()
                parent = next((r for r in runs if r["run_kind"] == "full"), None)
                child = next((r for r in runs if r["run_kind"] == "incremental"), None)
                if not parent or not child:
                    print("  ERROR: expected one full and one incremental run; found "
                          f"{[r['run_kind'] for r in runs]}", file=sys.stderr)
                    conn.rollback()
                    return 1
                added = _insert_missing_act_one_reviews(
                    cur, org_id, patient_id, parent["id"], user_id, datetime.now(timezone.utc)
                )
                print(f"  act-one slot reviews added: {added}")
                conn.commit()

                print("\nCarrying act one forward onto the incremental run (real service)...")
                result = _carry_forward(org_id, child["id"], user_id)
                print(f"  link decisions carried  : {result['carried_link_decisions']}")
                print(f"  reviews carried         : {result['carried_reviews']}")
                print(f"  acknowledgements written: {result['acknowledgements']}")
                print(f"  target selection carried: {result['carried_target_selection']}")
                print(f"  identities              : {result['counts']}")
                print(f"  RECIST {result['recist_call_before']} -> {result['recist_call_after']}")
                _verify(dsn, org_id, patient_id, subject_code)
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
                    "report_version_id": version_id,
                    "text_sha256": sha,
                    "chart_date": chart_date,
                }
            print(f"Inserted {len(report_version_map)} reports + report_versions")

            # -- helper: persist tracks/frames/events for a run ---------------
            def persist_run(run_id, trks: dict, rv_map: dict, include_reports: int):
                """Persist tracks, frames and track_events for a run."""
                n_tracks = n_frames = n_events = 0
                for track_key_base in sorted(trks):
                    track = trks[track_key_base]
                    section = clinical_section_for(track)
                    prog, prog_detail = progression_for(track)
                    cur.execute(
                        "insert into ff.tracks (run_id, org_id, patient_id, track_key, "
                        "finding_type, anatomy, laterality, latest_status, progression, "
                        "progression_detail, event_count, report_range, unresolved_link, "
                        "false_split_candidate, clinical_section) values "
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                        (run_id, org_id, patient_id, track_key_base,
                         track.get("finding_type"), track.get("anatomy"),
                         track.get("laterality"), track.get("latest_status"),
                         prog, prog_detail, track.get("event_count", 0),
                         report_range_for(track),
                         bool(track.get("unresolved_link", False)),
                         bool(track.get("false_split_candidate", False)),
                         section),
                    )
                    track_id = cur.fetchone()["id"]
                    n_tracks += 1

                    for ev in track.get("events", []):
                        sid = ev.get("source_report_id")
                        rv = rv_map.get(sid)
                        if rv is None:
                            continue
                        report_version_id = rv["report_version_id"]
                        span_start = ev.get("evidence_span_start")
                        span_end = ev.get("evidence_span_end")
                        evidence_verified = (
                            span_start is not None and span_end is not None
                            and span_start >= 0 and span_end >= 0
                        )
                        event_date = _parse_dt(ev.get("report_date"))
                        measurement = ev.get("measurement")
                        cur.execute(
                            "insert into ff.frames (run_id, org_id, patient_id, "
                            "report_version_id, source_report_id, frame_index, track_key, "
                            "finding_type, finding_surface, assertion, anatomy, laterality, "
                            "uncertainty, temporal_change, measurement, clinical_importance, "
                            "evidence_text, evidence_span_start, evidence_span_end, "
                            "evidence_verified, review_only, lesion_key) values "
                            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,"
                            "%s,%s,%s,%s,%s) returning id",
                            (run_id, org_id, patient_id, report_version_id, sid,
                             ev.get("frame_index"), ev.get("track_key", track_key_base),
                             ev.get("finding_type"), ev.get("finding_surface"),
                             ev.get("assertion", "present"), ev.get("anatomy"),
                             ev.get("laterality"), ev.get("uncertainty"),
                             ev.get("temporal_change"),
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
                            "report_version_id, event_date, assertion, evidence_text, "
                            "temporal_change, measurement) values "
                            "(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                            (track_id, frame_id, org_id, report_version_id, event_date,
                             ev.get("assertion", "present"), ev.get("evidence_text", ""),
                             ev.get("temporal_change"),
                             json.dumps(measurement) if measurement is not None else None),
                        )
                        n_events += 1
                return n_tracks, n_frames, n_events

            # ---- ACT ONE: Parent run (reports 1–10) -------------------------
            baselines_10 = {s: r for s, r in sorted(report_version_map.items(),
                                                     key=lambda kv: (kv[1]["chart_date"], kv[0]))
                            if s in {f"report_{i}" for i in range(1, 11)}}

            report_manifest_10 = [
                {"source_report_id": sid, "report_version_id": str(v["report_version_id"]),
                 "text_sha256": v["text_sha256"], "chart_date": v["chart_date"].isoformat()}
                for sid, v in sorted(baselines_10.items(),
                                     key=lambda kv: (kv[1]["chart_date"], kv[0]))
            ]

            manifest_payload_10 = json.dumps({
                "engine_git_sha": baseline_manifest.get("engine_git_sha", engine_git_sha),
                "model_provider": MODEL_PROVIDER,
                "model_id": baseline_manifest.get("model_id", model_id),
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "temperature": 0.0,
                "reasoning_effort": REASONING_EFFORT,
                "reports": report_manifest_10,
            }, sort_keys=True)
            manifest_hash_10 = _sha256(manifest_payload_10)

            cur.execute(
                "insert into ff.extraction_runs (org_id, patient_id, status, engine_git_sha, "
                "model_provider, model_id, prompt_version, schema_version, temperature, "
                "reasoning_effort, manifest_hash, report_manifest, attempts, progress_total, "
                "progress_done, run_kind, created_by, started_at, finished_at) values "
                "(%s,%s,'succeeded',%s,%s,%s,%s,%s,0.0,%s,%s,%s::jsonb,1,%s,%s,'full',%s,"
                "now(),now()) returning id",
                (org_id, patient_id, baseline_manifest.get("engine_git_sha", engine_git_sha),
                 MODEL_PROVIDER, baseline_manifest.get("model_id", model_id),
                 prompt_version, schema_version, REASONING_EFFORT, manifest_hash_10,
                 json.dumps(report_manifest_10), len(report_manifest_10),
                 len(report_manifest_10), user_id),
            )
            parent_run_id = cur.fetchone()["id"]
            print(f"Created parent run {parent_run_id} (full, {len(report_manifest_10)} reports)")

            nt, nf, ne = persist_run(parent_run_id, baseline_tracks, report_version_map, 10)
            print(f"  Inserted {nt} tracks, {nf} frames, {ne} track_events for parent run")

            # Act-one clinician work on the parent run:
            # 1. Confirm each target lesion (link_decision = "confirm")
            # 2. Set target lesion selection (RECIST targets: lung, liver, lung_mets)
            # 3. Clear the quarantine queue with reviews
            # 4. Sign-off

            now = datetime.now(timezone.utc)
            # Act one is a FULL clinician pass, not just the three targets. The reviewer
            # confirms every linkable track -- the measurable lesions and the routine
            # negatives alike. That matters for act two: the carried-forward count is the
            # demo's headline number, and it is only honest if the parent run really does
            # hold that many confirmed identities. Confirming only the targets would leave
            # nothing to carry and quietly understate the work being saved.
            #
            # review_only tracks are excluded: the engine mints a per-report key for them
            # (`|review_only|<report>|<kind>|<index>`) precisely so they never link across
            # timepoints, so there is no longitudinal identity to attest.
            cur.execute(
                "select track_key from ff.tracks where run_id = %s and track_key not like "
                "%s order by track_key",
                (parent_run_id, "%|review_only|%"),
            )
            confirmable = [r["track_key"] for r in cur.fetchall()]
            for track_key in confirmable:
                is_target = track_key in TARGET_KEYS
                cur.execute(
                    "insert into ff.link_decisions (org_id, patient_id, run_id, decision, "
                    "primary_track_key, resulting_track_key, rationale, decided_by, decided_at) "
                    "values (%s,%s,%s,'confirm',%s,%s,%s,%s,%s) returning id",
                    (org_id, patient_id, parent_run_id, track_key, track_key,
                     "Target lesion identity confirmed. Consistent appearance across "
                     "all imaging timepoints." if is_target else
                     "Identity confirmed on review of the source evidence.",
                     user_id, now),
                )
            print(f"  Inserted link decisions confirming {len(confirmable)} tracks "
                  f"({len(TARGET_KEYS)} target lesions, "
                  f"{len(confirmable) - len(TARGET_KEYS)} other findings)")

            # Act-one slot reviews (see _insert_missing_act_one_reviews).
            added = _insert_missing_act_one_reviews(
                cur, org_id, patient_id, parent_run_id, user_id, now
            )
            print(f"  Inserted {added} act-one slot reviews")

            # Act-one target lesion selection.
            recist_doc = json.loads((SEED_DATA_DIR / "long_patient_recist.json").read_text())
            selections = [
                {"confirmed_track_key": t["track_key"], "organ": t["name"], "baseline_mm": t["baseline_mm"]}
                for t in recist_doc.get("targets", [])
            ]
            # Baseline report version = first report's version.
            baseline_rvid = report_version_map["report_1"]["report_version_id"]
            cur.execute(
                "insert into ff.target_lesion_selections (org_id, patient_id, run_id, "
                "baseline_report_version_id, selections, selected_by, selected_at) "
                "values (%s,%s,%s,%s,%s::jsonb,%s,%s) returning id",
                (org_id, patient_id, parent_run_id, baseline_rvid,
                 json.dumps(selections), user_id, now),
            )
            print("  Inserted target lesion selection")

            # Act-one sign-off.
            signoff_payload = json.dumps({
                "run_id": str(parent_run_id),
                "patient_id": str(patient_id),
                "scope": "patient",
                "targets": selections,
                "confirmed_track_count": len(TARGET_KEYS),
                "signed_at": now.isoformat(),
            }, sort_keys=True)
            cur.execute(
                "insert into ff.signoffs (org_id, patient_id, run_id, scope, payload, "
                "signed_by, signed_at) values (%s,%s,%s,'patient',%s::jsonb,%s,%s) returning id",
                (org_id, patient_id, parent_run_id, signoff_payload, user_id, now),
            )
            print("  Inserted sign-off")

            # ---- ACT TWO: Incremental run (all 11 reports) ------------------
            all_11 = {s: r for s, r in sorted(report_version_map.items(),
                                              key=lambda kv: (kv[1]["chart_date"], kv[0]))}

            report_manifest_11 = [
                {"source_report_id": sid, "report_version_id": str(v["report_version_id"]),
                 "text_sha256": v["text_sha256"], "chart_date": v["chart_date"].isoformat()}
                for sid, v in sorted(all_11.items(),
                                     key=lambda kv: (kv[1]["chart_date"], kv[0]))
            ]

            manifest_payload_11 = json.dumps({
                "engine_git_sha": manifest.get("engine_git_sha", engine_git_sha),
                "model_provider": MODEL_PROVIDER,
                "model_id": manifest.get("model_id", model_id),
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "temperature": 0.0,
                "reasoning_effort": REASONING_EFFORT,
                "reports": report_manifest_11,
            }, sort_keys=True)
            manifest_hash_11 = _sha256(manifest_payload_11)

            # extraction_provenance: 10 cache-served, 1 freshly extracted.
            fresh = report_version_map.get("report_11", {})
            extraction_provenance = {
                "cache_served": [
                    {"source_report_id": sid, "report_version_id": str(rv["report_version_id"]),
                     "text_sha256": rv["text_sha256"], "chart_date": rv["chart_date"].isoformat()}
                    for sid, rv in all_11.items() if sid != "report_11"
                ],
                "freshly_extracted": [
                    {"source_report_id": "report_11",
                     "report_version_id": str(fresh.get("report_version_id", "")),
                     "text_sha256": fresh.get("text_sha256", ""),
                     "chart_date": (fresh.get("chart_date", "")).isoformat()
                     if isinstance(fresh.get("chart_date"), datetime) else fresh.get("chart_date", "")}
                ],
                "llm_calls": 1,
                "reports_total": 11,
            }

            cur.execute(
                "insert into ff.extraction_runs (org_id, patient_id, status, engine_git_sha, "
                "model_provider, model_id, prompt_version, schema_version, temperature, "
                "reasoning_effort, manifest_hash, report_manifest, attempts, progress_total, "
                "progress_done, run_kind, parent_run_id, extraction_provenance, created_by, "
                "started_at, finished_at) values "
                "(%s,%s,'succeeded',%s,%s,%s,%s,%s,0.0,%s,%s,%s::jsonb,1,%s,%s,'incremental',"
                "%s,%s::jsonb,%s,now(),now()) returning id",
                (org_id, patient_id, manifest.get("engine_git_sha", engine_git_sha),
                 MODEL_PROVIDER, manifest.get("model_id", model_id),
                 prompt_version, schema_version, REASONING_EFFORT, manifest_hash_11,
                 json.dumps(report_manifest_11), len(report_manifest_11),
                 len(report_manifest_11), parent_run_id,
                 json.dumps(extraction_provenance), user_id),
            )
            child_run_id = cur.fetchone()["id"]
            print(f"Created incremental run {child_run_id} (incremental, parent={parent_run_id})")

            nt2, nf2, ne2 = persist_run(child_run_id, tracks, report_version_map, 11)
            print(f"  Inserted {nt2} tracks, {nf2} frames, {ne2} track_events for child run")

        conn.commit()

    # Replay act one onto the child run, through the REAL service rather than more SQL.
    # In production the worker does this after a successful incremental run; a seeded run
    # never goes through the worker, so without this call the child ends up with zero
    # carried decisions and the workbench shows ten reports of settled work as outstanding.
    # Using the service (not a SQL copy) also means the seed exercises the same gate the
    # product does, so a bug there fails the seed instead of hiding in it.
    print("\nCarrying act one forward onto the incremental run (real service)...")
    result = _carry_forward(org_id, child_run_id, user_id)
    print(f"  link decisions carried : {result['carried_link_decisions']}")
    print(f"  reviews carried        : {result['carried_reviews']}")
    print(f"  acknowledgements written: {result['acknowledgements']}")
    print(f"  target selection carried: {result['carried_target_selection']}")
    print(f"  identities              : {result['counts']}")
    print(f"  RECIST {result['recist_call_before']} -> {result['recist_call_after']}")

    _verify(dsn, org_id, patient_id, subject_code)
    print("\n=== Seeded (SYNTHETIC long patient) ===")
    print(f"  org:         {DEMO_ORG_NAME} ({org_id})")
    print(f"  patient:     {subject_code} ({patient_id})")
    print(f"  parent run:  {parent_run_id} (full, reports 1-10, signed)")
    print(f"  child run:   {child_run_id} (incremental, reports 1-11, parent={parent_run_id})")
    print(f"  provenance:  {extraction_provenance['llm_calls']} LLM call(s) for report 11")
    print("Done.")
    return 0


def _verify(dsn: str, org_id, patient_id, subject_code: str) -> None:
    print("\n=== Verification ===")
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for table in ("reports", "extraction_runs", "tracks", "frames", "link_decisions"):
                cur.execute(f"select count(*) c from ff.{table} where patient_id = %s",
                            (patient_id,))
                print(f"  ff.{table} (patient {subject_code}): {cur.fetchone()['c']}")
            cur.execute(
                "select count(*) c from ff.track_events te join ff.tracks t on t.id = te.track_id "
                "where t.patient_id = %s", (patient_id,))
            print(f"  ff.track_events (patient {subject_code}): {cur.fetchone()['c']}")
            cur.execute(
                "select run_kind, parent_run_id is not null as has_parent, status "
                "from ff.extraction_runs where patient_id = %s order by created_at",
                (patient_id,))
            for r in cur.fetchall():
                print(f"  run: kind={r['run_kind']} has_parent={r['has_parent']} "
                      f"status={r['status']}")


if __name__ == "__main__":
    raise SystemExit(main())
