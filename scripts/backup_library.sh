#!/usr/bin/env bash
# Backup the Local Video Search database without stopping the app.
#
# Usage:
#   scripts/backup_library.sh [--out FILE] [--force] [--project NAME]
#
# What it does:
#   1. Dumps the database from the running db container
#      (docker compose exec -T db pg_dump -U video --no-owner video).
#      No service is stopped or interrupted.
#   2. Writes a plain-SQL dump to .codex-backups/db-backups/
#      video-backup-YYYYMMDD-HHMMSS.sql. That folder is gitignored. A dump
#      holds paths, fingerprints, embeddings, descriptions and speech text of
#      your footage; treat it as private data.
#   3. Writes a SHA-256 sidecar next to the dump (<dump>.sha256). Verify it
#      later with: sha256sum -c <dump>.sha256 (run from the repository root).
#   4. Refuses to overwrite an existing dump file unless --force is given.
#   5. Prints what the dump covers and what it does not (models and uploads
#      volumes, your source folder).
#
# Options:
#   --out FILE     write the dump to FILE instead of the timestamped default
#   --force        allow overwriting an existing dump file
#   --project NAME operate on a custom Compose project (docker compose -p NAME)
#
# Proof on record (2026-11-20, this machine):
#   - Live backup while the full stack was serving: dump
#     .codex-backups/db-backups/video-backup-20261120-163908.sql,
#     12,596,809 bytes, SHA-256
#     37be8043e098b723a2db5f56e3806b87f56f2d9ff84aedc3a510ddb8f8ad5979.
#     The sidecar round-tripped: sha256sum -c reported OK.
#   - Overwrite refusal tested: re-running with --out <that dump> and no
#     --force refused with a clear error and exit code 1.
#   - The produced dump was restored for real in a throwaway Compose project;
#     see the header of scripts/restore_library.sh.
set -euo pipefail

OUT_DIR=".codex-backups/db-backups"
OUT=""
FORCE=0
PROJECT=""

usage() {
    cat <<'EOF'
Usage: scripts/backup_library.sh [--out FILE] [--force] [--project NAME]

Dumps the video database from the running db container into a timestamped
plain-SQL file under .codex-backups/db-backups (gitignored), with a SHA-256
sidecar. The app keeps running; nothing is interrupted.

Options:
  --out FILE     write the dump to FILE instead of the timestamped default
  --force        allow overwriting an existing dump file
  --project NAME operate on a custom Compose project (docker compose -p NAME)
  -h, --help     show this help
EOF
}

die() {
    printf 'backup_library.sh: error: %s\n' "$*" >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --out)
            [ $# -ge 2 ] || die "--out needs a file path"
            OUT="$2"
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

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ -n "$PROJECT" ]; then
    COMPOSE=(docker compose -p "$PROJECT")
else
    COMPOSE=(docker compose)
fi
VOLUME_PREFIX=${PROJECT:-local-video-search}

RUNNING_DB=$("${COMPOSE[@]}" ps -q db)
if [ -z "$RUNNING_DB" ]; then
    die "the db container is not running. Start the stack first: docker compose up -d --wait. This backup runs inside the running container and interrupts nothing."
fi

if [ -z "$OUT" ]; then
    mkdir -p "$OUT_DIR"
    OUT="$OUT_DIR/video-backup-$(date +%Y%m%d-%H%M%S).sql"
else
    case "$OUT" in
        */*) mkdir -p "$(dirname "$OUT")" ;;
    esac
fi

if [ -e "$OUT" ] && [ "$FORCE" -ne 1 ]; then
    die "refusing to overwrite existing file: $OUT (use --force)"
fi

printf 'Dumping database video from the running db container...\n'
PART="$OUT.part"
if ! "${COMPOSE[@]}" exec -T db pg_dump -U video --no-owner video >"$PART"; then
    rm -f "$PART"
    die "pg_dump failed; no backup was written"
fi
if [ ! -s "$PART" ]; then
    rm -f "$PART"
    die "pg_dump produced an empty dump; no backup was written"
fi
mv "$PART" "$OUT"

if command -v sha256sum >/dev/null 2>&1; then
    HASH_LINE=$(sha256sum "$OUT")
elif command -v shasum >/dev/null 2>&1; then
    HASH_LINE=$(shasum -a 256 "$OUT")
else
    die "no SHA-256 tool found (sha256sum or shasum); the dump was written but has no sidecar: $OUT"
fi
printf '%s\n' "$HASH_LINE" >"$OUT.sha256"

BYTES=$(wc -c <"$OUT")
printf 'Backup written: %s (%s bytes)\n' "$OUT" "$BYTES"
printf 'SHA-256: %s\n' "${HASH_LINE%% *}"
printf 'Sidecar: %s (verify later with: sha256sum -c %s)\n' "$OUT.sha256" "$OUT.sha256"

printf 'Volumes of Compose project %s:\n' "$VOLUME_PREFIX"
printf '  %s_database  covered by this dump (paths, fingerprints, embeddings,\n' "$VOLUME_PREFIX"
printf '               descriptions, speech text). Treat the dump as private data.\n'
printf '  %s_models     NOT covered. Keep the volume, or re-download the pinned models.\n' "$VOLUME_PREFIX"
printf '  %s_uploads     NOT covered. Browser-uploaded videos live there. Keep the\n' "$VOLUME_PREFIX"
printf '               volume, or copy it separately.\n'
printf 'Your video folder stays outside Docker (read-only mount); it is not part of any volume.\n'
printf 'docker compose down keeps these volumes; docker compose down -v deletes them.\n'
printf 'Restore with: scripts/restore_library.sh --dump %s\n' "$OUT"
