# CSV Data Analysis Tool

A web tool for exploring CSV datasets from thousands to millions of rows: upload a
CSV, get an instant schema/row-count/preview, then run SQL against it (with Claude
generating SQL/profiling in a later pass).

## Architecture

- **Frontend** — Next.js (App Router) + Tailwind, deployed on **Vercel**.
- **Backend** — FastAPI + DuckDB, deployed on **Render** (needs a real persistent
  process — Vercel's serverless functions have no local disk between requests, which
  DuckDB needs during ingestion).
- **Database & Auth** — **Supabase**: Postgres holds a `datasets` table (owner,
  filename, schema, row count, storage keys); Supabase Auth issues the JWT the
  frontend sends as `Authorization: Bearer <token>` on every backend call.
- **File storage** — **Cloudflare R2**: every upload lands as `raw/<id>.csv` (original
  bytes) and `processed/<id>.parquet` (DuckDB-readable). Queries read the Parquet file
  directly off R2 via DuckDB's `httpfs`/S3 support (`read_parquet('s3://...')`) — the
  backend keeps no per-dataset state locally, so it can restart or spin down (Render's
  free tier does this when idle) without losing anything.

```
Upload:  browser --CSV--> FastAPI --stream to /tmp--> DuckDB ingest --> Parquet --> R2
                                                          |
                                                          v
                                              Supabase `datasets` row (metadata)

Query:   browser --SQL--> FastAPI --owner check via Supabase--> DuckDB reads
                                                                  Parquet from R2
```

## Local development

**Backend** (`backend/`):
```
uv sync
cp .env.example .env   # fill in Supabase + R2 credentials
uv run uvicorn src.main:app --reload
uv run pytest -v
```

**Frontend** (`frontend/`):
```
yarn install
cp .env.local.example .env.local   # fill in Supabase URL/anon key
yarn dev
```

## Deploying

1. **Supabase**: create a project, run `supabase/migrations/0001_create_datasets.sql`
   (SQL Editor or `supabase db push`), copy the Project URL + service role key
   (Settings > API) into the backend env, and the URL + anon key into the frontend env.
2. **Cloudflare R2**: create a bucket, create an API token (R2 > Manage API Tokens)
   with read/write access, copy the Account ID + Access Key ID + Secret Access Key +
   bucket name into the backend env.
3. **Render**: connect this repo, it should pick up `render.yaml` (root directory
   `backend/`) automatically — fill in the secret env vars in the dashboard (they're
   marked `sync: false` in the blueprint so they're not committed).
4. **Vercel**: import this repo, set the project's Root Directory to `frontend`, set
   `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and
   `NEXT_PUBLIC_API_BASE_URL` (your Render service URL) in the project's env vars.
