#!/usr/bin/env python3
"""FindingFrame — demo bootstrap for the R6 vertical slice.

Idempotent. Run with the backend venv:
    backend/.venv/bin/python infra/scripts/seed_demo.py

What it does:
  1. Creates (or reuses) a demo org "Tata Memorial (Demo)".
  2. Creates (or reuses) a CONFIRMED demo auth user (demo@findingframe.dev / demo1234)
     directly via SQL against Supabase's `auth` schema (auth.users + auth.identities),
     so password login works against modern GoTrue. Creates matching ff.profiles +
     ff.memberships(role=admin) in the demo org.
  3. Ingests the precomputed patient 10000935 as a COMPLETED extraction run, sourced
     from tmc's evaluation packet + raw report text, so the product is demoable
     without a live LLM key:
       - tmc/evaluation/track_annotations/full_review_packet_10000935.json (tracks/events)
       - tmc/outputs/paired_v1/subject_10000935_raw_reports.md (source report text)

     NOTE on idempotency (migration 0003_integrity.sql): frames/tracks/track_events/
     reviews/link_decisions/target_lesion_selections/recist_assessments/signoffs are
     now append-only via BEFORE UPDATE/DELETE triggers that fire for every role,
     including the superuser DSN this script connects as — so a plain DELETE FROM
     ff.patients no longer cascades (patient_id FKs are also ON DELETE RESTRICT as of
     0003). Re-running this script therefore TRUNCATEs the demo-relevant tables
     (RESTART IDENTITY CASCADE — TRUNCATE bypasses row-level triggers and pulls in any
     FK-dependent rows even if not listed) before re-inserting. This is a demo
     bootstrap script: it assumes it owns these tables' contents in this environment.
  4. Verifies the demo user can obtain an access_token via GoTrue's password grant.

Prints row counts and credentials at the end.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

# --- repo layout -------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
PRE_DIR = FF_ROOT.parent
BACKEND_ENV = FF_ROOT / "backend" / ".env"
TMC_DIR = PRE_DIR / "tmc"
PACKET_PATH = TMC_DIR / "evaluation" / "track_annotations" / "full_review_packet_10000935.json"
RAW_REPORTS_PATH = TMC_DIR / "outputs" / "paired_v1" / "subject_10000935_raw_reports.md"

DEMO_ORG_NAME = "Tata Memorial (Demo)"
DEMO_EMAIL = "demo@findingframe.dev"
DEMO_PASSWORD = "demo1234"
DEMO_FULL_NAME = "Demo Reviewer"
SUBJECT_CODE = "10000935"
CANCER_TYPE = "gastric"
MODEL_ID = "openai/gpt-5.5"
MODEL_PROVIDER = "openrouter"
REASONING_EFFORT = "medium"

# --- psycopg: install into this venv if missing (per BUILD task instructions) ----
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("psycopg not found; installing psycopg[binary] into this interpreter's venv ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg[binary]"], check=True)
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def build_pg_dsn(database_url: str) -> str:
    """postgresql(+asyncpg)://user:pass@host:port/db -> a plain libpq DSN string."""
    scheme, _, rest = database_url.partition("://")
    if "+" in scheme:
        scheme = "postgresql"
    u = urlsplit(f"{scheme}://{rest}")
    dbname = (u.path or "/postgres").lstrip("/") or "postgres"
    user = unquote(u.username or "postgres")
    password = unquote(u.password or "")
    host = u.hostname or ""
    port = u.port or 5432
    # psycopg conninfo handles special chars fine when passed as kwargs; build via
    # psycopg.conninfo to be safe with quoting.
    from psycopg.conninfo import make_conninfo

    return make_conninfo(
        host=host, port=port, user=user, password=password, dbname=dbname, sslmode="require",
    )


def resolve_git_sha(repo_path: Path) -> str:
    """HEAD sha, suffixed "+dirty" when the checkout has uncommitted changes.

    Mirrors backend/app/engine/adapter.py::_resolve_git_sha — keep the two in sync so a
    seeded run and a live run label engine provenance identically.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return ""
        sha = out.stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if status.returncode == 0 and status.stdout.strip():
            return f"{sha}+dirty"
        return sha
    except Exception:
        return ""


def resolve_prompt_schema_versions(tmc_dir: Path) -> tuple[str, str]:
    """Best-effort import of the engine's version constants (mirrors app/engine/adapter.py)."""
    prompt_version = "unknown"
    schema_version = "unknown"
    engine_path = str(tmc_dir.resolve())
    if engine_path not in sys.path:
        sys.path.insert(0, engine_path)
    try:
        from extraction.finding_frame_extractor import _PROMPT_VERSION  # type: ignore
        prompt_version = _PROMPT_VERSION
    except Exception as exc:
        print(f"  (warn) could not import prompt version: {exc}")
    try:
        from extraction.finding_frame_schema import SCHEMA_VERSION  # type: ignore
        schema_version = SCHEMA_VERSION
    except Exception as exc:
        print(f"  (warn) could not import schema version: {exc}")
    return prompt_version, schema_version


# --- raw report parsing -------------------------------------------------------
REPORT_BLOCK_RE = re.compile(
    r"## Report (?P<num>\d+)\n\n"
    r"- \*\*Date:\*\* (?P<date>[^\n]+)\n"
    r"- \*\*Note ID:\*\* (?P<note_id>[^\n]+)\n"
    r"- \*\*Type:\*\* (?P<type>[^\n]+)\n\n"
    r"### Report Text\n\n"
    r"(?P<text>.*?)"
    r"(?=\n\n---\n|\Z)",
    re.DOTALL,
)


def parse_raw_reports(md_path: Path) -> dict[str, dict]:
    content = md_path.read_text()
    reports: dict[str, dict] = {}
    for m in REPORT_BLOCK_RE.finditer(content):
        num = int(m.group("num"))
        source_report_id = f"report_{num}"
        reports[source_report_id] = {
            "chart_date": datetime.strptime(m.group("date").strip(), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            ),
            "note_id": m.group("note_id").strip(),
            "note_type": m.group("type").strip(),
            "text": m.group("text").strip("\n"),
        }
    return reports


# --- clinical_section / progression heuristics (packet has no explicit fields) --
def clinical_section_for(track: dict) -> str:
    status = track.get("latest_status") or "uncertain"
    if status == "resolved":
        return "resolved"
    if status == "uncertain":
        return "uncertain"
    if status == "absent":
        return "routine_negatives"
    if status == "active":
        events = track.get("events") or []
        latest_importance = events[-1].get("clinical_importance") if events else None
        if latest_importance == "high":
            return "needs_attention"
        return "stable"
    return "uncertain"


TEMPORAL_TO_PROGRESSION = {
    "increased": "progressing",
    "decreased": "improving",
    "new": "new",
    "stable": "stable",
    "not_stated": None,
}


def progression_for(track: dict) -> tuple[str | None, str | None]:
    events = track.get("events") or []
    if not events:
        return None, None
    latest_tc = events[-1].get("temporal_change")
    return TEMPORAL_TO_PROGRESSION.get(latest_tc), latest_tc


def report_range_for(track: dict) -> str | None:
    events = track.get("events") or []
    if not events:
        return None
    dates = sorted(e.get("report_date") for e in events if e.get("report_date"))
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0]
    return f"{dates[0]} to {dates[-1]}"


def main() -> int:
    print("=== FindingFrame demo seed ===")

    if not PACKET_PATH.exists():
        print(f"ERROR: packet not found: {PACKET_PATH}", file=sys.stderr)
        return 1
    if not RAW_REPORTS_PATH.exists():
        print(f"ERROR: raw reports not found: {RAW_REPORTS_PATH}", file=sys.stderr)
        return 1

    env = load_env_file(BACKEND_ENV)
    database_url = env.get("FF_DATABASE_URL", "")
    if not database_url:
        print(f"ERROR: FF_DATABASE_URL missing from {BACKEND_ENV}", file=sys.stderr)
        return 1
    supabase_url = env.get("FF_SUPABASE_URL", "")
    publishable_key = env.get("FF_SUPABASE_PUBLISHABLE_KEY", "")

    dsn = build_pg_dsn(database_url)

    print(f"Loading packet: {PACKET_PATH}")
    packet = json.loads(PACKET_PATH.read_text())
    tracks = packet["tracks"]
    print(f"  {packet['report_count']} reports, {packet['track_count']} tracks in packet")

    print(f"Parsing raw reports: {RAW_REPORTS_PATH}")
    raw_reports = parse_raw_reports(RAW_REPORTS_PATH)
    print(f"  parsed {len(raw_reports)} report blocks")
    if len(raw_reports) != packet["report_count"]:
        print(
            f"  (warn) parsed count ({len(raw_reports)}) != packet report_count "
            f"({packet['report_count']})"
        )

    engine_git_sha = resolve_git_sha(TMC_DIR)
    prompt_version, schema_version = resolve_prompt_schema_versions(TMC_DIR)
    print(f"Engine: git_sha={engine_git_sha[:12]}... prompt_version={prompt_version} "
          f"schema_version={schema_version}")

    with psycopg.connect(dsn, autocommit=False, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # ---------------------------------------------------------------
            # 1. Demo org
            # ---------------------------------------------------------------
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

            # ---------------------------------------------------------------
            # 2. Demo confirmed auth user + identity + profile + membership
            # ---------------------------------------------------------------
            cur.execute("select id from auth.users where email = %s", (DEMO_EMAIL,))
            row = cur.fetchone()
            if row:
                user_id = row["id"]
                print(f"Demo user exists: {DEMO_EMAIL} ({user_id})")
                # Make sure the password matches what we're about to report/verify.
                cur.execute(
                    """
                    update auth.users
                    set encrypted_password = crypt(%s, gen_salt('bf')),
                        email_confirmed_at = coalesce(email_confirmed_at, now()),
                        updated_at = now()
                    where id = %s
                    """,
                    (DEMO_PASSWORD, user_id),
                )
            else:
                cur.execute(
                    """
                    insert into auth.users (
                        instance_id, id, aud, role, email, encrypted_password,
                        email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
                        is_super_admin, created_at, updated_at, confirmation_token,
                        recovery_token, email_change_token_new, email_change,
                        is_sso_user, is_anonymous
                    ) values (
                        '00000000-0000-0000-0000-000000000000',
                        gen_random_uuid(), 'authenticated', 'authenticated', %s,
                        crypt(%s, gen_salt('bf')), now(),
                        '{"provider":"email","providers":["email"]}'::jsonb,
                        jsonb_build_object('full_name', %s::text),
                        false, now(), now(), '', '', '', '',
                        false, false
                    )
                    returning id
                    """,
                    (DEMO_EMAIL, DEMO_PASSWORD, DEMO_FULL_NAME),
                )
                user_id = cur.fetchone()["id"]
                print(f"Created demo user: {DEMO_EMAIL} ({user_id})")

            cur.execute("select 1 from auth.identities where provider = 'email' and provider_id = %s", (DEMO_EMAIL,))
            if not cur.fetchone():
                cur.execute(
                    """
                    insert into auth.identities (
                        id, provider_id, user_id, identity_data, provider,
                        last_sign_in_at, created_at, updated_at
                    ) values (
                        gen_random_uuid(), %s, %s,
                        jsonb_build_object('sub', %s::text, 'email', %s::text),
                        'email', now(), now(), now()
                    )
                    """,
                    (DEMO_EMAIL, user_id, str(user_id), DEMO_EMAIL),
                )
                print("Created matching auth.identities row (provider=email)")
            else:
                print("auth.identities row already present")

            cur.execute(
                """
                insert into ff.profiles (id, full_name)
                values (%s, %s)
                on conflict (id) do update set full_name = excluded.full_name
                """,
                (user_id, DEMO_FULL_NAME),
            )
            cur.execute(
                """
                insert into ff.memberships (org_id, user_id, role)
                values (%s, %s, 'admin')
                on conflict (org_id, user_id) do update set role = excluded.role
                """,
                (org_id, user_id),
            )
            print(f"Ensured ff.profiles + ff.memberships(role=admin) for {DEMO_EMAIL} in {DEMO_ORG_NAME}")

            # ---------------------------------------------------------------
            # 3. Ingest patient 10000935 (idempotent via TRUNCATE reset)
            # ---------------------------------------------------------------
            # As of migration 0003_integrity.sql, frames/tracks/track_events/reviews/
            # link_decisions/target_lesion_selections/recist_assessments/signoffs are
            # append-only (BEFORE UPDATE/DELETE triggers fire for every role, including
            # this superuser DSN), and patient_id FKs are ON DELETE RESTRICT. A plain
            # DELETE FROM ff.patients therefore can no longer cascade. TRUNCATE bypasses
            # row-level triggers and (with CASCADE) pulls in any FK-dependent rows even
            # if not explicitly listed, so it is the supported reset path for this demo
            # bootstrap script. This clears ALL rows in these tables, not just the demo
            # subject's — acceptable here because this script assumes it owns demo-env
            # data end-to-end (ff.orgs/profiles/memberships are left untouched).
            print("Resetting demo-owned clinical tables (TRUNCATE ... RESTART IDENTITY CASCADE) ...")
            cur.execute(
                """
                truncate table
                    ff.signoffs, ff.recist_assessments, ff.target_lesion_selections,
                    ff.link_decisions, ff.reviews, ff.track_events, ff.frames, ff.tracks,
                    ff.report_versions, ff.reports, ff.extraction_runs, ff.patients
                restart identity cascade
                """
            )

            cur.execute(
                """
                insert into ff.patients (org_id, subject_code, cancer_type, created_by)
                values (%s, %s, %s, %s)
                returning id
                """,
                (org_id, SUBJECT_CODE, CANCER_TYPE, user_id),
            )
            patient_id = cur.fetchone()["id"]
            print(f"Created patient {SUBJECT_CODE} ({patient_id})")

            # Reports + report_versions -------------------------------------------------
            report_version_map: dict[str, dict] = {}  # source_report_id -> {report_id, version_id, sha256, chart_date}
            for source_report_id in sorted(raw_reports, key=lambda k: int(k.split("_")[1])):
                r = raw_reports[source_report_id]
                cur.execute(
                    """
                    insert into ff.reports (org_id, patient_id, report_date, note_type, external_note_id, created_by)
                    values (%s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                    (org_id, patient_id, r["chart_date"], r["note_type"], r["note_id"], user_id),
                )
                report_id = cur.fetchone()["id"]
                sha = _sha256(r["text"])
                cur.execute(
                    """
                    insert into ff.report_versions (report_id, org_id, version_no, text, text_sha256, is_addendum, created_by)
                    values (%s, %s, 1, %s, %s, false, %s)
                    returning id
                    """,
                    (report_id, org_id, r["text"], sha, user_id),
                )
                version_id = cur.fetchone()["id"]
                report_version_map[source_report_id] = {
                    "report_id": report_id,
                    "report_version_id": version_id,
                    "text_sha256": sha,
                    "chart_date": r["chart_date"],
                }
            print(f"Inserted {len(report_version_map)} reports + report_versions")

            # Extraction run (immutable manifest) ----------------------------------------
            report_manifest = [
                {
                    "source_report_id": sid,
                    "report_version_id": str(v["report_version_id"]),
                    "text_sha256": v["text_sha256"],
                    "chart_date": v["chart_date"].isoformat(),
                }
                for sid, v in sorted(report_version_map.items(), key=lambda kv: (kv[1]["chart_date"], kv[0]))
            ]
            manifest_payload = json.dumps(
                {
                    "engine_git_sha": engine_git_sha,
                    "model_provider": MODEL_PROVIDER,
                    "model_id": MODEL_ID,
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
                """
                insert into ff.extraction_runs (
                    org_id, patient_id, status, engine_git_sha, model_provider, model_id,
                    prompt_version, schema_version, temperature, reasoning_effort,
                    manifest_hash, report_manifest, attempts, progress_total, progress_done,
                    created_by, started_at, finished_at
                ) values (
                    %s, %s, 'succeeded', %s, %s, %s, %s, %s, 0.0, %s, %s, %s::jsonb,
                    1, %s, %s, %s, now(), now()
                )
                returning id
                """,
                (
                    org_id, patient_id, engine_git_sha, MODEL_PROVIDER, MODEL_ID,
                    prompt_version, schema_version, REASONING_EFFORT, manifest_hash,
                    json.dumps(report_manifest), len(report_manifest), len(report_manifest), user_id,
                ),
            )
            run_id = cur.fetchone()["id"]
            print(f"Created extraction_run {run_id} (status=succeeded, manifest_hash={manifest_hash[:12]}...)")

            # Tracks + frames + track_events ----------------------------------------------
            n_tracks = n_frames = n_events = 0
            for track in tracks:
                section = clinical_section_for(track)
                progression, progression_detail = progression_for(track)
                cur.execute(
                    """
                    insert into ff.tracks (
                        run_id, org_id, patient_id, track_key, finding_type, anatomy, laterality,
                        latest_status, progression, progression_detail, event_count, report_range,
                        unresolved_link, false_split_candidate, clinical_section
                    ) values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    on conflict (run_id, track_key) do nothing
                    returning id
                    """,
                    (
                        run_id, org_id, patient_id, track["track_key"], track.get("finding_type"),
                        track.get("anatomy"), track.get("laterality"), track.get("latest_status"),
                        progression, progression_detail, track.get("event_count", 0),
                        report_range_for(track),
                        bool(track.get("unresolved_link", False)),
                        # Packet has no explicit false_split_candidate flag; contains_compatible_merges
                        # is the closest available signal (a track whose events include a compatible-merge
                        # opportunity), used here as a sensible default per the build spec.
                        bool(track.get("contains_compatible_merges", False)),
                        section,
                    ),
                )
                track_row = cur.fetchone()
                if track_row is None:
                    # Should not happen right after a TRUNCATE reset, but guard anyway.
                    cur.execute(
                        "select id from ff.tracks where run_id = %s and track_key = %s",
                        (run_id, track["track_key"]),
                    )
                    track_row = cur.fetchone()
                track_id = track_row["id"]
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
                    event_date = None
                    if ev.get("report_date"):
                        try:
                            event_date = datetime.strptime(ev["report_date"], "%Y-%m-%d %H:%M:%S").replace(
                                tzinfo=timezone.utc
                            )
                        except ValueError:
                            event_date = None

                    measurement = ev.get("measurement")
                    cur.execute(
                        """
                        insert into ff.frames (
                            run_id, org_id, patient_id, report_version_id, source_report_id,
                            frame_index, track_key, finding_type, finding_surface, assertion,
                            anatomy, laterality, uncertainty, temporal_change, measurement,
                            clinical_importance, evidence_text, evidence_span_start, evidence_span_end,
                            evidence_verified, review_only, lesion_key
                        ) values (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                            %s, %s, %s, %s, %s, %s, %s
                        )
                        returning id
                        """,
                        (
                            run_id, org_id, patient_id, report_version_id, sid,
                            ev.get("frame_index"), ev.get("track_key", track["track_key"]),
                            ev.get("finding_type"), ev.get("finding_surface"), ev.get("assertion", "present"),
                            ev.get("anatomy"), ev.get("laterality"), ev.get("uncertainty"),
                            ev.get("temporal_change"),
                            json.dumps(measurement) if measurement is not None else None,
                            ev.get("clinical_importance"), ev.get("evidence_text", ""),
                            span_start if span_start is not None else -1,
                            span_end if span_end is not None else -1,
                            evidence_verified, bool(ev.get("review_only", False)), ev.get("lesion_key"),
                        ),
                    )
                    frame_id = cur.fetchone()["id"]
                    n_frames += 1

                    cur.execute(
                        """
                        insert into ff.track_events (
                            track_id, frame_id, org_id, report_version_id, event_date,
                            assertion, evidence_text, temporal_change, measurement
                        ) values (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                        )
                        """,
                        (
                            track_id, frame_id, org_id, report_version_id, event_date,
                            ev.get("assertion", "present"), ev.get("evidence_text", ""),
                            ev.get("temporal_change"),
                            json.dumps(measurement) if measurement is not None else None,
                        ),
                    )
                    n_events += 1

            print(f"Inserted {n_tracks} tracks, {n_frames} frames, {n_events} track_events")

        conn.commit()

    # ---------------------------------------------------------------------------
    # 4. Verify counts + login
    # ---------------------------------------------------------------------------
    print("\n=== Verification ===")
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for label, sql in [
                ("orgs", "select count(*) c from ff.orgs where name = %s"),
                ("patients", "select count(*) c from ff.patients where subject_code = %s"),
            ]:
                cur.execute(sql, (DEMO_ORG_NAME if label == "orgs" else SUBJECT_CODE,))
                print(f"  ff.{label}: {cur.fetchone()['c']}")
            direct_tables = ["reports", "extraction_runs", "tracks", "frames"]
            for table in direct_tables:
                cur.execute(
                    f"select count(*) c from ff.{table} where patient_id = %s", (patient_id,)
                )
                print(f"  ff.{table} (patient {SUBJECT_CODE}): {cur.fetchone()['c']}")
            # report_versions has no patient_id column directly; join via reports.
            cur.execute(
                """
                select count(*) c from ff.report_versions rv
                join ff.reports r on r.id = rv.report_id
                where r.patient_id = %s
                """,
                (patient_id,),
            )
            print(f"  ff.report_versions (patient {SUBJECT_CODE}): {cur.fetchone()['c']}")
            # track_events has no patient_id column directly; join via tracks.
            cur.execute(
                """
                select count(*) c from ff.track_events te
                join ff.tracks t on t.id = te.track_id
                where t.patient_id = %s
                """,
                (patient_id,),
            )
            print(f"  ff.track_events (patient {SUBJECT_CODE}): {cur.fetchone()['c']}")

    if supabase_url and publishable_key:
        print(f"\nVerifying password login for {DEMO_EMAIL} ...")
        token_url = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
        body = json.dumps({"email": DEMO_EMAIL, "password": DEMO_PASSWORD}).encode()
        req = urllib.request.Request(
            token_url, data=body, method="POST",
            headers={
                "apikey": publishable_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            if data.get("access_token"):
                print(f"  OK: got access_token (len={len(data['access_token'])}), "
                      f"token_type={data.get('token_type')}, expires_in={data.get('expires_in')}")
            else:
                print(f"  WARN: no access_token in response: {data}")
        except urllib.error.HTTPError as e:
            print(f"  FAILED: HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            return 1
    else:
        print("\nSkipping login verification (FF_SUPABASE_URL / FF_SUPABASE_PUBLISHABLE_KEY not set)")

    print("\n=== Demo credentials ===")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")
    print(f"  org:      {DEMO_ORG_NAME} ({org_id})")
    print(f"  patient:  {SUBJECT_CODE} ({patient_id}), run {run_id}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
