-- Up to 5 header/footer presets each, one "active" per type (see backend
-- src/settings/schemas.py::HeaderPreset/FooterPreset for the shape and
-- src/settings/service.py for the max-5 / at-most-one-enabled enforcement,
-- both done in Python rather than DB constraints/triggers -- same reasoning
-- as ownership enforcement in this table: the backend is the only writer.
-- footer_presets[].html is sanitized server-side before storage (see
-- service.py) since it's rendered to other people (shared links, exported
-- PDFs), not just the owner.
alter table public.user_settings
    add column if not exists header_presets jsonb not null default '[]'::jsonb,
    add column if not exists footer_presets jsonb not null default '[]'::jsonb;
