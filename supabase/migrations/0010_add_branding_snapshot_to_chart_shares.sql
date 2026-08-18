-- Snapshots the owner's active header/footer preset (if any) at the moment a
-- share link is created -- same reasoning as chart_shares.result: the public
-- viewer has no session and can't fetch the owner's live settings, and a
-- later branding change shouldn't retroactively change links already shared.
alter table public.chart_shares
    add column if not exists header_snapshot jsonb,
    add column if not exists footer_snapshot jsonb;
