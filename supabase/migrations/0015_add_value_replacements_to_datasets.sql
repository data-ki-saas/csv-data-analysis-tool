-- Per-column literal substring-replacement rules (e.g. replacing every
-- occurrence of "Delhi / NCR" with "Delhi" within a column's values) --
-- distinct from value_remaps' whole-value merges: a replacement can change
-- part of a value, not just map one whole value to another. Applied at
-- query time, chained before value_remaps' CASE mapping (see
-- duckdb_manager._column_transform_replace_clause) -- same immutable-
-- Parquet reasoning as value_remaps (see 0014_add_value_remaps_to_datasets.sql).
-- Shape: { "<column name>": [ { "find": "Delhi / NCR", "replace": "Delhi" },
-- ... ], ... }. Null means "no replacements on this dataset yet".
alter table public.datasets
    add column if not exists value_replacements jsonb;
