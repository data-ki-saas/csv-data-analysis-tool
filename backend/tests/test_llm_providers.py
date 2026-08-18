import json

import httpx
import pytest

from src.core.config import settings
from src.llm import client as llm_client
from src.llm.providers import deepseek_provider as deepseek_module
from src.llm.providers.anthropic_provider import AnthropicProvider
from src.llm.providers.deepseek_provider import DeepSeekProvider


@pytest.fixture(autouse=True)
def clear_provider_cache():
    llm_client.get_llm_provider.cache_clear()
    yield
    llm_client.get_llm_provider.cache_clear()


def test_get_llm_provider_returns_anthropic_by_default(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    assert isinstance(llm_client.get_llm_provider(), AnthropicProvider)


def test_get_llm_provider_returns_deepseek(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    assert isinstance(llm_client.get_llm_provider(), DeepSeekProvider)


def test_get_llm_provider_rejects_unknown(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "made-up")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        llm_client.get_llm_provider()


async def test_deepseek_provider_sends_expected_request_and_parses_response(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hello from deepseek"}}]}
        )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        deepseek_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(
            *args, **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    provider = DeepSeekProvider(api_key="test-key", model="deepseek-chat")
    result = await provider.complete("hi", system="be nice", max_tokens=42)

    assert result == "hello from deepseek"
    request = captured["request"]
    assert request.url.path == "/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-chat"
    assert body["max_tokens"] == 42
    assert body["messages"] == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
    ]


async def test_deepseek_provider_raises_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        deepseek_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(
            *args, **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    provider = DeepSeekProvider(api_key="bad-key", model="deepseek-chat")
    with pytest.raises(httpx.HTTPStatusError):
        await provider.complete("hi")


async def test_deepseek_provider_raises_a_clear_error_on_empty_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        deepseek_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(
            *args, **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    provider = DeepSeekProvider(api_key="test-key", model="deepseek-chat")
    with pytest.raises(ValueError, match="no content"):
        await provider.complete("hi")


class _FakeBlock:
    def __init__(self, type_: str, text: str | None = None):
        self.type = type_
        self.text = text


class _FakeAnthropicResponse:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, response: _FakeAnthropicResponse):
        self._response = response
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


async def test_anthropic_provider_extracts_text_blocks(monkeypatch):
    provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5")
    fake_messages = _FakeMessages(
        _FakeAnthropicResponse([_FakeBlock("text", "hello "), _FakeBlock("text", "world")])
    )
    monkeypatch.setattr(provider._client, "messages", fake_messages)

    result = await provider.complete("hi", system="be nice", max_tokens=42)

    assert result == "hello world"
    assert fake_messages.calls[0]["max_tokens"] == 42
    assert fake_messages.calls[0]["system"] == "be nice"


async def test_anthropic_provider_raises_a_clear_error_when_no_text_content(monkeypatch):
    # e.g. the response was cut off before any text block was produced --
    # previously this silently returned "" and every caller's json.loads()
    # failed instead with an opaque "Expecting value" error.
    provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5")
    fake_messages = _FakeMessages(
        _FakeAnthropicResponse([_FakeBlock("thinking", None)], stop_reason="max_tokens")
    )
    monkeypatch.setattr(provider._client, "messages", fake_messages)

    with pytest.raises(ValueError, match="max_tokens"):
        await provider.complete("hi")
