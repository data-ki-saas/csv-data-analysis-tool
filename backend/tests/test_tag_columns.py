import pytest


@pytest.fixture
def location_csv_path(tmp_path):
    # "location": 6 distinct packed strings across 150 rows (ratio 0.04,
    # well under the categorical threshold) -- most of them holding more
    # than one city, and one holding a "Hybrid - " work-mode prefix ahead of
    # its city list (the compound case from the real request this feature
    # was built for).
    rows = (
        ["Mumbai, Pune"] * 30
        + ["Hyderabad, Gurugram, Bengaluru"] * 25
        + ["Hybrid - Pune, Noida, Bengaluru"] * 30
        + ["Chennai"] * 20
        + ["Delhi"] * 25
        + ["Gurugram"] * 20
    )
    lines = ["location,amount"]
    for i, location in enumerate(rows, start=1):
        lines.append(f'"{location}",{round(i * 1.37, 2)}')
    path = tmp_path / "location.csv"
    path.write_text("\n".join(lines) + "\n")
    return path


async def _upload(client, csv_path, filename="location.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": (filename, f, "text/csv")})
    assert response.status_code == 200
    return response.json()["dataset_id"]


async def test_multi_value_column_is_flagged_at_ingest(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema")
    column = next(c for c in response.json()["columns"] if c["name"] == "location")
    assert column["category"] == "categorical"
    assert column["multi_value_separator"] == ","


async def test_tag_candidates_without_prefix_config_show_raw_split_noise(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/location/tags")
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["tag_separator"] == ","
    assert body["config"]["prefix_separator"] is None
    assert body["config"]["vocabulary"] == []

    counts = {c["tag"]: c["count"] for c in body["candidates"]}
    # Without prefix stripping, the "Hybrid - " row splits into a bogus
    # "Hybrid - Pune" tag glued to the mode label, instead of a clean "Pune".
    assert counts["Hybrid - Pune"] == 30
    assert counts["Mumbai"] == 30
    assert counts["Chennai"] == 20


async def test_update_tag_config_with_prefix_separator_cleans_up_candidates(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/location/tags/config",
        json={"prefix_separator": "-", "tag_separator": ",", "vocabulary": [], "include_other": False},
    )
    assert response.status_code == 200
    counts = {c["tag"]: c["count"] for c in response.json()["candidates"]}

    assert "Hybrid - Pune" not in counts
    assert counts["Mumbai"] == 30
    assert counts["Pune"] == 60  # 30 from "Mumbai, Pune" + 30 from the Hybrid row
    assert counts["Hyderabad"] == 25
    assert counts["Gurugram"] == 45  # 25 from the 3-city row + 20 standalone
    assert counts["Bengaluru"] == 55  # 25 + 30
    assert counts["Noida"] == 30
    assert counts["Chennai"] == 20
    assert counts["Delhi"] == 25

    # Persisted -- a follow-up GET sees the same (not just echoed back once).
    followup = await client.get(f"/api/datasets/{dataset_id}/schema/columns/location/tags")
    assert followup.json()["config"]["prefix_separator"] == "-"


async def test_get_tag_candidates_rejects_non_categorical_column(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/amount/tags")
    assert response.status_code == 400


async def test_add_tag_chart_rejects_non_categorical_column(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.post(f"/api/datasets/{dataset_id}/schema/columns/amount/tags/chart")
    assert response.status_code == 400


async def test_add_tag_chart_with_curated_vocabulary_and_other_bucket(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/location/tags/config",
        json={
            "prefix_separator": "-",
            "tag_separator": ",",
            "vocabulary": ["Hyderabad", "Bengaluru", "Chennai", "Delhi", "Gurugram", "Pune"],
            "include_other": True,
        },
    )

    response = await client.post(f"/api/datasets/{dataset_id}/schema/columns/location/tags/chart")
    assert response.status_code == 200
    chart = response.json()
    assert chart["source"] == "custom"
    assert chart["partition_type"] == "categorical"
    assert chart["chart_type"] == "bar"
    assert chart["error"] is None

    counts = {row[0]: row[1] for row in chart["result"]["rows"]}
    assert counts["Hyderabad"] == 25
    assert counts["Bengaluru"] == 55
    assert counts["Chennai"] == 20
    assert counts["Delhi"] == 25
    assert counts["Gurugram"] == 45
    assert counts["Pune"] == 60
    assert counts["Other"] == 60  # Mumbai (30) + Noida (30), neither in the vocabulary
    assert "Mumbai" not in counts
    assert "Noida" not in counts

    # Persisted onto the dataset's report -- a follow-up cache-hit call sees it.
    followup = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert any(r["id"] == chart["id"] for r in followup.json()["recommendations"])


async def test_add_tag_chart_without_other_bucket_excludes_non_vocabulary_tags(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/location/tags/config",
        json={
            "prefix_separator": "-",
            "tag_separator": ",",
            "vocabulary": ["Hyderabad", "Bengaluru", "Chennai", "Delhi", "Gurugram", "Pune"],
            "include_other": False,
        },
    )

    response = await client.post(f"/api/datasets/{dataset_id}/schema/columns/location/tags/chart")
    assert response.status_code == 200
    counts = {row[0]: row[1] for row in response.json()["result"]["rows"]}
    assert "Other" not in counts
    assert "Mumbai" not in counts
    assert set(counts) == {"Hyderabad", "Bengaluru", "Chennai", "Delhi", "Gurugram", "Pune"}


async def test_add_tag_chart_uses_custom_title(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/location/tags/chart",
        json={"title": "Headcount by city"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Headcount by city"


async def test_add_tag_chart_defaults_to_alias_based_title(client, location_csv_path):
    dataset_id = await _upload(client, location_csv_path)
    response = await client.post(f"/api/datasets/{dataset_id}/schema/columns/location/tags/chart")
    assert response.status_code == 200
    assert "by tag" in response.json()["title"].lower()
