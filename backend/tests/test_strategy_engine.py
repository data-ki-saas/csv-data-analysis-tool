import json

import pytest

from src.datasets.strategy_engine import build_prompt, suggest_visual_strategy


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return self._response


def _columns():
    return [
        {
            "name": "signup_date",
            "alias": "Signup Date",
            "type": "DATE",
            "category": "datetime",
            "distinct_count": 40,
            "null_percentage": 0.0,
            "samples": ["2024-01-05"],
        },
        {
            "name": "age",
            "alias": "Age",
            "type": "BIGINT",
            "category": "continuous_numerical",
            "distinct_count": 35,
            "null_percentage": 0.0,
            "samples": [25, 31, 45],
        },
        {
            "name": "plan",
            "alias": "Plan",
            "type": "VARCHAR",
            "category": "categorical",
            "distinct_count": 3,
            "null_percentage": 0.0,
            "samples": ["basic", "pro"],
        },
    ]


def _recommendation(**overrides):
    base = {
        "column": "plan",
        "partition_type": "categorical",
        "chart_type": "pie",
        "title": "Plan distribution",
        "rationale": "few distinct values",
        "sql": 'SELECT "plan" AS category, count(*) AS count FROM data GROUP BY 1',
    }
    return {**base, **overrides}


def test_build_prompt_includes_all_column_details():
    prompt = build_prompt(_columns())
    assert "signup_date" in prompt
    assert "continuous_numerical" in prompt
    assert "basic" in prompt


async def test_suggest_visual_strategy_parses_valid_recommendations():
    provider = FakeProvider(json.dumps([_recommendation()]))
    result = await suggest_visual_strategy(_columns(), provider)
    assert result == [_recommendation()]
    assert provider.calls[0]["max_tokens"] == 4096


async def test_suggest_visual_strategy_enforces_datetime_numerical_categorical_order():
    # Deliberately returned out of order by the "model" -- the function must
    # still emit datetime, then numerical_bins, then categorical.
    out_of_order = [
        _recommendation(column="plan", partition_type="categorical", chart_type="pie"),
        _recommendation(
            column="signup_date",
            partition_type="datetime",
            chart_type="line",
            sql="SELECT date_trunc('month', \"signup_date\") AS period, count(*) FROM data GROUP BY 1",
        ),
        _recommendation(
            column="age",
            partition_type="numerical_bins",
            chart_type="bell_curve",
            sql='SELECT avg("age") FROM data',
        ),
    ]
    provider = FakeProvider(json.dumps(out_of_order))

    result = await suggest_visual_strategy(_columns(), provider)

    assert [r["partition_type"] for r in result] == ["datetime", "numerical_bins", "categorical"]


async def test_suggest_visual_strategy_drops_recommendation_for_unknown_column():
    provider = FakeProvider(json.dumps([_recommendation(column="not_a_real_column")]))
    result = await suggest_visual_strategy(_columns(), provider)
    assert result == []


async def test_suggest_visual_strategy_drops_invalid_partition_type():
    provider = FakeProvider(json.dumps([_recommendation(partition_type="something_else")]))
    result = await suggest_visual_strategy(_columns(), provider)
    assert result == []


async def test_suggest_visual_strategy_drops_invalid_chart_type():
    provider = FakeProvider(json.dumps([_recommendation(chart_type="pie_chart_3d")]))
    result = await suggest_visual_strategy(_columns(), provider)
    assert result == []


async def test_suggest_visual_strategy_drops_missing_sql():
    entry = _recommendation()
    del entry["sql"]
    provider = FakeProvider(json.dumps([entry]))
    result = await suggest_visual_strategy(_columns(), provider)
    assert result == []


async def test_suggest_visual_strategy_drops_blank_title():
    provider = FakeProvider(json.dumps([_recommendation(title="   ")]))
    result = await suggest_visual_strategy(_columns(), provider)
    assert result == []


async def test_suggest_visual_strategy_raises_when_response_is_not_a_list():
    provider = FakeProvider(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError, match="JSON array"):
        await suggest_visual_strategy(_columns(), provider)


async def test_suggest_visual_strategy_raises_on_non_json_response():
    provider = FakeProvider("not json")
    with pytest.raises(json.JSONDecodeError):
        await suggest_visual_strategy(_columns(), provider)


async def test_suggest_visual_strategy_with_no_columns_skips_the_call():
    provider = FakeProvider("should never be read")
    result = await suggest_visual_strategy([], provider)
    assert result == []
    assert provider.calls == []
