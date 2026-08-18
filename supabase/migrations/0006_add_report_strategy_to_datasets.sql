-- Cached chart-recommendation report (the LLM's suggestions plus each
-- recommendation's already-executed SQL result -- see backend
-- src/datasets/schemas.py::ChartRecommendation for the shape). Null means
-- "never generated"; cleared back to null whenever `schema` is updated (see
-- repository.update_dataset_schema), since recommendations are derived from
-- column categories.
alter table public.datasets
    add column if not exists report_strategy jsonb;
