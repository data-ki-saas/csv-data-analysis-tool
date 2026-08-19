-- Per-column range-parsing config for a column whose cells hold a numeric
-- range (see profiling.detect_range_pattern), e.g. "experience_raw" holding
-- "4-10 yrs" -- how to split one cell into min/max numbers and which single
-- representative value (midpoint, by default) a chart should use per row.
-- Distinct from value_remaps/value_replacements/tag_configs: those either
-- transform a cell's displayed text or explode it into several counted tag
-- memberships; this parses it into ONE numeric measure per row.
-- Shape: { "<column name>": { "separator": "-", "unit": "yrs" | null,
-- "value_type": "midpoint" | "min" | "max" } }. Null means "not configured
-- on this dataset yet".
alter table public.datasets
    add column if not exists range_configs jsonb;
