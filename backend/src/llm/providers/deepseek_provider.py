import httpx

from src.llm.providers.base import LLMProvider

# DeepSeek's API is OpenAI-chat-completions-compatible, so no vendor SDK is
# needed — a plain HTTP POST is enough. https://api-docs.deepseek.com
_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    async def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=60) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "messages": messages, "max_tokens": max_tokens},
            )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
