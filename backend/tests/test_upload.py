from src.datasets import repository
from src.storage import r2_client


async def test_upload_csv_creates_dataset(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 3
    assert {col["name"] for col in body["schema"]} == {"id", "name", "amount"}
    assert len(body["preview"]["rows"]) == 3


async def test_upload_rejects_non_csv(client, tmp_path):
    bad_file = tmp_path / "sample.txt"
    bad_file.write_text("not a csv")
    with open(bad_file, "rb") as f:
        response = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.txt", f, "text/plain")},
        )
    assert response.status_code == 400


async def test_get_dataset_after_upload(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        upload = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    response = await client.get(f"/api/datasets/{dataset_id}")
    assert response.status_code == 200
    assert response.json()["row_count"] == 3


async def test_get_unknown_dataset_returns_404(client):
    response = await client.get("/api/datasets/does-not-exist")
    assert response.status_code == 404


async def test_list_datasets_returns_uploaded(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})

    response = await client.get("/api/datasets")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_delete_dataset_removes_it(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        upload = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    delete_response = await client.delete(f"/api/datasets/{dataset_id}")
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/datasets/{dataset_id}")
    assert get_response.status_code == 404


async def test_query_dataset(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        upload = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    response = await client.post(
        f"/api/datasets/{dataset_id}/query",
        json={"sql": "SELECT count(*) AS n FROM data"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["n"]
    assert body["rows"] == [[3]]


async def test_get_dataset_schema(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        upload = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    response = await client.get(f"/api/datasets/{dataset_id}/schema")
    assert response.status_code == 200
    body = response.json()

    assert body["dataset_id"] == dataset_id
    assert body["row_count"] == 3
    assert "health_score" in body
    assert "created_at" in body
    assert {col["name"] for col in body["columns"]} == {"id", "name", "amount"}
    assert all(
        {"alias", "category", "null_count", "null_percentage", "distinct_count", "health_score"}
        <= col.keys()
        for col in body["columns"]
    )
    assert len(body["preview"]["rows"]) == 3


async def test_get_schema_for_unknown_dataset_returns_404(client):
    response = await client.get("/api/datasets/does-not-exist/schema")
    assert response.status_code == 404


async def test_upload_response_includes_health_score(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    assert response.json()["health_score"] == 100.0


async def test_query_rejects_unsafe_sql(client, sample_csv_path):
    with open(sample_csv_path, "rb") as f:
        upload = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    dataset_id = upload.json()["dataset_id"]

    response = await client.post(
        f"/api/datasets/{dataset_id}/query",
        json={"sql": "DROP TABLE data"},
    )
    assert response.status_code == 400


async def test_upload_returns_502_and_cleans_up_when_raw_storage_fails(
    client, sample_csv_path, monkeypatch
):
    # The Parquet export succeeds (real R2/moto round trip) but the raw-CSV
    # archive upload fails -- a distinct failure mode from a bad CSV, and one
    # that previously had no except clause at all (an unhandled 500).
    deleted_keys = []
    monkeypatch.setattr(r2_client, "delete_object", lambda key: deleted_keys.append(key))
    monkeypatch.setattr(
        r2_client,
        "upload_raw_file",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("R2 unreachable")),
    )

    with open(sample_csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )

    assert response.status_code == 502
    assert len(deleted_keys) == 1  # the already-written parquet object gets cleaned up


async def test_upload_returns_502_and_cleans_up_when_saving_metadata_fails(
    client, sample_csv_path, monkeypatch
):
    # Both R2 objects (parquet + raw CSV) are written successfully, but the
    # Supabase insert fails -- previously this was also entirely unhandled.
    deleted_keys = []
    monkeypatch.setattr(r2_client, "delete_object", lambda key: deleted_keys.append(key))
    monkeypatch.setattr(
        repository,
        "create_dataset",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Supabase unreachable")),
    )

    with open(sample_csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )

    assert response.status_code == 502
    assert len(deleted_keys) == 2  # both the parquet and raw CSV objects get cleaned up
