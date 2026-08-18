-- Permanent cache of "Generate insights" results, keyed per dataset by a hash
-- of the exact chart view (column, chart_type, partition_type, and the
-- aggregated result's columns+rows -- see backend
-- src/datasets/service.py::_insights_cache_key). Unlike datasets.report_strategy,
-- entries here are never invalidated: the Parquet data behind any one exact
-- aggregation never changes, so a cache hit is valid forever.

create table if not exists public.chart_insights_cache (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references public.datasets (id) on delete cascade,
    owner_id uuid not null references auth.users (id) on delete cascade,
    cache_key text not null,
    insights jsonb not null,
    created_at timestamptz not null default now(),
    unique (dataset_id, cache_key)
);

create index if not exists chart_insights_cache_owner_id_idx on public.chart_insights_cache (owner_id);

alter table public.chart_insights_cache enable row level security;

-- The backend talks to Supabase with the service role key, which bypasses RLS
-- and enforces ownership itself (see src/datasets/insights_cache_repository.py).
-- These policies matter only if the frontend ever queries Supabase directly.
-- Only select/insert exist: app code never updates or deletes a cache row
-- directly (deletion only happens via the dataset's ON DELETE CASCADE).
create policy "Users can view their own chart insights cache"
    on public.chart_insights_cache for select
    using (auth.uid() = owner_id);

create policy "Users can insert their own chart insights cache"
    on public.chart_insights_cache for insert
    with check (auth.uid() = owner_id);
