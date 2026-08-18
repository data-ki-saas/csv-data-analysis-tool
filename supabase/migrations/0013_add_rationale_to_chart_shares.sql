-- The chart's subtitle (ChartRecommendation.rationale) was never captured on
-- share -- the public share page only ever had the chart's title, not its
-- subtitle, to display. Snapshotted at share-creation time for the same
-- reason as every other field on this table: frozen once shared.
alter table public.chart_shares
    add column if not exists rationale text not null default '';
