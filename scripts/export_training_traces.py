"""Export training traces from the running app database.

One command for the flywheel's first step: reads description windows and
verification runs out of the live PostgreSQL database via
`docker compose exec -T db psql`, writes them as no-BOM JSONL under
`.codex-backups/finetune-data/` with a manifest of row counts and SHA-256
hashes, refuses to overwrite existing exports unless --force, and prints the
exact next commands (dataset build, merge, pre-flight).

Description payloads are exported without the hosted `_trace` block
(`payload - '_trace'`), the same trace-free contract the dataset builder
enforces at training time. Verification responses keep their recorded
`_trace` for provenance; training uses only the serving fields either way.
Stdlib only. Run from the repository root with the Compose services up.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

DESCRIPTIONS_FILE = "descriptions.jsonl"
VERIFICATIONS_FILE = "verifications.jsonl"
MANIFEST_FILE = "traces-manifest.json"

# Mirrors the manual export recorded in PLAN.md (fine-tuned system model
# campaign, 20 November 2026): full samples and payloads joined to each
# recording's source path, size and mtime for media provenance.
DESCRIPTIONS_SQL = """SELECT jsonb_build_object(
         'kind', 'description',
         'size', r.size,
         'spec', b.spec,
         'payload', w.payload - '_trace',
         'samples', w.samples,
         'mtime_ns', r.mtime_ns,
         'end_seconds', w.end_seconds,
         'source_path', r.source_path,
         'start_seconds', w.start_seconds)
FROM description_windows w
JOIN description_builds b ON b.id = w.build_id
JOIN recordings r ON r.id = b.recording_id
ORDER BY r.source_path, b.id, w.start_seconds, w.end_seconds"""

VERIFICATIONS_SQL = """SELECT jsonb_build_object(
         'kind', 'verification',
         'spec', v.spec,
         'query', v.query,
         'samples', v.samples,
         'response', v.response,
         'end_seconds', v.end_seconds,
         'source_path', r.source_path,
         'start_seconds', v.start_seconds)
FROM verification_runs v
JOIN recordings r ON r.id = v.recording_id
ORDER BY r.source_path, v.created_at, v.id"""

PSQL_COMMAND = ["docker", "compose", "exec", "-T", "db", "psql",
                "-U", "video", "-d", "video", "-At", "-v", "ON_ERROR_STOP=1", "-c"]

DESCRIPTION_KEYS = ("kind", "size", "spec", "payload", "samples", "mtime_ns",
                    "end_seconds", "source_path", "start_seconds")
DESCRIPTION_PAYLOAD_KEYS = ("summary", "actions", "objects", "uncertainties")
VERIFICATION_KEYS = ("kind", "spec", "query", "samples", "response",
                      "end_seconds", "source_path", "start_seconds")
VERIFICATION_RESPONSE_KEYS = ("status", "intervals", "observation")


def run_psql(sql: str, name: str) -> bytes:
    """Run one read-only SQL statement through the Compose db service."""
    command = PSQL_COMMAND + [sql]
    try:
        result = subprocess.run(command, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{name} export timed out after 600 s: {PSQL_COMMAND}") from error
    if result.returncode != 0:
        raise RuntimeError(
            f"{name} export failed with exit code {result.returncode}.\n"
            f"command: {' '.join(PSQL_COMMAND)}\n"
            f"stderr: {result.stderr.decode('utf-8', errors='replace').strip()}\n"
            "Is the Compose db service up? Start it with: docker compose up -d db api worker")
    return result.stdout


def validate(data: bytes, name: str, required_keys, inner_name, inner_keys) -> list:
    """Parse one JSONL export and check the training-relevant keys exist."""
    rows = []
    for number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{name} row {number} is not valid JSON: {error}") from error
        missing = [key for key in required_keys if key not in row]
        if missing:
            raise RuntimeError(f"{name} row {number} is missing keys: {missing}")
        if inner_keys:
            missing = [key for key in inner_keys if key not in row[inner_name]]
            if missing:
                raise RuntimeError(f"{name} row {number} {inner_name} is missing keys: {missing}")
        rows.append(row)
    return rows


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: Path, data: bytes):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def checklist(out: Path) -> str:
    build = f"python scripts/build_finetune_dataset.py --traces {out.as_posix()} --output {(out / 'dataset').as_posix()}"
    merge = (f"python scripts/merge_finetune_datasets.py --distillation {(out / 'dataset').as_posix()}"
             f" --output {(out / 'merged-dataset').as_posix()}")
    preflight = (f"python -c \"import sys; from pathlib import Path; sys.path.insert(0, 'scripts/sol');"
                 f" from finetune_vlm import load_rows; rows = load_rows(Path('{(out / 'merged-dataset' / 'train.jsonl').as_posix()}'),"
                 f" Path('{(out / 'merged-dataset').as_posix()}'));"
                 f" print(len(rows), 'train rows load; all image paths resolve')\"")
    media_note = ("" if (out / "media").is_dir() else
                  f"\nWARNING: {out.as_posix()}/media does not exist. Copy the source videos there before step 1"
                  f" (the default .codex-backups/finetune-data/media has them)."
                  "\n         New /__uploads/ recordings also need an UPLOAD_MAP entry in scripts/build_finetune_dataset.py.")
    return f"""NEXT COMMANDS, in order (ready to run):
1. Build the chat dataset (extracts frames with ffmpeg; needs the source videos under {out.as_posix()}/media):{media_note}
   {build}
2. Merge the hard-negative dataset (needs .codex-backups/hard-negatives-dataset;
   rebuild it first with: python scripts/build_hard_negatives.py):
   {merge}
3. Local pre-flight before any GPU job (exact load_rows path check; needs Pillow on the host):
   {preflight}
Then train on Sol: smoke first (FINETUNE_MODE=smoke), full run, acceptance eval.
Only a measured pass on the held-out gate replaces the hosted model; see docs/SELF-IMPROVEMENT.md."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(".codex-backups/finetune-data"),
                        help="Output directory for the JSONL exports and manifest")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing exports in the output directory")
    args = parser.parse_args()
    out = args.out
    targets = {DESCRIPTIONS_FILE: DESCRIPTIONS_SQL, VERIFICATIONS_FILE: VERIFICATIONS_SQL}
    existing = [name for name in targets if (out / name).is_file()]
    if existing and not args.force:
        print(f"Refusing to overwrite existing export(s) in {out.as_posix()}: {', '.join(existing)}."
              " Pass --force to replace them.", file=sys.stderr)
        raise SystemExit(2)
    exports = {}
    for name, sql in targets.items():
        data = run_psql(sql, name)
        if name == DESCRIPTIONS_FILE:
            rows = validate(data, name, DESCRIPTION_KEYS, "payload", DESCRIPTION_PAYLOAD_KEYS)
            traced = [index for index, row in enumerate(rows, start=1) if "_trace" in row["payload"]]
            if traced:
                raise RuntimeError(f"{name} rows still carry a hosted _trace block: {traced[:3]}")
        else:
            rows = validate(data, name, VERIFICATION_KEYS, "response", VERIFICATION_RESPONSE_KEYS)
        exports[name] = (data, rows)
        if not rows:
            print(f"WARNING: 0 {name} rows exported. Is the app database populated?", file=sys.stderr)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, (data, rows) in exports.items():
        write_atomic(out / name, data)
        summary[name.removesuffix(".jsonl")] = {
            "path": name, "rows": len(rows), "sha256": sha256(data), "bytes": len(data)}
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"command": " ".join(PSQL_COMMAND), "user": "video", "database": "video"},
        "output_root": out.as_posix(),
        **summary,
        "trace_handling": ("description payloads are exported without the hosted _trace block"
                           " (payload - '_trace'); verification responses keep their recorded _trace"
                           " for provenance; the dataset builder trains on the serving fields only"),
        "sql": {"descriptions": DESCRIPTIONS_SQL, "verifications": VERIFICATIONS_SQL},
    }
    write_atomic(out / MANIFEST_FILE, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"event": "export_complete", "output_root": out.as_posix(), **summary,
                      "manifest": MANIFEST_FILE, "force": bool(existing)}, ensure_ascii=False))
    print(checklist(out))


if __name__ == "__main__":
    main()
