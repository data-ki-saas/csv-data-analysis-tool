import json

import pytest

from src.datasets import service


class FakeReviewProvider:
    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return self._response


class RaisingProvider:
    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        raise RuntimeError("provider unreachable")


@pytest.fixture
def boundary_csv_path(tmp_path):
    """50 rows engineered so exactly one column ("code", sitting right at the
    numeric categorical/continuous boundary) lands below the review-confidence
    threshold, while "row_num" (clearly continuous -- deliberately not named
    like an identifier, since that would itself route it through the
    identifier-name heuristic) and "label" (clearly categorical, all one
    value) stay confidently classified."""
    path = tmp_path / "boundary.csv"
    lines = ["row_num,code,label"]
    for i in range(1, 51):
        lines.append(f"{i},{(i % 20) + 1},constant")
    path.write_text("\n".join(lines) + "\n")
    return path


async def _upload(client, csv_path, filename="boundary.csv"):
    with open(csv_path, "rb") as f:
        response = await client.post("/api/datasets/upload", files={"file": (filename, f, "text/csv")})
    return response.json()["dataset_id"]


async def _schema(client, dataset_id):
    response = await client.get(f"/api/datasets/{dataset_id}/schema")
    assert response.status_code == 200
    return response.json()


async def test_only_the_boundary_column_is_flagged_for_review(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)
    body = await _schema(client, dataset_id)

    flagged = {c["name"] for c in body["columns"] if c["needs_review"]}
    assert flagged == {"code"}


async def test_review_without_explicit_columns_only_touches_flagged_ones(
    client, boundary_csv_path, monkeypatch
):
    dataset_id = await _upload(client, boundary_csv_path)

    provider = FakeReviewProvider(
        json.dumps({"code": {"category": "categorical", "confidence": 95, "rationale": "small fixed set"}})
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(f"/api/datasets/{dataset_id}/schema/review")
    assert response.status_code == 200
    columns = {c["name"]: c for c in response.json()["columns"]}

    assert columns["code"]["category_source"] == "ai"
    assert columns["code"]["confidence"] == 95.0
    assert columns["code"]["needs_review"] is False
    assert columns["code"]["rationale"] == "small fixed set"
    # untouched columns keep their rule-based classification
    assert columns["row_num"]["category_source"] == "rule"
    assert columns["label"]["category_source"] == "rule"
    assert "code" in provider.prompts[0]
    assert "row_num" not in provider.prompts[0]  # only the flagged column went into the prompt


async def test_review_with_explicit_columns_targets_exactly_those(
    client, boundary_csv_path, monkeypatch
):
    dataset_id = await _upload(client, boundary_csv_path)

    provider = FakeReviewProvider(
        json.dumps(
            {"row_num": {"category": "categorical", "confidence": 88, "rationale": "actually a code"}}
        )
    )
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(
        f"/api/datasets/{dataset_id}/schema/review", json={"columns": ["row_num"]}
    )
    assert response.status_code == 200
    columns = {c["name"]: c for c in response.json()["columns"]}

    assert columns["row_num"]["category_source"] == "ai"
    assert columns["row_num"]["category"] == "categorical"
    # "code" wasn't named, so it's left alone even though it's flagged
    assert columns["code"]["category_source"] == "rule"


async def test_review_leaves_partially_unmatched_suggestions_unchanged(
    client, boundary_csv_path, monkeypatch
):
    dataset_id = await _upload(client, boundary_csv_path)

    # model returns a bogus category for the only flagged column
    provider = FakeReviewProvider(json.dumps({"code": {"category": "not_real", "confidence": 90}}))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(f"/api/datasets/{dataset_id}/schema/review")
    assert response.status_code == 200
    columns = {c["name"]: c for c in response.json()["columns"]}
    assert columns["code"]["category_source"] == "rule"  # unchanged


async def test_review_skips_columns_already_confirmed_by_a_user(
    client, boundary_csv_path, monkeypatch, fake_datasets_table
):
    dataset_id = await _upload(client, boundary_csv_path)

    # Force an inconsistent-but-possible state directly: a user-confirmed
    # column that (hypothetically) still needs review. The default review
    # pass must never touch it even so -- a human decision always wins.
    row = fake_datasets_table.rows[dataset_id]
    for col in row["schema"]:
        if col["name"] == "code":
            col["category_source"] = "user"
            col["needs_review"] = True

    provider = FakeReviewProvider(json.dumps({"code": {"category": "free_text", "confidence": 90}}))
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)

    response = await client.post(f"/api/datasets/{dataset_id}/schema/review")
    assert response.status_code == 200
    columns = {c["name"]: c for c in response.json()["columns"]}
    assert columns["code"]["category_source"] == "user"
    assert columns["code"]["category"] == "categorical"  # untouched


async def test_review_returns_502_when_provider_fails(client, boundary_csv_path, monkeypatch):
    dataset_id = await _upload(client, boundary_csv_path)
    monkeypatch.setattr(service, "get_llm_provider", lambda: RaisingProvider())

    response = await client.post(f"/api/datasets/{dataset_id}/schema/review")
    assert response.status_code == 502


async def test_review_for_unknown_dataset_returns_404(client):
    response = await client.post("/api/datasets/does-not-exist/schema/review")
    assert response.status_code == 404


async def test_set_column_category_overrides_and_stops_flagging_it(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)

    response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/code", json={"category": "free_text"}
    )
    assert response.status_code == 200
    column = next(c for c in response.json()["columns"] if c["name"] == "code")
    assert column["category"] == "free_text"
    assert column["category_source"] == "user"
    assert column["confidence"] == 100.0
    assert column["needs_review"] is False
    assert column["rationale"] is None


async def test_set_column_category_rejects_invalid_category(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)
    response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/code", json={"category": "not_a_category"}
    )
    assert response.status_code == 422


async def test_set_column_category_for_unknown_column_returns_404(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)
    response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/does_not_exist", json={"category": "categorical"}
    )
    assert response.status_code == 404


async def test_set_column_category_for_unknown_dataset_returns_404(client):
    response = await client.patch(
        "/api/datasets/does-not-exist/schema/columns/code", json={"category": "categorical"}
    )
    assert response.status_code == 404


async def test_rename_column_alias_leaves_category_untouched(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)

    response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/code", json={"alias": "Promo Code"}
    )
    assert response.status_code == 200
    column = next(c for c in response.json()["columns"] if c["name"] == "code")
    assert column["alias"] == "Promo Code"
    assert column["category_source"] == "rule"  # untouched -- alias rename isn't a type override
    assert column["needs_review"] is True  # still whatever the rule-based pass said


async def test_update_column_can_set_alias_and_category_together(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)

    response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/code",
        json={"alias": "Promo Code", "category": "categorical"},
    )
    assert response.status_code == 200
    column = next(c for c in response.json()["columns"] if c["name"] == "code")
    assert column["alias"] == "Promo Code"
    assert column["category_source"] == "user"
    assert column["needs_review"] is False


async def test_update_column_rejects_empty_body(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)
    response = await client.patch(f"/api/datasets/{dataset_id}/schema/columns/code", json={})
    assert response.status_code == 422


async def test_update_column_rejects_blank_alias(client, boundary_csv_path):
    dataset_id = await _upload(client, boundary_csv_path)
    response = await client.patch(
        f"/api/datasets/{dataset_id}/schema/columns/code", json={"alias": "   "}
    )
    assert response.status_code == 422
