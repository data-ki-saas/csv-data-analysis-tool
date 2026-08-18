-- One presentation per (dataset, owner): a multi-page deck the user builds
-- by pinning charts + AI insights from the dataset's report-strategy feed.
-- Pages/blocks are stored as a single jsonb document (see
-- backend src/presentations/schemas.py for the shape) since they're always
-- read/written as a whole document by the drag-and-drop builder, never
-- queried piecemeal.

create table if not exists public.presentations (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references public.datasets (id) on delete cascade,
    owner_id uuid not null references auth.users (id) on delete cascade,
    title text not null default 'Untitled Presentation',
    pages jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (dataset_id, owner_id)
);

create index if not exists presentations_owner_id_idx on public.presentations (owner_id);

alter table public.presentations enable row level security;

-- The backend talks to Supabase with the service role key, which bypasses RLS
-- and enforces ownership itself (see src/presentations/repository.py). These
-- policies matter only if the frontend ever queries Supabase directly.
create policy "Users can view their own presentations"
    on public.presentations for select
    using (auth.uid() = owner_id);

create policy "Users can insert their own presentations"
    on public.presentations for insert
    with check (auth.uid() = owner_id);

create policy "Users can update their own presentations"
    on public.presentations for update
    using (auth.uid() = owner_id);

create policy "Users can delete their own presentations"
    on public.presentations for delete
    using (auth.uid() = owner_id);
