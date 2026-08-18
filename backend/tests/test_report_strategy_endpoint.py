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
    """A datetime column, a continuous-numerical column, a low-cardinality
    categorical column, and a free-text column -- one of each partition type
    the strategy engine reasons about, plus the one it must exclude."""
    path = tmp_path / "mixed.csv"
    lines = ["signup_date,age,plan,notes"]
    plans = ["basic", "pro", "enterprise"]
    for i in range(50):
        month = (i % 6) + 1
        day = (i % 27) + 1
        age = 20 + i
        plan = plans[i % 3]
        notes = f"Customer feedback entry number {i} with extra descriptive words for length."
        lines.append(f"2024-{month:02d}-{day:02d},{age},{plan},\"{notes}\"")
    path.write_text("\n".join(lines) + "\n")
    return path


async def _upload(client, csv_path):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": ("mixed.csv", f, "text/csv")})
    return response.json()["dataset_id"]


_VALID_RECOMMENDATIONS = [
    {
        "column": "plan",
        "partition_type": "categorical",
        "chart_type": "pie",
        "title": "Plan distribution",
        "rationale": "only 3 distinct values",
        "sql": 'SELECT "plan" AS category, count(*) AS count FROM data GROUP BY 1 ORDER BY 2 DESC',
    },
    {
        "column": "signup_date",
        "partition_type": "datetime",
        "chart_type": "line",
        "title": "Signups over time",
        "rationale": "time series trend",
        "sql": "SELECT date_trunc('month', \"signup_date\") AS period, count(*) AS count "
        "FROM data GROUP BY 1 ORDER BY 1",
    },
    {
        "column": "age",
        "partition_type": "numerical_bins",
        "chart_type": "bell_curve",
        "title": "Age distribution",
        "rationale": "clusters around a center",
        "sql": (
            'WITH stats AS (SELECT avg("age") AS mean, stddev("age") AS stddev, '
            'min("age") AS min_val, max("age") AS max_val FROM data), '
            'binned AS (SELECT LEAST(CAST(floor(("age" - stats.min_val) / '
            "NULLIF(stats.max_val - stats.min_val, 0) * 5) AS INTEGER), 4) AS bucket "
            'FROM data, stats WHERE "age" IS NOT NULL) '
            "SELECT binned.bucket, count(*) AS count, stats.mean, stats.stddev "
            "FROM binned CROSS JOIN stats GROUP BY binned.bucket, stats.mean, stats.stddev "
            "ORDER BY binned.bucket"
        ),
    },
]


async def test_report_strategy_executes_recommendations_and_orders_by_priority(
    client, mixed_csv_path, monkeypatch
):
    dataset_id = await _upload(client, mixed_csv_path)

    provider = FakeProvider(json.dumps(_VALID_RECOMMENDATIONS))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert response.status_code == 200
    body = response.json()

    assert body["dataset_id"] == dataset_id
    recs = body["recommendations"]
    assert len(recs) == 3
    # datetime first, then numerical_bins, then categorical -- regardless of
    # the order the (fake) model returned them in.
    assert [r["partition_type"] for r in recs] == ["datetime", "numerical_bins", "categorical"]

    by_column = {r["column"]: r for r in recs}
    assert by_column["plan"]["error"] is None
    assert by_column["plan"]["result"]["row_count"] == 3  # basic/pro/enterprise
    assert by_column["signup_date"]["result"]["row_count"] >= 1
    assert by_column["age"]["result"]["columns"] == ["bucket", "count", "mean", "stddev"]

    # free_text ("notes") never reaches the prompt at all
    assert "notes" not in provider.prompts[0]


async def test_report_strategy_flags_unsafe_sql_without_crashing(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)

    malicious = [
        {
            "column": "plan",
            "partition_type": "categorical",
            "chart_type": "pie",
            "title": "Malicious",
            "rationale": "n/a",
            "sql": "DROP TABLE data",
        }
    ]
    provider = FakeProvider(json.dumps(malicious))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert response.status_code == 200
    rec = response.json()["recommendations"][0]
    assert rec["result"] is None
    assert rec["error"] is not None


async def test_report_strategy_flags_syntactically_broken_sql(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)

    broken = [
        {
            "column": "plan",
            "partition_type": "categorical",
            "chart_type": "pie",
            "title": "Broken",
            "rationale": "n/a",
            "sql": 'SELECT "plan" AS FROM GROUP BY nonsense(',
        }
    ]
    provider = FakeProvider(json.dumps(broken))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert response.status_code == 200
    rec = response.json()["recommendations"][0]
    assert rec["result"] is None
    assert rec["error"] is not None


async def test_report_strategy_returns_502_when_provider_fails(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)

    class RaisingProvider:
        async def complete(self, prompt, *, system=None, max_tokens=1024):
            raise RuntimeError("provider unreachable")

    monkeypatch.setattr(service, "get_llm_provider", lambda: RaisingProvider())

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert response.status_code == 502


async def test_report_strategy_for_unknown_dataset_returns_404(client):
    response = await client.post("/api/datasets/does-not-exist/report-strategy")
    assert response.status_code == 404


async def test_report_strategy_with_no_chartable_columns_returns_empty_list(
    client, tmp_path, monkeypatch, fake_datasets_table
):
    csv_path = tmp_path / "all_free_text.csv"
    rows = "\n".join(
        f"row{i},This is a fairly long free-form comment used only to pad average length past forty characters {i}."
        for i in range(10)
    )
    csv_path.write_text("id_text,comment\n" + rows + "\n")
    # both columns are unique long-ish text -> free_text, so nothing is chartable

    provider = FakeProvider("should never be called")
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    dataset_id = await _upload(client, csv_path)
    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert response.status_code == 200
    assert response.json()["recommendations"] == []
    assert provider.prompts == []
    # Persisted as [] (not left NULL) so this reliably reads as "generated,
    # nothing chartable" rather than a permanent cache-miss.
    assert fake_datasets_table.rows[dataset_id]["report_strategy"] == []


async def test_report_strategy_serves_cache_without_llm_or_sql_on_second_call(
    client, mixed_csv_path, monkeypatch
):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_VALID_RECOMMENDATIONS))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    first = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    second = await client.post(f"/api/datasets/{dataset_id}/report-strategy")

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["recommendations"] == second.json()["recommendations"]
    assert len(provider.prompts) == 1  # the second call never touched the LLM


async def test_report_strategy_force_bypasses_cache_and_recomputes(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_VALID_RECOMMENDATIONS))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    await client.post(f"/api/datasets/{dataset_id}/report-strategy")

    # Change what the (fake) model would return, then force a recompute.
    single_recommendation = [_VALID_RECOMMENDATIONS[0]]
    provider._response = json.dumps(single_recommendation)

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy", json={"force": True})
    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 1
    assert len(provider.prompts) == 2  # force made a second real LLM call


async def test_report_strategy_cache_invalidated_by_schema_update(client, mixed_csv_path, monkeypatch):
    dataset_id = await _upload(client, mixed_csv_path)
    provider = FakeProvider(json.dumps(_VALID_RECOMMENDATIONS))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert len(provider.prompts) == 1

    # A column category override invalidates the cached report-strategy,
    # since recommendations are derived from column categories.
    patch_response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/plan", json={"category": "free_text"}
    )
    assert patch_response.status_code == 200

    response = await client.post(f"/api/datasets/{dataset_id}/report-strategy")
    assert response.status_code == 200
    assert len(provider.prompts) == 2  # cache miss after invalidation -> LLM called again
