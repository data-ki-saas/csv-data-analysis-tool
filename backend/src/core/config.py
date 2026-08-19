import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which LLMProvider src.llm.client.get_llm_provider() returns: "anthropic" or "deepseek".
    # Override per environment via the LLM_PROVIDER env var (.env locally, a Render
    # env var in production) -- this default is only the local/test fallback.
    llm_provider: str = "anthropic"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # Local staging directory for streamed uploads before they're ingested by
    # DuckDB and pushed to R2. Nothing durable lives here.
    scratch_dir: Path = Path(tempfile.gettempdir()) / "csv-analysis-tool" / "scratch"

    max_upload_size_mb: int = 2048
    query_max_rows: int = 10_000
    query_timeout_seconds: int = 30

    # A branding-preset logo is a data URL embedded directly in the
    # user_settings row (see src/settings/), not an R2 upload -- capped small
    # since it's a logo, not a dataset file.
    max_logo_size_kb: int = 200

    # ---- Value-editing / tag-column form limits (schemas.py Field(max_length=...)) ----
    # Free-text "Ask AI to merge values, or replace text" command box (both
    # the merge instruction and a literal/regex replace command share this).
    value_edit_command_max_length: int = 300
    # A literal replacement rule's `find`/`replace` text (POST .../replace/accept),
    # independent of the command-box parsing above.
    replacement_text_max_length: int = 300
    # A multi-value column's optional prefix-separator marker (e.g. "-" in
    # "Hybrid - Pune, Noida") and its tag separator (usually ",").
    tag_prefix_separator_max_length: int = 40
    tag_separator_max_length: int = 5
    # How many tags a user can curate into one column's vocabulary.
    tag_vocabulary_max_size: int = 200
    # A dataset's editable description and a chart's editable title.
    dataset_description_max_length: int = 200
    chart_title_max_length: int = 200
    # Free-text "Add custom chart" prompt -- generous enough for a
    # fully-spelled-out parsing instruction (e.g. "parse experience_raw as
    # 'min - max yrs', strip 'yrs', split on '-', average the two numbers...").
    custom_chart_prompt_max_length: int = 500

    # ---- Value-editing / tag-column pagination (the Edit Column dialog's
    # "Current values"/"Tags" lists and their "Load more" button) ----
    column_values_page_size: int = 200
    column_values_max_page_size: int = 5000
    tag_candidates_page_size: int = 200
    tag_candidates_max_page_size: int = 5000

    # ---- Range-column parsing (e.g. "4-10 yrs" -> a chartable numeric measure) ----
    # A range column's separator (e.g. "-") and unit suffix (e.g. "yrs") to strip.
    range_separator_max_length: int = 5
    range_unit_max_length: int = 20
    # How many (raw value, parsed value) pairs the "Range" panel's live
    # preview shows -- a UI aid, not an exhaustive export.
    range_preview_sample_size: int = 20

    cors_origins: str = "http://localhost:3000"

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    # Overrides the computed R2 endpoint — set only in tests, to point DuckDB's
    # and boto3's S3 clients at a local mock server instead of real R2.
    r2_endpoint_override: str = ""

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_logo_size_bytes(self) -> int:
        return self.max_logo_size_kb * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def r2_endpoint_url(self) -> str:
        return self.r2_endpoint_override or f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


settings = Settings()
settings.scratch_dir.mkdir(parents=True, exist_ok=True)
