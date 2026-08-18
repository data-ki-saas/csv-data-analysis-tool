import json

import pytest

from src.datasets.insights import build_prompt, generate_insights


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return self._response


def _chart_context(**overrides):
    base = {
        "title": "Plan distribution",
        "chart_type": "pie",
        "partition_type": "categorical",
        "column": "plan",
        "result": {"columns": ["category", "count"], "rows": [["basic", 40], ["pro", 8], ["enterprise", 2]]},
    }
    return {**base, **overrides}


def test_build_prompt_includes_chart_details_and_data():
    prompt = build_prompt(_chart_context())
    assert "Plan distribution" in prompt
    assert "categorical" in prompt
    assert "basic" in prompt
    assert "40" in prompt


async def test_generate_insights_parses_valid_response():
    bullets = ["Basic plan dominates at 80% of users (40 of 50).", "Enterprise adoption is minimal at 4%."]
    provider = FakeProvider(json.dumps(bullets))

    result = await generate_insights(_chart_context(), provider)

    assert result == bullets
    assert provider.calls[0]["max_tokens"] == 512


async def test_generate_insights_truncates_to_max_five():
    bullets = [f"Bullet {i}" for i in range(8)]
    provider = FakeProvider(json.dumps(bullets))
    result = await generate_insights(_chart_context(), provider)
    assert len(result) == 5
    assert result == bullets[:5]


async def test_generate_insights_drops_blank_and_non_string_entries():
    provider = FakeProvider(json.dumps(["Real bullet", "   ", 42, None, "Another real one"]))
    result = await generate_insights(_chart_context(), provider)
    assert result == ["Real bullet", "Another real one"]


async def test_generate_insights_raises_when_response_is_not_a_list():
    provider = FakeProvider(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError, match="JSON array"):
        await generate_insights(_chart_context(), provider)


async def test_generate_insights_raises_on_non_json_response():
    provider = FakeProvider("not json")
    with pytest.raises(json.JSONDecodeError):
        await generate_insights(_chart_context(), provider)


async def test_insights_endpoint_returns_generated_bullets(client, sample_csv_path, monkeypatch):
    from src.datasets import service

    with open(sample_csv_path, "rb") as f:
        upload = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
    dataset_id = upload.json()["dataset_id"]

    bullets = ["Alice, Bob, and Carol each appear once — no repeats.", "Amounts range from 5 to 20.25."]
    monkeypatch.setattr(service, "get_llm_provider", lambda: FakeProvider(json.dumps(bullets)))

    response = await client.post(
        f"/api/datasets/{dataset_id}/insights",
        json={
            "title": "Amount by name",
            "chart_type": "bar",
            "partition_type": "categorical",
            "column": "name",
            "result": {"columns": ["name", "amount"], "rows": [["alice", 10.5]], "row_count": 1, "truncated": False},
        },
    )
    assert response.status_code == 200
    assert response.json() == {"insights": bullets}


async def test_insights_endpoint_returns_502_when_provider_fails(client, sample_csv_path, monkeypatch):
    from src.datasets import service

    class RaisingProvider:
        async def complete(self, prompt, *, system=None, max_tokens=1024):
            raise RuntimeError("provider unreachable")

    with open(sample_csv_path, "rb") as f:
        upload = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
    dataset_id = upload.json()["dataset_id"]

    monkeypatch.setattr(service, "get_llm_provider", lambda: RaisingProvider())

    response = await client.post(
        f"/api/datasets/{dataset_id}/insights",
        json={
            "title": "Amount by name",
            "chart_type": "bar",
            "partition_type": "categorical",
            "column": "name",
            "result": {"columns": ["name"], "rows": [], "row_count": 0, "truncated": False},
        },
    )
    assert response.status_code == 502


async def test_insights_endpoint_for_unknown_dataset_returns_404(client):
    response = await client.post(
        "/api/datasets/does-not-exist/insights",
        json={
            "title": "X",
            "chart_type": "bar",
            "partition_type": "categorical",
            "column": "x",
            "result": {"columns": [], "rows": [], "row_count": 0, "truncated": False},
        },
    )
    assert response.status_code == 404


async def test_insights_endpoint_serves_cache_for_identical_chart_view_without_llm_call(
    client, sample_csv_path, monkeypatch
):
    from src.datasets import service

    with open(sample_csv_path, "rb") as f:
        upload = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
    dataset_id = upload.json()["dataset_id"]

    provider = FakeProvider(json.dumps(["Same view, same insight."]))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    body = {
        "title": "Amount by name",
        "chart_type": "bar",
        "partition_type": "categorical",
        "column": "name",
        "result": {"columns": ["name", "amount"], "rows": [["alice", 10.5]], "row_count": 1, "truncated": False},
    }

    first = await client.post(f"/api/datasets/{dataset_id}/insights", json=body)
    second = await client.post(f"/api/datasets/{dataset_id}/insights", json=body)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()
    assert len(provider.calls) == 1  # the second call never touched the LLM


async def test_insights_endpoint_recomputes_for_same_column_different_result_data(
    client, sample_csv_path, monkeypatch
):
    from src.datasets import service

    with open(sample_csv_path, "rb") as f:
        upload = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
    dataset_id = upload.json()["dataset_id"]

    provider = FakeProvider(json.dumps(["An insight."]))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    def body(rows):
        return {
            "title": "Amount by name",
            "chart_type": "bar",
            "partition_type": "categorical",
            "column": "name",
            "result": {"columns": ["name", "amount"], "rows": rows, "row_count": len(rows), "truncated": False},
        }

    # Same column/chart_type/partition_type, but different aggregated data --
    # simulating the same chart viewed under a different filter/bin state.
    await client.post(f"/api/datasets/{dataset_id}/insights", json=body([["alice", 10.5]]))
    await client.post(f"/api/datasets/{dataset_id}/insights", json=body([["bob", 20.25]]))

    assert len(provider.calls) == 2  # two distinct chart views, no false cache hit


async def test_insights_cache_scoped_per_dataset(client, sample_csv_path, monkeypatch):
    from src.datasets import service

    dataset_ids = []
    for _ in range(2):
        with open(sample_csv_path, "rb") as f:
            upload = await client.post("/api/datasets/upload", files={"file": ("sample.csv", f, "text/csv")})
        dataset_ids.append(upload.json()["dataset_id"])

    provider = FakeProvider(json.dumps(["An insight."]))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    body = {
        "title": "Amount by name",
        "chart_type": "bar",
        "partition_type": "categorical",
        "column": "name",
        "result": {"columns": ["name", "amount"], "rows": [["alice", 10.5]], "row_count": 1, "truncated": False},
    }

    # Identical request body, but against two different datasets -- must not
    # collide even though the cache_key portion of the lookup is identical.
    await client.post(f"/api/datasets/{dataset_ids[0]}/insights", json=body)
    await client.post(f"/api/datasets/{dataset_ids[1]}/insights", json=body)

    assert len(provider.calls) == 2
