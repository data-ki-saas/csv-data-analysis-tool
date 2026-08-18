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


class GenerateInsightsRequest(BaseModel):
    title: str
    chart_type: str
    partition_type: str
    column: str
    result: QueryResponse


class InsightsResponse(BaseModel):
    insights: list[str]
