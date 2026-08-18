import json

import pytest

from src.datasets.type_review import build_prompt, suggest_column_categories


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return self._response


def _column(**overrides):
    base = {
        "name": "zip_code",
        "type": "INTEGER",
        "category": "continuous_numerical",
        "distinct_count": 42,
        "null_percentage": 0.0,
        "samples": [10001, 90210, 60601],
    }
    return {**base, **overrides}


def test_build_prompt_includes_column_details():
    prompt = build_prompt([_column()])
    assert "zip_code" in prompt
    assert "continuous_numerical" in prompt
    assert "10001" in prompt


async def test_suggest_column_categories_parses_valid_response():
    provider = FakeProvider(
        json.dumps(
            {
                "zip_code": {
                    "category": "categorical",
                    "confidence": 92,
                    "rationale": "ZIP codes are location codes, not a measured quantity",
                }
            }
        )
    )

    result = await suggest_column_categories([_column()], provider)

    assert result == {
        "zip_code": {
            "category": "categorical",
            "confidence": 92.0,
            "rationale": "ZIP codes are location codes, not a measured quantity",
        }
    }
    assert provider.calls[0]["max_tokens"] == 1024


async def test_suggest_column_categories_skips_invalid_category():
    provider = FakeProvider(json.dumps({"zip_code": {"category": "not_a_real_category", "confidence": 90}}))
    result = await suggest_column_categories([_column()], provider)
    assert result == {}


async def test_suggest_column_categories_skips_missing_confidence():
    provider = FakeProvider(json.dumps({"zip_code": {"category": "categorical"}}))
    result = await suggest_column_categories([_column()], provider)
    assert result == {}


async def test_suggest_column_categories_ignores_unknown_column_keys():
    provider = FakeProvider(json.dumps({"some_other_column": {"category": "categorical", "confidence": 80}}))
    result = await suggest_column_categories([_column()], provider)
    assert result == {}


async def test_suggest_column_categories_raises_on_non_json_response():
    provider = FakeProvider("not json")
    with pytest.raises(json.JSONDecodeError):
        await suggest_column_categories([_column()], provider)


async def test_suggest_column_categories_with_no_columns_skips_the_call():
    provider = FakeProvider("should never be read")
    result = await suggest_column_categories([], provider)
    assert result == {}
    assert provider.calls == []
