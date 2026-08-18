-- A dataset owner's opt-in, revocable public link for one specific chart snapshot
-- (title/chart_type/partition_type/column/result at the moment "Share" was clicked --
-- see backend src/shares/schemas.py for the shape). `token` is the unguessable part
-- of the public URL (backend/src/shares/service.py generates it via
-- secrets.token_urlsafe) -- anyone with it can read this one row with no auth;
-- revoking is deleting the row. Not updatable: a share is a frozen snapshot.

create table if not exists public.chart_shares (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references public.datasets (id) on delete cascade,
    owner_id uuid not null references auth.users (id) on delete cascade,
    token text not null unique,
    title text not null,
    chart_type text not null,
    partition_type text not null,
    column_name text not null,
    result jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists chart_shares_owner_id_idx on public.chart_shares (owner_id);
create index if not exists chart_shares_token_idx on public.chart_shares (token);

alter table public.chart_shares enable row level security;

-- The backend talks to Supabase with the service role key, which bypasses RLS. The
-- PUBLIC /api/shares/{token} read is also served through the service-role client
-- (see src/shares/repository.py::get_share_by_token, no owner_id filter) -- these
-- policies are defense-in-depth for direct frontend/Supabase access, not what makes
-- the public route work.
create policy "Users can view their own chart shares"
    on public.chart_shares for select
    using (auth.uid() = owner_id);

create policy "Users can insert their own chart shares"
    on public.chart_shares for insert
    with check (auth.uid() = owner_id);

create policy "Users can delete their own chart shares"
    on public.chart_shares for delete
    using (auth.uid() = owner_id);
