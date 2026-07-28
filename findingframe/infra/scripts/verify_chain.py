#!/usr/bin/env python3
"""FindingFrame — independent hash-chain verifier ("verify the audit trail yourself").

Walks the two DB-computed hash chains from genesis and INDEPENDENTLY recomputes every
hash in Python, using the EXACT preimage format the triggers in
infra/supabase/migrations/0003_integrity.sql use:

  ff.signoffs   — chained per (org_id, patient_id):
      payload_sha256 = sha256( coalesce(payload::text,'') )
      row_sha256     = sha256(
          coalesce(prev,'GENESIS') || '|' || payload_sha256 || '|' ||
          coalesce(run_id::text,'') || '|' || scope::text || '|' ||
          signed_by::text || '|' || coalesce(signed_at::text, now()::text) )
      prev = row_sha256 of the previous sign-off for the same (org_id, patient_id),
             NULL for genesis.

  ff.audit_log  — chained per org_id:
      row_hash = sha256(
          coalesce(prev,'GENESIS') || '|' || action || '|' ||
          coalesce(entity_type,'') || '|' || coalesce(entity_id,'') || '|' ||
          coalesce(actor_id::text,'system') || '|' || coalesce(before::text,'') || '|' ||
          coalesce(after::text,'') || '|' || coalesce(created_at::text, now()::text) )
      prev = row_hash of the previous audit row for the same org_id, NULL for genesis.

The jsonb / timestamptz / uuid / enum fields are rendered to text BY POSTGRES (``::text``)
in this verifier's own SELECT — the same casts the triggers used — and the ONLY thing this
script does is the '|' concatenation + UTF8 sha256, so the recomputation is a genuine
independent check of the stored hashes. It connects without changing the session TimeZone,
so timestamptz::text renders identically to the writing session (both use the server
default).

For each chain it checks:
  * genesis has NULL prev; every other row's stored prev == the previous row's stored hash
    (no gaps, no forks — two rows sharing a prev is a fork),
  * recomputed payload_sha256 / row_sha256 / row_hash == the stored value (no tampering).

Prints a per-chain PASS/FAIL summary. Exit 0 iff every chain verifies, else 1.

Run with the backend venv:
    backend/.venv/bin/python infra/scripts/verify_chain.py [--org-id UUID | --org-name NAME]
                                                            [--patient-id UUID | --patient-code CODE]
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

# --- repo layout (mirror seed_demo.py) ---------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_ENV = FF_ROOT / "backend" / ".env"

DEMO_ORG_NAME = "Tata Memorial (Demo)"

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("psycopg not found; installing psycopg[binary] into this interpreter's venv ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg[binary]"], check=True)
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore


# --- env + DSN (copied from seed_demo.py so we connect the same way) ---------
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
    scheme, _, rest = database_url.partition("://")
    if "+" in scheme:
        scheme = "postgresql"
    u = urlsplit(f"{scheme}://{rest}")
    dbname = (u.path or "/postgres").lstrip("/") or "postgres"
    from psycopg.conninfo import make_conninfo

    return make_conninfo(
        host=u.hostname or "",
        port=u.port or 5432,
        user=unquote(u.username or "postgres"),
        password=unquote(u.password or ""),
        dbname=dbname,
        sslmode="require",
    )


# --- the ONLY crypto we do: '|' join + UTF8 sha256 ---------------------------
def _sha256_utf8(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class ChainResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows = 0
        self.errors: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


# --- signoffs: chain per (org_id, patient_id) --------------------------------
def verify_signoff_chain(rows: list[dict], label: str) -> ChainResult:
    res = ChainResult(f"signoffs[{label}]")
    res.rows = len(rows)
    expected_prev: str | None = None
    seen_prev: set[str] = set()
    for i, r in enumerate(rows):
        stored_prev = r["prev_signoff_sha256"]
        # linkage: genesis prev is NULL; every other row links the previous row's hash.
        if i == 0:
            if stored_prev is not None:
                res.fail(f"id={r['id']}: genesis row has non-null prev {stored_prev!r}")
        else:
            if stored_prev != expected_prev:
                res.fail(
                    f"id={r['id']}: broken linkage — stored prev {stored_prev!r} "
                    f"!= previous row hash {expected_prev!r}"
                )
        if stored_prev is not None:
            if stored_prev in seen_prev:
                res.fail(f"id={r['id']}: FORK — prev {stored_prev!r} referenced twice")
            seen_prev.add(stored_prev)

        # recompute payload_sha256
        recomputed_payload = _sha256_utf8(r["payload_text"] or "")
        if recomputed_payload != r["payload_sha256"]:
            res.fail(
                f"id={r['id']}: payload_sha256 mismatch "
                f"(stored {r['payload_sha256']}, recomputed {recomputed_payload})"
            )

        # recompute row_sha256 using the EXACT trigger preimage
        head = stored_prev if stored_prev is not None else "GENESIS"
        preimage = "|".join(
            [
                head,
                r["payload_sha256"],
                r["run_id_text"],
                r["scope_text"],
                r["signed_by_text"],
                r["signed_at_text"],
            ]
        )
        recomputed_row = _sha256_utf8(preimage)
        if recomputed_row != r["row_sha256"]:
            res.fail(
                f"id={r['id']}: row_sha256 mismatch "
                f"(stored {r['row_sha256']}, recomputed {recomputed_row})"
            )
        expected_prev = r["row_sha256"]
    return res


# --- audit_log: chain per org_id ---------------------------------------------
def verify_audit_chain(rows: list[dict], label: str) -> ChainResult:
    res = ChainResult(f"audit_log[{label}]")
    res.rows = len(rows)
    expected_prev: str | None = None
    seen_prev: set[str] = set()
    for i, r in enumerate(rows):
        stored_prev = r["prev_hash"]
        if i == 0:
            if stored_prev is not None:
                res.fail(f"id={r['id']}: genesis row has non-null prev {stored_prev!r}")
        else:
            if stored_prev != expected_prev:
                res.fail(
                    f"id={r['id']}: broken linkage — stored prev {stored_prev!r} "
                    f"!= previous row hash {expected_prev!r}"
                )
        if stored_prev is not None:
            if stored_prev in seen_prev:
                res.fail(f"id={r['id']}: FORK — prev {stored_prev!r} referenced twice")
            seen_prev.add(stored_prev)

        head = stored_prev if stored_prev is not None else "GENESIS"
        preimage = "|".join(
            [
                head,
                r["action"],
                r["entity_type_t"],
                r["entity_id_t"],
                r["actor_t"],
                r["before_t"],
                r["after_t"],
                r["created_t"],
            ]
        )
        recomputed = _sha256_utf8(preimage)
        if recomputed != r["row_hash"]:
            res.fail(
                f"id={r['id']}: row_hash mismatch "
                f"(stored {r['row_hash']}, recomputed {recomputed})"
            )
        expected_prev = r["row_hash"]
    return res


def resolve_org_id(cur, args) -> str | None:
    if args.org_id:
        cur.execute("select id from ff.orgs where id = %s", (args.org_id,))
    else:
        cur.execute("select id from ff.orgs where name = %s", (args.org_name,))
    row = cur.fetchone()
    return str(row["id"]) if row else None


def resolve_patient_id(cur, org_id: str, args) -> str | None:
    if args.patient_id:
        cur.execute(
            "select id from ff.patients where id = %s and org_id = %s",
            (args.patient_id, org_id),
        )
    else:
        cur.execute(
            "select id from ff.patients where subject_code = %s and org_id = %s",
            (args.patient_code, org_id),
        )
    row = cur.fetchone()
    return str(row["id"]) if row else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent FindingFrame hash-chain verifier")
    ap.add_argument("--org-id", help="org UUID (else resolve by --org-name)")
    ap.add_argument("--org-name", default=DEMO_ORG_NAME, help=f"org name (default: {DEMO_ORG_NAME!r})")
    ap.add_argument("--patient-id", help="restrict signoff chains to this patient UUID")
    ap.add_argument("--patient-code", help="restrict signoff chains to this subject_code")
    args = ap.parse_args()

    env = load_env_file(BACKEND_ENV)
    database_url = env.get("FF_DATABASE_URL", "")
    if not database_url:
        print(f"ERROR: FF_DATABASE_URL missing from {BACKEND_ENV}", file=sys.stderr)
        return 1
    dsn = build_pg_dsn(database_url)

    print("=== FindingFrame hash-chain verifier ===")
    results: list[ChainResult] = []

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            org_id = resolve_org_id(cur, args)
            if org_id is None:
                who = args.org_id or repr(args.org_name)
                print(f"ERROR: org not found: {who}", file=sys.stderr)
                return 1
            print(f"org_id = {org_id}")

            patient_id: str | None = None
            if args.patient_id or args.patient_code:
                patient_id = resolve_patient_id(cur, org_id, args)
                if patient_id is None:
                    print("ERROR: patient not found in org", file=sys.stderr)
                    return 1
                print(f"patient_id = {patient_id}")

            # --- signoffs: one chain per patient (order genesis-first) ------
            sign_sql = """
                select
                    id::text as id,
                    patient_id::text as patient_id,
                    payload::text as payload_text,
                    coalesce(run_id::text, '') as run_id_text,
                    scope::text as scope_text,
                    signed_by::text as signed_by_text,
                    signed_at::text as signed_at_text,
                    payload_sha256, prev_signoff_sha256, row_sha256
                from ff.signoffs
                where org_id = %s
                {patient_filter}
                order by patient_id, signed_at asc, id asc
            """
            if patient_id:
                cur.execute(
                    sign_sql.format(patient_filter="and patient_id = %s"),
                    (org_id, patient_id),
                )
            else:
                cur.execute(sign_sql.format(patient_filter=""), (org_id,))
            sign_rows = cur.fetchall()

            by_patient: dict[str, list[dict]] = {}
            for r in sign_rows:
                by_patient.setdefault(r["patient_id"], []).append(r)
            if not by_patient:
                print("  (no signoff rows for this scope)")
            for pid, rows in by_patient.items():
                results.append(verify_signoff_chain(rows, pid[:8]))

            # --- audit_log: one chain per org -------------------------------
            cur.execute(
                """
                select
                    id,
                    action,
                    coalesce(entity_type, '') as entity_type_t,
                    coalesce(entity_id, '') as entity_id_t,
                    coalesce(actor_id::text, 'system') as actor_t,
                    coalesce(before::text, '') as before_t,
                    coalesce(after::text, '') as after_t,
                    coalesce(created_at::text, now()::text) as created_t,
                    prev_hash, row_hash
                from ff.audit_log
                where org_id = %s
                order by id asc
                """,
                (org_id,),
            )
            audit_rows = cur.fetchall()
            if not audit_rows:
                print("  (no audit_log rows for this org)")
            else:
                results.append(verify_audit_chain(audit_rows, org_id[:8]))

    # --- summary --------------------------------------------------------------
    print("\n--- chain summary ---")
    all_ok = True
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"  [{status}] {r.name}: {r.rows} rows")
        for err in r.errors:
            print(f"           - {err}")
        all_ok = all_ok and r.ok

    if not results:
        print("  (no chains found to verify)")

    print(f"\nOVERALL: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
