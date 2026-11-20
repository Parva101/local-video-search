ALTER TABLE recordings ADD COLUMN IF NOT EXISTS capture_date date;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS capture_date_source text
    CHECK (capture_date_source IN ('user', 'file_mtime') OR capture_date_source IS NULL);
ALTER TABLE recordings DROP CONSTRAINT IF EXISTS capture_date_source_matches_date;
ALTER TABLE recordings ADD CONSTRAINT capture_date_source_matches_date
    CHECK ((capture_date IS NULL) = (capture_date_source IS NULL));
CREATE INDEX IF NOT EXISTS recordings_capture_date ON recordings (capture_date) WHERE capture_date IS NOT NULL;
