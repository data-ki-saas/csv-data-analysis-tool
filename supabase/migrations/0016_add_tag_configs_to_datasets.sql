-- Per-column tag-extraction config for a "multi-value" categorical column
-- (see profiling.detect_multi_value_separator) -- how to split one packed
-- cell (e.g. "Hybrid - Pune, Noida, Bengaluru") into individual tags, and
-- the curated canonical vocabulary a tag-count chart should actually count
-- against. Distinct from value_remaps/value_replacements: those transform
-- one whole cell's displayed value, this explodes one cell into several
-- counted tag memberships.
-- Shape: { "<column name>": { "prefix_separator": "-" | null,
-- "tag_separator": ",", "vocabulary": ["Hyderabad", "Bengaluru", ...],
-- "include_other": false } }. Null means "not configured on this dataset yet".
alter table public.datasets
    add column if not exists tag_configs jsonb;
