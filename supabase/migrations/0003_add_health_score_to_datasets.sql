-- Dataset-level data quality score (mean column completeness, 0-100),
-- computed once at ingestion time by the massaging/profiling pipeline
-- (see backend src/datasets/profiling.py) and served by the schema API.
alter table public.datasets
    add column if not exists health_score numeric not null default 100;
