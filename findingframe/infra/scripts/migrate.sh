#!/usr/bin/env bash
# FindingFrame — apply infra/supabase/migrations/*.sql in order via psql.
#
# Reads the DSN from backend/.env (FF_DATABASE_URL) unless FF_DATABASE_URL / PG* env
# vars are already set in the environment. Safe to re-run: every migration in this repo
# is written to be idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS / etc).
#
# Usage:
#   infra/scripts/migrate.sh                      # uses backend/.env
#   FF_ENV_FILE=/path/to/other.env infra/scripts/migrate.sh
#   PSQL_BIN=/usr/local/bin/psql infra/scripts/migrate.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FF_ROOT="$(cd "$INFRA_DIR/.." && pwd)"
ENV_FILE="${FF_ENV_FILE:-$FF_ROOT/backend/.env}"
MIGRATIONS_DIR="$INFRA_DIR/supabase/migrations"

# Resolve a psql binary: prefer an explicit override, then the Homebrew postgresql@15
# keg (used in this environment because the default `psql` may be missing/older),
# then whatever is on PATH.
if [[ -n "${PSQL_BIN:-}" ]]; then
  :
elif [[ -x /opt/homebrew/opt/postgresql@15/bin/psql ]]; then
  PSQL_BIN=/opt/homebrew/opt/postgresql@15/bin/psql
else
  PSQL_BIN=psql
fi

if [[ -z "${FF_DATABASE_URL:-}" && -f "$ENV_FILE" ]]; then
  echo "Reading DB connection from $ENV_FILE"
  # Pull just the one line we need rather than `source`-ing the whole .env: some values
  # (e.g. FF_CORS_ORIGINS=["..."]) are JSON-ish and not safe/necessary to eval as shell.
  FF_DATABASE_URL="$(grep -m1 '^FF_DATABASE_URL=' "$ENV_FILE" | cut -d'=' -f2-)"
fi

if [[ -z "${FF_DATABASE_URL:-}" ]]; then
  echo "ERROR: FF_DATABASE_URL not set (checked $ENV_FILE and the environment)." >&2
  exit 1
fi

# Parse postgresql(+asyncpg)://user:pass@host:port/dbname -> PG* env vars.
# Done in python so the (possibly %-encoded, and containing '$') password round-trips
# correctly instead of fighting bash/URL quoting.
CONN_EXPORTS="$(python3 - "$FF_DATABASE_URL" <<'PY'
import sys
from urllib.parse import urlsplit, unquote

url = sys.argv[1]
scheme, _, rest = url.partition("://")
if "+" in scheme:
    scheme = "postgresql"
u = urlsplit(f"{scheme}://{rest}")
dbname = (u.path or "/postgres").lstrip("/") or "postgres"

def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"

print(f"export PGHOST={sh_quote(u.hostname or '')}")
print(f"export PGPORT={sh_quote(str(u.port or 5432))}")
print(f"export PGUSER={sh_quote(unquote(u.username or ''))}")
print(f"export PGPASSWORD={sh_quote(unquote(u.password or ''))}")
print(f"export PGDATABASE={sh_quote(dbname)}")
PY
)"
eval "$CONN_EXPORTS"
export PGSSLMODE=require

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
  echo "ERROR: migrations dir not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

shopt -s nullglob
files=("$MIGRATIONS_DIR"/*.sql)
shopt -u nullglob
if [[ ${#files[@]} -eq 0 ]]; then
  echo "ERROR: no *.sql files in $MIGRATIONS_DIR" >&2
  exit 1
fi

# Sort lexically (0001_, 0002_, ... convention keeps this = intended order).
IFS=$'\n' sorted_files=($(printf '%s\n' "${files[@]}" | sort))
unset IFS

echo "Target: $PGHOST:$PGPORT/$PGDATABASE (user=$PGUSER)"
echo "Applying ${#sorted_files[@]} migration(s) from $MIGRATIONS_DIR:"
for f in "${sorted_files[@]}"; do
  name="$(basename "$f")"
  echo "==> $name"
  "$PSQL_BIN" -v ON_ERROR_STOP=1 -X -q -f "$f"
  echo "    OK: $name"
done

echo
echo "All migrations applied successfully:"
for f in "${sorted_files[@]}"; do
  echo "  - $(basename "$f")"
done
