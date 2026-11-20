CREATE TABLE description_builds (
    id uuid PRIMARY KEY,
    recording_id uuid NOT NULL REFERENCES recordings (id),
    config_key text NOT NULL,
    spec jsonb NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'ready', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (recording_id, config_key)
);

ALTER TABLE jobs ADD COLUMN description_build_id uuid REFERENCES description_builds (id);
ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs DROP CONSTRAINT jobs_kind_build;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('import', 'visual', 'description'));
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_build CHECK (
    (kind = 'visual') = (index_build_id IS NOT NULL)
    AND (kind = 'description') = (description_build_id IS NOT NULL)
);
CREATE UNIQUE INDEX jobs_description_build ON jobs (description_build_id) WHERE description_build_id IS NOT NULL;

CREATE TABLE description_windows (
    build_id uuid NOT NULL REFERENCES description_builds (id),
    start_seconds double precision NOT NULL,
    end_seconds double precision NOT NULL,
    samples jsonb NOT NULL,
    payload jsonb NOT NULL,
    searchable_text text NOT NULL CHECK (length(searchable_text) BETWEEN 1 AND 4000),
    embedding vector(384) NOT NULL,
    PRIMARY KEY (build_id, start_seconds, end_seconds)
);
CREATE INDEX description_text_search ON description_windows
    USING gin (to_tsvector('english', searchable_text));

CREATE TABLE verification_runs (
    id uuid PRIMARY KEY,
    recording_id uuid NOT NULL REFERENCES recordings (id),
    query text NOT NULL,
    start_seconds double precision NOT NULL,
    end_seconds double precision NOT NULL,
    spec jsonb NOT NULL,
    samples jsonb NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
