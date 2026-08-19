import pytest


@pytest.fixture
def experience_csv_path(tmp_path):
    # "experience_raw": 150 rows of "min-max yrs" ranges (well under the
    # categorical threshold at 5 distinct buckets, ratio 0.033) -- the real
    # case this feature was built for. "department" is a filler categorical
    # column so the dataset isn't single-column.
    rows = (
        ["0-2 yrs"] * 30
        + ["2-4 yrs"] * 30
        + ["4-6 yrs"] * 30
        + ["6-10 yrs"] * 30
        + ["10-15 yrs"] * 30
    )
    lines = ["experience_raw,department,amount"]
    for i, exp in enumerate(rows, start=1):
        lines.append(f'"{exp}",Engineering,{round(i * 1.37, 2)}')
    path = tmp_path / "experience.csv"
    path.write_text("\n".join(lines) + "\n")
    return path


async def _upload(client, csv_path, filename="experience.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": (filename, f, "text/csv")})
    assert response.status_code == 200
    return response.json()["dataset_id"]


async def test_range_column_is_flagged_at_ingest(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema")
    column = next(c for c in response.json()["columns"] if c["name"] == "experience_raw")
    assert column["range_separator"] == "-"
    assert column["range_unit"] == "yrs"


async def test_schema_badge_reflects_manually_saved_range_config(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    # "department" never gets auto-flagged as a range column (it's a plain
    # categorical label, "Engineering") -- confirm that up front.
    before = await client.get(f"/api/datasets/{dataset_id}/schema")
    department_before = next(c for c in before.json()["columns"] if c["name"] == "department")
    assert department_before["range_separator"] is None

    # Manually configure it as a range anyway (e.g. a column auto-detection
    # missed) and confirm the schema response's badge fields pick it up --
    # not just the dedicated .../range endpoint, but GET .../schema too,
    # since that's what the Column Types page's badge actually reads.
    save = await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/department/range/config",
        json={"separator": "~", "unit": "u", "value_type": "midpoint"},
    )
    assert save.status_code == 200

    after = await client.get(f"/api/datasets/{dataset_id}/schema")
    department_after = next(c for c in after.json()["columns"] if c["name"] == "department")
    assert department_after["range_separator"] == "~"
    assert department_after["range_unit"] == "u"


async def test_schema_badge_reflects_updated_separator_over_detected_one(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    # experience_raw auto-detects as separator "-"/unit "yrs" -- saving a
    # config with different values should override what the badge shows,
    # not leave it stuck on the original ingest-time guess.
    await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range/config",
        json={"separator": "to", "unit": "years", "value_type": "midpoint"},
    )
    response = await client.get(f"/api/datasets/{dataset_id}/schema")
    column = next(c for c in response.json()["columns"] if c["name"] == "experience_raw")
    assert column["range_separator"] == "to"
    assert column["range_unit"] == "years"


async def test_get_range_preview_uses_detected_defaults(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range")
    assert response.status_code == 200
    body = response.json()
    assert body["config"] == {"separator": "-", "unit": "yrs", "value_type": "midpoint"}
    assert body["total_count"] == 150
    assert body["parsed_count"] == 150  # every row matches the detected format
    assert len(body["sample"]) > 0
    # Spot-check one parse: "0-2 yrs" -> midpoint 1.0
    row = next(r for r in body["sample"] if r["raw_value"] == "0-2 yrs")
    assert row["parsed_value"] == 1.0


async def test_update_range_config_switches_value_type(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range/config",
        json={"separator": "-", "unit": "yrs", "value_type": "max"},
    )
    assert response.status_code == 200
    body = response.json()
    row = next(r for r in body["sample"] if r["raw_value"] == "0-2 yrs")
    assert row["parsed_value"] == 2.0

    # Persisted -- a follow-up GET sees the same config, not just echoed once.
    followup = await client.get(f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range")
    assert followup.json()["config"]["value_type"] == "max"


async def test_update_range_config_reports_unparseable_rows(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    # A unit that doesn't actually appear in the data -- every row's TRY_CAST
    # still succeeds here since REPLACE with a no-op string is harmless, so
    # use a separator that doesn't match instead to prove parsed_count reacts.
    response = await client.put(
        f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range/config",
        json={"separator": "~", "unit": None, "value_type": "midpoint"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parsed_count"] == 0
    assert body["total_count"] == 150


async def test_add_range_chart_produces_histogram_with_min_max(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.post(f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range/chart")
    assert response.status_code == 200
    chart = response.json()
    assert chart["source"] == "custom"
    assert chart["partition_type"] == "numerical_bins"
    assert chart["chart_type"] == "histogram"
    assert chart["error"] is None
    assert chart["result"]["columns"] == ["bucket", "count", "min_val", "max_val"]

    total_rows = sum(row[1] for row in chart["result"]["rows"])
    assert total_rows == 150
    min_vals = {row[2] for row in chart["result"]["rows"]}
    max_vals = {row[3] for row in chart["result"]["rows"]}
    assert min_vals == {1.0}  # midpoint of "0-2 yrs"
    assert max_vals == {12.5}  # midpoint of "10-15 yrs"

    # Persisted onto the dataset's report -- a follow-up cache-hit call sees it.
    followup = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert any(r["id"] == chart["id"] for r in followup.json()["recommendations"])


async def test_add_range_chart_uses_custom_title(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/experience_raw/range/chart",
        json={"title": "Experience spread"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Experience spread"


async def test_range_endpoints_reject_continuous_column(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/amount/range")
    assert response.status_code == 400


async def test_range_endpoints_allow_ordinary_categorical_column(client, experience_csv_path):
    # A plain categorical column (no range shape) is still a valid target --
    # range editing is restricted to text-like columns in general, not to
    # ones profiling already flagged as range-shaped, since a user may want
    # to configure it manually even without auto-detection.
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/department/range")
    assert response.status_code == 200
    assert response.json()["parsed_count"] == 0  # "Engineering" doesn't match "N-N" at all


async def test_add_range_chart_rejects_continuous_column(client, experience_csv_path):
    dataset_id = await _upload(client, experience_csv_path)
    response = await client.post(f"/api/datasets/{dataset_id}/schema/columns/amount/range/chart")
    assert response.status_code == 400
