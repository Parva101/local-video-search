CREATE TABLE IF NOT EXISTS transcript_builds (
    id uuid PRIMARY KEY,
    recording_id uuid NOT NULL REFERENCES recordings (id),
    config_key text NOT NULL,
    spec jsonb NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'ready', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (recording_id, config_key)
);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS transcript_build_id uuid REFERENCES transcript_builds (id);
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_kind_check;
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_kind_build;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('import', 'visual', 'description', 'transcript'));
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_build CHECK (
    (kind = 'visual') = (index_build_id IS NOT NULL)
    AND (kind = 'description') = (description_build_id IS NOT NULL)
    AND (kind = 'transcript') = (transcript_build_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_transcript_build ON jobs (transcript_build_id) WHERE transcript_build_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS transcript_segments (
    build_id uuid NOT NULL REFERENCES transcript_builds (id),
    start_seconds double precision NOT NULL CHECK (start_seconds >= 0),
    end_seconds double precision NOT NULL CHECK (end_seconds > start_seconds),
    text text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
    embedding vector(384) NOT NULL,
    PRIMARY KEY (build_id, start_seconds, end_seconds)
);
CREATE INDEX IF NOT EXISTS transcript_text_search ON transcript_segments USING gin (to_tsvector('english', text));
