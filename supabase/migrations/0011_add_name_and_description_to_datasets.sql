-- A user-editable display name (defaults to the uploaded filename at ingest),
-- an optional short description (<=200 chars, shown on the dataset card), and
-- an optional longer free-form `notes` field for detailed analysis writeups
-- (no length cap -- unlike `description`, this isn't meant to fit neatly in a
-- card). All three are editable after upload via PATCH /api/datasets/{id}
-- (src/datasets/service.py::update_dataset_metadata).
alter table public.datasets
    add column if not exists name text,
    add column if not exists description text,
    add column if not exists notes text;

-- Backfill existing rows so `name` is never null once the column below is
-- made required -- datasets created before this migration only have a
-- filename to fall back to.
update public.datasets set name = filename where name is null;

alter table public.datasets alter column name set not null;

alter table public.datasets
    add constraint datasets_description_length check (char_length(description) <= 200);
