#!/usr/bin/env bash
# Restore a Local Video Search database dump, with explicit safety checks.
#
# Usage:
#   scripts/restore_library.sh --dump PATH [--force] [--project NAME] [--skip-api-check]
#
# Safety model (each check stops the script before data changes):
#   1. --dump PATH is mandatory.
#   2. The app must be down: the api and worker containers must not be running
#      for the target Compose project. This protects the database you replace.
#      Bring it down with: docker compose down (volumes are kept).
#   3. The target database must be fresh (no recordings table). A database that
#      already holds recordings is refused unless --force is given; --force
#      drops and recreates the video database, replacing its contents.
#   4. The library binding is printed before the restore: the database records
#      the VIDEO_DIRECTORY identity from .env, and the api refuses a different
#      directory at startup by design. After the restore the script re-checks
#      that identity against .env and stops on a mismatch.
#   5. After the restore the stack is started and /health is checked for its
#      schema_version. --skip-api-check leaves the api down instead (for
#      isolated verification against a throwaway Compose project; port 8000
#      can only serve one project at a time).
#
# The models and uploads volumes are never touched; they need no dump.
#
# Proof on record (2026-11-20, this machine):
#   - Real restore in the throwaway project restore-proof (fresh volume
#     restore-proof_database, VIDEO_DIRECTORY taken from .env): the dump
#     .codex-backups/db-backups/video-backup-20261120-163908.sql restored with
#     ON_ERROR_STOP; 8 recordings (the same count as the live database) and
#     the library identity matched VIDEO_DIRECTORY. The throwaway project was
#     removed afterwards with: docker compose -p restore-proof down -v.
#     The main project's volumes were never touched.
#   - Safety refusals tested and observed: missing --dump (exit 1); a restore
#     attempted while the main api container was running (refused before any
#     data changed, exit 1); a re-run against the restored throwaway database
#     without --force (refused: 8 recordings, exit 1); the same re-run with
#     --force replaced the database and restored it again (exit 0).
#   - Not proven live on purpose: the api start and the /health schema_version
#     check in the main project. That path needs the main stack down and port
#     8000 free, which this proof run did not allow; the throwaway run used
#     --skip-api-check for exactly that reason.
set -euo pipefail

DUMP=""
FORCE=0
PROJECT=""
SKIP_API_CHECK=0

usage() {
    cat <<'EOF'
Usage: scripts/restore_library.sh --dump PATH [--force] [--project NAME] [--skip-api-check]

Restores a pg_dump plain-SQL dump into the database of this Compose project.
The app must be down first: docker compose down (volumes are kept).

Safety checks before any data changes:
  - --dump PATH is mandatory.
  - api and worker must not be running.
  - the target database must hold no recordings, unless --force is given.
  - the dump's library identity must match VIDEO_DIRECTORY in .env (checked
    after the restore; the api also enforces it at startup, by design).

Options:
  --dump PATH       the dump file to restore (required)
  --force           replace the contents of an already-initialized database
                    (drops and recreates the video database first)
  --project NAME    operate on a custom Compose project (docker compose -p NAME)
  --skip-api-check  do not start the api and do not call /health; for isolated
                    verification against a throwaway project
  -h, --help         show this help
EOF
}

die() {
    printf 'restore_library.sh: error: %s\n' "$*" >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dump)
            [ $# -ge 2 ] || die "--dump needs a file path"
            DUMP="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --project)
            [ $# -ge 2 ] || die "--project needs a name"
            PROJECT="$2"
            shift 2
            ;;
        --skip-api-check)
            SKIP_API_CHECK=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "unknown argument: $1"
            ;;
    esac
done

if [ -z "$DUMP" ]; then
    usage >&2
    die "--dump PATH is required"
fi

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ -n "$PROJECT" ]; then
    COMPOSE=(docker compose -p "$PROJECT")
else
    COMPOSE=(docker compose)
fi
VOLUME_PREFIX=${PROJECT:-local-video-search}

if [ ! -f "$DUMP" ]; then
    die "dump file not found: $DUMP"
fi
if [ ! -s "$DUMP" ]; then
    die "dump file is empty: $DUMP"
fi

if [ ! -f .env ]; then
    die "no .env file in $ROOT; Compose and this script both need VIDEO_DIRECTORY"
fi
VIDEO_DIRECTORY=$(sed -n 's/^VIDEO_DIRECTORY=//p' .env)
VIDEO_DIRECTORY=${VIDEO_DIRECTORY%%$'\r'}
case "$VIDEO_DIRECTORY" in
    \"*\")
        VIDEO_DIRECTORY=${VIDEO_DIRECTORY#\"}
        VIDEO_DIRECTORY=${VIDEO_DIRECTORY%\"}
        ;;
esac
if [ -z "$VIDEO_DIRECTORY" ]; then
    die "VIDEO_DIRECTORY is not set in .env"
fi

for SVC in api worker; do
    RUNNING=$("${COMPOSE[@]}" ps -q "$SVC")
    if [ -n "$RUNNING" ]; then
        die "the $SVC container is still running. Bring the app down first: docker compose down (volumes are kept), or docker compose stop $SVC. This protects the database you are replacing."
    fi
done

printf 'Target database identity\n'
printf '  The database records the video directory and refuses a different one\n'
printf '  at api startup, by design.\n'
printf '  VIDEO_DIRECTORY in .env: %s\n' "$VIDEO_DIRECTORY"
printf '  The dump must come from a database bound to that same directory. This\n'
printf '  script re-checks it after the restore and stops on a mismatch.\n'

printf 'Starting the db container and waiting for it to be healthy...\n'
if ! "${COMPOSE[@]}" up -d db --wait; then
    die "docker compose up -d db --wait failed; fix the reported error and re-run"
fi

HAS_RECORDINGS_TABLE=$("${COMPOSE[@]}" exec -T db psql -U video -d video -tAc "SELECT to_regclass('public.recordings') IS NOT NULL")
if [ "$HAS_RECORDINGS_TABLE" = "t" ]; then
    EXISTING_COUNT=$("${COMPOSE[@]}" exec -T db psql -U video -d video -tAc "SELECT count(*) FROM recordings")
    if [ "$FORCE" -ne 1 ]; then
        die "the target database is already initialized and holds ${EXISTING_COUNT} recordings. Restore into a fresh database volume instead: docker compose down && docker volume rm ${VOLUME_PREFIX}_database — or pass --force to replace its contents."
    fi
    printf 'Replacing the existing database (--force): dropping and recreating database video (%s recordings removed)...\n' "$EXISTING_COUNT"
    "${COMPOSE[@]}" exec -T db psql -U video -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE video WITH (FORCE)" -c "CREATE DATABASE video OWNER video"
fi

printf 'Restoring the dump (ON_ERROR_STOP on)...\n'
if ! "${COMPOSE[@]}" exec -T db psql -U video -d video -v ON_ERROR_STOP=1 <"$DUMP"; then
    die "psql restore failed; the database is now in a partial state. Re-run against a fresh volume (docker compose down && docker volume rm ${VOLUME_PREFIX}_database) or with --force"
fi

COUNT=$("${COMPOSE[@]}" exec -T db psql -U video -d video -tAc "SELECT count(*) FROM recordings")
IDENTITY=$("${COMPOSE[@]}" exec -T db psql -U video -d video -tAc "SELECT identity FROM library WHERE singleton")
printf 'Restored recordings: %s\n' "$COUNT"
if [ "$IDENTITY" != "$VIDEO_DIRECTORY" ]; then
    die "library identity mismatch: the restored database is bound to '${IDENTITY}' but .env VIDEO_DIRECTORY is '${VIDEO_DIRECTORY}'. The api refuses this pairing at startup by design. Fix .env or restore a dump of that library."
fi
printf 'Library identity matches VIDEO_DIRECTORY: %s\n' "$VIDEO_DIRECTORY"

if [ "$SKIP_API_CHECK" -eq 1 ]; then
    printf 'api start and /health check skipped (--skip-api-check). Start the stack and\n'
    printf 'check http://127.0.0.1:8000/health before use.\n'
else
    printf 'Starting the full stack and waiting for health...\n'
    if ! "${COMPOSE[@]}" up -d --wait; then
        die "docker compose up -d --wait failed; check docker compose logs api"
    fi
    HEALTH=$(curl -fsS --max-time 30 http://127.0.0.1:8000/health) || die "the api did not answer GET /health; check docker compose logs api"
    SCHEMA_VERSION=$(printf '%s' "$HEALTH" | grep -o '"schema_version":[0-9][0-9]*' | head -n 1 | cut -d: -f2) || SCHEMA_VERSION=""
    if [ -z "$SCHEMA_VERSION" ]; then
        die "no schema_version in the /health response: $HEALTH"
    fi
    printf 'api is up; /health reports schema_version %s\n' "$SCHEMA_VERSION"
fi

printf 'The %s_models and %s_uploads volumes were not touched; they need no dump.\n' "$VOLUME_PREFIX" "$VOLUME_PREFIX"
