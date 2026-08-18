from httpx import ASGITransport, AsyncClient

from src.core.auth import CurrentUser, get_current_user

_ANOTHER_USER = CurrentUser(id="another-test-user-id", email="other@example.com")

_CHART_PAYLOAD = {
    "title": "Plan distribution",
    "chart_type": "pie",
    "partition_type": "categorical",
    "column": "plan",
    "result": {"columns": ["category", "count"], "rows": [["basic", 3]], "row_count": 1, "truncated": False},
}


def _new_app():
    from src.main import create_app

    return create_app()


async def _upload(client, csv_path):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
    return response.json()["dataset_id"]


async def test_create_share_returns_token_and_snapshot(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)

    response = await client.post(f"/api/datasets/{dataset_id}/shares", json=_CHART_PAYLOAD)
    assert response.status_code == 200
    body = response.json()

    assert body["token"]
    assert body["title"] == _CHART_PAYLOAD["title"]
    assert body["chart_type"] == _CHART_PAYLOAD["chart_type"]
    assert body["partition_type"] == _CHART_PAYLOAD["partition_type"]
    assert body["column"] == _CHART_PAYLOAD["column"]
    assert body["result"]["rows"] == _CHART_PAYLOAD["result"]["rows"]


async def test_get_public_share_by_token_requires_no_auth(sample_csv_path):
    # No dependency override at all here -- a real unauthenticated request.
    app = _new_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="owner", email="owner@example.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner_client:
        dataset_id = await _upload(owner_client, sample_csv_path)
        created = await owner_client.post(f"/api/datasets/{dataset_id}/shares", json=_CHART_PAYLOAD)
        token = created.json()["token"]

    del app.dependency_overrides[get_current_user]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon_client:
        response = await anon_client.get(f"/api/shares/{token}")

    assert response.status_code == 200
    assert response.json()["token"] == token


async def test_get_share_for_unknown_token_returns_404(client):
    response = await client.get("/api/shares/does-not-exist")
    assert response.status_code == 404


async def test_revoke_share_makes_it_unreachable(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)
    created = await client.post(f"/api/datasets/{dataset_id}/shares", json=_CHART_PAYLOAD)
    token = created.json()["token"]

    assert (await client.get(f"/api/shares/{token}")).status_code == 200

    revoke_response = await client.delete(f"/api/datasets/{dataset_id}/shares/{token}")
    assert revoke_response.status_code == 204

    assert (await client.get(f"/api/shares/{token}")).status_code == 404


async def test_create_share_for_unknown_dataset_returns_404(client):
    response = await client.post("/api/datasets/does-not-exist/shares", json=_CHART_PAYLOAD)
    assert response.status_code == 404


async def test_another_owner_cannot_create_or_revoke_shares_for_a_dataset_they_dont_own(
    sample_csv_path,
):
    app = _new_app()

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="owner-a", email="a@example.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner_client:
        dataset_id = await _upload(owner_client, sample_csv_path)
        created = await owner_client.post(f"/api/datasets/{dataset_id}/shares", json=_CHART_PAYLOAD)
        token = created.json()["token"]

    app.dependency_overrides[get_current_user] = lambda: _ANOTHER_USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other_client:
        create_response = await other_client.post(f"/api/datasets/{dataset_id}/shares", json=_CHART_PAYLOAD)
        revoke_response = await other_client.delete(f"/api/datasets/{dataset_id}/shares/{token}")

    assert create_response.status_code == 404
    assert revoke_response.status_code == 404

    # The original owner's share is untouched by the other user's failed revoke attempt.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as check_client:
        assert (await check_client.get(f"/api/shares/{token}")).status_code == 200
