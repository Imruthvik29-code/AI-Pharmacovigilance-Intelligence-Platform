"""
Phase 15 LLM provider tests.

Unit tests for `app/services/llm_providers.py`'s two providers
(GeminiProvider, OpenRouterProvider). All HTTP calls are mocked via a
fake httpx.AsyncClient (mirrors the pattern already used in
tests/test_auth_api.py for the Supabase Auth proxy) -- no real network
calls are made, and no real API keys are required.

Phase 15 improvement additions: `complete()` now returns an
`LLMCompletion` (text + optional token usage) instead of a bare string --
existing success-path assertions were updated from `result == "..."` to
`result.text == "..."` accordingly. New tests cover: Gemini's single
retry on transient failures (429/500/502/503/504/timeout) and its
absence on non-transient failures (bad request, auth failure, malformed
response shape), token usage extraction from both providers when
present/absent, and that both providers' model names come from
configuration rather than being hardcoded.

Run with:  pytest backend/tests/test_llm_providers.py -v
"""
import httpx
import pytest

from app.core.config import get_settings
from app.services.llm_providers import GeminiProvider, LLMProviderError, OpenRouterProvider

settings = get_settings()


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or (str(json_data) if json_data is not None else "")

    def json(self):
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse | None = None, raise_error: Exception | None = None):
        self._response = response
        self._raise_error = raise_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if self._raise_error:
            raise self._raise_error
        return self._response


class _SequencedAsyncClient:
    """
    Returns a different canned response (or raises a different canned
    exception) on each successive `.post()` call, consumed in order --
    used only to simulate a transient-failure-then-(success|failure)
    sequence for the retry tests below. The SAME instance must be handed
    back by the monkeypatched `httpx.AsyncClient` factory across both of
    `GeminiProvider`'s attempts (each attempt constructs its own
    `httpx.AsyncClient(...)`), so `call_count` and the remaining steps
    are shared/consumed correctly across the retry.
    """

    def __init__(self, steps: list):
        self._steps = list(steps)
        self.call_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        self.call_count += 1
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture(autouse=True)
def _configure_keys(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-openrouter-key")


# ---------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_provider_success(monkeypatch):
    fake_data = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )

    provider = GeminiProvider()
    result = await provider.complete("some prompt", timeout_seconds=5.0)
    assert result.text == '{"ok": true}'


@pytest.mark.asyncio
async def test_gemini_provider_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    provider = GeminiProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_gemini_provider_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(_FakeResponse(500, text="server error")),
    )
    provider = GeminiProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_gemini_provider_network_error_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(raise_error=httpx.ConnectError("boom")),
    )
    provider = GeminiProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_gemini_provider_unexpected_shape_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(_FakeResponse(200, {"unexpected": True})),
    )
    provider = GeminiProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_gemini_provider_empty_text_raises(monkeypatch):
    fake_data = {"candidates": [{"content": {"parts": [{"text": "   "}]}}]}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )
    provider = GeminiProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


# ---------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openrouter_provider_success(monkeypatch):
    fake_data = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )

    provider = OpenRouterProvider()
    result = await provider.complete("some prompt", timeout_seconds=5.0)
    assert result.text == '{"ok": true}'


@pytest.mark.asyncio
async def test_openrouter_provider_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    provider = OpenRouterProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_openrouter_provider_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(_FakeResponse(429, text="rate limited")),
    )
    provider = OpenRouterProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_openrouter_provider_network_error_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(raise_error=httpx.ConnectTimeout("timed out")),
    )
    provider = OpenRouterProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_openrouter_provider_unexpected_shape_raises(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(_FakeResponse(200, {"unexpected": True})),
    )
    provider = OpenRouterProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_openrouter_provider_empty_text_raises(monkeypatch):
    fake_data = {"choices": [{"message": {"content": "  "}}]}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )
    provider = OpenRouterProvider()

    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)


# ---------------------------------------------------------------------
# GeminiProvider -- retry (Phase 15 improvement)
# ---------------------------------------------------------------------

_GEMINI_SUCCESS_DATA = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
@pytest.mark.asyncio
async def test_gemini_retries_once_on_transient_http_status_then_succeeds(monkeypatch, status_code):
    sequenced = _SequencedAsyncClient(
        [_FakeResponse(status_code, text="transient"), _FakeResponse(200, _GEMINI_SUCCESS_DATA)]
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    result = await provider.complete("prompt", timeout_seconds=5.0)

    assert result.text == '{"ok": true}'
    assert sequenced.call_count == 2


@pytest.mark.asyncio
async def test_gemini_retries_once_on_network_timeout_then_succeeds(monkeypatch):
    sequenced = _SequencedAsyncClient(
        [httpx.ReadTimeout("timed out"), _FakeResponse(200, _GEMINI_SUCCESS_DATA)]
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    result = await provider.complete("prompt", timeout_seconds=5.0)

    assert result.text == '{"ok": true}'
    assert sequenced.call_count == 2


@pytest.mark.asyncio
async def test_gemini_retries_exactly_once_not_repeatedly(monkeypatch):
    """Two consecutive transient failures must still result in exactly
    two calls (one retry), then a raised LLMProviderError -- never a
    second retry."""
    sequenced = _SequencedAsyncClient(
        [_FakeResponse(503, text="unavailable"), _FakeResponse(503, text="still unavailable")]
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)

    assert sequenced.call_count == 2


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
@pytest.mark.asyncio
async def test_gemini_does_not_retry_on_non_transient_http_status(monkeypatch, status_code):
    """Bad request / authentication / not-found failures must not be
    retried -- exactly one call."""
    sequenced = _SequencedAsyncClient([_FakeResponse(status_code, text="not transient")])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)

    assert sequenced.call_count == 1


@pytest.mark.asyncio
async def test_gemini_does_not_retry_on_non_timeout_network_error(monkeypatch):
    """A non-timeout network error (e.g. connection refused) is not in
    the retry list -- exactly one call."""
    sequenced = _SequencedAsyncClient([httpx.ConnectError("connection refused")])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)

    assert sequenced.call_count == 1


@pytest.mark.asyncio
async def test_gemini_does_not_retry_on_malformed_response_shape(monkeypatch):
    """An unexpected/malformed response shape (missing candidates, etc.)
    is not a transient failure -- exactly one call, no retry."""
    sequenced = _SequencedAsyncClient([_FakeResponse(200, {"unexpected": True})])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)

    assert sequenced.call_count == 1


@pytest.mark.asyncio
async def test_gemini_does_not_retry_on_missing_api_key(monkeypatch):
    """A missing API key fails before any HTTP call is even attempted --
    confirms this isn't mistakenly treated as a retryable failure."""
    monkeypatch.setattr(settings, "gemini_api_key", "")
    sequenced = _SequencedAsyncClient([_FakeResponse(200, _GEMINI_SUCCESS_DATA)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = GeminiProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)

    assert sequenced.call_count == 0


@pytest.mark.asyncio
async def test_openrouter_never_retries_on_transient_status(monkeypatch):
    """Retry is a Gemini-only behavior -- OpenRouter must make exactly
    one attempt even for a status code that would be retryable on Gemini."""
    sequenced = _SequencedAsyncClient([_FakeResponse(503, text="unavailable")])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: sequenced)

    provider = OpenRouterProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete("prompt", timeout_seconds=5.0)

    assert sequenced.call_count == 1


# ---------------------------------------------------------------------
# Token usage extraction (Phase 15 improvement)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_provider_extracts_token_usage_when_present(monkeypatch):
    fake_data = {
        "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 40,
            "totalTokenCount": 160,
        },
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )

    provider = GeminiProvider()
    result = await provider.complete("prompt", timeout_seconds=5.0)

    assert result.prompt_tokens == 120
    assert result.completion_tokens == 40
    assert result.total_tokens == 160


@pytest.mark.asyncio
async def test_gemini_provider_omits_token_usage_when_absent(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, _GEMINI_SUCCESS_DATA))
    )

    provider = GeminiProvider()
    result = await provider.complete("prompt", timeout_seconds=5.0)

    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.total_tokens is None


@pytest.mark.asyncio
async def test_openrouter_provider_extracts_token_usage_when_present(monkeypatch):
    fake_data = {
        "choices": [{"message": {"content": '{"ok": true}'}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 60, "total_tokens": 260},
    }
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )

    provider = OpenRouterProvider()
    result = await provider.complete("prompt", timeout_seconds=5.0)

    assert result.prompt_tokens == 200
    assert result.completion_tokens == 60
    assert result.total_tokens == 260


@pytest.mark.asyncio
async def test_openrouter_provider_omits_token_usage_when_absent(monkeypatch):
    fake_data = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(_FakeResponse(200, fake_data))
    )

    provider = OpenRouterProvider()
    result = await provider.complete("prompt", timeout_seconds=5.0)

    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.total_tokens is None


# ---------------------------------------------------------------------
# Configuration-driven model selection (Phase 15 improvement)
# ---------------------------------------------------------------------


def test_gemini_provider_model_reads_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "gemini-custom-test-model")
    provider = GeminiProvider()
    assert provider.model == "gemini-custom-test-model"


def test_openrouter_provider_model_reads_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_model", "some/other-model:free")
    provider = OpenRouterProvider()
    assert provider.model == "some/other-model:free"


@pytest.mark.asyncio
async def test_gemini_provider_request_url_uses_configured_model(monkeypatch):
    """Confirms the configured model name is what actually goes into the
    outbound request URL -- not just readable via the `model` property,
    but the value the request is actually built with."""
    monkeypatch.setattr(settings, "gemini_model", "gemini-custom-test-model")
    captured_urls: list[str] = []

    class _UrlCapturingClient(_FakeAsyncClient):
        async def post(self, url, *args, **kwargs):
            captured_urls.append(url)
            return await super().post(url, *args, **kwargs)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _UrlCapturingClient(_FakeResponse(200, _GEMINI_SUCCESS_DATA)),
    )

    provider = GeminiProvider()
    await provider.complete("prompt", timeout_seconds=5.0)

    assert "gemini-custom-test-model" in captured_urls[0]
