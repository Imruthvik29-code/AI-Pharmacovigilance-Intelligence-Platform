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
call to a single provider and turn it into a normalized result or error.
It has no knowledge of prompts, JSON schemas, or fallback ordering,
keeping it a thin, swappable I/O boundary.

Every failure (network error, timeout, non-2xx response, unexpected
response shape, empty body, missing configuration) is normalized to
`LLMProviderError` so callers never need to catch httpx-specific
exceptions or reach into either provider's raw response shape.

## `complete()` return shape

`complete()` returns an `LLMCompletion` (raw text + optional token usage),
not a bare string. This is deliberate rather than storing per-call
metadata as instance state on the provider: `_PROVIDERS` (see
`llm_service.py`) holds a single long-lived instance of each provider
class shared across all requests, so any per-call data written onto
`self` would be a race condition under concurrent requests. Returning an
immutable value keeps each call's data local to that call.

## Retry (Gemini only)

`GeminiProvider.complete()` retries exactly once, and only for transient
failures -- HTTP 429/500/502/503/504 or a network timeout
(`httpx.TimeoutException`). Every other failure (missing/invalid API key,
a non-transient 4xx, a malformed/unexpected response shape) is raised
immediately with no retry. This is tracked via `LLMProviderError.retryable`,
set at the point each error is raised so the retry decision never has to
pattern-match an error message. `OpenRouterProvider` never retries --
retrying only the primary provider, once, before the existing
Gemini -> OpenRouter fallback in `llm_service.py` takes over, is the
approved Phase 15 design.
"""
import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.llm_providers")
settings = get_settings()

# HTTP status codes considered transient for Gemini's single retry.
# Deliberately narrow: a 4xx outside this set (bad request, auth failure,
# not found, ...) is a request/config problem retrying can't fix.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class LLMCompletion:
    """
    A single successful provider call: the raw response text plus token
    usage, when the provider's response included it.

    `prompt_tokens`/`completion_tokens`/`total_tokens` are `None` when a
    provider's response doesn't report usage (varies by provider/model,
    especially on OpenRouter's free tier) -- callers must handle `None`
    gracefully rather than assuming usage is always available.
    """

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMProviderError(Exception):
    """Raised when a single provider call fails for any reason (missing
    configuration, network error, timeout, non-2xx response, empty or
    unexpected response shape).

    `retryable` marks whether this specific failure is a transient one
    `GeminiProvider` should retry once before giving up (see module
    docstring) -- `False` by default, since most failure modes (bad
    config, malformed response, non-transient HTTP status) are not worth
    retrying.
    """

    def __init__(self, provider: str, message: str, *, retryable: bool = False):
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"{provider}: {message}")


class LLMProvider:
    """Base class for a single LLM provider. Subclasses implement `complete`."""

    name: str = "base"

    @property
    def model(self) -> str:
        """Model name this provider is currently configured to use, read
        fresh from settings -- never hardcoded. Used for logging."""
        raise NotImplementedError

    async def complete(self, prompt: str, *, timeout_seconds: float) -> LLMCompletion:
        """Send `prompt` to the provider and return its response.

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

    Retries once on a transient failure -- see module docstring's "Retry"
    section. `complete()` only decides whether to retry; `_request_once`
    does the actual HTTP call and never retries itself.
    """

    name = "gemini"

    @property
    def model(self) -> str:
        return settings.gemini_model

    async def complete(self, prompt: str, *, timeout_seconds: float) -> LLMCompletion:
        if not settings.gemini_api_key:
            raise LLMProviderError(self.name, "GEMINI_API_KEY is not configured.")

        try:
            return await self._request_once(prompt, timeout_seconds)
        except LLMProviderError as exc:
            if not exc.retryable:
                raise
            logger.warning(
                "Gemini call failed with a transient error, retrying once: %s", exc
            )
            # Second and final attempt. Whatever this produces (success or
            # failure) is returned/raised as-is -- no further retries.
            return await self._request_once(prompt, timeout_seconds)

    async def _request_once(self, prompt: str, timeout_seconds: float) -> LLMCompletion:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
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
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                self.name, f"request timed out: {exc}", retryable=True
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(self.name, f"request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMProviderError(
                self.name,
                f"HTTP {resp.status_code}: {resp.text[:500]}",
                retryable=resp.status_code in _RETRYABLE_STATUS_CODES,
            )

        try:
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMProviderError(self.name, f"unexpected response shape: {exc}") from exc

        if not text or not text.strip():
            raise LLMProviderError(self.name, "empty response text.")

        # usageMetadata is best-effort -- absent on some Gemini responses;
        # .get() throughout so a missing/partial block never raises here.
        usage = data.get("usageMetadata") or {}
        return LLMCompletion(
            text=text,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            total_tokens=usage.get("totalTokenCount"),
        )


class OpenRouterProvider(LLMProvider):
    """
    Calls OpenRouter's OpenAI-compatible `/chat/completions` endpoint via
    httpx. Requests JSON-object output via `response_format`; not every
    fallback-tier model on OpenRouter honors this reliably, so
    `llm_service.py`'s parsing still validates the result defensively
    regardless.

    No retry here -- only Gemini (the primary provider) retries once
    before falling back; OpenRouter is already the fallback, so a single
    attempt is the approved behavior (see module docstring).
    """

    name = "openrouter"

    @property
    def model(self) -> str:
        return settings.openrouter_model

    async def complete(self, prompt: str, *, timeout_seconds: float) -> LLMCompletion:
        if not settings.openrouter_api_key:
            raise LLMProviderError(self.name, "OPENROUTER_API_KEY is not configured.")

        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": self.model,
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

        # usage is best-effort -- some OpenRouter models/free-tier
        # responses omit it; .get() throughout so that never raises here.
        usage = data.get("usage") or {}
        return LLMCompletion(
            text=text,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
