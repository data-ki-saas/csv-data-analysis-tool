from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.query.schemas import QueryResponse

CategoryLiteral = Literal["datetime", "continuous_numerical", "categorical", "free_text"]


class ColumnInfo(BaseModel):
    name: str
    type: str
    alias: str
    category: str
    category_source: str
    confidence: float
    needs_review: bool
    rationale: str | None = None
    null_count: int
    null_percentage: float
    distinct_count: int
    health_score: float
    conversion_warning: str | None = None
    # Set when this categorical column's cells look like they pack several
    # delimited tags into one string (e.g. "Mumbai, Pune") -- see
    # profiling.detect_multi_value_separator.
    multi_value_separator: str | None = None


class DatasetPreview(BaseModel):
    columns: list[str]
    rows: list[list]


class UploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str
    filename: str
    name: str
    description: str | None = None
    notes: str | None = None
    row_count: int
    health_score: float
    schema_: list[ColumnInfo] = Field(alias="schema")
    preview: DatasetPreview


class DatasetInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str
    filename: str
    name: str
    description: str | None = None
    notes: str | None = None
    row_count: int
    health_score: float
    schema_: list[ColumnInfo] = Field(alias="schema")


class DatasetSchemaResponse(BaseModel):
    """Response for GET /api/datasets/{id}/schema: dataset metadata, data
    quality health, inferred column types, and a fresh sample preview."""

    dataset_id: str
    filename: str
    name: str
    description: str | None = None
    notes: str | None = None
    row_count: int
    created_at: str
    health_score: float
    columns: list[ColumnInfo]
    preview: DatasetPreview
    # True once a report strategy has been generated at least once (even if
    # it found nothing chartable -- see generate_report_strategy's `[]` vs
    # `None` distinction). Lets the reports page auto-load an already
    # -generated report on open without ever auto-triggering a first-time
    # LLM call for a dataset that was never analyzed.
    has_report_strategy: bool = False


class UpdateDatasetRequest(BaseModel):
    """All fields optional so a single PATCH can rename a dataset, edit its
    description/notes, or any combination -- but at least one must actually
    be present. Unlike UpdateColumnRequest's `alias`, `description`/`notes`
    are nullable, so an explicit "" is a valid, meaningful value (clears the
    field) that's different from omitting it entirely (leave unchanged) --
    `model_fields_set` (not a plain `is None` check) is what distinguishes
    them, since `None` can't serve as the "not provided" sentinel when the
    field's own valid range already includes falsy values."""

    name: str | None = None
    description: str | None = Field(default=None, max_length=200)
    # Unlike `description`, not meant to fit neatly in a card -- a longer,
    # uncapped free-form field for a detailed writeup of the data.
    notes: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateDatasetRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one of name, description, or notes")
        if "name" in self.model_fields_set and (self.name is None or not self.name.strip()):
            raise ValueError("name cannot be blank")
        return self


class ReviewColumnsRequest(BaseModel):
    # None = review every column currently flagged needs_review; an explicit
    # list reviews exactly those columns regardless of their current confidence.
    columns: list[str] | None = None


class UpdateColumnRequest(BaseModel):
    """Both fields optional so a single PATCH can rename a column, override
    its type, or both -- but at least one must actually be present."""

    category: CategoryLiteral | None = None
    alias: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateColumnRequest":
        if self.category is None and self.alias is None:
            raise ValueError("Provide at least one of category or alias")
        if self.alias is not None and not self.alias.strip():
            raise ValueError("alias cannot be blank")
        return self


class ChartRecommendation(BaseModel):
    # Assigned server-side (never by the LLM) so an individual chart can be
    # deleted or reordered later -- see service._with_ids() for how older
    # cached recommendations (persisted before this field existed) get one
    # backfilled on first load.
    id: str
    # "auto" (the default, including every recommendation persisted before
    # this field existed) came from generate_report_strategy's whole-dataset
    # LLM pass; "custom" came from a user's free-text request
    # (service.add_custom_chart). generate_report_strategy(force=True)
    # ("Regenerate report") only recomputes/replaces the "auto" set --
    # "custom" charts survive a regenerate, since they aren't part of what
    # that whole-dataset strategy pass is reconsidering.
    source: Literal["auto", "custom"] = "auto"
    column: str
    partition_type: Literal["datetime", "numerical_bins", "categorical"]
    chart_type: Literal["line", "bar", "pie", "histogram", "bell_curve"]
    title: str
    rationale: str
    sql: str
    # Populated by executing `sql` against the dataset's Parquet; `error` is
    # set instead if that SQL failed validation or execution -- the LLM's
    # output is never trusted to be runnable just because it parsed as JSON.
    result: QueryResponse | None = None
    error: str | None = None


class ReportStrategyResponse(BaseModel):
    dataset_id: str
    filename: str
    recommendations: list[ChartRecommendation]


class ReportStrategyRequest(BaseModel):
    # False (default): serve a cached result if one exists (no LLM call, no
    # SQL re-run) -- what the frontend's initial "Generate visual report"
    # click sends. True: always recompute and overwrite the cache -- what
    # the "Regenerate report" click (shown once recommendations already
    # exist) sends.
    force: bool = False


class CustomChartRequest(BaseModel):
    # e.g. "show me distribution of annual income city wise" -- see
    # strategy_engine.suggest_custom_chart(). Capped well above any
    # reasonable request; this isn't a free-text notes field.
    prompt: str = Field(min_length=1, max_length=300)


class UpdateChartRequest(BaseModel):
    """Edits a chart's displayed title and/or subtitle (`rationale`) --
    both originally LLM-generated, but not fixed once shown. Same
    at-least-one-field / model_fields_set pattern as UpdateDatasetRequest:
    `title` can never be blank, `rationale` can be cleared to ""."""

    title: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateChartRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one of title or rationale")
        if "title" in self.model_fields_set and (self.title is None or not self.title.strip()):
            raise ValueError("title cannot be blank")
        return self


class ReorderChartsRequest(BaseModel):
    # The full, reordered list of every chart id currently on the dataset's
    # report -- a whole-array replace (like presentations/branding presets
    # elsewhere in this codebase) rather than a granular "move chart to
    # index N" endpoint, since the frontend already has the full list in
    # memory to reorder locally before persisting.
    chart_ids: list[str]


class GenerateInsightsRequest(BaseModel):
    title: str
    chart_type: str
    partition_type: str
    column: str
    result: QueryResponse
    # Unused by the insights endpoint itself (generate_chart_insights() never
    # reads it) -- only present because src/shares/service.py's
    # create_chart_share() reuses this same request shape and needs the
    # chart's subtitle to snapshot alongside its title.
    rationale: str = ""


class InsightsResponse(BaseModel):
    insights: list[str]


class ValueMergeRule(BaseModel):
    """One accepted or proposed merge: every value in `sources` reads as
    `target` from then on, everywhere this column is read (see
    duckdb_manager._column_transform_replace_clause)."""

    target: str
    sources: list[str]
    # How many rows this rule affected, as of the last time it was accepted
    # or grown -- a best-effort, cumulative figure (not a live re-count), so
    # the "Active rules" tab can show the volume of change each rule
    # represents. None for rules that predate this field.
    rows_affected: int | None = None


class ReplacementRule(BaseModel):
    """One replacement, applied to every value of a column before any
    ValueMergeRule -- see duckdb_manager._column_transform_expr. `find` is
    either a literal substring (e.g. "Delhi / NCR" -> "Delhi") or, when
    `is_regex` is set, a regular expression (DuckDB's RE2-based dialect,
    e.g. "Kolkata\\(.*\\)" -> "Kolkata" to strip any parenthetical) matched
    and replaced globally (every occurrence, not just the first)."""

    find: str
    replace: str
    is_regex: bool = False
    # Snapshotted at accept time, same caveat as ValueMergeRule.rows_affected.
    rows_affected: int | None = None


class ColumnValueCount(BaseModel):
    value: str
    count: int


class ColumnValuesResponse(BaseModel):
    """A categorical/free-text column's current distinct values (post
    already-accepted edits) plus the merge and replacement rules in effect --
    backs the "Edit column" dialog's value list and its list of active,
    individually-revertible rules."""

    dataset_id: str
    column: str
    values: list[ColumnValueCount]
    rules: list[ValueMergeRule]
    replacements: list[ReplacementRule] = []
    # The column's true distinct-value count after current rules -- NOT
    # capped like `values` is, so "N categories" stays accurate even past
    # that cap.
    distinct_count: int


class SuggestValueMergeRequest(BaseModel):
    # e.g. "merge all values that contain NY or New York City into New York",
    # or a literal "replace 'Delhi / NCR' with 'Delhi'" -- a single-turn
    # instruction against the column's current state, not a multi-turn chat
    # (see src/datasets/value_merge.py).
    command: str = Field(min_length=1, max_length=300)


class ValueMergeSuggestion(BaseModel):
    """A proposed (not yet persisted) edit. `kind` discriminates which of
    `groups` (a merge) or `replacement` (a literal substring replace) is
    populated. `preview_values`/`preview_distinct_count` are what the
    column's value list/category count would look like if it were accepted,
    so the dialog can show a before/after without touching stored rules yet."""

    kind: Literal["merge", "replace"] = "merge"
    groups: list[ValueMergeRule] = []
    replacement: ReplacementRule | None = None
    preview_values: list[ColumnValueCount]
    preview_distinct_count: int


class AcceptValueMergeRequest(BaseModel):
    groups: list[ValueMergeRule] = Field(min_length=1)


class AcceptReplacementRequest(BaseModel):
    find: str = Field(min_length=1, max_length=300)
    replace: str = Field(max_length=300)
    is_regex: bool = False


class AcceptValueMergeResponse(ColumnValuesResponse):
    # How many rows' displayed value actually changed as a result of THIS
    # accept call (a source value merging into itself doesn't count) -- not
    # a running total, just this one action's effect, so the dialog can
    # confirm what just happened.
    rows_updated: int


class TagConfig(BaseModel):
    """How to explode one multi-value column's cell into individual tags,
    and the curated vocabulary a tag chart should actually count against --
    see duckdb_manager.build_tag_chart_sql. `vocabulary` is what gives the
    user control over the size of the resulting chart: an empty vocabulary
    means "not curated yet, count every exploded tag"; a non-empty one means
    "only these"."""

    # e.g. "-" to split "Hybrid - Pune, Noida" into a discarded "Hybrid"
    # prefix and a "Pune, Noida" tag list. None: no prefix stripping. Capped
    # generously (not tightly like tag_separator) since this is realistically
    # typed as a short marker string (e.g. "-", " - ", "Mode:"), not always a
    # single character.
    prefix_separator: str | None = Field(default=None, max_length=40)
    tag_separator: str = Field(default=",", min_length=1, max_length=5)
    vocabulary: list[str] = Field(default=[], max_length=200)
    # When vocabulary is set: fold every non-vocabulary tag into one "Other"
    # bucket instead of excluding it, so the chart's total still covers
    # every row. Ignored when vocabulary is empty (nothing to be "other" than).
    include_other: bool = False


class TagCandidate(BaseModel):
    tag: str
    count: int


class TagCandidatesResponse(BaseModel):
    dataset_id: str
    column: str
    candidates: list[TagCandidate]
    config: TagConfig
    # The true, uncapped count of distinct tags -- NOT capped like
    # `candidates` is, so the "Tags" panel's "Load more" can tell whether
    # there's more to page through.
    total_tags: int


class UpdateTagConfigRequest(TagConfig):
    pass


class AddTagChartRequest(BaseModel):
    # Optional override for the generated chart's title -- default is
    # "{alias} by tag" (see service.add_tag_chart).
    title: str | None = Field(default=None, max_length=200)
