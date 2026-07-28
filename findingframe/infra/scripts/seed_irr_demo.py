#!/usr/bin/env python3
"""FindingFrame — seed a populated, SYNTHETIC blinded IRR (Cohen's kappa) pilot for the demo.

Idempotent. Run with the backend venv (after seed_demo.py has created the demo org + patient):
    backend/.venv/bin/python infra/scripts/seed_irr_demo.py

What it creates (all clearly labeled synthetic/demo — never cite as clinician-validated IRR):
  1. Two SYNTHETIC reader users ("IRR Reader 1 (synthetic demo)", "IRR Reader 2 (synthetic
     demo)") + ff.profiles + ff.memberships(reviewer) in the demo org. Auth users are minted
     via GoTrue signup (anon key) — the app DB role (ff_app) has no auth-schema access, so we
     cannot INSERT auth.users directly the way seed_demo.py did as superuser. Their ids are
     persisted as profile "marker" rows so re-runs reuse them and never re-signup.
  2. One ff.annotation_tasks row (unit_of_agreement='frame') over patient 10000935's run,
     with a stratified ~15-frame sample stored in description JSON (the exact shape
     app.services.irr reads — so GET /api/v1/irr/tasks/{id}/kappa works against it).
  3. Two ff.annotation_assignments (model_output_visible=false, shared independence_group
     'demo_pair_1', run_id set) — a valid blinded pair.
  4. Two independent sets of ff.annotation_records with realistic PARTIAL agreement, so
     GET .../kappa returns real per-slot kappa values (not 1.0 everywhere).

Governance (docs/IRR_PROTOCOL.md §5/§6): this is synthetic demo data. It exists only so the
kappa VIEW is populated for a product demo; it is NOT a clinician pilot and its numbers must
never be presented as clinician-validated IRR.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
INFRA_DIR = SCRIPT_DIR.parent
FF_ROOT = INFRA_DIR.parent
BACKEND_ENV = FF_ROOT / "backend" / ".env"

DEMO_ORG_NAME = "Tata Memorial (Demo)"
SUBJECT_CODE = "10000935"
READER_MARKERS = ["IRR Reader 1 (synthetic demo)", "IRR Reader 2 (synthetic demo)"]
TASK_NAME = "[DEMO] IRR Pilot — blinded double-read (synthetic)"
INDEPENDENCE_GROUP = "demo_pair_1"
SAMPLE_SIZE = 15
SLOTS = ["finding_type", "anatomy", "laterality", "assertion", "temporal_change"]
# per-slot probability that a reader independently deviates from the base label. Tuned to
# land per-slot kappa in the fair..almost-perfect range so the demo table is interesting.
DEVIATION_P = {
    "finding_type": 0.10,
    "anatomy": 0.06,
    "laterality": 0.16,
    "assertion": 0.12,
    "temporal_change": 0.22,
}
RNG_SEED = 20260718

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("psycopg not found; installing psycopg[binary] into this interpreter's venv ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg[binary]"], check=True)
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore


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
        host=u.hostname or "", port=u.port or 5432, user=unquote(u.username or "postgres"),
        password=unquote(u.password or ""), dbname=dbname, sslmode="require",
    )


# ---------------------------------------------------------------------------
# reader auth users
# ---------------------------------------------------------------------------
def _gotrue_signup(url: str, key: str, email: str, password: str) -> str | None:
    """Create an auth user via GoTrue signup; return its id (works even if the project
    requires email confirmation — the user object with id is returned regardless). None on
    a hard failure the caller should surface."""
    req = urllib.request.Request(
        url.rstrip("/") + "/auth/v1/signup",
        data=json.dumps({"email": email, "password": password}).encode(),
        method="POST",
        headers={"apikey": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        d = json.loads(resp.read())
    return d.get("id") or (d.get("user") or {}).get("id")


def _admin_create_user(url: str, service_key: str, email: str, password: str) -> str:
    """Create a confirmed auth user via the GoTrue admin API (needs a service-role key).
    Preferred when available — no email is sent and the user is immediately usable."""
    req = urllib.request.Request(
        url.rstrip("/") + "/auth/v1/admin/users",
        data=json.dumps({"email": email, "password": password, "email_confirm": True}).encode(),
        method="POST",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        d = json.loads(resp.read())
    return d["id"]


def ensure_reader(cur, env: dict, org_id, marker: str) -> str:
    """Return the auth user id for a synthetic reader identified by its profile marker
    full_name; create the auth user (admin API if a service-role key is present, else anon
    signup) and its profile+membership on first run."""
    cur.execute("select id from ff.profiles where full_name = %s", (marker,))
    row = cur.fetchone()
    if row:
        # make sure the membership exists (idempotent)
        cur.execute(
            "insert into ff.memberships (org_id, user_id, role) values (%s,%s,'reviewer') "
            "on conflict (org_id, user_id) do nothing",
            (org_id, row["id"]),
        )
        return row["id"]

    url = env.get("FF_SUPABASE_URL", "")
    anon = env.get("FF_SUPABASE_PUBLISHABLE_KEY", "")
    service = env.get("FF_SUPABASE_SERVICE_ROLE_KEY", "")
    tag = uuid.uuid4().hex[:10]
    email = f"ff.irr.reader.{tag}@gmail.com"
    password = f"irr-{tag}-Demo1!"

    user_id: str | None = None
    err: str | None = None
    if service:
        try:
            user_id = _admin_create_user(url, service, email, password)
        except Exception as exc:  # noqa: BLE001
            err = f"admin API: {exc}"
    if user_id is None:
        # anon signup, with a little backoff in case of the shared email-send rate limit
        for attempt in range(3):
            try:
                user_id = _gotrue_signup(url, anon, email, password)
                if user_id:
                    break
            except urllib.error.HTTPError as exc:
                err = f"signup HTTP {exc.code}: {exc.read().decode()[:160]}"
                if exc.code == 429 and attempt < 2:
                    time.sleep(20)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                err = f"signup: {exc}"
                break

    if not user_id:
        raise RuntimeError(
            f"Could not mint synthetic reader auth user ({marker}). Last error: {err}.\n"
            "This environment's app DB role (ff_app) cannot INSERT auth.users, so the seed "
            "creates readers via GoTrue. If the anon signup is rate-limited/disabled, set "
            "FF_SUPABASE_SERVICE_ROLE_KEY in backend/.env (GoTrue admin API) and re-run, or "
            "wait for the email rate limit to clear. The kappa math itself is independently "
            "verified via `compute_kappa.py --demo` and the backend unit tests."
        )

    cur.execute(
        "insert into ff.profiles (id, full_name) values (%s,%s) "
        "on conflict (id) do update set full_name = excluded.full_name",
        (user_id, marker),
    )
    cur.execute(
        "insert into ff.memberships (org_id, user_id, role) values (%s,%s,'reviewer') "
        "on conflict (org_id, user_id) do nothing",
        (org_id, user_id),
    )
    print(f"  created synthetic reader {marker} ({user_id}) via {'admin API' if service else 'signup'}")
    return user_id


# ---------------------------------------------------------------------------
# stratified sample (mirrors app.services.irr._sample_frames)
# ---------------------------------------------------------------------------
def sample_frames(cur, org_id, run_id, total: int, seed: int) -> tuple[list[str], dict]:
    cur.execute(
        """
        select f.id::text as id, f.evidence_verified, f.uncertainty,
               coalesce(t.unresolved_link,false) as unresolved_link,
               coalesce(t.false_split_candidate,false) as false_split_candidate
        from ff.frames f
        left join ff.tracks t on t.run_id = f.run_id and t.track_key = f.track_key
        where f.run_id = %s and f.org_id = %s
        """,
        (run_id, org_id),
    )
    rows = cur.fetchall()
    hard, lowconf, standard = [], [], []
    for r in rows:
        if r["unresolved_link"] or r["false_split_candidate"]:
            hard.append(r["id"])
        elif (not r["evidence_verified"]) or (r["uncertainty"] is not None):
            lowconf.append(r["id"])
        else:
            standard.append(r["id"])
    rng = random.Random(seed)
    picked, seen, realized = [], set(), {}
    for name, pool, frac in [
        ("unresolved_or_false_split", hard, 0.25),
        ("low_confidence_or_gate_adjacent", lowconf, 0.25),
        ("standard", standard, 0.50),
    ]:
        avail = [x for x in pool if x not in seen]
        rng.shuffle(avail)
        take = avail[: min(round(total * frac), len(avail))]
        seen.update(take)
        picked.extend(take)
        realized[name] = len(take)
    if len(picked) < total:
        leftover = [x for x in (hard + lowconf + standard) if x not in seen]
        rng.shuffle(leftover)
        for x in leftover:
            if len(picked) >= total:
                break
            seen.add(x); picked.append(x); realized["fill"] = realized.get("fill", 0) + 1
    meta = {"seed": seed, "requested": total, "realized_total": len(picked),
            "per_stratum": realized,
            "strategy": "stratified: 50% standard / 25% unresolved-link|false-split / "
                        "25% low-confidence|gate-adjacent (IRR_PROTOCOL §2.2)"}
    return picked, meta


# ---------------------------------------------------------------------------
# synthetic reader labels with controlled partial agreement
# ---------------------------------------------------------------------------
def build_reader_labels(frames: dict[str, dict], item_refs: list[str]) -> tuple[dict, dict]:
    """Two readers independently (seeded) deviate from each frame's base label per slot, so
    A-vs-B agreement is high-but-imperfect and both roughly track the model (small correction
    rate). Returns {item_ref: labels} for reader A and reader B."""
    # observed value pools per slot (for realistic alternative categories)
    pools: dict[str, list[str]] = {s: [] for s in SLOTS}
    for f in frames.values():
        for s in SLOTS:
            v = f.get(s)
            if v is not None and v not in pools[s]:
                pools[s].append(v)
    fallback = {
        "finding_type": ["liver_metastasis", "lung_nodule", "lymph_node_metastasis"],
        "anatomy": ["liver", "lung", "lymph_node"],
        "laterality": ["left", "right", "bilateral"],
        "assertion": ["present", "absent", "uncertain"],
        "temporal_change": ["stable", "increased", "decreased", "new"],
    }
    for s in SLOTS:
        for v in fallback[s]:
            if v not in pools[s]:
                pools[s].append(v)

    def deviate(rng, slot, base):
        alts = [v for v in pools[slot] if v != base]
        return rng.choice(alts) if alts else base

    rng_a = random.Random(RNG_SEED + 1)
    rng_b = random.Random(RNG_SEED + 2)
    labels_a, labels_b = {}, {}
    for ref in item_refs:
        f = frames.get(ref, {})
        la, lb = {}, {}
        for s in SLOTS:
            base = f.get(s)
            if base is None:
                base = pools[s][0]
            la[s] = deviate(rng_a, s, base) if rng_a.random() < DEVIATION_P[s] else base
            lb[s] = deviate(rng_b, s, base) if rng_b.random() < DEVIATION_P[s] else base
        labels_a[ref] = la
        labels_b[ref] = lb
    return labels_a, labels_b


def main() -> int:
    print("=== FindingFrame IRR demo seed (SYNTHETIC) ===")
    env = load_env_file(BACKEND_ENV)
    if not env.get("FF_DATABASE_URL"):
        print(f"ERROR: FF_DATABASE_URL missing from {BACKEND_ENV}", file=sys.stderr)
        return 1
    dsn = build_pg_dsn(env["FF_DATABASE_URL"])

    with psycopg.connect(dsn, autocommit=False, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from ff.orgs where name = %s", (DEMO_ORG_NAME,))
            org = cur.fetchone()
            if not org:
                print(f"ERROR: demo org {DEMO_ORG_NAME!r} not found — run seed_demo.py first.",
                      file=sys.stderr)
                return 1
            org_id = org["id"]

            cur.execute(
                """
                select r.id as run_id, p.id as patient_id
                from ff.extraction_runs r join ff.patients p on p.id = r.patient_id
                where p.subject_code = %s and p.org_id = %s and r.status = 'succeeded'
                order by r.created_at desc limit 1
                """,
                (SUBJECT_CODE, org_id),
            )
            run = cur.fetchone()
            if not run:
                print(f"ERROR: no succeeded run for patient {SUBJECT_CODE} — run seed_demo.py.",
                      file=sys.stderr)
                return 1
            run_id = run["run_id"]
            print(f"Org {org_id}, patient {SUBJECT_CODE}, run {run_id}")

            # 1. synthetic readers
            print("Ensuring synthetic reader users ...")
            reader_ids = [ensure_reader(cur, env, org_id, m) for m in READER_MARKERS]
            if reader_ids[0] == reader_ids[1]:
                print("ERROR: the two readers resolved to the same auth id (invariant §2.4).",
                      file=sys.stderr)
                return 1

            # 2. task (idempotent by name) with stratified frozen sample
            cur.execute(
                "select id, description from ff.annotation_tasks where org_id = %s and name = %s",
                (org_id, TASK_NAME),
            )
            existing = cur.fetchone()
            if existing:
                task_id = existing["id"]
                item_refs = (json.loads(existing["description"]) or {}).get("item_refs", [])
                print(f"Task exists: {task_id} ({len(item_refs)} items)")
            else:
                seed = (int(uuid.UUID(str(run_id))) ^ (SAMPLE_SIZE * 2654435761)) & 0x7FFFFFFF
                item_refs, sampling = sample_frames(cur, org_id, run_id, SAMPLE_SIZE, seed)
                description = json.dumps({
                    "text": "Synthetic demo pilot so the kappa view is populated. NOT a real "
                            "clinician IRR pilot — see docs/IRR_PROTOCOL.md §6.",
                    "run_id": str(run_id),
                    "unit_of_agreement": "frame",
                    "sampling": sampling,
                    "item_refs": item_refs,
                })
                cur.execute(
                    """
                    insert into ff.annotation_tasks
                        (org_id, protocol_id, name, unit_of_agreement, description, created_by)
                    values (%s, 'irr_pilot_v1_demo', %s, cast(%s as ff.agreement_unit), %s, %s)
                    returning id
                    """,
                    (org_id, TASK_NAME, "frame", description, reader_ids[0]),
                )
                task_id = cur.fetchone()["id"]
                print(f"Created task {task_id} with {len(item_refs)} stratified frames")

            # 3. assignments (idempotent by task+annotator)
            assignment_ids = []
            for uid in reader_ids:
                cur.execute(
                    "select id from ff.annotation_assignments where task_id=%s and annotator_id=%s",
                    (task_id, uid),
                )
                a = cur.fetchone()
                if a:
                    assignment_ids.append(a["id"])
                    continue
                cur.execute(
                    """
                    insert into ff.annotation_assignments
                        (task_id, org_id, annotator_id, run_id, model_output_visible,
                         independence_group, status)
                    values (%s,%s,%s,%s,false,%s,'completed')
                    returning id
                    """,
                    (task_id, org_id, uid, run_id, INDEPENDENCE_GROUP),
                )
                assignment_ids.append(cur.fetchone()["id"])
            print(f"Assignments: {assignment_ids} (independence_group={INDEPENDENCE_GROUP})")

            # 4. records with realistic partial agreement (append-only; skip if already present)
            cur.execute(
                "select f.id::text as id, f.finding_type, f.anatomy, f.laterality, "
                "f.assertion::text as assertion, f.temporal_change "
                "from ff.frames f where f.id::text = any(%s)",
                (item_refs,),
            )
            frames = {r["id"]: r for r in cur.fetchall()}
            labels_a, labels_b = build_reader_labels(frames, item_refs)

            inserted = 0
            for aid, labels in zip(assignment_ids, (labels_a, labels_b)):
                cur.execute(
                    "select count(*) c from ff.annotation_records where assignment_id=%s", (aid,)
                )
                if cur.fetchone()["c"] > 0:
                    print(f"  assignment {aid} already has records — skipping")
                    continue
                for ref in item_refs:
                    cur.execute(
                        "insert into ff.annotation_records (assignment_id, org_id, item_ref, labels) "
                        "values (%s,%s,%s, cast(%s as jsonb))",
                        (aid, org_id, ref, json.dumps(labels[ref])),
                    )
                    inserted += 1
            print(f"Inserted {inserted} annotation_records")

        conn.commit()

    print("\n=== Done ===")
    print(f"  task_id: {task_id}")
    print("  Score it:  backend/.venv/bin/python infra/scripts/compute_kappa.py --task-id " + str(task_id))
    print("  Or:        GET /api/v1/irr/tasks/{task_id}/kappa")
    print(f"  (SYNTHETIC demo data — not clinician-validated IRR; see docs/IRR_PROTOCOL.md §6)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
