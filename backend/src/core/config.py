import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which LLMProvider src.llm.client.get_llm_provider() returns: "anthropic" or "deepseek".
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
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def r2_endpoint_url(self) -> str:
        return self.r2_endpoint_override or f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


settings = Settings()
settings.scratch_dir.mkdir(parents=True, exist_ok=True)
