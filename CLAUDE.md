# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A CSV data-analysis web tool: upload a CSV (thousands to millions of rows), get an
instant schema/row-count/preview, then run SQL against it. See [README.md](README.md)
for the full architecture diagram and deployment steps. In short:

- `frontend/` — Next.js (App Router) + Tailwind, deployed on Vercel.
- `backend/` — FastAPI + DuckDB, deployed on Render (not Vercel — DuckDB needs a real
  persistent process, which serverless functions don't provide between requests).
- **Database & Auth**: Supabase (Postgres `datasets` table + Supabase Auth JWTs).
- **File storage**: Cloudflare R2 (S3-compatible) — raw CSVs and DuckDB-exported
  Parquet files. Queries read Parquet directly off R2; the backend keeps **no**
  per-dataset state in memory or on local disk between requests. Don't reintroduce an
  in-memory dataset registry or a local `.duckdb` file meant to persist across
  requests — that assumption breaks the moment Render's free tier spins the service
  down.

## Commands

**Backend** (run from `backend/`):
```
uv sync                                    # install deps
uv run uvicorn src.main:app --reload       # run dev server (localhost:8000)
uv run pytest -v                           # run all tests
uv run pytest tests/test_upload.py -v      # run one test file
uv run pytest -k test_upload_csv_creates_dataset  # run one test
```

**Frontend** (run from `frontend/`):
```
yarn install
yarn dev      # localhost:3000
yarn lint
yarn build
```

There is no top-level build/test command — the two halves are run independently.

## Backend architecture

- `src/main.py` — FastAPI app factory, CORS, router registration.
- `src/core/config.py` — `pydantic-settings` `Settings`, loaded from `.env`. Includes
  `r2_endpoint_override`, which exists solely so tests can point DuckDB's and boto3's
  S3 clients at a local mock server instead of real R2 — don't remove it.
- `src/core/auth.py` — `get_current_user` FastAPI dependency: verifies the bearer
  token against Supabase Auth (`supabase.auth.get_user(token)`) and returns a
  `CurrentUser`. Every dataset/query route depends on this.
- `src/datasets/duckdb_manager.py` — the DuckDB wrapper. `ingest_and_export()` streams
  a local CSV into DuckDB, `COPY`s it to Parquet on R2, and returns schema/row
  count/preview. `execute_query()` opens a fresh connection, creates a view over
  `read_parquet('s3://...')`, and runs the (validated) SQL. `_assert_readonly_select()`
  guards every query to a single `SELECT`/`WITH` statement via `sqlglot` — this matters
  because query SQL may eventually be LLM-generated (Claude), so don't relax it without
  adding an equivalent guard elsewhere. A fresh DuckDB connection is used per
  operation because connections aren't safe to share across concurrent requests.
- `src/datasets/repository.py` — Supabase-backed CRUD for the `datasets` table using
  the *service role* key (bypasses RLS), so every function takes and filters by
  `owner_id` explicitly — RLS is not doing the ownership enforcement here, the Python
  code is.
- `src/storage/r2_client.py` — boto3 client for the raw CSV upload/delete only. Parquet
  read/write goes through DuckDB's own `httpfs` extension instead (configured in
  `duckdb_manager.py`), not through this module.
- `src/datasets/service.py` / `src/query/service.py` (routers) — orchestrate the above;
  routers stay thin, business logic lives in `service.py`.

Dataset IDs are Supabase-generated UUIDs (the `datasets.id` column), not generated
by DuckDB or the filesystem — `dataset_id` in API responses **is** the Supabase row ID.

## Testing approach

Tests don't hit real Supabase or real R2:
- `tests/conftest.py`'s `fake_datasets_table` fixture monkeypatches
  `src.datasets.repository` module functions with an in-memory dict, keyed the same
  way the real Postgres table is.
- The `moto_r2_server` / `r2_settings` fixtures spin up a `ThreadedMotoServer` (a real
  local HTTP server implementing the S3 API) and point both DuckDB's `httpfs` and
  boto3 at it via `r2_endpoint_override`. This is necessary because `moto`'s usual
  `@mock_aws` decorator only intercepts boto3 calls — DuckDB's S3 client talks HTTP
  directly and needs an actual server to hit.
- `get_current_user` is overridden via FastAPI's `app.dependency_overrides` in the
  `client` fixture, not mocked at the Supabase client level.

When adding a new dataset/query route, follow the existing pattern: depend on
`get_current_user`, look up the record via `repository.get_dataset(id, user.id)`
(returns `None` on not-found *or* wrong owner — both should 404, not 403, to avoid
leaking existence of other users' datasets).

## Frontend architecture

- `src/lib/supabase/{client,server,middleware}.ts` — the standard `@supabase/ssr`
  three-client split (browser / server component / middleware session refresh).
  `src/proxy.ts` (Next.js 16 renamed `middleware.ts` → `proxy.ts`) calls
  `updateSession()` and redirects unauthenticated requests to `/login`.
- `src/lib/api.ts` — the only place that calls the FastAPI backend. Every function
  attaches the current Supabase session's access token as `Authorization: Bearer
  <token>`, read fresh per call via `supabase.auth.getSession()` — don't cache the
  token elsewhere, it can rotate.
- `src/hooks/` — thin TanStack Query wrappers (`useUploadDataset`, `useDatasets`)
  around `src/lib/api.ts`. Data-fetching in this project goes through React Query,
  not raw `useEffect`/`fetch`.
- Tailwind v4 (CSS-first config in `globals.css`, no `tailwind.config.js`) — this
  differs from the older Tailwind v3 + `tailwind.config.js` setup used in some of this
  user's other repos; don't add a v3-style config file here.

The frontend currently covers upload + list + preview only. SQL query UI and
charts (Recharts/Plotly are already installed) are the natural next slice — see the
backend's `/api/datasets/{id}/query` endpoint, which is already wired and tested.
