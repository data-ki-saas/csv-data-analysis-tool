import json

import pytest

from src.datasets import service


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return self._response


@pytest.fixture
def mixed_csv_path(tmp_path):
    path = tmp_path / "mixed.csv"
    lines = ["city,annual_income"]
    cities = ["Austin", "Denver", "Seattle"]
    for i in range(30):
        lines.append(f"{cities[i % 3]},{40000 + i * 1000}")
    path.write_text("\n".join(lines) + "\n")
    return path


async def _upload(client, csv_path):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": ("mixed.csv", f, "text/csv")})
    return response.json()["dataset_id"]


_CUSTOM_CHART = {
    "column": "city",
    "partition_type": "categorical",
    "chart_type": "bar",
    "title": "Average income by city",
    "rationale": "user requested a city-wise breakdown",
    "sql": 'SELECT "city" AS category, avg("annual_income") AS value FROM data '
    'WHERE "city" IS NOT NULL GROUP BY 1 ORDER BY 2 DESC',
}


async def test_add_custom_chart_appends_to_existing_report(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom",
        json={"prompt": "show me distribution of annual income city wise"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Average income by city"
    assert body["column"] == "city"
    assert body["error"] is None
    assert body["result"]["row_count"] == 3
    assert body["id"]  # server-assigned

    # Persisted -- a follow-up "generate" call (cache hit) sees it too.
    followup = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert len(followup.json()["recommendations"]) == 1
    assert followup.json()["recommendations"][0]["id"] == body["id"]


async def test_add_custom_chart_appends_without_clobbering_existing_charts(
    client, mixed_csv_path, monkeypatch
):
    dataset_id = await _upload(client, mixed_csv_path)
    auto_recommendation = [
        {
            "column": "city",
            "partition_type": "categorical",
            "chart_type": "pie",
            "title": "City distribution",
            "rationale": "n/a",
            "sql": 'SELECT "city" AS category, count(*) AS count FROM data GROUP BY 1 ORDER BY 2 DESC',
        }
    ]
    provider = FakeProvider(json.dumps(auto_recommendation))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    await client.post(f"/api/datasets/{dataset_id}/report-strategy")

    provider._response = json.dumps(_CUSTOM_CHART)
    response = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom",
        json={"prompt": "average income by city"},
    )
    assert response.status_code == 200

    followup = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert len(followup.json()["recommendations"]) == 2


async def test_add_custom_chart_with_unusable_model_response_is_a_502(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps({"column": "does-not-exist", "sql": "SELECT 1"}))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "anything"}
    )
    assert response.status_code == 502


async def test_add_custom_chart_flags_unsafe_sql_without_crashing(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    malicious = {**_CUSTOM_CHART, "sql": "DROP TABLE data"}
    provider = FakeProvider(json.dumps(malicious))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "anything"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] is None
    assert body["error"] is not None


async def test_delete_chart_removes_it_and_leaves_the_rest(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    first = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"}
    )
    second = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "b"}
    )
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    response = await client.delete(f"/api/datasets/{dataset_id}/report-strategy/{first_id}")

    assert response.status_code == 200
    remaining_ids = [r["id"] for r in response.json()["recommendations"]]
    assert remaining_ids == [second_id]


async def test_delete_unknown_chart_id_404s(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    await client.post(f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"})

    response = await client.delete(f"/api/datasets/{dataset_id}/report-strategy/not-a-real-id")

    assert response.status_code == 404


async def test_reorder_charts_persists_new_order(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    first = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"}
    )
    second = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "b"}
    )
    first_id, second_id = first.json()["id"], second.json()["id"]

    response = await client.put(
        f"/api/datasets/{dataset_id}/report-strategy/order",
        json={"chart_ids": [second_id, first_id]},
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["recommendations"]] == [second_id, first_id]

    # Reload -- the new order is actually persisted, not just echoed back.
    followup = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert [r["id"] for r in followup.json()["recommendations"]] == [second_id, first_id]


async def test_reorder_charts_with_mismatched_ids_is_rejected(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    await client.post(f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"})

    response = await client.put(
        f"/api/datasets/{dataset_id}/report-strategy/order",
        json={"chart_ids": ["not-a-real-id"]},
    )

    assert response.status_code == 400


async def test_regenerate_report_preserves_custom_charts(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    auto_recommendation = [
        {
            "column": "city",
            "partition_type": "categorical",
            "chart_type": "pie",
            "title": "City distribution",
            "rationale": "n/a",
            "sql": 'SELECT "city" AS category, count(*) AS count FROM data GROUP BY 1 ORDER BY 2 DESC',
        }
    ]
    provider = FakeProvider(json.dumps(auto_recommendation))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    await client.post(f"/api/datasets/{dataset_id}/report-strategy")

    provider._response = json.dumps(_CUSTOM_CHART)
    custom = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "average income by city"}
    )
    custom_id = custom.json()["id"]

    # "Regenerate report" (force=True) recomputes the auto set but must not
    # drop the custom chart the user added on top of it.
    provider._response = json.dumps(auto_recommendation)
    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy", json={"force": True})

    assert response.status_code == 200
    recs = response.json()["recommendations"]
    assert len(recs) == 2
    sources = {r["id"]: r["source"] for r in recs}
    assert sources[custom_id] == "custom"
    assert sum(1 for s in sources.values() if s == "auto") == 1


async def test_update_chart_edits_title_and_rationale(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    created = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"}
    )
    chart_id = created.json()["id"]

    response = await client.patch(
        f"/api/datasets/{dataset_id}/report-strategy/{chart_id}",
        json={"title": "Income by City", "rationale": "Requested by the analyst"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Income by City"
    assert body["rationale"] == "Requested by the analyst"
    assert body["sql"] == _CUSTOM_CHART["sql"]  # editing the label never touches the query

    # Persisted -- survives a reload.
    followup = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert followup.json()["recommendations"][0]["title"] == "Income by City"


async def test_update_chart_blank_title_is_rejected(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    created = await client.post(
        f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"}
    )
    chart_id = created.json()["id"]

    response = await client.patch(
        f"/api/datasets/{dataset_id}/report-strategy/{chart_id}", json={"title": "   "}
    )

    assert response.status_code == 422


async def test_update_chart_unknown_id_404s(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_CUSTOM_CHART))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    await client.post(f"/api/datasets/{dataset_id}/report-strategy/custom", json={"prompt": "a"})

    response = await client.patch(
        f"/api/datasets/{dataset_id}/report-strategy/not-a-real-id", json={"title": "New title"}
    )

    assert response.status_code == 404


async def test_old_cached_recommendation_without_id_is_backfilled_on_load(
    client, mixed_csv_path, fake_datasets_table
):
    dataset_id = await _upload(client, mixed_csv_path)
    # Simulate a report_strategy cached before ChartRecommendation gained `id`.
    fake_datasets_table.rows[dataset_id]["report_strategy"] = [
        {
            "column": "city",
            "partition_type": "categorical",
            "chart_type": "pie",
            "title": "City distribution",
            "rationale": "n/a",
            "sql": 'SELECT "city" AS category, count(*) AS count FROM data GROUP BY 1',
            "result": None,
            "error": None,
        }
    ]

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")

    assert response.status_code == 200
    rec = response.json()["recommendations"][0]
    assert rec["id"]
    # The backfilled id is persisted, not regenerated on every read.
    assert fake_datasets_table.rows[dataset_id]["report_strategy"][0]["id"] == rec["id"]
