CREATE TABLE IF NOT EXISTS dataset_imports (
    source_path TEXT PRIMARY KEY,
    table_name TEXT NOT NULL,
    year INTEGER,
    rows_inserted BIGINT NOT NULL DEFAULT 0,
    rows_skipped BIGINT NOT NULL DEFAULT 0,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dataset_tables (
    schema_hash TEXT PRIMARY KEY,
    table_name TEXT NOT NULL UNIQUE,
    columns_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
