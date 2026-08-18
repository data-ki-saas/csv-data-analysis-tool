from httpx import ASGITransport, AsyncClient

from src.core.auth import CurrentUser, get_current_user
from src.datasets.duckdb_manager import duckdb_manager
from src.storage import r2_client

_ANOTHER_USER = CurrentUser(id="another-test-user-id", email="other@example.com")


def _new_app():
    from src.main import create_app

    return create_app()


async def _upload(client, csv_path, filename="dup.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload", files={"file": (filename, f, "text/csv")}
        )
    return response


async def test_duplicate_upload_by_same_owner_shares_storage_and_skips_processing(
    client, sample_csv_path, monkeypatch
):
    ingest_calls = []
    raw_upload_calls = []
    real_ingest_and_export = duckdb_manager.ingest_and_export
    real_upload_raw_file = r2_client.upload_raw_file

    def spy_ingest_and_export(*args, **kwargs):
        ingest_calls.append(1)
        return real_ingest_and_export(*args, **kwargs)

    def spy_upload_raw_file(*args, **kwargs):
        raw_upload_calls.append(1)
        return real_upload_raw_file(*args, **kwargs)

    monkeypatch.setattr(duckdb_manager, "ingest_and_export", spy_ingest_and_export)
    monkeypatch.setattr(r2_client, "upload_raw_file", spy_upload_raw_file)

    first = await _upload(client, sample_csv_path, "first.csv")
    assert first.status_code == 200
    assert len(ingest_calls) == 1
    assert len(raw_upload_calls) == 1

    second = await _upload(client, sample_csv_path, "second.csv")
    assert second.status_code == 200
    # The duplicate upload never touched DuckDB ingest or the raw R2 upload again.
    assert len(ingest_calls) == 1
    assert len(raw_upload_calls) == 1

    first_body, second_body = first.json(), second.json()
    assert first_body["dataset_id"] != second_body["dataset_id"]
    assert second_body["filename"] == "second.csv"  # keeps its own filename
    assert second_body["row_count"] == first_body["row_count"]


async def test_duplicate_upload_preserves_new_filename_but_copies_schema_health_row_count(
    client, sample_csv_path, fake_datasets_table
):
    first = await _upload(client, sample_csv_path, "first.csv")
    second = await _upload(client, sample_csv_path, "second.csv")

    first_row = fake_datasets_table.rows[first.json()["dataset_id"]]
    second_row = fake_datasets_table.rows[second.json()["dataset_id"]]

    assert second_row["filename"] == "second.csv"
    assert second_row["raw_key"] == first_row["raw_key"]
    assert second_row["parquet_key"] == first_row["parquet_key"]
    assert second_row["schema"] == first_row["schema"]
    assert second_row["health_score"] == first_row["health_score"]
    assert second_row["row_count"] == first_row["row_count"]
    assert second_row["content_hash"] == first_row["content_hash"]


async def test_duplicate_upload_by_different_owner_does_not_dedup(sample_csv_path, fake_datasets_table):
    app = _new_app()

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="owner-a", email="a@example.com"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client_a:
        first = await _upload(client_a, sample_csv_path, "first.csv")

    app.dependency_overrides[get_current_user] = lambda: _ANOTHER_USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client_b:
        second = await _upload(client_b, sample_csv_path, "second.csv")

    assert first.status_code == 200 and second.status_code == 200
    first_row = fake_datasets_table.rows[first.json()["dataset_id"]]
    second_row = fake_datasets_table.rows[second.json()["dataset_id"]]
    assert second_row["raw_key"] != first_row["raw_key"]
    assert second_row["parquet_key"] != first_row["parquet_key"]


async def test_non_identical_upload_runs_full_pipeline(client, tmp_path):
    path_a = tmp_path / "a.csv"
    path_a.write_text("id,name,amount\n1,alice,10.5\n2,bob,20.25\n3,carol,5\n")
    path_b = tmp_path / "b.csv"
    path_b.write_text("id,name,amount\n1,alice,10.5\n2,bob,20.25\n3,carol,6\n")  # one byte differs

    first = await _upload(client, path_a, "a.csv")
    second = await _upload(client, path_b, "b.csv")

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["dataset_id"] != second.json()["dataset_id"]
