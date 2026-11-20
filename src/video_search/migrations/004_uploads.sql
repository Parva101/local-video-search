ALTER TABLE jobs ADD COLUMN auto_description_spec jsonb;
ALTER TABLE jobs ADD COLUMN original_filename text;
ALTER TABLE jobs ADD CONSTRAINT jobs_auto_description_import
    CHECK (auto_description_spec IS NULL OR (kind = 'import' AND jsonb_typeof(auto_description_spec) = 'object'));
