CREATE TABLE visual_builds (
    id uuid PRIMARY KEY,
    recording_id uuid NOT NULL REFERENCES recordings (id),
    config_key text NOT NULL,
    spec jsonb NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'ready', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (recording_id, config_key)
);

ALTER TABLE jobs ADD COLUMN kind text NOT NULL DEFAULT 'import' CHECK (kind IN ('import', 'visual'));
ALTER TABLE jobs ADD COLUMN index_build_id uuid REFERENCES visual_builds (id);
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_build CHECK ((kind = 'visual') = (index_build_id IS NOT NULL));
CREATE UNIQUE INDEX jobs_visual_build ON jobs (index_build_id) WHERE index_build_id IS NOT NULL;

CREATE TABLE visual_windows (
    build_id uuid NOT NULL REFERENCES visual_builds (id),
    start_seconds double precision NOT NULL,
    end_seconds double precision NOT NULL,
    samples jsonb NOT NULL,
    embedding vector(768) NOT NULL,
    PRIMARY KEY (build_id, start_seconds, end_seconds)
);
