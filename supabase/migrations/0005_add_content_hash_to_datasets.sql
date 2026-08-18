-- MD5 of the uploaded CSV's raw bytes (computed while streaming to disk, no
-- extra I/O pass -- see backend src/datasets/service.py::_stream_upload_to_disk),
-- used to dedup repeat uploads of byte-identical content by the same owner
-- (see repository.get_dataset_by_content_hash). Nullable: rows created before
-- this migration have no hash and simply never participate in dedup lookups.
alter table public.datasets
    add column if not exists content_hash text;

create index if not exists datasets_owner_content_hash_idx
    on public.datasets (owner_id, content_hash)
    where content_hash is not null;
