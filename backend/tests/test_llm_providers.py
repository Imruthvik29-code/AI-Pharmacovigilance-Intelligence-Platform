"""
Phase 15 LLM provider tests.

Unit tests for `app/services/llm_providers.py`'s two providers
(GeminiProvider, OpenRouterProvider). All HTTP calls are mocked via a
fake httpx.AsyncClient (mirrors the pattern already used in
tests/test_auth_api.py for the Supabase Auth proxy) -- no real network
calls are made, and no real API keys are required.

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
    assert result == '{"ok": true}'


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
    assert result == '{"ok": true}'


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
