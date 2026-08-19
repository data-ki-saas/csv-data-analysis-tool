import json

import pytest

from src.datasets import service


class FakeMergeProvider:
    def __init__(self, response: str):
        self._response = response

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        return self._response


class ExplodingProvider:
    """Asserts the LLM is never reached -- used to prove a literal `replace`
    command is parsed deterministically (see value_merge.parse_replace_command)."""

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        raise AssertionError("LLM should not be called for a literal replace command")


@pytest.fixture
def cities_csv_path(tmp_path):
    # "city": 6 distinct values across 150 rows (ratio 0.04, well under the
    # categorical threshold) -- including one containing "/" (Delhi / NCR),
    # deliberately, to exercise the query-param revert routing fix.
    # "amount": 150 distinct floats, a genuinely continuous column, used to
    # test the categorical/text-like restriction. "notes": unique long text
    # per row, classified free_text.
    cities = (
        ["NY"] * 20
        + ["New York"] * 20
        + ["New York City"] * 20
        + ["Delhi / NCR"] * 30
        + ["Delhi"] * 30
        + ["Mumbai"] * 30
    )
    lines = ["id,city,amount,notes"]
    for i, city in enumerate(cities, start=1):
        amount = round(i * 1.37, 2)
        note = f"This is a unique note number {i} used only once in this dataset for testing purposes here."
        lines.append(f"{i},{city},{amount},{note}")
    path = tmp_path / "cities.csv"
    path.write_text("\n".join(lines) + "\n")
    return path


async def _upload(client, csv_path, filename="cities.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": (filename, f, "text/csv")})
    assert response.status_code == 200
    return response.json()["dataset_id"]


async def _column_category(client, dataset_id, column_name):
    response = await client.get(f"/api/datasets/{dataset_id}/schema")
    return next(c for c in response.json()["columns"] if c["name"] == column_name)["category"]


async def test_dataset_classifies_columns_as_expected(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    assert await _column_category(client, dataset_id, "city") == "categorical"
    assert await _column_category(client, dataset_id, "amount") == "continuous_numerical"
    assert await _column_category(client, dataset_id, "notes") == "free_text"


async def test_get_column_values_returns_categorical_counts(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/city/values")
    assert response.status_code == 200
    body = response.json()
    assert body["distinct_count"] == 6
    counts = {v["value"]: v["count"] for v in body["values"]}
    assert counts == {
        "NY": 20,
        "New York": 20,
        "New York City": 20,
        "Delhi / NCR": 30,
        "Delhi": 30,
        "Mumbai": 30,
    }
    assert body["rules"] == []
    assert body["replacements"] == []


async def test_get_column_values_limit_paginates_and_reports_the_true_total(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    response = await client.get(
        f"/api/datasets/{dataset_id}/schema/columns/city/values", params={"limit": 2}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["values"]) == 2
    # distinct_count is the true, uncapped total -- unaffected by `limit` --
    # so the dialog's "Load more" can tell there's more beyond this page.
    assert body["distinct_count"] == 6


async def test_get_column_values_rejects_continuous_column(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/amount/values")
    assert response.status_code == 400


async def test_get_column_values_allows_free_text_column(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    response = await client.get(f"/api/datasets/{dataset_id}/schema/columns/notes/values")
    assert response.status_code == 200


async def test_merge_suggest_and_accept_reduces_distinct_count(client, cities_csv_path, monkeypatch):
    dataset_id = await _upload(client, cities_csv_path)
    provider = FakeMergeProvider(
        json.dumps({"groups": [{"target": "New York", "sources": ["NY", "New York City"]}]})
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    suggest_resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/suggest",
        json={"command": "merge NY and New York City into New York"},
    )
    assert suggest_resp.status_code == 200
    suggestion = suggest_resp.json()
    assert suggestion["kind"] == "merge"
    assert suggestion["groups"][0]["target"] == "New York"
    assert set(suggestion["groups"][0]["sources"]) == {"NY", "New York City"}
    assert suggestion["preview_distinct_count"] == 4  # New York, Delhi / NCR, Delhi, Mumbai

    accept_resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/accept",
        json={"groups": suggestion["groups"]},
    )
    assert accept_resp.status_code == 200
    accepted = accept_resp.json()
    assert accepted["rows_updated"] == 40  # 20 NY + 20 New York City moved
    assert accepted["distinct_count"] == 4
    rule = next(r for r in accepted["rules"] if r["target"] == "New York")
    assert set(rule["sources"]) == {"NY", "New York City"}
    assert rule["rows_affected"] == 40

    values_resp = await client.get(f"/api/datasets/{dataset_id}/schema/columns/city/values")
    counts = {v["value"]: v["count"] for v in values_resp.json()["values"]}
    assert counts["New York"] == 60  # 20 original "New York" + 20 NY + 20 New York City
    assert "NY" not in counts
    assert "New York City" not in counts


async def test_merge_suggest_rejected_for_free_text_column(client, cities_csv_path, monkeypatch):
    dataset_id = await _upload(client, cities_csv_path)
    monkeypatch.setattr(service, "get_llm_provider", lambda: ExplodingProvider())
    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/notes/merge/suggest",
        json={"command": "merge similar notes together"},
    )
    assert resp.status_code == 400


async def test_revert_merge_fully_restores_original_values(client, cities_csv_path, monkeypatch):
    dataset_id = await _upload(client, cities_csv_path)
    provider = FakeMergeProvider(
        json.dumps({"groups": [{"target": "New York", "sources": ["NY", "New York City"]}]})
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    suggest_resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/suggest", json={"command": "merge"}
    )
    groups = suggest_resp.json()["groups"]
    await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/accept", json={"groups": groups}
    )

    revert_resp = await client.delete(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge", params={"target": "New York"}
    )
    assert revert_resp.status_code == 200
    body = revert_resp.json()
    assert body["distinct_count"] == 6
    assert body["rules"] == []
    counts = {v["value"]: v["count"] for v in body["values"]}
    # exactly the original counts -- nothing was ever rewritten in storage,
    # so removing the rule is a full, exact restoration, not an approximation.
    assert counts == {
        "NY": 20,
        "New York": 20,
        "New York City": 20,
        "Delhi / NCR": 30,
        "Delhi": 30,
        "Mumbai": 30,
    }


async def test_replace_command_is_parsed_without_calling_the_llm(client, cities_csv_path, monkeypatch):
    dataset_id = await _upload(client, cities_csv_path)
    monkeypatch.setattr(service, "get_llm_provider", lambda: ExplodingProvider())

    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/suggest",
        json={"command": "Replace 'Delhi / NCR' with 'Delhi'"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "replace"
    assert body["replacement"]["find"] == "Delhi / NCR"
    assert body["replacement"]["replace"] == "Delhi"
    assert body["preview_distinct_count"] == 5  # Delhi / NCR folded into Delhi


async def test_regex_replace_command_is_parsed_without_calling_the_llm(client, cities_csv_path, monkeypatch):
    dataset_id = await _upload(client, cities_csv_path)
    monkeypatch.setattr(service, "get_llm_provider", lambda: ExplodingProvider())

    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/suggest",
        json={"command": "Replace regex 'New York.*' with 'New York'"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "replace"
    assert body["replacement"]["find"] == "New York.*"
    assert body["replacement"]["is_regex"] is True
    assert body["preview_distinct_count"] == 5  # NY, New York (folded), Delhi / NCR, Delhi, Mumbai


async def test_regex_replace_command_rejects_an_invalid_pattern(client, cities_csv_path, monkeypatch):
    dataset_id = await _upload(client, cities_csv_path)
    monkeypatch.setattr(service, "get_llm_provider", lambda: ExplodingProvider())

    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge/suggest",
        json={"command": "Replace regex '(unclosed' with 'X'"},
    )
    assert resp.status_code == 400


async def test_regex_replace_accept_only_counts_rows_that_actually_change(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    # "New York.*" also matches the value "New York" itself (zero-width `.*`),
    # but replacing it with "New York" is a no-op for those rows -- only the
    # 20 "New York City" rows should count as actually updated.
    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/replace/accept",
        json={"find": "New York.*", "replace": "New York", "is_regex": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_updated"] == 20
    assert body["replacements"][0]["is_regex"] is True

    values_resp = await client.get(f"/api/datasets/{dataset_id}/schema/columns/city/values")
    counts = {v["value"]: v["count"] for v in values_resp.json()["values"]}
    assert counts["New York"] == 40  # original 20 "New York" + 20 folded "New York City"
    assert "New York City" not in counts


async def test_replace_accept_and_revert_with_slash_in_find(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)

    accept_resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/city/replace/accept",
        json={"find": "Delhi / NCR", "replace": "Delhi"},
    )
    assert accept_resp.status_code == 200
    accepted = accept_resp.json()
    assert accepted["rows_updated"] == 30
    assert accepted["distinct_count"] == 5
    replacement = accepted["replacements"][0]
    assert replacement == {
        "find": "Delhi / NCR",
        "replace": "Delhi",
        "is_regex": False,
        "rows_affected": 30,
    }

    values_resp = await client.get(f"/api/datasets/{dataset_id}/schema/columns/city/values")
    counts = {v["value"]: v["count"] for v in values_resp.json()["values"]}
    assert counts["Delhi"] == 60
    assert "Delhi / NCR" not in counts

    # The revert route takes `find` as a query param specifically so a value
    # containing "/" (as this one deliberately does) still routes correctly.
    revert_resp = await client.delete(
        f"/api/datasets/{dataset_id}/schema/columns/city/replace", params={"find": "Delhi / NCR"}
    )
    assert revert_resp.status_code == 200
    body = revert_resp.json()
    assert body["distinct_count"] == 6
    assert body["replacements"] == []
    counts = {v["value"]: v["count"] for v in body["values"]}
    assert counts["Delhi / NCR"] == 30
    assert counts["Delhi"] == 30


async def test_replace_works_on_free_text_column(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/notes/replace/accept",
        json={"find": "unique note", "replace": "special note"},
    )
    assert resp.status_code == 200
    assert resp.json()["rows_updated"] == 150


async def test_replace_rejected_for_continuous_column(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    resp = await client.post(
        f"/api/datasets/{dataset_id}/schema/columns/amount/replace/accept",
        json={"find": "1", "replace": "one"},
    )
    assert resp.status_code == 400


async def test_revert_replace_for_unknown_find_returns_404(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    resp = await client.delete(
        f"/api/datasets/{dataset_id}/schema/columns/city/replace", params={"find": "does not exist"}
    )
    assert resp.status_code == 404


async def test_revert_merge_for_unknown_target_returns_404(client, cities_csv_path):
    dataset_id = await _upload(client, cities_csv_path)
    resp = await client.delete(
        f"/api/datasets/{dataset_id}/schema/columns/city/merge", params={"target": "does not exist"}
    )
    assert resp.status_code == 404
