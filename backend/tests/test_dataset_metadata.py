from httpx import ASGITransport, AsyncClient

from src.core.auth import CurrentUser, get_current_user

_OTHER_USER = CurrentUser(id="another-test-user-id", email="other@example.com")


async def _upload(client, csv_path, filename="dataset.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post(
            "/api/datasets/upload", files={"file": (filename, f, "text/csv")}
        )
    return response


async def test_upload_defaults_name_to_filename_with_no_description_or_notes(client, sample_csv_path):
    response = await _upload(client, sample_csv_path, "sales.csv")
    body = response.json()
    assert body["name"] == "sales.csv"
    assert body["description"] is None
    assert body["notes"] is None


async def test_patch_renames_dataset(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]

    response = await client.patch(f"/api/datasets/{dataset_id}", json={"name": "Q1 Sales"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Q1 Sales"
    assert body["filename"] == "dataset.csv"  # filename is untouched by a rename


async def test_patch_sets_description(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]

    response = await client.patch(
        f"/api/datasets/{dataset_id}", json={"description": "Regional sales for Q1."}
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Regional sales for Q1."


async def test_patch_description_over_200_chars_is_rejected(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]

    response = await client.patch(f"/api/datasets/{dataset_id}", json={"description": "x" * 201})

    assert response.status_code == 422


async def test_patch_empty_description_clears_it(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]
    await client.patch(f"/api/datasets/{dataset_id}", json={"description": "temporary"})

    response = await client.patch(f"/api/datasets/{dataset_id}", json={"description": ""})

    assert response.status_code == 200
    assert response.json()["description"] is None


async def test_patch_notes_has_no_length_cap(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]
    long_notes = "Detailed analysis. " * 50  # ~1000 chars, well over description's 200 cap

    response = await client.patch(f"/api/datasets/{dataset_id}", json={"notes": long_notes})

    assert response.status_code == 200
    assert response.json()["notes"] == long_notes.strip()  # trailing whitespace is trimmed on save


async def test_patch_name_and_description_together(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]

    response = await client.patch(
        f"/api/datasets/{dataset_id}", json={"name": "Q1 Sales", "description": "Regional sales."}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Q1 Sales"
    assert body["description"] == "Regional sales."


async def test_patch_with_no_fields_is_rejected(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]

    response = await client.patch(f"/api/datasets/{dataset_id}", json={})

    assert response.status_code == 422


async def test_patch_blank_name_is_rejected(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]

    response = await client.patch(f"/api/datasets/{dataset_id}", json={"name": "   "})

    assert response.status_code == 422


async def test_patch_does_not_touch_omitted_fields(client, sample_csv_path):
    upload = await _upload(client, sample_csv_path)
    dataset_id = upload.json()["dataset_id"]
    await client.patch(f"/api/datasets/{dataset_id}", json={"description": "keep me"})

    response = await client.patch(f"/api/datasets/{dataset_id}", json={"name": "Renamed"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["description"] == "keep me"  # untouched by the name-only PATCH


async def test_patch_another_owners_dataset_404s(sample_csv_path):
    from src.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner_client:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id="owner-a", email="a@example.com"
        )
        upload = await _upload(owner_client, sample_csv_path)
        dataset_id = upload.json()["dataset_id"]

    app.dependency_overrides[get_current_user] = lambda: _OTHER_USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other_client:
        response = await other_client.patch(f"/api/datasets/{dataset_id}", json={"name": "Hijacked"})

    assert response.status_code == 404
