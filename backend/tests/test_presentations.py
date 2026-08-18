async def _upload(client, csv_path):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
    return response.json()["dataset_id"]


_CHART = {
    "id": "chart-1",
    "title": "Plan distribution",
    "chart_type": "pie",
    "partition_type": "categorical",
    "column": "plan",
    "result": {"columns": ["category", "count"], "rows": [["basic", 3]], "row_count": 1, "truncated": False},
}


async def test_get_presentation_returns_empty_default_when_unset(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/presentation")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] == dataset_id
    assert body["title"] == "Untitled Presentation"
    assert body["pages"] == []


async def test_get_presentation_for_unknown_dataset_returns_404(client):
    response = await client.get("/api/datasets/does-not-exist/presentation")
    assert response.status_code == 404


async def test_pin_block_creates_first_page(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)

    response = await client.post(f"/api/datasets/{dataset_id}/presentation/pin", json={"chart": _CHART})
    assert response.status_code == 200
    body = response.json()

    assert len(body["pages"]) == 1
    assert body["pages"][0]["title"] == "Page 1"
    assert len(body["pages"][0]["blocks"]) == 1
    assert body["pages"][0]["blocks"][0]["type"] == "chart"
    assert body["pages"][0]["blocks"][0]["id"] == "chart-1"


async def test_pin_block_with_insights_adds_both_blocks(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)

    response = await client.post(
        f"/api/datasets/{dataset_id}/presentation/pin",
        json={"chart": _CHART, "insights": ["Basic dominates at 60%.", "No enterprise signups yet."]},
    )
    assert response.status_code == 200
    blocks = response.json()["pages"][0]["blocks"]

    assert len(blocks) == 2
    assert blocks[0]["type"] == "chart"
    assert blocks[1]["type"] == "insights"
    assert blocks[1]["bullets"] == ["Basic dominates at 60%.", "No enterprise signups yet."]
    assert blocks[1]["chart_title"] == "Plan distribution"


async def test_pin_block_appends_to_last_existing_page(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)

    await client.post(f"/api/datasets/{dataset_id}/presentation/pin", json={"chart": _CHART})
    second_chart = {**_CHART, "id": "chart-2", "title": "Second chart"}
    response = await client.post(f"/api/datasets/{dataset_id}/presentation/pin", json={"chart": second_chart})

    body = response.json()
    assert len(body["pages"]) == 1  # still one page
    assert len(body["pages"][0]["blocks"]) == 2
    assert [b["id"] for b in body["pages"][0]["blocks"]] == ["chart-1", "chart-2"]


async def test_pin_block_for_unknown_dataset_returns_404(client):
    response = await client.post("/api/datasets/does-not-exist/presentation/pin", json={"chart": _CHART})
    assert response.status_code == 404


async def test_replace_presentation_persists_full_document(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)

    document = {
        "title": "Q1 Review",
        "pages": [
            {
                "id": "page-1",
                "title": "Overview",
                "blocks": [
                    {"type": "chart", **_CHART},
                    {"type": "text", "id": "note-1", "text": "Manually written context."},
                ],
            },
            {"id": "page-2", "title": "Appendix", "blocks": []},
        ],
    }

    response = await client.put(f"/api/datasets/{dataset_id}/presentation", json=document)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Q1 Review"
    assert [p["id"] for p in body["pages"]] == ["page-1", "page-2"]
    assert body["pages"][0]["blocks"][1]["type"] == "text"

    # a subsequent GET returns exactly what was saved
    follow_up = await client.get(f"/api/datasets/{dataset_id}/presentation")
    assert follow_up.json() == body


async def test_replace_presentation_rejects_unknown_block_type(client, sample_csv_path):
    dataset_id = await _upload(client, sample_csv_path)
    document = {
        "title": "Bad",
        "pages": [{"id": "page-1", "title": "P1", "blocks": [{"type": "video", "id": "x"}]}],
    }
    response = await client.put(f"/api/datasets/{dataset_id}/presentation", json=document)
    assert response.status_code == 422


async def test_replace_presentation_for_unknown_dataset_returns_404(client):
    response = await client.put(
        "/api/datasets/does-not-exist/presentation", json={"title": "X", "pages": []}
    )
    assert response.status_code == 404
