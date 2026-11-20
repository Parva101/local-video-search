"""PostgreSQL storage for source records and leased import jobs."""

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA_VERSION = 6


class LeaseLost(RuntimeError):
    """The worker no longer owns a live job lease."""


def _connect(database_url):
    return psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5)


def init_db(database_url):
    with _connect(database_url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(871634203)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
                version integer NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (%s) ON CONFLICT DO NOTHING",
            (1,),
        )
        version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
        if version not in (1, 2, 3, 4, 5, SCHEMA_VERSION):
            raise RuntimeError(f"Unsupported schema version {version}; expected {SCHEMA_VERSION}")
        conn.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        for target, filename in ((2, "002_visual.sql"), (3, "003_descriptions.sql"), (4, "004_uploads.sql"),
                                 (5, "005_capture_date.sql"), (6, "006_transcripts.sql")):
            if version < target:
                conn.execute(Path(__file__).with_name("migrations").joinpath(filename).read_text(encoding="utf-8"))
                conn.execute("UPDATE schema_version SET version = %s", (target,))


def ready(database_url):
    with _connect(database_url) as conn:
        row = conn.execute("SELECT version FROM schema_version WHERE singleton").fetchone()
        return row is not None and row["version"] == SCHEMA_VERSION


def bind_library(database_url, identity: str):
    """A single-library database must not reuse paths from a different mount."""
    if not identity:
        raise ValueError("Library identity must not be empty")
    with _connect(database_url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(871634203)")
        conn.execute("INSERT INTO library (identity) VALUES (%s) ON CONFLICT DO NOTHING", (identity,))
        actual = conn.execute("SELECT identity FROM library WHERE singleton").fetchone()["identity"]
        if actual != identity:
            raise RuntimeError("This database belongs to a different video directory. Restore its original directory or use a separate Compose project/database.")


def retry_job(database_url, job_id):
    with _connect(database_url) as conn:
        job = conn.execute(
            """UPDATE jobs SET state = 'queued', attempts = 0, error = NULL,
                   result = NULL, updated_at = now()
               WHERE id = %s AND state = 'failed' RETURNING *""", (job_id,)
        ).fetchone()
        if job and job["kind"] == "visual":
            conn.execute("UPDATE visual_builds SET state = 'queued', updated_at = now() WHERE id = %s", (job["index_build_id"],))
        if job and job["kind"] == "description":
            conn.execute("UPDATE description_builds SET state = 'queued', updated_at = now() WHERE id = %s", (job["description_build_id"],))
        if job and job["kind"] == "transcript":
            conn.execute("UPDATE transcript_builds SET state = 'queued', updated_at = now() WHERE id = %s", (job["transcript_build_id"],))
        return job


def enqueue(database_url, source_path: str, size: int, mtime_ns: int, *, auto_description_spec=None, original_filename=None):
    if not source_path or size < 0 or mtime_ns < 0:
        raise ValueError("Import source path, size, and modification time must be valid")
    payload = json.dumps([source_path, size, mtime_ns], ensure_ascii=False).encode("utf-8")
    dedupe_key = hashlib.sha256(payload).hexdigest()
    if auto_description_spec is not None:
        _description_key(auto_description_spec)
    with _connect(database_url) as conn:
        conn.execute(
            """INSERT INTO jobs (id, dedupe_key, source_path, expected_size, expected_mtime_ns,
                                auto_description_spec, original_filename)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dedupe_key) DO NOTHING""",
            (uuid4(), dedupe_key, source_path, size, mtime_ns,
             Jsonb(auto_description_spec) if auto_description_spec is not None else None, original_filename),
        )
        job = conn.execute("SELECT * FROM jobs WHERE dedupe_key = %s", (dedupe_key,)).fetchone()
        if auto_description_spec is not None and job["auto_description_spec"] != auto_description_spec:
            raise ValueError("This upload was already queued with a different description specification")
        return job


@contextmanager
def upload_lock(database_url, upload_id):
    """A session lock releases automatically if an uploading API process exits."""
    key = int.from_bytes(hashlib.sha256(str(upload_id).encode()).digest()[:8], "big", signed=True)
    with _connect(database_url) as conn:
        acquired = conn.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (key,)).fetchone()["acquired"]
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute("SELECT pg_advisory_unlock(%s)", (key,))


def get_job(database_url, job_id: str):
    with _connect(database_url) as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()


def _check_page(limit, offset=0):
    if not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("Limit must be 1..1000 and offset must be nonnegative")


def list_jobs(database_url, limit=100):
    """List jobs, newest first. Page cap: limit 1..1000."""
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, id LIMIT %s", (limit,)).fetchall()


def job_queue_depth(database_url):
    """Count queued and running jobs for the health endpoint."""
    with _connect(database_url) as conn:
        rows = conn.execute(
            "SELECT state, count(*) AS depth FROM jobs WHERE state IN ('queued', 'running') GROUP BY state"
        ).fetchall()
    return {row["state"]: row["depth"] for row in rows}


def claim_job(database_url, lease_seconds=60):
    if lease_seconds < 1:
        raise ValueError("Lease duration must be at least one second")
    with _connect(database_url) as conn:
        expired = conn.execute("""
            UPDATE jobs SET state = 'failed', lease_token = NULL, lease_until = NULL,
                error = '{"type":"LeaseExpired","message":"Worker lease expired after maximum attempts"}'::jsonb,
                updated_at = now()
            WHERE state = 'running' AND lease_until <= now() AND attempts >= max_attempts
            RETURNING index_build_id, description_build_id, transcript_build_id
        """).fetchall()
        for job in expired:
            if job["index_build_id"] is not None:
                conn.execute("UPDATE visual_builds SET state = 'failed', updated_at = now() WHERE id = %s", (job["index_build_id"],))
            if job["description_build_id"] is not None:
                conn.execute("UPDATE description_builds SET state = 'failed', updated_at = now() WHERE id = %s", (job["description_build_id"],))
            if job["transcript_build_id"] is not None:
                conn.execute("UPDATE transcript_builds SET state = 'failed', updated_at = now() WHERE id = %s", (job["transcript_build_id"],))
        job = conn.execute(
            """WITH candidate AS (
                SELECT id FROM jobs
                WHERE (state = 'queued' OR (state = 'running' AND lease_until <= now()))
                    AND attempts < max_attempts
                ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE jobs j SET state = 'running', attempts = attempts + 1,
                lease_token = %s, lease_until = now() + %s * interval '1 second',
                updated_at = now(), error = NULL
            FROM candidate c WHERE j.id = c.id RETURNING j.*""",
            (uuid4(), lease_seconds),
        ).fetchone()
        if job and job["kind"] == "visual":
            conn.execute("UPDATE visual_builds SET state = 'running', updated_at = now() WHERE id = %s", (job["index_build_id"],))
        if job and job["kind"] == "description":
            conn.execute("UPDATE description_builds SET state = 'running', updated_at = now() WHERE id = %s", (job["description_build_id"],))
        if job and job["kind"] == "transcript":
            conn.execute("UPDATE transcript_builds SET state = 'running', updated_at = now() WHERE id = %s", (job["transcript_build_id"],))
        return job


def heartbeat(database_url, job_id, token, lease_seconds=60):
    if lease_seconds < 1:
        raise ValueError("Lease duration must be at least one second")
    with _connect(database_url) as conn:
        return conn.execute(
            """UPDATE jobs SET lease_until = now() + %s * interval '1 second', updated_at = now()
               WHERE id = %s AND lease_token = %s AND state = 'running'
                   AND lease_until > clock_timestamp() RETURNING id""",
            (lease_seconds, job_id, token),
        ).fetchone() is not None


def fail_job(database_url, job_id, token, error: dict):
    with _connect(database_url) as conn:
        job = conn.execute(
            """UPDATE jobs SET state = 'failed', error = %s, lease_token = NULL,
                   lease_until = NULL, updated_at = now()
               WHERE id = %s AND lease_token = %s AND state = 'running'
                   AND lease_until > clock_timestamp() RETURNING index_build_id, description_build_id, transcript_build_id""",
            (Jsonb(error), job_id, token),
        ).fetchone()
        if job and job["index_build_id"] is not None:
            conn.execute("UPDATE visual_builds SET state = 'failed', updated_at = now() WHERE id = %s", (job["index_build_id"],))
        if job and job["description_build_id"] is not None:
            conn.execute("UPDATE description_builds SET state = 'failed', updated_at = now() WHERE id = %s", (job["description_build_id"],))
        if job and job["transcript_build_id"] is not None:
            conn.execute("UPDATE transcript_builds SET state = 'failed', updated_at = now() WHERE id = %s", (job["transcript_build_id"],))
        return job is not None


def complete_job(database_url, job_id, token, sha256: str, metadata: dict, windows: list[tuple[float, float]]):
    duration = metadata["duration_seconds"]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Recording duration must be finite and positive")
    if not windows or any(
        not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration
        for start, end in windows
    ):
        raise ValueError("Windows must be finite, ordered intervals within the recording")
    with _connect(database_url) as conn:
        job = conn.execute(
            """SELECT * FROM jobs WHERE id = %s AND lease_token = %s AND state = 'running' AND kind = 'import'
               AND lease_until > clock_timestamp() FOR UPDATE""",
            (job_id, token),
        ).fetchone()
        if job is None:
            raise LeaseLost("Job lease expired or belongs to another worker")
        conn.execute(
            "INSERT INTO assets (sha256, metadata) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (sha256, Jsonb(metadata)),
        )
        recording = conn.execute(
            """INSERT INTO recordings (id, source_path, sha256, size, mtime_ns)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (source_path, sha256) DO UPDATE
                   SET size = EXCLUDED.size, mtime_ns = EXCLUDED.mtime_ns
               RETURNING id""",
            (uuid4(), job["source_path"], sha256, job["expected_size"], job["expected_mtime_ns"]),
        ).fetchone()
        recording_id = str(recording["id"])
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO windows (recording_id, start_seconds, end_seconds)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                [(recording_id, start, end) for start, end in windows],
            )
        result = {"recording_id": recording_id}
        if job["auto_description_spec"] is not None:
            description = _enqueue_description(conn, recording_id, job["auto_description_spec"])
            result["description_job_id"] = str(description["id"])
            result["description_build_id"] = str(description["description_build_id"])
        committed = conn.execute(
            """UPDATE jobs SET state = 'succeeded', result = %s, error = NULL,
                   lease_token = NULL, lease_until = NULL, updated_at = now()
               WHERE id = %s AND lease_token = %s AND lease_until > clock_timestamp()
               RETURNING id""",
            (Jsonb(result), job_id, token),
        ).fetchone()
        if committed is None:
            raise LeaseLost("Job lease expired before commit")
        return recording_id


_RECORDINGS = """
    SELECT r.*, a.metadata || jsonb_build_object('search_index_status', CASE
        WHEN EXISTS (SELECT 1 FROM visual_builds b WHERE b.recording_id = r.id AND b.state = 'ready')
          OR EXISTS (SELECT 1 FROM description_builds b WHERE b.recording_id = r.id AND b.state = 'ready') THEN 'ready'
        WHEN EXISTS (SELECT 1 FROM visual_builds b WHERE b.recording_id = r.id AND b.state IN ('queued', 'running'))
          OR EXISTS (SELECT 1 FROM description_builds b WHERE b.recording_id = r.id AND b.state IN ('queued', 'running')) THEN 'partial'
        WHEN EXISTS (SELECT 1 FROM visual_builds b WHERE b.recording_id = r.id AND b.state = 'failed')
          OR EXISTS (SELECT 1 FROM description_builds b WHERE b.recording_id = r.id AND b.state = 'failed') THEN 'failed'
        ELSE 'not_built' END) AS metadata,
        (SELECT count(*) FROM windows w WHERE w.recording_id = r.id) AS windows_count
    FROM recordings r JOIN assets a ON a.sha256 = r.sha256
"""


def get_recording(database_url, recording_id):
    with _connect(database_url) as conn:
        return conn.execute(_RECORDINGS + " WHERE r.id = %s", (recording_id,)).fetchone()


def list_recordings(database_url, limit=100):
    """List recordings, newest first. Page cap: limit 1..1000."""
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute(
            _RECORDINGS + " ORDER BY r.created_at DESC, r.id LIMIT %s", (limit,)
        ).fetchall()


def set_capture_date(database_url, recording_id, capture_date, source):
    """Set or clear one recording's calendar capture date. None clears both fields."""
    if source not in ("user", "file_mtime"):
        raise ValueError("Capture date source must be 'user' or 'file_mtime'")
    if capture_date is not None and not isinstance(capture_date, date):
        raise ValueError("Capture date must be a calendar date")
    with _connect(database_url) as conn:
        return conn.execute(
            """UPDATE recordings SET capture_date = %s, capture_date_source = %s
               WHERE id = %s RETURNING id, capture_date, capture_date_source""",
            (capture_date, source if capture_date is not None else None, recording_id),
        ).fetchone()


def capture_dates_from_files(database_url, utc_offset_minutes, recording_ids=None):
    """Derive capture dates from stored modification times at the user's time-zone offset.

    Only recordings without a capture date are updated, so an explicit user date is
    never overwritten. The stored mtime is the value verified at import time.
    """
    if not isinstance(utc_offset_minutes, int) or isinstance(utc_offset_minutes, bool) \
            or not -1440 <= utc_offset_minutes <= 1440:
        raise ValueError("utc_offset_minutes must be an integer between -1440 and 1440")
    zone = timezone(timedelta(minutes=utc_offset_minutes))
    with _connect(database_url) as conn:
        rows = conn.execute(
            """SELECT id, mtime_ns FROM recordings
               WHERE capture_date IS NULL AND (%s::uuid[] IS NULL OR id = ANY(%s::uuid[]))""",
            (recording_ids, recording_ids),
        ).fetchall()
        updated = []
        for row in rows:
            day = datetime.fromtimestamp(row["mtime_ns"] / 1_000_000_000, tz=zone).date()
            conn.execute(
                "UPDATE recordings SET capture_date = %s, capture_date_source = 'file_mtime' WHERE id = %s",
                (day, row["id"]),
            )
            updated.append({"id": str(row["id"]), "capture_date": day.isoformat()})
        return updated


def list_windows(database_url, recording_id, limit=100, offset=0):
    """List one recording's windows in time order. Page cap: limit 1..1000, offset 0+."""
    _check_page(limit, offset)
    with _connect(database_url) as conn:
        return conn.execute(
            """SELECT start_seconds, end_seconds FROM windows WHERE recording_id = %s
               ORDER BY start_seconds, end_seconds LIMIT %s OFFSET %s""",
            (recording_id, limit, offset),
        ).fetchall()


def count_windows(database_url, recording_id, start_seconds=None, end_seconds=None):
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (start_seconds, end_seconds)):
        raise ValueError("Window-count times must be finite and nonnegative")
    with _connect(database_url) as conn:
        row = conn.execute(
            """SELECT count(*) AS total FROM windows WHERE recording_id = %s
               AND (%s::float8 IS NULL OR end_seconds > %s) AND (%s::float8 IS NULL OR start_seconds < %s)""",
            (recording_id, start_seconds, start_seconds, end_seconds, end_seconds),
        ).fetchone()
        return row["total"]


def _visual_key(spec):
    required = ("model_id", "revision", "preprocess_version", "sampling_version", "runtime")
    if not isinstance(spec, dict) or any(not spec.get(key) for key in required):
        raise ValueError("Visual specification needs model, revision, preprocessing, sampling, and runtime")
    if spec.get("dimensions") != 768 or not 1 <= spec.get("frames_per_window", 0) <= 16:
        raise ValueError("Visual index requires 768 dimensions and 1..16 frames per window")
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _vector_literal(embedding, dimensions=768):
    if len(embedding) != dimensions or any(not math.isfinite(value) for value in embedding):
        raise ValueError(f"Embedding must contain {dimensions} finite values")
    if not math.isclose(sum(value * value for value in embedding), 1, abs_tol=0.005):
        raise ValueError("Embedding must have unit length")
    return json.dumps(embedding, allow_nan=False)


def enqueue_visual(database_url, recording_id, spec):
    key = _visual_key(spec)
    with _connect(database_url) as conn:
        recording = conn.execute("SELECT * FROM recordings WHERE id = %s", (recording_id,)).fetchone()
        if recording is None:
            raise ValueError("Recording not found")
        conn.execute(
            """INSERT INTO visual_builds (id, recording_id, config_key, spec)
               VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""", (uuid4(), recording_id, key, Jsonb(spec))
        )
        build = conn.execute("SELECT id FROM visual_builds WHERE recording_id = %s AND config_key = %s", (recording_id, key)).fetchone()
        dedupe_key = "visual:" + str(build["id"])
        conn.execute(
            """INSERT INTO jobs (id, dedupe_key, source_path, expected_size, expected_mtime_ns, kind, index_build_id)
               VALUES (%s, %s, %s, %s, %s, 'visual', %s) ON CONFLICT DO NOTHING""",
            (uuid4(), dedupe_key, recording["source_path"], recording["size"], recording["mtime_ns"], build["id"]),
        )
        return conn.execute("SELECT * FROM jobs WHERE dedupe_key = %s", (dedupe_key,)).fetchone()


_VISUAL_BUILDS = """
    SELECT b.*, r.source_path, j.id AS job_id,
        (SELECT count(*) FROM visual_windows v WHERE v.build_id = b.id) AS completed_windows,
        (SELECT count(*) FROM windows w WHERE w.recording_id = b.recording_id) AS total_windows
    FROM visual_builds b JOIN recordings r ON r.id = b.recording_id
    JOIN jobs j ON j.index_build_id = b.id
"""


def get_visual_build(database_url, build_id):
    with _connect(database_url) as conn:
        return conn.execute(_VISUAL_BUILDS + " WHERE b.id = %s", (build_id,)).fetchone()


def list_visual_builds(database_url, recording_id=None, limit=100):
    """List visual index builds, newest first. Page cap: limit 1..1000."""
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute(_VISUAL_BUILDS + " WHERE (%s::uuid IS NULL OR b.recording_id = %s) ORDER BY b.created_at DESC, b.id LIMIT %s",
                            (recording_id, recording_id, limit)).fetchall()


def pending_visual_windows(database_url, build_id, limit=100):
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute(
            """SELECT w.start_seconds, w.end_seconds FROM visual_builds b
               JOIN windows w ON w.recording_id = b.recording_id
               LEFT JOIN visual_windows v ON v.build_id = b.id
                   AND v.start_seconds = w.start_seconds AND v.end_seconds = w.end_seconds
               WHERE b.id = %s AND v.build_id IS NULL ORDER BY w.start_seconds, w.end_seconds LIMIT %s""", (build_id, limit)
        ).fetchall()


def _visual_lease(conn, job_id, token):
    job = conn.execute(
        """SELECT j.*, b.recording_id, b.spec, a.metadata FROM jobs j
           JOIN visual_builds b ON b.id = j.index_build_id
           JOIN recordings r ON r.id = b.recording_id JOIN assets a ON a.sha256 = r.sha256
           WHERE j.id = %s AND j.lease_token = %s AND j.state = 'running'
               AND j.kind = 'visual' AND j.lease_until > clock_timestamp() FOR UPDATE OF j""", (job_id, token)
    ).fetchone()
    if job is None:
        raise LeaseLost("Visual job lease expired or belongs to another worker")
    return job


def save_visual_window(database_url, job_id, token, start, end, samples, embedding):
    vector = _vector_literal(embedding)
    if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end:
        raise ValueError("Window must be a finite, ordered interval")
    with _connect(database_url) as conn:
        job = _visual_lease(conn, job_id, token)
        if len(samples) != job["spec"]["frames_per_window"]:
            raise ValueError("Sample count does not match the visual specification")
        origin = job["metadata"].get("source_start_seconds", 0.0)
        for sample in samples:
            values = [sample[key] for key in ("requested_seconds", "source_seconds", "pts_seconds")]
            if not all(math.isfinite(value) for value in values) or not start <= values[0] < end or not start <= values[1] < end:
                raise ValueError("Frame samples must lie inside their source window")
            if not math.isclose(values[2], values[1] + origin, abs_tol=0.00001):
                raise ValueError("Frame PTS does not map to the source timeline")
        window = conn.execute("SELECT 1 FROM windows WHERE recording_id = %s AND start_seconds = %s AND end_seconds = %s",
                              (job["recording_id"], start, end)).fetchone()
        if window is None:
            raise ValueError("Window is not registered for this recording")
        conn.execute(
            """INSERT INTO visual_windows (build_id, start_seconds, end_seconds, samples, embedding)
               VALUES (%s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING""",
            (job["index_build_id"], start, end, Jsonb(samples), vector),
        )
        _visual_lease(conn, job_id, token)


def finish_visual_job(database_url, job_id, token):
    with _connect(database_url) as conn:
        job = _visual_lease(conn, job_id, token)
        pending = conn.execute(
            """SELECT count(*) AS total,
                   count(v.build_id) AS completed FROM windows w LEFT JOIN visual_windows v
                   ON v.build_id = %s AND v.start_seconds = w.start_seconds AND v.end_seconds = w.end_seconds
               WHERE w.recording_id = %s""", (job["index_build_id"], job["recording_id"])
        ).fetchone()
        if pending["total"] == 0 or pending["total"] != pending["completed"]:
            raise ValueError("Cannot publish an incomplete visual index")
        conn.execute("UPDATE visual_builds SET state = 'ready', updated_at = now() WHERE id = %s", (job["index_build_id"],))
        done = conn.execute(
            """UPDATE jobs SET state = 'succeeded', result = %s, error = NULL,
                   lease_token = NULL, lease_until = NULL, updated_at = now()
               WHERE id = %s AND lease_token = %s AND lease_until > clock_timestamp() RETURNING id""",
            (Jsonb({"build_id": str(job["index_build_id"])}), job_id, token),
        ).fetchone()
        if done is None:
            raise LeaseLost("Visual job lease expired before publication")
        return str(job["index_build_id"])


def search_visual(database_url, spec, query_vector, limit=10, recording_ids=None, start_seconds=None, end_seconds=None,
                  start_date=None, end_date=None):
    _check_page(limit)
    key, vector = _visual_key(spec), _vector_literal(query_vector)
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (start_seconds, end_seconds)):
        raise ValueError("Search times must be finite and nonnegative")
    if start_seconds is not None and end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("Search end must be after its start")
    if any(value is not None and not isinstance(value, date) for value in (start_date, end_date)):
        raise ValueError("Search dates must be calendar dates")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("Search end date must not be before its start date")
    scope = "(%s::uuid[] IS NULL OR r.id = ANY(%s::uuid[]))"
    times = "(%s::float8 IS NULL OR w.end_seconds > %s) AND (%s::float8 IS NULL OR w.start_seconds < %s)"
    dates = "((%s::date IS NULL OR r.capture_date >= %s::date) AND (%s::date IS NULL OR r.capture_date <= %s::date))"
    scope_params = (recording_ids, recording_ids, start_seconds, start_seconds, end_seconds, end_seconds)
    params = scope_params + (start_date, start_date, end_date, end_date)
    with _connect(database_url) as conn:
        results = conn.execute(
            """SELECT b.id AS build_id, r.id AS recording_id, r.source_path, r.size, r.mtime_ns,
                   w.start_seconds, w.end_seconds, w.samples, 1 - (w.embedding <=> %s::vector) AS similarity
               FROM visual_windows w JOIN visual_builds b ON b.id = w.build_id
               JOIN recordings r ON r.id = b.recording_id
               WHERE b.config_key = %s AND b.state = 'ready' AND """ + scope + " AND " + times +
            " AND " + dates + " ORDER BY w.embedding <=> %s::vector, r.id, w.start_seconds, b.id LIMIT %s",
            (vector, key, *params, vector, limit),
        ).fetchall()
        coverage = conn.execute(
            """SELECT count(DISTINCT r.id) AS total_recordings, count(w.recording_id) AS total_windows,
                   count(DISTINCT r.id) FILTER (WHERE b.state = 'ready') AS ready_recordings,
                   count(w.recording_id) FILTER (WHERE b.state = 'ready') AS ready_windows,
                   count(DISTINCT r.id) FILTER (WHERE r.capture_date IS NULL) AS recordings_without_capture_date
               FROM recordings r LEFT JOIN windows w ON w.recording_id = r.id
               LEFT JOIN visual_builds b ON b.recording_id = r.id AND b.config_key = %s
               WHERE """ + scope + " AND " + times, (key, *scope_params),
        ).fetchone()
        incomplete = conn.execute(
            """SELECT b.id, b.recording_id, b.state, count(*) OVER () AS total_count
               FROM visual_builds b JOIN recordings r ON r.id = b.recording_id
               WHERE b.config_key = %s AND b.state <> 'ready' AND """ + scope +
            " AND EXISTS (SELECT 1 FROM windows w WHERE w.recording_id = r.id AND " + times + ")"
            " AND " + dates + " ORDER BY b.created_at, b.id LIMIT 100",
            (key, *params),
        ).fetchall()
        incomplete_count = incomplete[0]["total_count"] if incomplete else 0
        for item in incomplete:
            item.pop("total_count")
        return {"results": results, "coverage": {**coverage, "incomplete_builds": incomplete,
                                                   "incomplete_builds_count": incomplete_count}}


def _description_key(spec):
    required = ("model_id", "revision", "preprocess_version", "sampling_version", "runtime")
    if not isinstance(spec, dict) or any(not spec.get(key) for key in required):
        raise ValueError("Description specification needs model, revision, preprocessing, sampling, and runtime")
    if spec.get("dimensions") != 384 or spec.get("frames_per_window") != 8:
        raise ValueError("Description index requires 384 dimensions and eight frame slots")
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def enqueue_description(database_url, recording_id, spec):
    with _connect(database_url) as conn:
        return _enqueue_description(conn, recording_id, spec)


def _enqueue_description(conn, recording_id, spec):
    key = _description_key(spec)
    recording = conn.execute("SELECT * FROM recordings WHERE id = %s", (recording_id,)).fetchone()
    if recording is None:
        raise ValueError("Recording not found")
    conn.execute("""INSERT INTO description_builds (id, recording_id, config_key, spec)
                        VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                     (uuid4(), recording_id, key, Jsonb(spec)))
    build = conn.execute("SELECT id FROM description_builds WHERE recording_id = %s AND config_key = %s",
                             (recording_id, key)).fetchone()
    dedupe_key = "description:" + str(build["id"])
    conn.execute("""INSERT INTO jobs (id, dedupe_key, source_path, expected_size, expected_mtime_ns, kind, description_build_id)
                        VALUES (%s, %s, %s, %s, %s, 'description', %s) ON CONFLICT DO NOTHING""",
                     (uuid4(), dedupe_key, recording["source_path"], recording["size"], recording["mtime_ns"], build["id"]))
    return conn.execute("SELECT * FROM jobs WHERE dedupe_key = %s", (dedupe_key,)).fetchone()


_DESCRIPTION_BUILDS = """
    SELECT b.*, r.source_path, j.id AS job_id,
        (SELECT count(*) FROM description_windows d WHERE d.build_id = b.id) AS completed_windows,
        (SELECT count(*) FROM windows w WHERE w.recording_id = b.recording_id) AS total_windows
    FROM description_builds b JOIN recordings r ON r.id = b.recording_id
    JOIN jobs j ON j.description_build_id = b.id
"""


def get_description_build(database_url, build_id):
    with _connect(database_url) as conn:
        return conn.execute(_DESCRIPTION_BUILDS + " WHERE b.id = %s", (build_id,)).fetchone()


def list_description_builds(database_url, recording_id=None, limit=100):
    """List description index builds, newest first. Page cap: limit 1..1000."""
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute(_DESCRIPTION_BUILDS + " WHERE (%s::uuid IS NULL OR b.recording_id = %s) ORDER BY b.created_at DESC, b.id LIMIT %s",
                            (recording_id, recording_id, limit)).fetchall()


def pending_description_windows(database_url, build_id, limit=32):
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute("""SELECT w.start_seconds, w.end_seconds FROM description_builds b
            JOIN windows w ON w.recording_id = b.recording_id LEFT JOIN description_windows d
            ON d.build_id = b.id AND d.start_seconds = w.start_seconds AND d.end_seconds = w.end_seconds
            WHERE b.id = %s AND d.build_id IS NULL ORDER BY w.start_seconds, w.end_seconds LIMIT %s""",
                            (build_id, limit)).fetchall()


def _description_lease(conn, job_id, token):
    job = conn.execute("""SELECT j.*, b.recording_id, b.spec, a.metadata FROM jobs j
        JOIN description_builds b ON b.id = j.description_build_id
        JOIN recordings r ON r.id = b.recording_id JOIN assets a ON a.sha256 = r.sha256
        WHERE j.id = %s AND j.lease_token = %s AND j.state = 'running' AND j.kind = 'description'
        AND j.lease_until > clock_timestamp() FOR UPDATE OF j""", (job_id, token)).fetchone()
    if job is None:
        raise LeaseLost("Description job lease expired or belongs to another worker")
    return job


def _check_samples(samples, start, end, metadata, count):
    if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end:
        raise ValueError("Window must be a finite, ordered interval")
    if len(samples) != count:
        raise ValueError("Sample count does not match the specification")
    origin = metadata.get("source_start_seconds", 0.0)
    for sample in samples:
        values = [sample[key] for key in ("requested_seconds", "source_seconds", "pts_seconds")]
        if not all(math.isfinite(value) for value in values) or not start <= values[0] < end or not start <= values[1] < end:
            raise ValueError("Frame samples must lie inside their source window")
        if not math.isclose(values[2], values[1] + origin, abs_tol=0.00001):
            raise ValueError("Frame PTS does not map to the source timeline")


def save_description_window(database_url, job_id, token, start, end, samples, payload, searchable_text, embedding):
    vector = _vector_literal(embedding, 384)
    if not isinstance(payload, dict) or not isinstance(searchable_text, str) or not 1 <= len(searchable_text.strip()) <= 4000:
        raise ValueError("Description needs a JSON object and 1..4000 searchable characters")
    with _connect(database_url) as conn:
        job = _description_lease(conn, job_id, token)
        _check_samples(samples, start, end, job["metadata"], job["spec"]["frames_per_window"])
        if conn.execute("SELECT 1 FROM windows WHERE recording_id = %s AND start_seconds = %s AND end_seconds = %s",
                        (job["recording_id"], start, end)).fetchone() is None:
            raise ValueError("Window is not registered for this recording")
        conn.execute("""INSERT INTO description_windows (build_id, start_seconds, end_seconds, samples, payload, searchable_text, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING""",
                     (job["description_build_id"], start, end, Jsonb(samples), Jsonb(payload), searchable_text, vector))
        _description_lease(conn, job_id, token)


def finish_description_job(database_url, job_id, token):
    with _connect(database_url) as conn:
        job = _description_lease(conn, job_id, token)
        counts = conn.execute("""SELECT count(*) AS total, count(d.build_id) AS completed FROM windows w
            LEFT JOIN description_windows d ON d.build_id = %s AND d.start_seconds = w.start_seconds AND d.end_seconds = w.end_seconds
            WHERE w.recording_id = %s""", (job["description_build_id"], job["recording_id"])).fetchone()
        if counts["total"] == 0 or counts["total"] != counts["completed"]:
            raise ValueError("Cannot publish an incomplete description index")
        conn.execute("UPDATE description_builds SET state = 'ready', updated_at = now() WHERE id = %s", (job["description_build_id"],))
        done = conn.execute("""UPDATE jobs SET state = 'succeeded', result = %s, error = NULL,
            lease_token = NULL, lease_until = NULL, updated_at = now()
            WHERE id = %s AND lease_token = %s AND lease_until > clock_timestamp() RETURNING id""",
                            (Jsonb({"build_id": str(job["description_build_id"])}), job_id, token)).fetchone()
        if done is None:
            raise LeaseLost("Description job lease expired before publication")
        return str(job["description_build_id"])


def search_descriptions(database_url, spec, query, query_vector, limit=10, recording_ids=None, start_seconds=None,
                        end_seconds=None, start_date=None, end_date=None):
    _check_page(limit)
    key, vector = _description_key(spec), _vector_literal(query_vector, 384)
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 4000:
        raise ValueError("Description query must contain 1..4000 characters")
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (start_seconds, end_seconds)):
        raise ValueError("Search times must be finite and nonnegative")
    if start_seconds is not None and end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("Search end must be after its start")
    if any(value is not None and not isinstance(value, date) for value in (start_date, end_date)):
        raise ValueError("Search dates must be calendar dates")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("Search end date must not be before its start date")
    scope = "(%s::uuid[] IS NULL OR r.id = ANY(%s::uuid[]))"
    times = "(%s::float8 IS NULL OR w.end_seconds > %s) AND (%s::float8 IS NULL OR w.start_seconds < %s)"
    dates = "((%s::date IS NULL OR r.capture_date >= %s::date) AND (%s::date IS NULL OR r.capture_date <= %s::date))"
    scope_params = (recording_ids, recording_ids, start_seconds, start_seconds, end_seconds, end_seconds)
    params = scope_params + (start_date, start_date, end_date, end_date)
    budget = min(100, limit * 4)
    with _connect(database_url) as conn:
        results = conn.execute("""WITH scoped AS (
            SELECT w.*, b.recording_id, r.source_path, r.size, r.mtime_ns FROM description_windows w
            JOIN description_builds b ON b.id = w.build_id JOIN recordings r ON r.id = b.recording_id
            WHERE b.config_key = %s AND b.state = 'ready' AND """ + scope + " AND " + times + " AND " + dates + """
        ), dense AS (
            SELECT build_id, start_seconds, end_seconds,
                row_number() OVER (ORDER BY embedding <=> %s::vector, recording_id, start_seconds) AS vector_rank
            FROM scoped ORDER BY vector_rank LIMIT %s
        ), lexical AS (
            SELECT build_id, start_seconds, end_seconds,
                ts_rank_cd(to_tsvector('english', searchable_text), plainto_tsquery('english', %s)) AS lexical_rank,
                row_number() OVER (ORDER BY ts_rank_cd(to_tsvector('english', searchable_text), plainto_tsquery('english', %s)) DESC,
                                   recording_id, start_seconds) AS lexical_position
            FROM scoped WHERE to_tsvector('english', searchable_text) @@ plainto_tsquery('english', %s)
            ORDER BY lexical_position LIMIT %s
        ), ranked AS (
            SELECT coalesce(d.build_id, l.build_id) AS build_id,
                coalesce(d.start_seconds, l.start_seconds) AS start_seconds,
                coalesce(d.end_seconds, l.end_seconds) AS end_seconds,
                d.vector_rank, l.lexical_rank, l.lexical_position,
                coalesce(1.0 / (60 + d.vector_rank), 0) + coalesce(1.0 / (60 + l.lexical_position), 0) AS rrf_score
            FROM dense d FULL JOIN lexical l USING (build_id, start_seconds, end_seconds)
        ) SELECT s.build_id, s.recording_id, s.source_path, s.size, s.mtime_ns,
            s.start_seconds, s.end_seconds, s.samples, s.payload AS description,
            1 - (s.embedding <=> %s::vector) AS vector_similarity,
            r.vector_rank, coalesce(r.lexical_rank, 0) AS lexical_rank, r.lexical_position, r.rrf_score
          FROM ranked r JOIN scoped s USING (build_id, start_seconds, end_seconds)
          ORDER BY r.rrf_score DESC, vector_similarity DESC, s.recording_id, s.start_seconds, s.build_id LIMIT %s""",
                               (key, *params, vector, budget, query, query, query, budget, vector, limit)).fetchall()
        coverage = conn.execute("""SELECT count(DISTINCT r.id) AS total_recordings, count(w.recording_id) AS total_windows,
            count(DISTINCT r.id) FILTER (WHERE b.state = 'ready') AS ready_recordings,
            count(w.recording_id) FILTER (WHERE b.state = 'ready') AS ready_windows,
            count(DISTINCT r.id) FILTER (WHERE r.capture_date IS NULL) AS recordings_without_capture_date
            FROM recordings r LEFT JOIN windows w ON w.recording_id = r.id
            LEFT JOIN description_builds b ON b.recording_id = r.id AND b.config_key = %s
            WHERE """ + scope + " AND " + times, (key, *scope_params)).fetchone()
        incomplete = conn.execute("""SELECT b.id, b.recording_id, b.state, count(*) OVER () AS total_count
            FROM description_builds b JOIN recordings r ON r.id = b.recording_id
            WHERE b.config_key = %s AND b.state <> 'ready' AND """ + scope +
            " AND EXISTS (SELECT 1 FROM windows w WHERE w.recording_id = r.id AND " + times + ")"
            " AND " + dates + " ORDER BY b.created_at, b.id LIMIT 100", (key, *params)).fetchall()
        incomplete_count = incomplete[0]["total_count"] if incomplete else 0
        for item in incomplete:
            item.pop("total_count")
        return {"results": results, "coverage": {**coverage, "incomplete_builds": incomplete,
                                                   "incomplete_builds_count": incomplete_count}}


def save_verification(database_url, recording_id, query, start, end, spec, samples, response):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 4000 or not isinstance(spec, dict) or not isinstance(response, dict):
        raise ValueError("Verification needs a query, specification, and JSON response")
    with _connect(database_url) as conn:
        row = conn.execute("SELECT a.metadata FROM recordings r JOIN assets a ON a.sha256 = r.sha256 WHERE r.id = %s",
                           (recording_id,)).fetchone()
        if row is None:
            raise ValueError("Recording not found")
        if end > row["metadata"]["duration_seconds"]:
            raise ValueError("Verification interval leaves the recording")
        _check_samples(samples, start, end, row["metadata"], 8)
        result_id = str(uuid4())
        conn.execute("""INSERT INTO verification_runs (id, recording_id, query, start_seconds, end_seconds, spec, samples, response)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                     (result_id, recording_id, query, start, end, Jsonb(spec), Jsonb(samples), Jsonb(response)))
        return result_id


def get_verification(database_url, verification_id):
    with _connect(database_url) as conn:
        return conn.execute("SELECT * FROM verification_runs WHERE id = %s", (verification_id,)).fetchone()


def _transcript_key(spec):
    if not isinstance(spec, dict) or spec.get("source") not in ("subtitle", "asr"):
        raise ValueError("Transcript specification needs a subtitle or asr source")
    if spec.get("dimensions") != 384:
        raise ValueError("Transcript search requires 384-dimensional text embeddings")
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


_TRANSCRIPT_BUILDS = """
    SELECT b.*, r.source_path, j.id AS job_id,
        (SELECT count(*) FROM transcript_segments s WHERE s.build_id = b.id) AS completed_segments
    FROM transcript_builds b JOIN recordings r ON r.id = b.recording_id
    LEFT JOIN jobs j ON j.transcript_build_id = b.id
"""


def get_transcript_build(database_url, build_id):
    with _connect(database_url) as conn:
        return conn.execute(_TRANSCRIPT_BUILDS + " WHERE b.id = %s", (build_id,)).fetchone()


def list_transcript_builds(database_url, recording_id=None, limit=100):
    """List transcript index builds, newest first. Page cap: limit 1..1000."""
    _check_page(limit)
    with _connect(database_url) as conn:
        return conn.execute(_TRANSCRIPT_BUILDS + " WHERE (%s::uuid IS NULL OR b.recording_id = %s) ORDER BY b.created_at DESC, b.id LIMIT %s",
                            (recording_id, recording_id, limit)).fetchall()


def _enqueue_transcript(conn, recording_id, spec):
    key = _transcript_key(spec)
    recording = conn.execute("SELECT * FROM recordings WHERE id = %s", (recording_id,)).fetchone()
    if recording is None:
        raise ValueError("Recording not found")
    conn.execute("""INSERT INTO transcript_builds (id, recording_id, config_key, spec)
                        VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                 (uuid4(), recording_id, key, Jsonb(spec)))
    build = conn.execute("SELECT id FROM transcript_builds WHERE recording_id = %s AND config_key = %s",
                         (recording_id, key)).fetchone()
    dedupe_key = "transcript:" + str(build["id"])
    conn.execute("""INSERT INTO jobs (id, dedupe_key, source_path, expected_size, expected_mtime_ns, kind, transcript_build_id)
                        VALUES (%s, %s, %s, %s, %s, 'transcript', %s) ON CONFLICT DO NOTHING""",
                 (uuid4(), dedupe_key, recording["source_path"], recording["size"], recording["mtime_ns"], build["id"]))
    return conn.execute("SELECT * FROM jobs WHERE dedupe_key = %s", (dedupe_key,)).fetchone()


def enqueue_transcript(database_url, recording_id, spec):
    with _connect(database_url) as conn:
        return _enqueue_transcript(conn, recording_id, spec)


def create_ready_transcript(database_url, recording_id, spec, segments):
    """Publish a complete deterministic transcript (subtitle import) in one transaction."""
    key = _transcript_key(spec)
    if not segments:
        raise ValueError("A transcript needs at least one segment")
    for start, end, text, _ in segments:
        if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end:
            raise ValueError("Transcript segments must be finite, ordered intervals")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
            raise ValueError("Transcript segment text must contain 1..4000 characters")
    with _connect(database_url) as conn:
        recording = conn.execute("SELECT * FROM recordings WHERE id = %s", (recording_id,)).fetchone()
        if recording is None:
            raise ValueError("Recording not found")
        existing = conn.execute("SELECT id FROM transcript_builds WHERE recording_id = %s AND config_key = %s",
                                (recording_id, key)).fetchone()
        if existing is not None:
            return str(existing["id"]), False
        build_id = uuid4()
        conn.execute("""INSERT INTO transcript_builds (id, recording_id, config_key, spec, state)
                        VALUES (%s, %s, %s, %s, 'ready')""", (build_id, recording_id, key, Jsonb(spec)))
        for start, end, text, embedding in segments:
            conn.execute("""INSERT INTO transcript_segments (build_id, start_seconds, end_seconds, text, embedding)
                            VALUES (%s, %s, %s, %s, %s::vector)""",
                         (build_id, start, end, text.strip(), _vector_literal(embedding, 384)))
        return str(build_id), True


def _transcript_lease(conn, job_id, token):
    job = conn.execute("""SELECT j.*, b.recording_id, b.spec FROM jobs j
        JOIN transcript_builds b ON b.id = j.transcript_build_id
        WHERE j.id = %s AND j.lease_token = %s AND j.state = 'running' AND j.kind = 'transcript'
        AND j.lease_until > clock_timestamp() FOR UPDATE OF j""", (job_id, token)).fetchone()
    if job is None:
        raise LeaseLost("Transcript job lease expired or belongs to another worker")
    return job


def save_transcript_segment(database_url, job_id, token, start, end, text, embedding):
    vector = _vector_literal(embedding, 384)
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
        raise ValueError("Transcript segment text must contain 1..4000 characters")
    with _connect(database_url) as conn:
        job = _transcript_lease(conn, job_id, token)
        duration = conn.execute("""SELECT a.metadata->>'duration_seconds' AS duration FROM recordings r
            JOIN assets a ON a.sha256 = r.sha256 WHERE r.id = %s""", (job["recording_id"],)).fetchone()["duration"]
        if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end <= float(duration):
            raise ValueError("Transcript segment must be a finite interval inside the recording")
        conn.execute("""INSERT INTO transcript_segments (build_id, start_seconds, end_seconds, text, embedding)
            VALUES (%s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING""",
                     (job["transcript_build_id"], start, end, text.strip(), vector))
        _transcript_lease(conn, job_id, token)


def finish_transcript_job(database_url, job_id, token):
    with _connect(database_url) as conn:
        job = _transcript_lease(conn, job_id, token)
        counts = conn.execute("SELECT count(*) AS segments FROM transcript_segments WHERE build_id = %s",
                               (job["transcript_build_id"],)).fetchone()
        if counts["segments"] == 0:
            raise ValueError("Cannot publish an empty transcript index")
        conn.execute("UPDATE transcript_builds SET state = 'ready', updated_at = now() WHERE id = %s",
                     (job["transcript_build_id"],))
        done = conn.execute("""UPDATE jobs SET state = 'succeeded', result = %s, error = NULL,
            lease_token = NULL, lease_until = NULL, updated_at = now()
            WHERE id = %s AND lease_token = %s AND lease_until > clock_timestamp() RETURNING id""",
                            (Jsonb({"build_id": str(job["transcript_build_id"])}), job_id, token)).fetchone()
        if done is None:
            raise LeaseLost("Transcript job lease expired before publication")
        return str(job["transcript_build_id"])


def search_speech(database_url, query, query_vector, limit=10, recording_ids=None, start_seconds=None,
                  end_seconds=None, start_date=None, end_date=None):
    """Search ready transcript segments (ASR or supplied subtitles) with dense and lexical ranks.

    All transcript segments share the pinned 384-dimensional text embedding space, so every
    ready build is searched rather than one configuration key. When the query contains a
    double-quoted phrase, the longest quoted phrase gets a bounded boost: lexical matches
    whose text contains that phrase (case-insensitive) take the top lexical positions.
    Queries without quoted text rank exactly as before.
    """
    _check_page(limit)
    vector = _vector_literal(query_vector, 384)
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 4000:
        raise ValueError("Speech query must contain 1..4000 characters")
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (start_seconds, end_seconds)):
        raise ValueError("Search times must be finite and nonnegative")
    if start_seconds is not None and end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("Search end must be after its start")
    if any(value is not None and not isinstance(value, date) for value in (start_date, end_date)):
        raise ValueError("Search dates must be calendar dates")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("Search end date must not be before its start date")
    scope = "(%s::uuid[] IS NULL OR r.id = ANY(%s::uuid[]))"
    times = "(%s::float8 IS NULL OR s.end_seconds > %s) AND (%s::float8 IS NULL OR s.start_seconds < %s)"
    dates = "((%s::date IS NULL OR r.capture_date >= %s::date) AND (%s::date IS NULL OR r.capture_date <= %s::date))"
    scope_params = (recording_ids, recording_ids, start_seconds, start_seconds, end_seconds, end_seconds)
    params = scope_params + (start_date, start_date, end_date, end_date)
    budget = min(100, limit * 4)
    quoted = [item.strip() for item in re.findall(r'"([^"]*)"', query)]
    quoted = [item for item in quoted if item]
    phrase = max(quoted, key=len) if quoted else None
    with _connect(database_url) as conn:
        results = conn.execute("""WITH scoped AS (
            SELECT s.*, b.recording_id, r.source_path, r.size, r.mtime_ns FROM transcript_segments s
            JOIN transcript_builds b ON b.id = s.build_id JOIN recordings r ON r.id = b.recording_id
            WHERE b.state = 'ready' AND """ + scope + " AND " + times + " AND " + dates + """
        ), dense AS (
            SELECT build_id, start_seconds, end_seconds,
                row_number() OVER (ORDER BY embedding <=> %s::vector, recording_id, start_seconds) AS vector_rank
            FROM scoped ORDER BY vector_rank LIMIT %s
        ), lexical AS (
            SELECT build_id, start_seconds, end_seconds,
                ts_rank_cd(to_tsvector('english', text), plainto_tsquery('english', %s)) AS lexical_rank,
                row_number() OVER (ORDER BY (strpos(lower(text), lower(%s::text)) > 0) DESC,
                                   ts_rank_cd(to_tsvector('english', text), plainto_tsquery('english', %s)) DESC,
                                   recording_id, start_seconds) AS lexical_position
            FROM scoped WHERE to_tsvector('english', text) @@ plainto_tsquery('english', %s)
            ORDER BY lexical_position LIMIT %s
        ), ranked AS (
            SELECT coalesce(d.build_id, l.build_id) AS build_id,
                coalesce(d.start_seconds, l.start_seconds) AS start_seconds,
                coalesce(d.end_seconds, l.end_seconds) AS end_seconds,
                d.vector_rank, l.lexical_rank, l.lexical_position,
                coalesce(1.0 / (60 + d.vector_rank), 0) + coalesce(1.0 / (60 + l.lexical_position), 0) AS rrf_score
            FROM dense d FULL JOIN lexical l USING (build_id, start_seconds, end_seconds)
        ) SELECT s.build_id, s.recording_id, s.source_path, s.size, s.mtime_ns,
            s.start_seconds, s.end_seconds, s.text,
            1 - (s.embedding <=> %s::vector) AS vector_similarity,
            r.vector_rank, coalesce(r.lexical_rank, 0) AS lexical_rank, r.lexical_position, r.rrf_score
          FROM ranked r JOIN scoped s USING (build_id, start_seconds, end_seconds)
          ORDER BY r.rrf_score DESC, vector_similarity DESC, s.recording_id, s.start_seconds, s.build_id LIMIT %s""",
                               (*params, vector, budget, query, phrase, query, query, budget, vector, limit)).fetchall()
        coverage = conn.execute("""SELECT count(DISTINCT r.id) AS total_recordings,
            count(DISTINCT r.id) FILTER (WHERE EXISTS (SELECT 1 FROM transcript_builds t
                WHERE t.recording_id = r.id AND t.state = 'ready')) AS ready_recordings,
            count(DISTINCT r.id) FILTER (WHERE r.capture_date IS NULL) AS recordings_without_capture_date,
            count(s.build_id) AS total_segments
            FROM recordings r LEFT JOIN transcript_builds b ON b.recording_id = r.id AND b.state = 'ready'
            LEFT JOIN transcript_segments s ON s.build_id = b.id
            WHERE """ + scope, (recording_ids, recording_ids)).fetchone()
        return {"results": results, "coverage": coverage}
