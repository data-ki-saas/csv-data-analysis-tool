import json

import pytest

from scripts.generate_seo import build_prompt, generate_metadata, render_snippet


class FakeProvider:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return self._response


def test_build_prompt_includes_route_description_and_keywords():
    prompt = build_prompt("/pricing", "Pricing page", ["pricing", "plans"])
    assert "/pricing" in prompt
    assert "Pricing page" in prompt
    assert "pricing, plans" in prompt


async def test_generate_metadata_parses_model_response():
    provider = FakeProvider(
        json.dumps(
            {
                "title": "Pricing",
                "description": "See plans and pricing.",
                "keywords": ["pricing", "plans"],
            }
        )
    )

    result = await generate_metadata("/pricing", "Pricing page", ["pricing"], provider)

    assert result == {
        "title": "Pricing",
        "description": "See plans and pricing.",
        "keywords": ["pricing", "plans"],
    }
    assert "/pricing" in provider.calls[0]["prompt"]
    assert provider.calls[0]["max_tokens"] == 512


async def test_generate_metadata_raises_on_non_json_response():
    provider = FakeProvider("not valid json")
    with pytest.raises(json.JSONDecodeError):
        await generate_metadata("/pricing", "Pricing page", [], provider)


def test_render_snippet_produces_pastable_metadata_object():
    snippet = render_snippet(
        {"title": "Pricing", "description": "See plans.", "keywords": ["pricing"]}
    )
    assert 'title: "Pricing"' in snippet
    assert 'description: "See plans."' in snippet
    assert 'keywords: ["pricing"]' in snippet
    assert snippet.startswith("export const metadata: Metadata = {")
