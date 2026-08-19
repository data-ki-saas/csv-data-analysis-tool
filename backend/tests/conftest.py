import uuid
from pathlib import Path

import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto.server import ThreadedMotoServer

from src.core.auth import CurrentUser, get_current_user
from src.core.config import settings
from src.datasets import insights_cache_repository, repository
from src.presentations import repository as presentations_repository
from src.settings import repository as settings_repository
from src.shares import repository as shares_repository

TEST_USER = CurrentUser(id="test-user-id", email="test@example.com")


@pytest.fixture(autouse=True)
def isolated_scratch_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "scratch_dir", tmp_path)
    yield tmp_path


@pytest.fixture(scope="session")
def moto_r2_server():
    server = ThreadedMotoServer(port=0)
    server.start()
    port = server._server.socket.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket="test-bucket")

    yield endpoint
    server.stop()


@pytest.fixture(autouse=True)
def r2_settings(moto_r2_server, monkeypatch):
    monkeypatch.setattr(settings, "r2_endpoint_override", moto_r2_server)
    monkeypatch.setattr(settings, "r2_access_key_id", "test")
    monkeypatch.setattr(settings, "r2_secret_access_key", "test")
    monkeypatch.setattr(settings, "r2_bucket_name", "test-bucket")


class FakeDatasetsTable:
    """In-memory stand-in for the Supabase `datasets` table used in router/service tests."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, **payload) -> repository.DatasetRecord:
        # Mirrors repository.create_dataset()'s own `report_strategy=None`
        # keyword default -- this fake fully replaces that function (rather
        # than wrapping it), so callers that omit report_strategy would
        # otherwise leave DatasetRecord's required field unset.
        payload = {
            "id": str(uuid.uuid4()),
            "created_at": "2026-01-01T00:00:00Z",
            "content_hash": None,
            "report_strategy": None,
            "value_remaps": None,
            "description": None,
            "notes": None,
            **payload,
        }
        self.rows[payload["id"]] = payload
        return repository.DatasetRecord(**payload)

    def get(self, dataset_id: str, owner_id: str) -> repository.DatasetRecord | None:
        row = self.rows.get(dataset_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        return repository.DatasetRecord(**row)

    def get_by_content_hash(self, owner_id: str, content_hash: str) -> repository.DatasetRecord | None:
        # self.rows preserves insertion order, so the first match found is
        # the oldest -- same tie-break as repository.get_dataset_by_content_hash's
        # `order("created_at")`.
        for row in self.rows.values():
            if row["owner_id"] == owner_id and row["content_hash"] == content_hash:
                return repository.DatasetRecord(**row)
        return None

    def count_sharing_storage(self, dataset_id: str, raw_key: str) -> int:
        return sum(
            1 for row in self.rows.values() if row["raw_key"] == raw_key and row["id"] != dataset_id
        )

    def update_schema(
        self, dataset_id: str, owner_id: str, schema: list[dict]
    ) -> repository.DatasetRecord | None:
        row = self.rows.get(dataset_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        row["schema"] = schema
        row["report_strategy"] = None  # mirrors the real function's atomic cache invalidation
        return repository.DatasetRecord(**row)

    def update_report_strategy(
        self, dataset_id: str, owner_id: str, report_strategy: list[dict] | None
    ) -> repository.DatasetRecord | None:
        row = self.rows.get(dataset_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        row["report_strategy"] = report_strategy
        return repository.DatasetRecord(**row)

    def update_metadata(
        self, dataset_id: str, owner_id: str, fields: dict
    ) -> repository.DatasetRecord | None:
        row = self.rows.get(dataset_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        row.update(fields)
        return repository.DatasetRecord(**row)

    def update_value_remaps(
        self, dataset_id: str, owner_id: str, value_remaps: dict[str, list[dict]] | None
    ) -> repository.DatasetRecord | None:
        row = self.rows.get(dataset_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        row["value_remaps"] = value_remaps
        row["report_strategy"] = None  # mirrors the real function's atomic cache invalidation
        return repository.DatasetRecord(**row)

    # NB: this method is named `list`, which shadows the builtin for any
    # annotation written below it in this class body (Python resolves class-body
    # annotations against the class namespace first) -- keep it as the last
    # method defined, or any `list[...]` annotation after it breaks at import time.
    def list(self, owner_id: str) -> list[repository.DatasetRecord]:
        return [
            repository.DatasetRecord(**row)
            for row in self.rows.values()
            if row["owner_id"] == owner_id
        ]

    def delete(self, dataset_id: str, owner_id: str) -> None:
        row = self.rows.get(dataset_id)
        if row is not None and row["owner_id"] == owner_id:
            del self.rows[dataset_id]


@pytest.fixture(autouse=True)
def fake_datasets_table(monkeypatch):
    table = FakeDatasetsTable()
    monkeypatch.setattr(
        repository,
        "create_dataset",
        lambda **kwargs: table.create(**kwargs),
    )
    monkeypatch.setattr(repository, "get_dataset", table.get)
    monkeypatch.setattr(repository, "get_dataset_by_content_hash", table.get_by_content_hash)
    monkeypatch.setattr(repository, "count_datasets_sharing_storage", table.count_sharing_storage)
    monkeypatch.setattr(repository, "list_datasets", table.list)
    monkeypatch.setattr(repository, "delete_dataset", table.delete)
    monkeypatch.setattr(repository, "update_dataset_schema", table.update_schema)
    monkeypatch.setattr(repository, "update_dataset_report_strategy", table.update_report_strategy)
    monkeypatch.setattr(repository, "update_dataset_metadata", table.update_metadata)
    monkeypatch.setattr(repository, "update_dataset_value_remaps", table.update_value_remaps)
    return table


class FakeUserSettingsTable:
    """In-memory stand-in for the Supabase `user_settings` table. `_merge`
    mirrors real PostgREST upsert semantics (`Prefer: resolution=merge-
    duplicates`): only the columns present in a given call's payload are
    written on conflict -- everything else on the row is left untouched, not
    reset to a default. This matters here because theme/color, header
    presets, and footer presets are all edited independently via separate
    calls against the same singleton row."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def _defaults(self, owner_id: str) -> dict:
        return {
            "owner_id": owner_id,
            "theme_mode": settings_repository.DEFAULT_THEME_MODE,
            "color_theme": settings_repository.DEFAULT_COLOR_THEME,
            "header_presets": [],
            "footer_presets": [],
        }

    def _merge(self, owner_id: str, **fields) -> settings_repository.UserSettingsRecord:
        row = {**self._defaults(owner_id), **self.rows.get(owner_id, {}), **fields}
        self.rows[owner_id] = row
        return settings_repository.UserSettingsRecord(**row)

    def get(self, owner_id: str) -> settings_repository.UserSettingsRecord | None:
        row = self.rows.get(owner_id)
        if row is None:
            return None
        return settings_repository.UserSettingsRecord(**row)

    def upsert(
        self, *, owner_id: str, theme_mode: str, color_theme: str
    ) -> settings_repository.UserSettingsRecord:
        return self._merge(owner_id, theme_mode=theme_mode, color_theme=color_theme)

    def update_header_presets(self, owner_id: str, presets: list[dict]) -> settings_repository.UserSettingsRecord:
        return self._merge(owner_id, header_presets=presets)

    def update_footer_presets(self, owner_id: str, presets: list[dict]) -> settings_repository.UserSettingsRecord:
        return self._merge(owner_id, footer_presets=presets)


@pytest.fixture(autouse=True)
def fake_user_settings_table(monkeypatch):
    table = FakeUserSettingsTable()
    monkeypatch.setattr(settings_repository, "get_settings", table.get)
    monkeypatch.setattr(settings_repository, "upsert_settings", lambda **kwargs: table.upsert(**kwargs))
    monkeypatch.setattr(settings_repository, "update_header_presets", table.update_header_presets)
    monkeypatch.setattr(settings_repository, "update_footer_presets", table.update_footer_presets)
    return table


class FakePresentationsTable:
    """In-memory stand-in for the Supabase `presentations` table."""

    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}

    def get(self, dataset_id: str, owner_id: str) -> presentations_repository.PresentationRecord | None:
        row = self.rows.get((dataset_id, owner_id))
        if row is None:
            return None
        return presentations_repository.PresentationRecord(**row)

    def upsert(
        self, *, dataset_id: str, owner_id: str, title: str, pages: list[dict]
    ) -> presentations_repository.PresentationRecord:
        row = {
            "dataset_id": dataset_id,
            "owner_id": owner_id,
            "title": title,
            "pages": pages,
            "updated_at": "2026-01-01T00:00:00Z",
        }
        self.rows[(dataset_id, owner_id)] = row
        return presentations_repository.PresentationRecord(**row)


@pytest.fixture(autouse=True)
def fake_presentations_table(monkeypatch):
    table = FakePresentationsTable()
    monkeypatch.setattr(presentations_repository, "get_presentation", table.get)
    monkeypatch.setattr(presentations_repository, "upsert_presentation", lambda **kwargs: table.upsert(**kwargs))
    return table


class FakeChartInsightsCacheTable:
    """In-memory stand-in for the Supabase `chart_insights_cache` table."""

    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}

    def get(self, dataset_id: str, cache_key: str) -> insights_cache_repository.InsightsCacheRecord | None:
        row = self.rows.get((dataset_id, cache_key))
        if row is None:
            return None
        return insights_cache_repository.InsightsCacheRecord(**row)

    def save(
        self, *, dataset_id: str, owner_id: str, cache_key: str, insights: list[str]
    ) -> insights_cache_repository.InsightsCacheRecord:
        row = {
            "id": str(uuid.uuid4()),
            "dataset_id": dataset_id,
            "owner_id": owner_id,
            "cache_key": cache_key,
            "insights": insights,
            "created_at": "2026-01-01T00:00:00Z",
        }
        self.rows[(dataset_id, cache_key)] = row
        return insights_cache_repository.InsightsCacheRecord(**row)


@pytest.fixture(autouse=True)
def fake_chart_insights_cache_table(monkeypatch):
    table = FakeChartInsightsCacheTable()
    monkeypatch.setattr(insights_cache_repository, "get_cached_insights", table.get)
    monkeypatch.setattr(insights_cache_repository, "save_insights_cache", lambda **kwargs: table.save(**kwargs))
    return table


class FakeChartSharesTable:
    """In-memory stand-in for the Supabase `chart_shares` table."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, **payload) -> shares_repository.ChartShareRecord:
        row = {"id": str(uuid.uuid4()), "created_at": "2026-01-01T00:00:00Z", **payload}
        self.rows[row["token"]] = row
        return shares_repository.ChartShareRecord(**row)

    def get_by_token(self, token: str) -> shares_repository.ChartShareRecord | None:
        row = self.rows.get(token)
        if row is None:
            return None
        return shares_repository.ChartShareRecord(**row)

    def delete(self, dataset_id: str, owner_id: str, token: str) -> None:
        row = self.rows.get(token)
        if row is not None and row["dataset_id"] == dataset_id and row["owner_id"] == owner_id:
            del self.rows[token]


@pytest.fixture(autouse=True)
def fake_chart_shares_table(monkeypatch):
    table = FakeChartSharesTable()
    monkeypatch.setattr(shares_repository, "create_share", lambda **kwargs: table.create(**kwargs))
    monkeypatch.setattr(shares_repository, "get_share_by_token", table.get_by_token)
    monkeypatch.setattr(shares_repository, "delete_share", table.delete)
    return table


@pytest.fixture
async def client():
    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_csv_path(tmp_path) -> Path:
    path = tmp_path / "sample.csv"
    path.write_text("id,name,amount\n1,alice,10.5\n2,bob,20.25\n3,carol,5\n")
    return path
