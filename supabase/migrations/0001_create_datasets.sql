-- Dataset metadata for uploaded CSVs. The actual data lives in Cloudflare R2
-- (raw_key = original CSV, parquet_key = DuckDB-readable export); this table
-- only tracks ownership and schema so the backend can list/authorize access.

create table if not exists public.datasets (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users (id) on delete cascade,
    filename text not null,
    row_count bigint not null,
    schema jsonb not null,
    raw_key text not null,
    parquet_key text not null,
    created_at timestamptz not null default now()
);

create index if not exists datasets_owner_id_idx on public.datasets (owner_id);

alter table public.datasets enable row level security;

-- The backend talks to Supabase with the service role key, which bypasses RLS
-- and enforces ownership itself (see src/datasets/repository.py). These
-- policies matter only if the frontend ever queries Supabase directly.
create policy "Users can view their own datasets"
    on public.datasets for select
    using (auth.uid() = owner_id);

create policy "Users can insert their own datasets"
    on public.datasets for insert
    with check (auth.uid() = owner_id);

create policy "Users can delete their own datasets"
    on public.datasets for delete
    using (auth.uid() = owner_id);
