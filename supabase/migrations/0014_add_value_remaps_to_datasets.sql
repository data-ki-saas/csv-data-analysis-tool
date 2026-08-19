-- Per-column category-value merge rules (e.g. merging "NY" and "New York
-- City" into "New York"), applied at query time everywhere this dataset's
-- Parquet is read -- the Parquet file itself is immutable after ingest (see
-- CLAUDE.md), so a merge can only ever be a mapping layered on top of it.
-- Shape: { "<column name>": [ { "target": "New York", "sources": ["NY", "New
-- York City"] }, ... ], ... }. Null means "no merges on this dataset yet".
alter table public.datasets
    add column if not exists value_remaps jsonb;
