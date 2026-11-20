CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS library (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    identity text NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY,
    dedupe_key text UNIQUE NOT NULL,
    source_path text NOT NULL,
    expected_size bigint NOT NULL CHECK (expected_size >= 0),
    expected_mtime_ns bigint NOT NULL CHECK (expected_mtime_ns >= 0),
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'succeeded', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    lease_token uuid,
    lease_until timestamptz,
    error jsonb,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'running') = (lease_token IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS jobs_pending ON jobs (created_at) WHERE state IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS assets (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    metadata jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recordings (
    id uuid PRIMARY KEY,
    source_path text NOT NULL,
    sha256 text NOT NULL REFERENCES assets (sha256),
    size bigint NOT NULL CHECK (size >= 0),
    mtime_ns bigint NOT NULL CHECK (mtime_ns >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_path, sha256)
);

CREATE TABLE IF NOT EXISTS windows (
    recording_id uuid NOT NULL REFERENCES recordings (id),
    start_seconds double precision NOT NULL CHECK (start_seconds >= 0 AND start_seconds < 'Infinity'::float8),
    end_seconds double precision NOT NULL CHECK (end_seconds > start_seconds AND end_seconds < 'Infinity'::float8),
    PRIMARY KEY (recording_id, start_seconds, end_seconds)
);
