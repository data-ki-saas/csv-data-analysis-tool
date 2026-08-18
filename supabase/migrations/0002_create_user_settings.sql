-- Per-user UI preferences (theme mode + colour theme). One row per user;
-- absence of a row means the frontend falls back to its built-in defaults.

create table if not exists public.user_settings (
    owner_id uuid primary key references auth.users (id) on delete cascade,
    theme_mode text not null default 'system'
        check (theme_mode in ('light', 'dark', 'system')),
    color_theme text not null default 'winter'
        check (color_theme in ('winter', 'pastel', 'photochromatic', 'warm', 'spring', 'contrast')),
    updated_at timestamptz not null default now()
);

alter table public.user_settings enable row level security;

-- The backend talks to Supabase with the service role key, which bypasses RLS
-- and enforces ownership itself (see src/settings/repository.py). These
-- policies matter only if the frontend ever queries Supabase directly.
create policy "Users can view their own settings"
    on public.user_settings for select
    using (auth.uid() = owner_id);

create policy "Users can upsert their own settings"
    on public.user_settings for insert
    with check (auth.uid() = owner_id);

create policy "Users can update their own settings"
    on public.user_settings for update
    using (auth.uid() = owner_id);
