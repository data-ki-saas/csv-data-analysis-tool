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

- `src/main.py` — FastAPI app factory, CORS, router registration. There's no
  observability stack here — Render's log stream *is* the debugging tool — so
  `logging.basicConfig()` is configured once at import time, the resolved
  `CORS_ORIGINS` list is logged at startup (an empty/mismatched value there is the
  single most common cause of a browser-side "Failed to fetch" on upload — see
  `ingest_csv_upload()` below), and an `@app.middleware("http")` request logger records
  every request's method/path/`Origin` header/status/duration. That last one matters
  specifically for CORS: a blocked preflight still reaches the server (the browser only
  hides the *response* from the page), so this is the one place that can distinguish
  "request landed but the origin didn't match `CORS_ORIGINS`" from "request never
  arrived at all" (DNS, a sleeping Render free-tier instance, etc.) without needing the
  reporting user's browser console.
- `src/core/config.py` — `pydantic-settings` `Settings`, loaded from `.env`. Includes
  `r2_endpoint_override`, which exists solely so tests can point DuckDB's and boto3's
  S3 clients at a local mock server instead of real R2 — don't remove it.
- `src/core/auth.py` — `get_current_user` FastAPI dependency: verifies the bearer
  token against Supabase Auth (`supabase.auth.get_user(token)`) and returns a
  `CurrentUser`. Every dataset/query route depends on this.
- `src/datasets/duckdb_manager.py` — the DuckDB wrapper. `ingest_and_export()` streams a
  local CSV into DuckDB, **massages** it (see below), `COPY`s the massaged table to
  Parquet on R2, and returns schema/row count/preview/health score — the Parquet file
  is the massaged data, the original upload is untouched in R2's `raw_key`.
  `execute_query()` opens a fresh connection, creates a view over `read_parquet('s3://
  ...')`, and runs the (validated) SQL. `preview_dataset()` does the same but with a
  fixed `SELECT * LIMIT n` (no `_assert_readonly_select()` needed — it's never
  user-supplied SQL), used by the schema API to serve a fresh preview without storing
  one. `_assert_readonly_select()` guards every query to a single `SELECT`/`WITH`
  statement via `sqlglot` — this matters because query SQL may eventually be
  LLM-generated, so don't relax it without adding an equivalent guard elsewhere. A
  fresh DuckDB connection is used per operation because connections aren't safe to
  share across concurrent requests. Column names come from uploaded CSV headers — every
  place one gets interpolated into SQL text goes through `_quote_ident()` first, since
  a crafted header is otherwise a SQL injection vector into the ingest pipeline.
  - **Massaging** (still in `duckdb_manager.py`): `read_csv(..., nullstr=[...])` folds
    common null sentinels (`"NA"`, `"N/A"`, `"-"`, empty string, etc.) into real SQL
    `NULL` during the same pass that loads the file — see `_NULL_TOKENS`.
    `_normalize_dates()` samples each text column, and if most values parse under
    *some* candidate `strptime` format (checked per-value against the whole candidate
    list, not one format for the whole column — a real export can mix formats row by
    row), rewrites it as a native `DATE` column via `COALESCE(try_strptime(...), ...)`.
    `_normalize_numeric_strings()` does the same sampling/threshold dance for
    currency/percentage-formatted numbers (`"$1,037.50"`, `"0%"`) that DuckDB's own
    auto-detection doesn't recognize as numeric and would otherwise leave stuck in
    `free_text` with no histogram/bell-curve ever possible — it strips `$`/`,`/`%` and
    `TRY_CAST`s to `DOUBLE`. Both normalization passes return a column-name → warning
    message dict (`_count_conversion_losses()`) whenever some non-null values didn't
    match the recognized format and were converted to `NULL` — surfaced as each
    column's `conversion_warning` rather than silently lowering the health score with
    no indication of why. `_assert_csv_parsed_cleanly()` runs right after the initial
    `read_csv` and raises `MalformedCsvError` (caught in `service.py` alongside
    `duckdb.Error`, both -> HTTP 400) for two DuckDB CSV-sniffer failure shapes that
    otherwise sail through as a "successful" upload with a nonsense schema: a ragged
    file (a row's field count doesn't match the header's, e.g. an unquoted value that
    embeds the delimiter) makes DuckDB discard the header and fall back to generic
    `column0, column1, ...` names; rarer, the whole file collapses into one text column
    whose "name" is the unsplit header line itself.
  - **Type inference** lives in `src/datasets/profiling.py` (no DuckDB dependency, pure
    functions, cheap to unit test directly). `classify_column()` categorizes each
    column as Datetime / Continuous Numerical / Categorical / Free Text from its DuckDB
    type plus null/distinct-count/avg-length stats computed in
    `duckdb_manager._profile_columns()`. Numeric categorical-vs-continuous is an
    *absolute* distinct-count cap (`NUMERIC_CATEGORICAL_MAX_DISTINCT`), not a ratio of
    row count — a continuous quantity like age can have a modest distinct count even in
    a small dataset while still being conceptually continuous, so a ratio would
    misclassify it. That cap is overridden by `_looks_like_identifier_name()` for a
    numeric column whose name (tokenized the same way `generate_alias()` splits
    snake_case/camelCase) matches an identifier-shaped word (`id`, `code`, `zip`,
    `phone`, `sku`, ...) — a real zip/phone/ID column can have thousands of legitimate
    distinct values, and cardinality alone can't tell that apart from a genuine
    continuous metric like revenue; only the column name signals it. The override's
    confidence (65) is deliberately below `CONFIDENCE_REVIEW_THRESHOLD`, since a
    name-based heuristic is more failure-prone than the type/cardinality checks it sits
    on top of. The text-categorical cap (`TEXT_CATEGORICAL_MAX_DISTINCT`) is floored,
    not flat — scaled by row count above that floor (`TEXT_CATEGORICAL_DISTINCT_RATIO`)
    so a low-cardinality column on a large dataset (65 distinct job titles across 5,000
    rows) doesn't get flagged for needless review just because 65 exceeds a number sized
    for much smaller datasets; the ratio check stays as its own separate condition
    alongside the scaled cap (not folded into it), since dropping it would wrongly call
    an all-unique small column (e.g. 50 distinct values across exactly 50 rows)
    categorical whenever distinct_count happens to sit at or under the floor.
    `generate_alias()` turns a raw header into a human-readable label
    (`"cust_dob"` → `"Customer Date of Birth"`) via snake/camelCase splitting (shared
    with the identifier-name heuristic via `_split_words()`) plus an abbreviation
    dictionary — deterministic and dependency-free, not LLM-generated (unlike the SEO
    metadata tool), so ingestion never depends on an API key being configured.
  - `compute_column_health()` / `compute_dataset_health()` (also in `profiling.py`)
    score completeness (non-null %) per column and as a dataset-level mean. Computed
    once at ingest time and stored on the `datasets` row (`schema` jsonb +
    `health_score` column) — datasets are immutable after upload, so there's no
    staleness concern with caching this instead of recomputing it per request.
  - `classify_column_with_confidence()` (also in `profiling.py`) pairs the category with
    a 0-100 confidence based on distance from the decision boundary — a numeric column
    with exactly `NUMERIC_CATEGORICAL_MAX_DISTINCT` distinct values is a coin flip
    (confidence 60), one far from any threshold is not (confidence 99). Columns below
    `CONFIDENCE_REVIEW_THRESHOLD` (70) get `needs_review=True` at ingest time — this is
    what drives both the AI-review default target set and the frontend's review page.
- **AI-assisted + human type review** — `classify_column()`'s rule-based pass is a
  first guess, not the final word; two ways exist to correct it after ingestion,
  neither of which the ingest flow depends on:
  - `POST /api/datasets/{id}/schema/review` (`service.ai_review_column_types()`) sends
    flagged columns (name, type, current guess, distinct/null stats, a handful of
    sample values pulled from the existing preview — no extra DuckDB query per column)
    to `src/datasets/type_review.py`'s `suggest_column_categories()`, which prompts the
    configured LLM provider (`src/llm/client.get_llm_provider()`) for a category +
    confidence + short rationale per column. With no `columns` in the request body, it
    only touches columns that are both `needs_review` and not already
    `category_source="user"` — a bulk review must never silently override a human
    decision. Pass an explicit `columns` list to ask about *any* column regardless of
    confidence. A malformed or unreachable-provider response degrades to leaving those
    columns unchanged rather than corrupting the schema (see
    `suggest_column_categories()`'s per-column validation) — except a hard provider
    failure (network/auth error), which surfaces as an HTTP 502 so the frontend can show
    it rather than silently no-op.
  - `PATCH /api/datasets/{id}/schema/columns/{column_name}` (`service.update_column()`)
    covers both a type override and a rename in one call — `category` and `alias` are
    independent optional fields (`UpdateColumnRequest` requires at least one). A category
    override sets `category_source="user"`, confidence to 100, and `needs_review=False`
    unconditionally and always wins over both the rule and any AI suggestion; a rename
    only touches `alias` and leaves category/confidence/source untouched.
- `src/datasets/repository.py` — Supabase-backed CRUD for the `datasets` table using
  the *service role* key (bypasses RLS), so every function takes and filters by
  `owner_id` explicitly — RLS is not doing the ownership enforcement here, the Python
  code is. `update_dataset_schema()` is the one mutation after ingestion — it only ever
  rewrites the `schema` column (AI review / user override), never `row_count` or the R2
  keys, since those are fixed at ingest time.
  - **Name/description/notes**: `name` (defaults to the uploaded filename at ingest,
    never blank), `description` (nullable, ≤200 chars, meant to fit on a dataset card),
    and `notes` (nullable, uncapped, for a longer analysis writeup) are user-editable
    via `PATCH /api/datasets/{id}` (`service.update_dataset_metadata()` /
    `UpdateDatasetRequest`) independently of the filename, which stays fixed at
    ingestion as the record of what was actually uploaded. `update_dataset_metadata()`
    (repository) takes a plain `fields: dict` built by the service from
    `request.model_dump(exclude_unset=True)` — not a `name`/`description` kwarg pair
    defaulting to `None` — because `None` can't serve as the "field not provided in this
    PATCH" sentinel when the field's own valid values already include null (an explicit
    `description: ""` must clear it, which is different from omitting `description`
    entirely to leave it untouched). A deduplicated upload (see below) gets its own
    default `name` (= its own filename), not the matched row's name, matching how it
    already gets its own filename and identity — only the computed artifacts
    (schema/health/row_count/report_strategy) are copied forward.
- `src/storage/r2_client.py` — boto3 client for the raw CSV upload/delete only. Parquet
  read/write goes through DuckDB's own `httpfs` extension instead (configured in
  `duckdb_manager.py`), not through this module.
- `src/datasets/service.py` / `src/query/service.py` (routers) — orchestrate the above;
  routers stay thin, business logic lives in `service.py`. `GET /api/datasets/{id}/schema`
  returns `DatasetSchemaResponse`: dataset metadata, the dataset-level health score, each
  column's inferred type/alias/health (the stored, enriched `ColumnInfo`), and a preview
  fetched fresh from the Parquet via `preview_dataset()` rather than cached.
  - `ingest_csv_upload()` logs at each upload stage (start, parsed, complete) so a
    stuck-in-prod upload is traceable from Render logs alone. It's also the one place
    with three genuinely different failure modes, each caught and reported separately
    rather than one broad try/except: (1) a CSV parse failure
    (`duckdb.Error`/`MalformedCsvError`, see `duckdb_manager.py` above) -> HTTP 400,
    the only one that's actually the user's file's fault; (2) the raw-CSV-archive
    upload to R2 failing *after* the Parquet export already succeeded (bad R2
    credentials, network blip) -> HTTP 502; (3) the Supabase metadata insert failing
    after *both* R2 objects were written -> HTTP 502. (2) and (3) both call
    `_cleanup_orphaned_objects()` to delete whatever was already written to R2 before
    the failure, so a transient storage/DB outage doesn't leak Parquet/raw-CSV objects
    that no `datasets` row will ever reference — cleanup itself is best-effort and logs
    (rather than raises) on failure, so it can never mask the original error being
    returned to the client.
  - **Upload dedup**: `_stream_upload_to_disk()` computes an MD5 of the upload's bytes
    while streaming to disk (no extra read pass; not a security hash, just a
    change-detection fingerprint, so MD5's speed over correctness is the right choice).
    If `repository.get_dataset_by_content_hash(user.id, content_hash)` finds a match
    (same owner, byte-identical content), `_create_deduplicated_dataset()` creates a
    new `datasets` row — its own id, its own `filename`, its own entry in "Your
    datasets" — but **shares** the matched row's `raw_key`/`parquet_key` R2 objects and
    copies its `schema`/`health_score`/`row_count`/`report_strategy` forward, skipping
    `duckdb_manager.ingest_and_export()` and `r2_client.upload_raw_file()` entirely.
    Dedup is scoped per-owner (the content-hash lookup filters by `owner_id`), so
    storage is only ever shared between one user's own duplicate uploads, never across
    users. `delete_dataset()` correspondingly only deletes the R2 objects once
    `repository.count_datasets_sharing_storage()` confirms no other row still
    references them — checking `raw_key` alone is sufficient, since it and
    `parquet_key` are always assigned or copied together as a pair, never
    independently. Accepted race (this app's scale doesn't warrant solving it):
    concurrent deletes of the last two sibling rows can each see the other still
    present and both skip the R2 delete, leaking the objects — never the reverse
    (deleting storage a surviving row still needs), which is the failure direction
    that actually matters.
- **Report Strategy Engine** (`src/datasets/strategy_engine.py`) — `POST
  /api/datasets/{id}/report-strategy` (`service.generate_report_strategy()`) asks the
  configured LLM provider (Anthropic by default) to recommend a prioritized set of
  charts for a dataset from its already-inferred schema, then actually runs each
  recommendation's SQL before returning it.
  - **Cached, not recomputed on every call**: a dataset's Parquet never changes after
    ingest, so the full result (recommendations + their already-executed SQL results)
    is persisted on `datasets.report_strategy` and reused unless the request's
    `force` flag (`ReportStrategyRequest`) is set or no cached result exists yet.
    `repository.update_dataset_schema()` clears this cache back to `NULL` in the same
    statement as any schema write (AI review or a user's category override), since
    recommendations are derived from column categories — a stale cache must not
    survive a schema edit. The zero-chartable-columns case persists an actual `[]`
    (via `update_dataset_report_strategy()`) rather than leaving the column `NULL`,
    so it reads as "generated, nothing chartable" instead of looking identical to
    "never generated" on the next check. On the frontend, the single "Generate visual
    report" / "Regenerate report" button (same label logic as before) now passes
    `force: recommendations.length > 0` — the first click is happy to take a cache
    hit, a later click while recommendations are already shown forces a fresh LLM
    call + SQL re-run and overwrites the cache.
  - `strategy_engine.SYSTEM_PROMPT` encodes the three requirements as prompt rules:
    prioritize datetime columns (time-series line charts) over numerical (binned
    histogram/bell-curve) over categorical (pie ≤6 distinct values, else bar); DuckDB
    dialect specifics the model reliably gets wrong otherwise (no `width_bucket` —
    the prompt gives a `LEAST(floor(...))` binning idiom instead; `stddev()`, not
    `stddev_samp()`); and a single-statement SQL constraint with worked examples.
    Free-text columns are filtered out **before** the prompt is built — there's no
    meaningful aggregate chart for a comments column, so it's not even given the option.
  - The prioritization instruction is enforced twice, deliberately: the prompt asks for
    it, and `suggest_visual_strategy()` re-sorts the parsed response by
    `PARTITION_PRIORITY` regardless of what order the model actually returned. Treat an
    instruction to an LLM as a strong hint, never as a guarantee of output order (or
    anything else structural) — this codebase's LLM call sites all re-validate their own
    invariants in code rather than trusting the prompt to have been followed.
  - Every recommendation's `sql` is executed via the *existing* `duckdb_manager.
    execute_query()` — this is the same `_assert_readonly_select()` guard the
    human-facing `/query` endpoint uses, not a parallel one, which is the whole point of
    that guard existing (see its docstring: "this SQL may come from an LLM"). A query
    that fails the guard or fails to execute is reported per-recommendation via `error`
    rather than raised — one bad suggestion shouldn't sink the other nine.
  - Fixing this feature surfaced a real pre-existing gap: `_assert_readonly_select()`
    didn't catch `sqlglot.ParseError` for SQL that fails to parse at all (as opposed to
    parsing into something disallowed), so it crashed uncaught instead of being reported
    as unsafe. This affected the human-facing `/query` endpoint too, just rarely enough
    in practice to not have been hit — LLM-generated SQL fails to parse far more often
    than hand-typed SQL does. Now caught and converted to `UnsafeQueryError`.
- **Insights Generator** (`src/datasets/insights.py`) — `POST /api/datasets/{id}/insights`
  (`service.generate_chart_insights()`) takes a chart's already-aggregated `{columns,
  rows}` data straight from the request body (the frontend already has it, whether from
  the original strategy result or a client-rebuilt fast-aggregation query) and asks the
  LLM for 3-5 executive-summary bullets. It never re-runs SQL itself — the endpoint only
  checks dataset ownership before calling the model. Unlike `type_review.py`/
  `strategy_engine.py`, a malformed response (`json.JSONDecodeError`, non-list JSON)
  propagates as a hard error rather than degrading to a partial result: there's no
  per-item structure here to salvage, just a flat list of strings.
  - **Cached permanently, per exact chart view** — `src/datasets/insights_cache_repository.py`
    (a `chart_insights_cache` table, not a column on `datasets`: there can be many
    entries per dataset, one per distinct view). `service._insights_cache_key()` hashes
    `{column, chart_type, partition_type, result: {columns, rows}}` — NOT the whole
    dataset, since the same column viewed through a different filter/bin state produces
    different aggregated data (and so, potentially, different insight text) — and
    deliberately excludes `title`, even though `build_prompt()` interpolates it into the
    prompt: a renamed column alias changing a chart's displayed title could serve
    stale-titled insight text on a hit, an accepted tradeoff (the system prompt already
    tells the model not to restate the title verbatim) rather than an oversight. Unlike
    `report_strategy` above, this cache is never invalidated — the Parquet data behind
    one specific aggregation never changes, so a hit is valid forever.
- **Presentations** (`src/presentations/`, mirrors the `settings/` package layout) — one
  presentation per (dataset, owner) — see the `unique (dataset_id, owner_id)` constraint
  in the migration — holding an ordered `pages` → `blocks` document (`chart` | `insights`
  | `text`, a Pydantic discriminated union on a `type` field). `GET
  /api/datasets/{id}/presentation` returns an empty default rather than 404ing when
  nothing's been saved (same reasoning as `settings.get_settings()`). Two different write
  paths, deliberately not unified into one:
  - `POST .../presentation/pin` (`service.pin_block()`) is a small, atomic,
    immediately-persisted append (chart block + optional insights block onto the last
    page) — this is what "Pin to presentation" on the reports page calls, and it has to
    survive the user never opening the builder at all.
  - `PUT .../presentation` (`service.replace_presentation()`) replaces the whole document
    verbatim — this is what the drag-and-drop builder's debounced autosave calls after
    every reorder/rename/delete. The full-document-replace approach only works because
    pages/blocks are always read and written as one nested JSON document (`pages` jsonb),
    never queried or updated piecemeal — there was no reason to build granular
    "reorder block" / "move block to page" endpoints when the frontend already has to
    hold the whole document in memory to render the builder UI anyway.
- **Shares** (`src/shares/`, mirrors the `presentations/` package layout) — the
  backend's first genuinely public, unauthenticated surface. `POST
  /api/datasets/{id}/shares` (`service.create_chart_share()`) snapshots one chart's
  title/chart_type/partition_type/column/result at the moment the owner clicks "Share"
  and returns an unguessable token (`secrets.token_urlsafe(24)` — the first use of
  `secrets` in this backend, chosen over `uuid4` specifically because it's the module
  Python documents for generating unguessable secrets/tokens). `GET /api/shares/{token}`
  is the one route in the whole backend with no `Depends(get_current_user)` at all —
  confirmed there's no global auth middleware to bypass, so simply omitting that
  dependency is sufficient to make a route public. It never touches the dataset's
  Parquet, R2, or SQL execution — it only reads the one `chart_shares` row by token, so
  revoking access is just deleting that row (`DELETE
  /api/datasets/{id}/shares/{token}`, owner-scoped, matches `repository.delete_dataset`'s
  ownership-check-then-404 pattern). Deliberately snapshot-based rather than a live
  query, same reasoning as `report_strategy`/insights caching and "Pin to
  presentation": once a chart's result is computed, it's immutable and safe to persist.
  `router.py` doesn't use a single fixed router-level `prefix` like every other
  package's router does, since it serves two different path shapes (owner-scoped under
  `/api/datasets/{id}/...`, public under `/api/shares/...`). No `list_shares` endpoint
  yet — the frontend only needs create+revoke (the chart card that generated a link
  holds its token in local state to offer "Revoke" right there), so a "manage all my
  share links" list is unbuilt until something would actually call it. On the frontend,
  `frontend/src/lib/supabase/middleware.ts`'s `SHARE_PATH_PREFIX` makes `/share/*`
  public for everyone — deliberately not added to `GUEST_ONLY_PATHS`, since unlike
  `/login`/`/signup` a logged-in visitor must still be able to view a share link
  instead of being bounced to `/dashboard`. `/share/[token]/page.tsx` renders a live
  interactive chart (reusing `TimeSeriesChart`/`HistogramChart`/`CategoricalChart`
  exactly like `ChartCard` does, minus the insights/pin/download chrome), not the
  static SVG used for JPG/PDF export, to back up the "interactive dashboards" claim on
  the marketing page. `robots.ts` disallows `/share` and its `layout.tsx` sets
  `noindex` — it's public and reachable (unlike `/dashboard`/`/settings`, a crawler
  hitting it gets real content, not a redirect), but it's arbitrary user-generated
  content, not canonical marketing content, so it's still kept out of the index.
  - **Branding snapshot**: `create_chart_share()` also fetches the owner's settings
    and copies whichever header/footer preset is currently `enabled` (if any) onto
    the new row as `header_snapshot`/`footer_snapshot` — same reasoning as the
    chart's own `result` snapshot: the public page has no session to fetch the
    owner's live settings with, and rebranding later shouldn't retroactively alter a
    link already shared (see `test_share_branding_snapshot_is_frozen_at_creation_time`).
- `src/settings/` — per-user UI preferences (theme mode + colour theme), stored in the
  `user_settings` table (one row per user, upserted on save). Same repository/service/
  router split and owner_id-filtered access pattern as `datasets/`. `GET /api/settings`
  returns built-in defaults (`system` / `winter`) when no row exists yet, rather than
  404ing — there's nothing to "not find," an unconfigured user just hasn't saved
  preferences.
  - **Branding presets** — up to 5 header presets (`title`/`logo`/`enabled`) and 5
    footer presets (`html`/`enabled`) per user, stored as `header_presets`/
    `footer_presets` jsonb arrays on the same singleton row, edited via
    `PUT /api/settings/header-presets` / `.../footer-presets` (whole-array replace,
    same shape as `presentations.replace_presentation()` — simpler than per-item
    CRUD for a capped, rarely-large list). "Enable/disable" means mutual exclusivity,
    not independent toggles: `_assert_at_most_one_enabled()` (service.py) rejects a
    request that would leave more than one preset of the same type active, since only
    one header and one footer can actually render on a document at a time — enforced
    server-side, not just in the UI. A logo is a data URL embedded directly in the
    row (no R2 upload flow — logos are small), capped by `max_logo_size_kb`
    (`src/core/config.py`, same "raw field + derived `_bytes` property" pattern as
    `max_upload_size_mb`). Footer HTML is sanitized server-side with `nh3`
    (`_FOOTER_ALLOWED_TAGS`/`_FOOTER_ALLOWED_ATTRIBUTES`, matching exactly what the
    frontend's hand-rolled `RichTextEditor` can produce — no `script`/`style`/
    `iframe`/`on*`) **before** it's ever persisted — this is the one dependency this
    plan added on security grounds rather than avoided on "no deps for
    presentational things" grounds: it's rendered to other people (shared links,
    exported PDFs), not just the owner, so hand-rolled sanitization would be
    reckless. The repository's `update_header_presets`/`update_footer_presets`
    deliberately omit `theme_mode`/`color_theme`/the *other* presets column from
    their upsert payload — PostgREST's upsert only `SET`s the columns present in a
    given call's payload on conflict, so this can't clobber the independently-edited
    fields sharing this same singleton row (verified by
    `test_updating_header_presets_does_not_clobber_theme_or_footer_presets`).
- `src/llm/` — provider-agnostic LLM access. `src/llm/providers/base.py` defines the
  `LLMProvider` ABC (single `complete()` method); `anthropic_provider.py` and
  `deepseek_provider.py` implement it. `src/llm/client.py`'s `get_llm_provider()` picks
  the implementation based on `settings.llm_provider` ("anthropic" | "deepseek").
  DeepSeek's API is OpenAI-chat-completions-compatible, so its provider talks to it
  directly over `httpx` rather than pulling in an SDK. Callers so far: the AI-assisted
  type review and report strategy engine above. The eventual NL-to-SQL feature (see
  `_assert_readonly_select()` above) is expected to be the next one. When adding a new
  provider, implement `LLMProvider` and add one branch to the factory; don't change the
  call sites. (SEO metadata is no longer LLM-generated — see the SEO section below —
  so it's not a caller here anymore.)

Dataset IDs are Supabase-generated UUIDs (the `datasets.id` column), not generated
by DuckDB or the filesystem — `dataset_id` in API responses **is** the Supabase row ID.

## Testing approach

Tests don't hit real Supabase or real R2:
- `tests/conftest.py`'s `fake_datasets_table` fixture monkeypatches
  `src.datasets.repository` module functions with an in-memory dict, keyed the same
  way the real Postgres table is. `FakeDatasetsTable` has a method literally named
  `list` — any method defined *after* it that annotates a bare `list[...]` breaks at
  import time, because Python resolves a class body's annotations against the class's
  own namespace first, and `list` is now that method. Keep `list` last, or annotate
  with `builtins.list[...]` if you must add something after it. It also fakes the
  dedup/caching lookups (`get_by_content_hash`, `count_sharing_storage`,
  `update_report_strategy`) directly against its in-memory `rows` dict, and
  `update_schema` mirrors the real function's atomic `report_strategy` cache
  invalidation. `FakeChartInsightsCacheTable` (same file) is the equivalent stand-in
  for the `chart_insights_cache` table.
- LLM-calling code (`type_review.py`'s `suggest_column_categories()`,
  `strategy_engine.py`'s `suggest_visual_strategy()`) is tested with a small in-file
  fake implementing `LLMProvider`'s `complete()` — no real API key needed, see
  `tests/test_type_review.py` / `test_llm_providers.py` for the pattern.
  `test_report_strategy_endpoint.py` goes a
  step further and runs the fake's canned SQL against a *real* DuckDB/Parquet round
  trip (not mocked) — worth doing here specifically because the whole point of the
  feature is "is this LLM-shaped SQL actually safe and runnable," which a mocked
  `execute_query()` couldn't tell you.
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
  `updateSession()`. `/` is the public marketing page, `/about`/`/contact`/`/docs`/
  `/privacy`/`/terms` (`MARKETING_STATIC_PATHS`) are public marketing pages too, and
  `/login`/`/signup` are guest-only; every other route requires auth and redirects to
  `/login`. Signed-in users hitting `/`, `/login`, or `/signup` get bounced to
  `/dashboard` instead — the authenticated app home lives at `/dashboard`, not `/`,
  specifically so `/` can be a crawlable SEO landing page (see the SEO section below).
  `MARKETING_STATIC_PATHS` gets the same treatment as `SHARE_PATH_PREFIX`: public for
  everyone, but deliberately **not** added to the guest-only bounce branch, since a
  signed-in visitor must still be able to read these pages (e.g. from the footer)
  instead of being redirected away.
- **Site navigation** — a standard marketing header/footer for the public site, and a
  persistent left sidebar for the authenticated app, deliberately built as two
  separate navigation systems rather than one nav reused everywhere:
  - `src/app/(marketing)/` — a route group (doesn't affect the URL) wrapping `/`,
    `/login`, `/signup`, and the new `/about`, `/contact`, `/docs`, `/privacy`,
    `/terms` pages in one shared `layout.tsx` that renders `<SiteHeader />
    {children} <SiteFooter />`. `src/components/SiteHeader.tsx` shows a dual-colour
    `HomeIcon` (`src/components/IconButton.tsx` — the only icon in that file with a
    second explicit colour, the roof in `var(--color-accent)`, since this is a brand
    mark rather than a functional action icon) linking to `/`, nav links to About/
    Contact/Documentation, and an auth-aware right side that shows **Dashboard** when
    a Supabase session exists or **Sign in**/**Sign up free** when it doesn't — it
    detects the session the same way `theme-sync.tsx` does
    (`supabase.auth.getSession()` + an `onAuthStateChange` subscription), since this
    header (unlike the old `/`-only one it replaced) now also renders on pages a
    signed-in visitor can reach. `src/components/SiteFooter.tsx` repeats those links
    plus Privacy Policy/Terms of Use and a copyright line.
  - `src/content/siteContent.json` — the editable source for About/Contact/
    Documentation body copy (`{title, sections: [{heading, body}]}`, plus `email` for
    Contact), imported directly by their (server component) pages — editing the JSON
    later needs no component changes as long as that shape holds. Currently
    placeholder text, not final copy. Privacy Policy and Terms of Use are deliberately
    **not** JSON-sourced: they're full boilerplate legal text written directly into
    `privacy/page.tsx`/`terms/page.tsx` (generic template text, not reviewed by
    counsel — normal practice before relying on it for real compliance). Contact is
    static contact info, not a working form — there's no email-sending infrastructure
    in this codebase, and building one is a separate, bigger scope.
  - `src/components/DashboardSidebar.tsx` — the authenticated app's left nav, mounted
    by both `dashboard/layout.tsx` and `settings/layout.tsx` (the only two top-level
    authenticated route trees). Global links (Datasets, Settings, Sign out — the sign-
    out logic moved here from `dashboard/page.tsx`) always show; a contextual "This
    dataset" section (Column Types/Visual Reports/Presentation) appears only when
    `useParams()` yields a `datasetId`, i.e. under `/dashboard/[datasetId]/*` —
    replacing the individual "Back to dashboard"/"Back to reports" links each of
    those pages used to hand-roll. Responsive via layout direction, not a hamburger
    drawer: `flex-row` (a horizontal top bar) below `md:`, `flex-col` (a left column)
    at `md:` and up — this codebase had no existing mobile-drawer pattern to extend.
- `src/lib/api.ts` — the only place that calls the FastAPI backend. Every function
  attaches the current Supabase session's access token as `Authorization: Bearer
  <token>`, read fresh per call via `supabase.auth.getSession()` — don't cache the
  token elsewhere, it can rotate. Every call goes through `apiFetch()` (a thin wrapper
  every exported function uses instead of calling `fetch()` directly) specifically to
  distinguish a network-level failure (CORS block, DNS/connection failure — `fetch()`
  itself rejects) from a valid HTTP error response (`fetch()` resolves fine;
  `handleResponse()` deals with that) — both used to surface identically to the user as
  a generic "Failed to fetch" with no hint it was a deployment/CORS problem rather than
  something wrong with their file. `apiFetch()` logs the failing URL and
  `handleResponse()` logs the parsed error body to the console on any failure, and
  `API_BASE_URL` itself is logged once at module load — since it's baked in at Vercel
  build time (`NEXT_PUBLIC_*`), a stale/misconfigured value is otherwise invisible
  without inspecting the Network tab.
- `src/hooks/` — thin TanStack Query wrappers (`useUploadDataset`, `useDatasets`,
  `useDatasetSchema`, `useReportStrategy`, `useGenerateInsights`, `usePresentation`)
  around `src/lib/api.ts`. Data-fetching in this project goes through React Query, not
  raw `useEffect`/`fetch`. `useUpdateDataset` (in `useDatasets.ts`, alongside
  `useDeleteDataset`) is shared by every surface that edits name/description/notes —
  its `onSuccess` both invalidates the `["datasets"]` list query and patches the
  changed fields directly into the `["datasetSchema", datasetId]` cache entry (rather
  than invalidating and refetching it) so an open Column Types/Reports/Presentation
  page reflects a rename made from the dashboard card without an extra round trip.
- `/dashboard` — "Your datasets" renders one `DatasetCard`
  (`src/components/DatasetCard.tsx`) per dataset in a responsive grid (this replaced a
  plain list). Each card: an inline click-to-edit `name` (same commit-on-blur/Enter
  pattern as the column `AliasEditor` below), a click-to-edit `description` (a
  `<textarea maxLength={200}>` with a live character count) that falls back to an
  *auto-generated* one-liner (`"{row_count} rows · {columns} columns · {health}%
  health"`, computed client-side from fields the card already has — no extra request)
  whenever the user hasn't written their own, `line-clamp-3`'d so a long description
  still fits neatly instead of blowing out card height, row count, the existing Review
  types/Visual reports/Presentation links, and a delete (trash icon) button. Deleting
  confirms via `window.confirm()` (no modal library) describing exactly what cascades
  (column types, visual reports, presentation, share links) before calling `DELETE
  /api/datasets/{id}` — already fully handled server-side (ref-counts shared R2
  storage from dedup, and Postgres `ON DELETE CASCADE` on `presentations` /
  `chart_insights_cache` / `chart_shares` handles the rest), so this needed no backend
  changes, only the frontend affordance.
- `/dashboard/[datasetId]/types` — the column-editing page: a category `<select>` and
  a click-to-rename alias field per column (both via `useUpdateColumn`, i.e. the
  `PATCH .../schema/columns/{name}` that can set either or both in one call), an
  "Ask AI" action (`useReviewColumnTypes`, the `POST .../schema/review`) enabled
  whenever any column is `needs_review`, and a full "cleaned data preview" table below
  it rendering the schema response's `preview` (post-massaging, not the raw CSV — see
  the massaging pipeline above). `AliasEditor` has no effect syncing local state from
  `column.alias`: it's the *only* thing that ever changes an alias and already sets its
  own local value at commit time, so there's no external-update case to reconcile —
  adding one anyway to "be safe" is exactly the `set-state-in-effect` anti-pattern
  eslint's `react-hooks` plugin flags (see below). A column with a `conversion_warning`
  (set when date/numeric-string normalization dropped some non-null values to `NULL`
  at ingest — see the massaging pipeline above) shows it inline next to that column's
  null percentage, so a lower health score has a visible reason instead of looking like
  unexplained data loss. The header block shows the dataset's editable `name` (not its
  fixed `filename`) and, below it, a **Notes** `<textarea>` for a longer analysis
  writeup (the `notes` field — uncapped, unlike the dashboard card's 200-char
  `description`) autosaved 800ms after the last keystroke via the same
  local-state-forks-from-query + debounced-effect pattern as the presentation
  builder/settings branding UI, through the shared `useUpdateDataset` hook. Inherits
  `noindex` from `dashboard/layout.tsx` — it's auth-gated, same as the rest of
  `/dashboard`.
- `/dashboard/[datasetId]/reports` + `src/components/charts/` — the visualization
  dashboard: `useReportStrategy` triggers `POST .../report-strategy` on demand (not
  automatically, same reasoning as the type-review "Ask AI" button — don't spend an LLM
  call the user didn't ask for) and renders each recommendation as a `ChartCard` (the
  "intelligent feed"). The one exception is a report that's already been generated on a
  previous visit: `DatasetSchemaResponse.has_report_strategy` (true once
  `report_strategy` is non-`NULL`, even if it's `[]`) lets the page auto-fire
  `strategy.mutate(false)` on mount — `force=false` is a free cache hit server-side, no
  LLM call — so returning to a dataset that's already been analyzed doesn't require
  re-clicking "Generate visual report." A dataset that's never been analyzed
  (`has_report_strategy` false) still waits for that first click, so no dataset is ever
  auto-analyzed without the user having asked at least once. `ChartCard` dispatches on
  `partition_type` to `TimeSeriesChart`
  (line/area toggle), `HistogramChart` (bars + an optional Gaussian overlay for
  `bell_curve` — see below), or `CategoricalChart` (bar/pie).
  - **Fast aggregation without another LLM round-trip**: `src/lib/chartQueries.ts`
    builds fresh DuckDB SQL client-side for bin-size changes and click-to-filter
    (`buildHistogramSql`/`buildCategoricalSql`/`buildTimeSeriesSql`, mirroring the same
    binning idiom `strategy_engine.py`'s prompt teaches Claude — no `width_bucket` in
    DuckDB). `ChartCard` only fires a real query (`/api/datasets/{id}/query`, via
    `useQuery` keyed on the computed SQL string) once the built SQL differs from the
    recommendation's original — the default, untouched view costs zero extra requests
    since it already has the strategy response's own `result`. Filtering a chart by its
    *own* column is a no-op by design (there's nothing useful to cross-filter a chart
    against itself); clicking a bar/slice/bin toggles a single dataset-wide
    `ChartFilter` that every other card's SQL then incorporates.
  - The Gaussian overlay in `HistogramChart` intentionally isn't a normalized PDF — it's
    `maxCount * exp(-0.5 * ((x - mean) / stddev)^2)`, scaled to visually line up with
    the bars on a categorical (per-bucket) axis, computed once per bucket center rather
    than as an independent smooth series, since Recharts can't cleanly overlay a
    continuous line against a categorical axis otherwise.
  - `strategy_engine.py`'s prompt requires `min_val`/`max_val` in every numerical_bins
    result specifically so the frontend can label bin edges and compute the curve —
    without them `HistogramChart` falls back to bare bucket indices as labels and skips
    the curve. LLM output is never assumed to include them; every lookup goes through
    `findColumn()` (`src/lib/chartData.ts`), which returns `undefined` rather than
    throwing when a column is missing.
  - "Generate insights" / "Pin to presentation" on each `ChartCard` (`useGenerateInsights`
    / `usePinBlock`) always act on that card's **currently displayed** result — the
    original recommendation, or a filtered/rebinned one, whichever `result` the card is
    showing at the moment — not a stale copy from when the card first rendered.
  - Every action on a `ChartCard` (insights/pin/download/share, plus a fullscreen
    toggle) is an icon-only `IconButton` (`src/components/IconButton.tsx`) with a
    hover tooltip showing its name — hand-rolled SVG icons and a pure-Tailwind
    tooltip, no icon or tooltip library dependency, matching this codebase's existing
    aversion to new deps for presentational concerns. Fullscreen uses the real
    Fullscreen API (`element.requestFullscreen()`/`document.exitFullscreen()`) on the
    card's own container (not the whole page), tracked via a `fullscreenchange`
    listener rather than assuming the toggle succeeded synchronously.
  - **Per-chart export** — "Download JPG"/"Download PDF" (also acting on the card's
    currently-displayed result, via the same `toChartBlock()` helper the insights/pin
    handlers' payload shape mirrors). Both are deliberately dependency-free and
    server-free, reusing `staticChart.ts`'s existing SVG renderer (the same one the
    standalone-HTML export and presentation-PDF print path use):
    `src/lib/exportChartImage.ts`'s `downloadChartAsJpg()` rasterizes that SVG via an
    off-screen canvas and triggers a blob download; `src/lib/exportChartPdf.ts`'s
    `printChartAsPdf()` opens a dedicated popup window containing just that one SVG and
    calls `window.print()` on it — the same browser-print mechanism the presentation
    builder's "Export as PDF" button uses, just scoped to a single chart via an isolated
    popup instead of print-only CSS across the whole current page (there's no need to
    coordinate hiding every *other* chart card when each one already renders in its own
    window). "Share" (see `src/shares/` below) rounds out the export row. First three
    of a planned JPG → PDF → URL → MP4 set of export options aimed at three audiences
    (YouTube/content creators, businesses, and PPT/presentation embedding — see the SEO
    section). Still open: an animated MP4 export, which needs a rendering-approach
    decision — client-side `canvas.captureStream()`/`MediaRecorder` produces WebM
    natively, not MP4, without a WASM encoder or server-side rendering, and the latter
    is a poor fit for Render's free tier per the PDF-export reasoning above.
  - **Branding** (`src/lib/branding.ts`) — `renderBrandedHeaderHtml()`/
    `renderBrandedFooterHtml()` are the one shared place "what does branding look
    like" is defined, called from all five export/share surfaces: standalone HTML
    export, the presentation builder's print-only header/footer (a `hidden
    print:block` block, same pattern `BlockView` uses for chart rendering), the
    per-chart PDF popup, the per-chart JPG (see below), and the public share page.
    Both fall back to the plain title / no footer line when no preset is enabled, so
    a user who hasn't configured branding sees no regression. Footer HTML is already
    sanitized server-side at save time (`src/settings/service.py`) — every
    `dangerouslySetInnerHTML` call site here is safe *because* of that, not because
    the HTML is otherwise trusted. For the per-chart JPG specifically
    (`exportChartImage.ts`), branding a *raster* image needs a different trick than
    the other four (which are all real HTML documents that can just include the
    markup directly): the chart's own SVG gets wrapped with header/footer
    `<foreignObject>` bands inside a taller combined SVG before the existing
    SVG→canvas rasterize step — `foreignObject` can embed real (X)HTML inside SVG,
    which canvas can then rasterize, so this needed no new dependency (no
    `html2canvas`) and no change to the rasterize step itself.
  - **`src/components/RichTextEditor.tsx`** — the footer preset editor (Settings
    page, see below): a hand-rolled `contentEditable` div plus a Bold/Italic/Link/
    line-break toolbar via `document.execCommand`, not a library — the well-supported
    subset of that API this needs, not its deprecated/inconsistent corners, and not a
    general-purpose document editor. **Deliberately uncontrolled after mount**: an
    earlier version fed `value` back in reactively via `dangerouslySetInnerHTML` on
    every render, on the assumption that React would skip re-writing `innerHTML` when
    the string was unchanged — that assumption didn't hold in practice, and resetting
    the DOM node on every keystroke also resets the caret to position 0 regardless of
    whether content actually changed, which (typed fast enough) showed up as text
    coming out reversed. Fixed by seeding `value` into the DOM exactly once, in a
    mount-only `useEffect([])`, and never writing it back — `onInput` still reports
    changes upward via `onChange`, but the component's own DOM is the only source of
    truth after mount. Callers needing to load different content into the same slot
    must remount via `key` (e.g. the preset id), not expect a `value` prop change to
    take effect in place.
- `/dashboard/[datasetId]/presentation` — the multi-page drag-and-drop report builder.
  Reorder pages, reorder blocks within a page, and move a block to a different page are
  all native HTML5 drag-and-drop (`draggable` + `dataTransfer`, see
  `setDragData`/`readDragData` in the page file) — no DnD library dependency was added
  for this. `src/lib/presentationEditing.ts` holds the actual reorder/move/CRUD logic as
  plain functions over a `PresentationPageData[]`, kept separate from the drag event
  wiring so the "what changed" logic isn't tangled up with the "how the drag happened"
  plumbing.
  - **Local-state-forks-from-query pattern**: `localTitle`/`localPages` start `null`
    ("no edits yet, defer to the query result") and only ever get set by a user action,
    never by an effect syncing from `usePresentation()`'s async result. This sidesteps
    needing an effect to seed local editable state from data that arrives after mount —
    the same `set-state-in-effect` trap noted in `AliasEditor` above, but for async
    query data instead of a sync localStorage read. Once a page or block has been
    touched, `pages`/`title` are permanently derived from the local fork, not the
    server, until the page reloads.
  - Autosave is a genuinely valid effect (a debounced side effect calling
    `updatePresentation.mutate(...)`, not a `setState`) gated on `hasEdits` so it never
    fires from the initial load, only from an actual change.
  - **Export.** Two deliberately different mechanisms, not one:
    - *Standalone HTML* (`src/lib/exportPresentation.ts` + `src/lib/staticChart.ts`) is a
      fully self-contained file — inline CSS, inline `<svg>` charts, zero JS framework,
      zero network requests — built by hand-rolled SVG geometry functions, **not** by
      reusing the Recharts components. A file meant to open correctly in any browser
      long after this app (or session) is gone can't depend on a live React tree to
      render its charts.
    - *PDF* is the browser's native print-to-PDF (`window.print()` behind an "Export as
      PDF" button, with `print:*` Tailwind utilities hiding editor chrome and forcing one
      presentation page per printed page via `print:break-after-page`). Deliberately not
      a server-generated binary: Render's free tier is a poor fit for a headless-browser
      PDF pipeline (memory/cold-start), and the browser print path needs no new backend
      dependency at all. `BlockView` renders the *live* Recharts chart for on-screen
      editing but a hidden `print:block` **static SVG** (via `renderStaticChart`, the
      same function the HTML export uses) for the print path specifically — Recharts'
      `ResponsiveContainer` measures its size via `ResizeObserver`, which doesn't reliably
      fire through print's layout pass, and a chart that silently renders blank in the
      exported PDF is a worse failure mode than maintaining two render paths.
- Tailwind v4 (CSS-first config in `globals.css`, no `tailwind.config.js`) — this
  differs from the older Tailwind v3 + `tailwind.config.js` setup used in some of this
  user's other repos; don't add a v3-style config file here. `dark:` is remapped to a
  class-based variant (`@custom-variant dark (&:where(.dark, .dark *));`) instead of
  the Tailwind default `prefers-color-scheme` media query, since theme mode is now a
  user setting, not just an OS preference.
- `src/components/theme-provider.tsx` / `theme-sync.tsx` — theme state (light/dark/
  system + one of 6 colour themes) lives in localStorage first for instant, no-flash
  apply (see the inline `<script>` in `layout.tsx`, which must stay in sync with
  `THEME_STORAGE_KEY` in `src/lib/theme.ts`), and is mirrored to the backend's
  `user_settings` table so it follows the user across devices. `ThemeSync` only queries
  `/api/settings` once a Supabase session exists, so the (unauthenticated) login/signup
  pages never hit it. Applied via `data-color-theme` + `.dark` attributes on `<html>`,
  which the per-theme CSS variable blocks in `globals.css` key off of.
- The settings page (`/settings`) is the only place that calls `useUpdateSettings` —
  every control applies immediately (theme context + localStorage) and persists in the
  same click, there's no separate Save step.
- `/signup` is a dedicated page (not a mode toggle on `/login`) — `src/proxy.ts`'s
  guest-only paths already listed it before the route existed.

The frontend currently covers upload + list + preview + auth + settings. SQL query UI
and charts (Recharts/Plotly are already installed) are the natural next slice — see the
backend's `/api/datasets/{id}/query` endpoint, which is already wired and tested.

## SEO

Every page needs SEO metadata — this app targets organic search for "data
intelligence", "business intelligence", "csv to charts", "interactive charts", plus
the export-focused terms added alongside the YouTube/white-label export features on
the marketing page (e.g. "chart mp4 export", "animated chart export", "white label
pdf export", "interactive dashboard export").

- `src/app/layout.tsx` sets site-wide defaults (`metadataBase`, title template, OG/
  Twitter, default keywords). Route-specific pages override these.
- Next.js's `Metadata` API (`export const metadata`) only works from **Server
  Components**. Every current page under `src/app/*/page.tsx` is a client component
  (`"use client"`, for hooks/state), so metadata can't live in `page.tsx` directly —
  instead each route gets a sibling `layout.tsx` (a plain server component that just
  exports `metadata` and renders `{children}`). The exceptions are the marketing pages
  with no interactivity — `src/app/(marketing)/page.tsx`, `about/page.tsx`,
  `contact/page.tsx`, `docs/page.tsx`, `privacy/page.tsx`, `terms/page.tsx` — which are
  server components and export `metadata` directly.
- `/dashboard` and `/settings` require auth, so their metadata sets
  `robots: { index: false, follow: false }` and `src/app/robots.ts` disallows them —
  crawling a page that just redirects to `/login` wastes crawl budget and looks bad.
- `src/app/sitemap.ts` lists only the public routes (`/`, `/login`, `/signup`, `/about`,
  `/contact`, `/docs`, `/privacy`, `/terms`). `src/app/robots.ts` needs no matching
  change for these — it already `allow`s `/` broadly and only disallows the
  auth-gated/user-content paths (`/dashboard`, `/settings`, `/share`).
- **When adding a new frontend page, hand-write its metadata directly** (no LLM tool
  involved — there used to be a `backend/scripts/generate_seo.py` that drafted it via
  the configured LLM provider; it's been removed in favor of writing metadata straight
  into the route, matching the site-wide description/keyword style already established
  in `layout.tsx`/`page.tsx` and never claiming a feature the page doesn't actually
  have). Add the route to `sitemap.ts` if it's public, or to `robots.ts`'s disallow
  list (plus `noindex` metadata) if it requires auth.
