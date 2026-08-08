"""
LLM provider abstraction (Phase 15).

Defines a single, provider-agnostic interface (`LLMProvider.complete`) that
`llm_service.py` calls without knowing whether it's talking to Gemini or
OpenRouter. Both providers are called over plain REST via `httpx` (already
a project dependency, used elsewhere in `api/v1/auth.py` for the Supabase
Auth proxy) -- no new dependency added, no provider SDK, per the approved
Phase 15 design.

Per spec section 4, Gemini is primary and OpenRouter is fallback; the
actual Gemini-then-OpenRouter ordering/fallback logic lives in
`llm_service.py`, not here -- this module only knows how to make a single
call to a single provider and turn it into raw text or a normalized
error. It has no knowledge of prompts, JSON schemas, or fallback
ordering, keeping it a thin, swappable I/O boundary.

Every failure (network error, timeout, non-2xx response, unexpected
response shape, empty body, missing configuration) is normalized to
`LLMProviderError` so callers never need to catch httpx-specific
exceptions or reach into either provider's raw response shape.
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.llm_providers")
settings = get_settings()


class LLMProviderError(Exception):
    """Raised when a single provider call fails for any reason (missing
    configuration, network error, timeout, non-2xx response, empty or
    unexpected response shape)."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"{provider}: {message}")


class LLMProvider:
    """Base class for a single LLM provider. Subclasses implement `complete`."""

    name: str = "base"

    async def complete(self, prompt: str, *, timeout_seconds: float) -> str:
        """Send `prompt` to the provider and return its raw text response.

        Raises `LLMProviderError` on any failure. Never returns partial
        or fabricated content -- an empty/missing response is itself a
        failure, not a valid (if unhelpful) result.
        """
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    """
    Calls Gemini's REST `generateContent` endpoint directly via httpx.

    Requests JSON-only output via `generationConfig.response_mime_type`
    -- a hint to the model, not a guarantee; `llm_service.py`'s response
    parsing still validates the result defensively regardless.
    """

    name = "gemini"

    async def complete(self, prompt: str, *, timeout_seconds: float) -> str:
        if not settings.gemini_api_key:
            raise LLMProviderError(self.name, "GEMINI_API_KEY is not configured.")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise LLMProviderError(self.name, f"request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMProviderError(
                self.name, f"HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMProviderError(self.name, f"unexpected response shape: {exc}") from exc

        if not text or not text.strip():
            raise LLMProviderError(self.name, "empty response text.")

        return text


class OpenRouterProvider(LLMProvider):
    """
    Calls OpenRouter's OpenAI-compatible `/chat/completions` endpoint via
    httpx. Requests JSON-object output via `response_format`; not every
    fallback-tier model on OpenRouter honors this reliably, so
    `llm_service.py`'s parsing still validates the result defensively
    regardless.
    """

    name = "openrouter"

    async def complete(self, prompt: str, *, timeout_seconds: float) -> str:
        if not settings.openrouter_api_key:
            raise LLMProviderError(self.name, "OPENROUTER_API_KEY is not configured.")

        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": settings.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.openrouter_api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise LLMProviderError(self.name, f"request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMProviderError(
                self.name, f"HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMProviderError(self.name, f"unexpected response shape: {exc}") from exc

        if not text or not text.strip():
            raise LLMProviderError(self.name, "empty response text.")

        return text
