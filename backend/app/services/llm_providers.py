"""REST provider adapters with sanitized structured errors and bounded retries.

Gemini accepts an explicit model per instance. Direct/legacy calls retain one
transient retry (including 429). The ordered production chain disables 429
retries, advances immediately and records model/project cooldowns instead.
Permanent credentials/configuration failures are never retried. Retry-After
sleeps must fit inside the candidate's total budget. OpenRouter never retries.
No raw HTTP error bodies, headers, prompts or completions enter error logs.
"""
import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.llm_providers")
settings = get_settings()
_sleep = asyncio.sleep

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

    def __init__(
        self, provider: str, message: str, *, retryable: bool = False,
        category: str = "provider_error", status_code: int | None = None,
        retry_after_seconds: float = 0.0, provider_wide: bool = False,
    ):
        self.provider = provider
        self.retryable = retryable
        self.category = category
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.provider_wide = provider_wide
        super().__init__(f"{provider}: {message}")


def _retry_after(response: httpx.Response) -> float:
    value = getattr(response, "headers", {}).get("Retry-After")
    if not value:
        return 0.0
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


def _project_quota(response: httpx.Response) -> bool:
    """Only explicit quota violations without a model dimension are shared.

    Unknown 429 scope is not proof of independent quotas. The orchestrator
    probes each eligible candidate at most once; all failures cool down.
    """
    try:
        details = response.json().get("error", {}).get("details", [])
        violations = [v for d in details for v in d.get("violations", [])]
        return bool(violations) and any(
            v.get("quotaMetric") and not v.get("quotaDimensions", {}).get("model")
            for v in violations
        )
    except (ValueError, TypeError, AttributeError):
        return False


def _http_failure(provider: str, response: httpx.Response) -> LLMProviderError:
    status = response.status_code
    category = ("rate_limit" if status == 429 else
                "authentication" if status in (401, 403) else
                "configuration" if status in (400, 404) else "http_error")
    return LLMProviderError(
        provider, f"HTTP {status}", category=category, status_code=status,
        retryable=status in _RETRYABLE_STATUS_CODES,
        retry_after_seconds=_retry_after(response),
        provider_wide=status in (401, 403) or (status == 429 and _project_quota(response)),
    )


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

    def __init__(self, model_id: str | None = None, *, retry_rate_limits: bool = True) -> None:
        self._model_id = model_id
        self._retry_rate_limits = retry_rate_limits

    @property
    def model(self) -> str:
        return self._model_id or settings.gemini_model

    async def complete(self, prompt: str, *, timeout_seconds: float) -> LLMCompletion:
        if not settings.gemini_api_key:
            raise LLMProviderError(
                self.name, "GEMINI_API_KEY is not configured.",
                category="configuration", provider_wide=True,
            )
        deadline = time.monotonic() + timeout_seconds
        try:
            return await self._request_once(prompt, timeout_seconds)
        except LLMProviderError as exc:
            if (not exc.retryable or exc.provider_wide
                    or (exc.category == "rate_limit" and not self._retry_rate_limits)):
                raise
            remaining = deadline - time.monotonic()
            delay = exc.retry_after_seconds
            if delay >= remaining:
                raise
            logger.warning("Gemini transient retry", extra={
                "provider_used": self.name, "model_used": self.model,
                "outcome": exc.category, "http_status": exc.status_code,
            })
            if delay:
                await _sleep(delay)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            return await self._request_once(prompt, remaining)

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
                self.name, "request timed out", retryable=True, category="timeout"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(self.name, "request failed", category="transport") from exc

        if resp.status_code >= 400:
            raise _http_failure(self.name, resp)

        try:
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMProviderError(self.name, "unexpected response shape", category="invalid_response") from exc

        if not isinstance(text, str) or not text.strip():
            raise LLMProviderError(self.name, "empty response text.", category="invalid_response")

        # usageMetadata is best-effort -- absent on some Gemini responses;
        # .get() throughout so a missing/partial block never raises here.
        usage = data.get("usageMetadata")
        if not isinstance(usage, dict):
            usage = {}
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
            raise LLMProviderError(self.name, "OPENROUTER_API_KEY is not configured.", category="configuration", provider_wide=True)

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
            raise LLMProviderError(self.name, "request failed", category="transport") from exc

        if resp.status_code >= 400:
            raise _http_failure(self.name, resp)

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMProviderError(self.name, "unexpected response shape", category="invalid_response") from exc

        if not isinstance(text, str) or not text.strip():
            raise LLMProviderError(self.name, "empty response text.", category="invalid_response")

        # usage is best-effort -- some OpenRouter models/free-tier
        # responses omit it; .get() throughout so that never raises here.
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return LLMCompletion(
            text=text,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
