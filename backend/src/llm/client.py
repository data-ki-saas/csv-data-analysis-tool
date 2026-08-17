from functools import lru_cache

from anthropic import Anthropic

from src.core.config import settings


@lru_cache
def get_anthropic_client() -> Anthropic:
    return Anthropic(api_key=settings.anthropic_api_key)
