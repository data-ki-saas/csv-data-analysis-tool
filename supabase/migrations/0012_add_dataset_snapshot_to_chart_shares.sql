-- Snapshots the owning dataset's name/description at the moment a chart is
-- shared -- same reasoning as the chart's own `result` snapshot and the
-- header/footer branding snapshot (0010): the public viewer has no session
-- to look the dataset up with, and a later rename shouldn't retroactively
-- change a link already shared.
alter table public.chart_shares
    add column if not exists dataset_name text,
    add column if not exists dataset_description text;
