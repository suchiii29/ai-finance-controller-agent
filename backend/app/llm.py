"""Centralized LLM provider configuration.

Provides a single factory function that returns a LangChain chat model
configured for OpenRouter (primary) or graceful fallback when unavailable.
No module in the application should instantiate an LLM directly.
"""

from __future__ import annotations

import logging
import os
from time import perf_counter

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_cached_llm = None
_llm_available: bool | None = None


def get_llm(*, temperature: float = 0.1, timeout: int = 25):
    """Return a ready-to-use LangChain ChatModel.

    Uses OpenRouter (OpenAI-compatible) with the key from OPENROUTER_API_KEY.
    Falls back to None if no key is configured.
    """
    global _cached_llm, _llm_available

    if _cached_llm is not None:
        return _cached_llm

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENROUTER_API_KEY is not set — AI features disabled")
        _llm_available = False
        return None

    try:
        from langchain_openai import ChatOpenAI

        started = perf_counter()
        _cached_llm = ChatOpenAI(
            model="openrouter/auto",
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=temperature,
            request_timeout=timeout,
            max_tokens=1024,
            default_headers={
                "HTTP-Referer": "https://financeos.app",
                "X-Title": "FinanceOS AI Controller",
            },
        )
        _llm_available = True
        logger.info("LLM initialized in %.3fs (OpenRouter → Gemini Flash)", perf_counter() - started)
        return _cached_llm
    except Exception as exc:
        logger.error("LLM initialization failed: %s", exc)
        _llm_available = False
        return None


def is_llm_available() -> bool:
    """Check whether the LLM was successfully initialized."""
    if _llm_available is None:
        get_llm()
    return bool(_llm_available)


def reset_llm():
    """Reset the cached LLM instance (useful for testing)."""
    global _cached_llm, _llm_available
    _cached_llm = None
    _llm_available = None
