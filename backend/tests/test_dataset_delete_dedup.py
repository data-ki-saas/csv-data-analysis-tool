from src.storage import r2_client


async def _upload(client, csv_path, filename="dup.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload", files={"file": (filename, f, "text/csv")}
        )
    return response


async def test_deleting_one_of_two_deduped_datasets_keeps_shared_storage(
    client, sample_csv_path, monkeypatch
):
    deleted_keys = []
    monkeypatch.setattr(r2_client, "delete_object", lambda key: deleted_keys.append(key))

    first = await _upload(client, sample_csv_path, "first.csv")
    second = await _upload(client, sample_csv_path, "second.csv")

    delete_response = await client.delete(f"/api/datasets/{first.json()['dataset_id']}")
    assert delete_response.status_code == 204
    assert deleted_keys == []  # the second dataset still references this storage

    # The survivor is unaffected -- its schema/query endpoints still work.
    schema_response = await client.get(f"/api/datasets/{second.json()['dataset_id']}/schema")
    assert schema_response.status_code == 200
    assert schema_response.json()["row_count"] == second.json()["row_count"]


async def test_deleting_last_dataset_referencing_shared_storage_deletes_it(
    client, sample_csv_path, monkeypatch
):
    deleted_keys = []
    monkeypatch.setattr(r2_client, "delete_object", lambda key: deleted_keys.append(key))

    first = await _upload(client, sample_csv_path, "first.csv")
    second = await _upload(client, sample_csv_path, "second.csv")

    await client.delete(f"/api/datasets/{first.json()['dataset_id']}")
    assert deleted_keys == []

    delete_response = await client.delete(f"/api/datasets/{second.json()['dataset_id']}")
    assert delete_response.status_code == 204
    # Now that no dataset row references this storage, both R2 objects (raw +
    # parquet) are cleaned up.
    assert len(deleted_keys) == 2


async def test_ordinary_delete_still_removes_its_own_storage(client, sample_csv_path, monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(r2_client, "delete_object", lambda key: deleted_keys.append(key))

    upload = await _upload(client, sample_csv_path, "solo.csv")

    delete_response = await client.delete(f"/api/datasets/{upload.json()['dataset_id']}")
    assert delete_response.status_code == 204
    assert len(deleted_keys) == 2  # raw_key + parquet_key, nothing shared to worry about
