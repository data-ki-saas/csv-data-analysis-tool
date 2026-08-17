import uuid
from pathlib import Path

import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto.server import ThreadedMotoServer

from src.core.auth import CurrentUser, get_current_user
from src.core.config import settings
from src.datasets import repository

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
        payload = {"id": str(uuid.uuid4()), "created_at": "2026-01-01T00:00:00Z", **payload}
        self.rows[payload["id"]] = payload
        return repository.DatasetRecord(**payload)

    def get(self, dataset_id: str, owner_id: str) -> repository.DatasetRecord | None:
        row = self.rows.get(dataset_id)
        if row is None or row["owner_id"] != owner_id:
            return None
        return repository.DatasetRecord(**row)

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
    monkeypatch.setattr(repository, "list_datasets", table.list)
    monkeypatch.setattr(repository, "delete_dataset", table.delete)
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
