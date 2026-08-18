# Deployment Guide

This app is split across four platforms, deliberately (see `README.md` for the
full architecture diagram and the reasoning behind each choice):

| Platform | What lives there | Why not somewhere else |
|---|---|---|
| **Vercel** | `frontend/` (Next.js, App Router) | Standard Next.js host. |
| **Render** | `backend/` (FastAPI + DuckDB) | DuckDB needs a real persistent process with local disk during ingestion — Vercel serverless functions don't keep disk between requests. |
| **Supabase** | Postgres (`datasets`, `user_settings`, `presentations` tables) + Auth | Only hosts Postgres/Auth/Storage/Edge Functions — can't run the Python/DuckDB backend itself. |
| **Cloudflare R2** | Raw CSVs (`raw/<id>.csv`) + exported Parquet (`processed/<id>.parquet`) | S3-compatible object storage DuckDB's `httpfs` extension reads/writes directly. |

Deploy in this order — each later step needs credentials from an earlier one.

---

## 0. Prerequisites

- [ ] Supabase account + a new project created
- [ ] Cloudflare account with R2 enabled
- [ ] Render account, connected to this repo
- [ ] Vercel account, connected to this repo
- [ ] An Anthropic API key (or DeepSeek, if using that provider instead — see
      `LLM_PROVIDER` below)

---

## 1. Supabase (database + auth)

1. Create a new Supabase project.
2. Apply every migration in `supabase/migrations/` **in order**, via the SQL Editor
   or `supabase db push` (one-time, to get the project to current — the GitHub
   integration below takes over from here for every future migration):
   - `0001_create_datasets.sql` — `datasets` table (owner, filename, schema jsonb,
     row count, R2 storage keys) + RLS policies.
   - `0002_create_user_settings.sql` — `user_settings` table (theme mode/color) +
     RLS policies.
   - `0003_add_health_score_to_datasets.sql` — adds `health_score` to `datasets`.
   - `0004_create_presentations.sql` — `presentations` table (drag-and-drop report
     builder documents) + RLS policies.
   - `0005_add_content_hash_to_datasets.sql` — adds `content_hash` (MD5) to `datasets`,
     for upload dedup.
   - `0006_add_report_strategy_to_datasets.sql` — adds cached `report_strategy` jsonb
     to `datasets`.
   - `0007_create_chart_insights_cache.sql` — `chart_insights_cache` table (permanent
     per-chart-view insights cache) + RLS policies.
   - `0008_create_chart_shares.sql` — `chart_shares` table (opt-in, revocable public
     chart-share links) + RLS policies.
   - `0009_add_branding_presets_to_user_settings.sql` — adds `header_presets`/
     `footer_presets` jsonb arrays to `user_settings` (up to 5 each).
   - `0010_add_branding_snapshot_to_chart_shares.sql` — adds `header_snapshot`/
     `footer_snapshot` jsonb to `chart_shares`.
   - `0011_add_name_and_description_to_datasets.sql` — adds user-editable `name`
     (backfilled from `filename`, then made `not null`), `description` (≤200 chars,
     check constraint), and `notes` (uncapped) to `datasets`.
   - `0012_add_dataset_snapshot_to_chart_shares.sql` — adds `dataset_name`/
     `dataset_description` text columns to `chart_shares`, snapshotted from the
     owning dataset at share-creation time.
   - `0013_add_rationale_to_chart_shares.sql` — adds `rationale` (the chart's
     subtitle, not-null default `''`) to `chart_shares`.
3. **Auth settings** (Authentication > Providers > Email): disable "Confirm email"
   unless you've configured SMTP — otherwise sign-up will silently require a
   confirmation email that never arrives.
4. Collect from **Project Settings > API**:

   | Value | Placeholder used below |
   |---|---|
   | Project URL | `<SUPABASE_URL>` |
   | `anon` `public` key | `<SUPABASE_ANON_KEY>` |
   | `service_role` key (⚠️ secret — backend only, never ship to the frontend) | `<SUPABASE_SERVICE_ROLE_KEY>` |

### 1a. Auto-deploying migrations on push (recommended, do this once)

Rather than re-running step 2 by hand for every future migration, connect this repo
to Supabase so anything added to `supabase/migrations/` deploys automatically when
pushed to `main`. Available on every plan, including free — no CLI linking or
`supabase/config.toml` required for this repo, since `supabase/migrations/` already
exists at the repo root in the shape the integration expects.

1. In the Supabase dashboard: **Project Settings > Integrations > GitHub Integration
   > Authorize GitHub**, and complete the GitHub OAuth prompt.
2. Select this repo (`data-ki-saas/csv-data-analysis-tool`).
3. Set **Working directory** to `.` — the path from the repo root to the directory
   *containing* `supabase/` (root, in this repo's layout).
4. Set the **production branch** to `main`.
5. Enable **Deploy to production**, then **Enable integration**. From this point on,
   every push/merge to `main` that touches `supabase/migrations/` auto-applies the
   new migration(s) — only files under `migrations/` are run; `config.toml`/seed
   files are ignored unless present.
6. Optional but recommended once you're merging via pull requests instead of pushing
   directly to `main`: in **GitHub > repo Settings > Branches > branch protection
   rule for `main`**, enable **Require status checks to pass before merging** and
   require the **Supabase Preview** check — this blocks a PR with a bad migration
   from merging instead of failing silently after the fact.

**Verify it worked**: push a trivial no-op migration (or just watch the next real
one) and check **Database > Migrations** in the Supabase dashboard, or the
integration's run log under **Project Settings > Integrations**, for a successful
deploy tied to your commit SHA.

---

## 2. Cloudflare R2 (file storage)

1. Enable R2 on your Cloudflare account and create a bucket, e.g. `<R2_BUCKET_NAME>`.
2. **R2 > Manage API Tokens > Create API Token** — grant this token
   **read + write** access scoped to that bucket only.
3. Collect:

   | Value | Placeholder used below |
   |---|---|
   | Account ID (right sidebar of the R2 dashboard) | `<R2_ACCOUNT_ID>` |
   | Access Key ID | `<R2_ACCESS_KEY_ID>` |
   | Secret Access Key (shown once — save it immediately) | `<R2_SECRET_ACCESS_KEY>` |
   | Bucket name | `<R2_BUCKET_NAME>` |

   The backend computes the endpoint itself as
   `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com` — you don't set an endpoint URL
   directly (that only exists as `R2_ENDPOINT_OVERRIDE`, and is for tests only —
   **leave it unset in every real deployment**).

---

## 3. Backend (Render)

1. **New > Blueprint**, connect this repo — Render auto-detects `render.yaml`
   (root dir `backend/`, build `pip install uv && uv sync --frozen --no-dev`, start
   `uv run uvicorn src.main:app --host 0.0.0.0 --port $PORT`).
2. In the service's **Environment** tab, fill in every variable below (the ones
   marked `sync: false` in `render.yaml` are blank by default — Render never commits
   secrets to the blueprint file):

   | Variable | Required | Placeholder / default |
   |---|---|---|
   | `SUPABASE_URL` | ✅ | `<SUPABASE_URL>` |
   | `SUPABASE_SERVICE_ROLE_KEY` | ✅ | `<SUPABASE_SERVICE_ROLE_KEY>` |
   | `R2_ACCOUNT_ID` | ✅ | `<R2_ACCOUNT_ID>` |
   | `R2_ACCESS_KEY_ID` | ✅ | `<R2_ACCESS_KEY_ID>` |
   | `R2_SECRET_ACCESS_KEY` | ✅ | `<R2_SECRET_ACCESS_KEY>` |
   | `R2_BUCKET_NAME` | ✅ | `<R2_BUCKET_NAME>` |
   | `CORS_ORIGINS` | ✅ | `<YOUR_VERCEL_URL>` (exact scheme + no trailing slash, e.g. `https://your-app.vercel.app`; comma-separate multiple origins) |
   | `LLM_PROVIDER` | optional | `anthropic` (or `deepseek`) |
   | `ANTHROPIC_API_KEY` | required if `LLM_PROVIDER=anthropic` | `<ANTHROPIC_API_KEY>` |
   | `ANTHROPIC_MODEL` | optional | `claude-sonnet-5` |
   | `DEEPSEEK_API_KEY` | required if `LLM_PROVIDER=deepseek` | `<DEEPSEEK_API_KEY>` |
   | `DEEPSEEK_MODEL` | optional | `deepseek-chat` |
   | `MAX_UPLOAD_SIZE_MB` | optional | `2048` |
   | `QUERY_MAX_ROWS` | optional | `10000` |
   | `QUERY_TIMEOUT_SECONDS` | optional | `30` |

   Do **not** set `R2_ENDPOINT_OVERRIDE` here — it exists only so tests can point
   DuckDB/boto3 at a local mock server; setting it in production points the app at
   the wrong (or no) S3 endpoint.

3. Deploy, then verify:
   ```
   curl https://<your-render-service>.onrender.com/health
   # -> {"status": "ok"}
   ```
4. Check the deploy logs for the startup line
   `CORS allow_origins=[...]` (logged once at app startup — see `src/main.py`) and
   confirm it shows exactly the Vercel URL you set in `CORS_ORIGINS`, not `[]` or
   `['http://localhost:3000']` (the default).
5. Render's free tier spins the service down when idle — the first request after
   idle can take 30–60s to respond. This is expected, not a bug.

---

## 4. Frontend (Vercel)

1. **Import project**, set **Root Directory** to `frontend`.
2. Framework preset: Next.js (auto-detected). Build command `yarn build`, install
   command `yarn install` (both auto-detected from `frontend/package.json`).
3. Set these **Project Settings > Environment Variables** (all `NEXT_PUBLIC_*`,
   since they're read in the browser — baked in at **build time**, see the pitfall
   below):

   | Variable | Placeholder |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `<SUPABASE_URL>` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `<SUPABASE_ANON_KEY>` |
   | `NEXT_PUBLIC_API_BASE_URL` | `<YOUR_RENDER_URL>` (e.g. `https://your-backend.onrender.com`, **no** trailing slash) |

4. Deploy, then verify:
   - Load the site root (`/`) — should render the public marketing page.
   - Sign up / log in, land on `/dashboard`.
   - Open the browser console — you should see `[api] backend base URL: <your Render
     URL>` logged once (see `src/lib/api.ts`). If it shows `http://localhost:8000`
     instead, `NEXT_PUBLIC_API_BASE_URL` wasn't set (or wasn't set *before* the last
     build — see below).
   - Upload a small CSV and confirm the schema/preview comes back.

---

## 5. Post-deploy smoke test (both platforms live)

- [ ] `GET /health` on the Render URL returns `{"status": "ok"}`
- [ ] Frontend loads and sign-up/login works
- [ ] CSV upload succeeds end-to-end (frontend -> Render -> R2 + Supabase)
- [ ] "Ask AI to review flagged columns" returns a result (confirms the LLM key works)
- [ ] "Generate visual report" on a dataset returns charts (confirms R2 read-back +
      LLM both work)

---

## Common pitfalls

These have each bitten this project before — check them first before digging deeper.

1. **"Env var set but not applied."** Both Vercel (`NEXT_PUBLIC_*` vars are baked
   into the JS bundle at build time) and Render (doesn't hot-reload env vars into a
   running instance) require a **fresh deploy after** changing an env var — saving
   the value in the dashboard alone does nothing until the next build/restart. If
   something is misbehaving right after you changed an env var, redeploy before
   assuming the code is broken.
2. **CORS mismatch causing "Failed to fetch" on upload.** `CORS_ORIGINS` on Render
   must exactly match the Vercel URL — scheme included, no trailing slash. Check the
   Render startup log line (`CORS allow_origins=[...]`, logged once — see
   `src/main.py`) to confirm what's actually configured, and the request-logging
   middleware's per-request log line (method/path/`Origin`/status) to confirm
   whether the request even reached the backend. A blocked CORS preflight still
   reaches the server and gets logged — the browser only hides the *response*.
3. **Browser console over the on-page error message.** `src/lib/api.ts`'s
   `apiFetch()` distinguishes a network/CORS-level failure from a real HTTP error
   response and logs the failing URL; `handleResponse()` logs the parsed error body.
   Check the console, not just the toast, when an upload fails.
4. **Email confirmation blocking sign-up.** If Supabase's "Confirm email" is on but
   no SMTP provider is configured, sign-up will look broken (no error, just no
   confirmation email ever arrives). Turn it off unless you've set up SMTP.
5. **Cold starts on Render's free tier.** A request after idle time can take
   30–60s. Don't mistake this for the service being down.
6. **`R2_ENDPOINT_OVERRIDE` set in a real environment.** This should only ever be
   set by the test suite (pointing at a local moto server). If it's set in Render's
   dashboard, R2 access will silently point at the wrong host.

---

## Environment variable reference (complete)

### Backend (Render), from `backend/src/core/config.py`

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` \| `deepseek` |
| `ANTHROPIC_API_KEY` | `""` | — |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | — |
| `DEEPSEEK_API_KEY` | `""` | — |
| `DEEPSEEK_MODEL` | `deepseek-chat` | — |
| `MAX_UPLOAD_SIZE_MB` | `2048` | — |
| `QUERY_MAX_ROWS` | `10000` | — |
| `QUERY_TIMEOUT_SECONDS` | `30` | — |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated |
| `SUPABASE_URL` | `""` | — |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | secret |
| `R2_ACCOUNT_ID` | `""` | — |
| `R2_ACCESS_KEY_ID` | `""` | — |
| `R2_SECRET_ACCESS_KEY` | `""` | secret |
| `R2_BUCKET_NAME` | `""` | — |
| `R2_ENDPOINT_OVERRIDE` | `""` | **tests only, do not set in deployment** |

### Frontend (Vercel), from `frontend/.env.local.example`

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | same value as backend's `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **not** the service role key |
| `NEXT_PUBLIC_API_BASE_URL` | the Render service URL, no trailing slash |

---

## Local development (for reference — see `README.md` for the authoritative version)

**Backend** (from `backend/`):
```
uv sync
cp .env.example .env   # fill in Supabase + R2 credentials
uv run uvicorn src.main:app --reload
uv run pytest -v
```

**Frontend** (from `frontend/`):
```
yarn install
cp .env.local.example .env.local   # fill in Supabase URL/anon key
yarn dev
```
