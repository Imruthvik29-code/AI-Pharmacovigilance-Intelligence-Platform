"""Synthetic ordered-chain, deadline, quota, concurrency and logging tests."""
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import llm_service, llm_providers
from app.services.llm_failover import CooldownRegistry
from app.services.llm_providers import GeminiProvider, LLMCompletion, LLMProviderError
from app.services.llm_service import LLMExplanationError
from backend.tests.test_llm_grounding import scenario, selection_for_prompt

MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


class Provider:
    def __init__(self, model, value="valid", name="gemini"):
        self.name, self.model, self.value = name, model, value
        self.calls = []

    async def complete(self, prompt, *, timeout_seconds):
        self.calls.append((prompt, timeout_seconds))
        if isinstance(self.value, Exception):
            raise self.value
        if callable(self.value):
            value = self.value(prompt)
            if hasattr(value, "__await__"):
                value = await value
        else:
            value = selection_for_prompt(prompt) if self.value == "valid" else self.value
        return LLMCompletion(value)


def failure(category="http_error", **kwargs):
    return LLMProviderError("gemini", "sensitive provider payload MUST NOT LOG",
                            category=category, **kwargs)


def install(monkeypatch, values):
    providers = [Provider(model, value) for model, value in zip(MODELS, values)]
    providers.append(Provider("openrouter/free", "valid", "openrouter"))
    monkeypatch.setattr(llm_service, "_PROVIDERS", tuple(providers))
    return providers


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(llm_service, "_COOLDOWNS", CooldownRegistry())


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", [0, 1, 2, 3])
async def test_order_first_valid_response_stops_chain(monkeypatch, winner):
    providers = install(monkeypatch, [failure() if i < winner else "valid" for i in range(3)])
    answer = await llm_service.generate_explanation(*scenario())
    assert answer.summary == "Recorded safety score: 95/100. Risk level: low."
    assert [len(p.calls) for p in providers] == [int(i <= winner) for i in range(4)]
    assert "cannot independently establish a cause" in answer.reasoning


@pytest.mark.asyncio
async def test_429_moves_immediately_to_secondary_and_cools_primary(monkeypatch):
    providers = install(monkeypatch, [failure("rate_limit", status_code=429), "valid", "valid"])
    await llm_service.generate_explanation(*scenario())
    await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [1, 2, 0, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", " ", "not JSON", "[]", None, 42])
async def test_malformed_empty_or_nontext_advances_without_retry(monkeypatch, bad):
    providers = install(monkeypatch, [bad, "valid", "valid"])
    answer = await llm_service.generate_explanation(*scenario())
    assert answer.summary.startswith("Recorded safety score")
    assert [len(p.calls) for p in providers] == [1, 1, 0, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["unknown", "scope", "coverage", "prose"])
async def test_rejected_evidence_advances_without_weakening_renderer(monkeypatch, tamper):
    def invalid(prompt):
        data = json.loads(selection_for_prompt(prompt))
        if tamper == "unknown": data["reasoning"].append("invented symptom")
        if tamper == "scope": data["scope"] = "another-analysis"
        if tamper == "coverage": data["reasoning"] = ["limits"]
        if tamper == "prose": data["summary"] = "This medicine caused the symptom."
        return json.dumps(data)
    providers = install(monkeypatch, [invalid, "valid", "valid"])
    answer = await llm_service.generate_explanation(*scenario())
    assert "invented symptom" not in answer.reasoning
    assert [len(p.calls) for p in providers] == [1, 1, 0, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["authentication", "configuration"])
async def test_shared_credentials_failure_skips_remaining_gemini_models(monkeypatch, category):
    providers = install(monkeypatch, [failure(category, provider_wide=True), "valid", "valid"])
    await llm_service.generate_explanation(*scenario())
    await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [1, 0, 0, 2]


@pytest.mark.asyncio
async def test_explicit_project_quota_suppresses_all_gemini_and_recovers(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(llm_service, "_COOLDOWNS", CooldownRegistry(lambda: now[0]))
    providers = install(monkeypatch, [failure("rate_limit", provider_wide=True,
                                            retry_after_seconds=120), "valid", "valid"])
    await llm_service.generate_explanation(*scenario())
    providers[0].value = "valid"
    now[0] = 119
    await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [1, 0, 0, 2]
    now[0] = 121
    await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [2, 0, 0, 2]


@pytest.mark.asyncio
async def test_repeated_validation_failures_cool_then_expiry_allows_recovery(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(llm_service, "_COOLDOWNS", CooldownRegistry(lambda: now[0]))
    providers = install(monkeypatch, ["invalid", "valid", "valid"])
    fixture = scenario()
    for _ in range(3):await llm_service.generate_explanation(*fixture)
    assert len(providers[0].calls) == 2
    providers[0].value = "valid"
    now[0] = 16
    await llm_service.generate_explanation(*fixture)
    assert len(providers[0].calls) == 3


@pytest.mark.asyncio
async def test_all_gemini_quota_failures_then_openrouter_without_quota_assumptions(monkeypatch):
    providers = install(monkeypatch, [failure("rate_limit") for _ in range(3)])
    for _ in range(2):await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [1, 1, 1, 2]


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_patient_explanations_or_probe_same_model(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    async def slow(prompt):
        entered.set(); await release.wait(); return selection_for_prompt(prompt)
    providers = install(monkeypatch, [slow, "valid", "valid"])
    first, second = scenario(), scenario()
    first = (replace(first[0], active_symptoms=[replace(first[0].active_symptoms[0],
                         description="Synthetic patient A symptom")]), *first[1:])
    second = (replace(second[0], active_symptoms=[replace(second[0].active_symptoms[0],
                         description="Synthetic patient B symptom")]), *second[1:])
    task = asyncio.create_task(llm_service.generate_explanation(*first))
    await entered.wait()
    b = await llm_service.generate_explanation(*second)
    release.set(); a = await task
    assert "patient A symptom" in a.reasoning and "patient B symptom" not in a.reasoning
    assert "patient B symptom" in b.reasoning and "patient A symptom" not in b.reasoning
    assert [len(p.calls) for p in providers] == [1, 1, 0, 0]


def test_registry_admission_is_atomic_across_threads():
    registry = CooldownRegistry()
    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(lambda _: registry.admit("gemini", MODELS[0]), range(24)))
    assert states.count(None) == 1 and states.count("in_flight") == 23


@pytest.mark.asyncio
async def test_deadline_bounds_all_attempts_and_reserves_time_for_fallback(monkeypatch):
    async def hang(prompt):await asyncio.sleep(100)
    providers = install(monkeypatch, [hang, hang, hang])
    monkeypatch.setattr(llm_service.settings, "llm_failover_deadline_seconds", 1.0)
    start = time.monotonic()
    answer = await llm_service.generate_explanation(*scenario())
    assert time.monotonic() - start < 2.0
    assert answer.summary.startswith("Recorded safety score")
    assert [len(p.calls) for p in providers] == [1, 1, 1, 1]


@pytest.mark.asyncio
async def test_cancellation_releases_model_admission(monkeypatch):
    entered = asyncio.Event()
    async def hang(prompt):entered.set();await asyncio.sleep(100)
    providers = install(monkeypatch, [hang, "valid", "valid"])
    task = asyncio.create_task(llm_service.generate_explanation(*scenario()))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    providers[0].value = "valid"
    await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [2, 0, 0, 0]


@pytest.mark.asyncio
async def test_all_failure_is_sanitized_and_no_response_or_prompt_logged(monkeypatch, caplog):
    providers = install(monkeypatch, [failure() for _ in range(3)])
    providers[-1].value = failure()
    with pytest.raises(LLMExplanationError) as raised:
        await llm_service.generate_explanation(*scenario())
    assert "sensitive provider payload" not in str(raised.value) + caplog.text
    assert "Synthetic symptom report" not in caplog.text
    records = [r for r in caplog.records if r.message == "LLM candidate failed; advancing"]
    assert [r.model_used for r in records] == MODELS + ["openrouter/free"]
    assert [r.next_model for r in records] == MODELS[1:] + ["openrouter/free", None]


@pytest.mark.parametrize("scope,expected", [("model", False), ("project", True), ("unknown", False)])
def test_structured_quota_scope_classification(scope, expected):
    data = {"error": {"details": [{"violations": [{"quotaMetric": "generate_requests",
                  "quotaDimensions": {"model": MODELS[0]} if scope == "model" else {}}]}]}}
    if scope == "unknown":data = {"error": {"status": "RESOURCE_EXHAUSTED"}}
    response = httpx.Response(429, json=data)
    assert llm_providers._http_failure("gemini", response).provider_wide is expected


@pytest.mark.parametrize("value,expected", [("120", 120), ("0", 0), ("-1", 0),
                                            ("NaN", 0), ("garbage", 0)])
def test_retry_after_seconds_are_safe(value, expected):
    assert llm_providers._retry_after(httpx.Response(429, headers={"Retry-After": value})) == expected


def test_retry_after_http_date():
    future = datetime.now(timezone.utc) + timedelta(seconds=120)
    wait = llm_providers._retry_after(httpx.Response(503, headers={"Retry-After": format_datetime(future)}))
    assert 118 <= wait <= 120


@pytest.mark.asyncio
async def test_retry_after_sleep_and_budget(monkeypatch):
    monkeypatch.setattr(llm_providers.settings, "gemini_api_key", "synthetic-key")
    provider = GeminiProvider(model_id=MODELS[0])
    calls, sleeps = [], []
    async def request(prompt, timeout):
        calls.append(timeout)
        if len(calls) == 1:raise failure("http_error", retryable=True, retry_after_seconds=0.1)
        return LLMCompletion("{}")
    async def sleep(delay):sleeps.append(delay)
    monkeypatch.setattr(provider, "_request_once", request)
    monkeypatch.setattr(llm_providers, "_sleep", sleep)
    await provider.complete("synthetic", timeout_seconds=1)
    assert len(calls) == 2 and sleeps == [0.1]
    calls.clear();sleeps.clear()
    with pytest.raises(LLMProviderError):
        await provider.complete("synthetic", timeout_seconds=0.05)
    assert len(calls) == 1 and not sleeps


@pytest.mark.asyncio
async def test_chain_mode_does_not_repeat_429(monkeypatch):
    monkeypatch.setattr(llm_providers.settings, "gemini_api_key", "synthetic-key")
    provider = GeminiProvider(model_id=MODELS[0], retry_rate_limits=False)
    calls = []
    async def request(*args):
        calls.append(True);raise failure("rate_limit", retryable=True, status_code=429)
    monkeypatch.setattr(provider, "_request_once", request)
    with pytest.raises(LLMProviderError):await provider.complete("synthetic", timeout_seconds=1)
    assert len(calls) == 1


def test_http_error_body_is_never_in_exception():
    error = llm_providers._http_failure("gemini", httpx.Response(401, text="SECRET patient evidence API_KEY"))
    assert "SECRET" not in str(error) and error.status_code == 401
    assert error.category == "authentication" and error.provider_wide


@pytest.mark.parametrize("values", [["gemini-a", "gemini-a"], [], ["https://bad"], ["gemini-a"] * 4])
def test_candidate_configuration_is_bounded_and_validated(values):
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://synthetic", gemini_candidate_models=values, _env_file=None)


def test_untrusted_usage_payload_cannot_enter_success_log(caplog):
    import logging
    from app.services.llm_providers import LLMCompletion
    provider = Provider(MODELS[0])
    completion = LLMCompletion("not logged", prompt_tokens="SECRET clinical text",
                               completion_tokens={"private": "SECRET"}, total_tokens=12)
    with caplog.at_level(logging.INFO, logger="app.llm_service"):
        llm_service._log_successful_completion(provider, completion, latency_ms=1,
                                               fallback_used=False)
    record = next(r for r in caplog.records if r.message == "LLM explanation generated")
    assert not hasattr(record, "prompt_tokens") and not hasattr(record, "completion_tokens")
    assert record.total_tokens == 12
    assert "SECRET" not in str(record.__dict__)


def test_configured_default_order_and_legacy_setting_are_separate():
    settings = Settings(database_url="postgresql://synthetic", gemini_model="gemini-3.5-flash-lite",
                        _env_file=None)
    assert settings.gemini_candidate_models == tuple(MODELS)
    assert settings.gemini_model == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [False, True])
async def test_expired_shared_deadline_never_starts_later_candidates_or_accepts_late_output(monkeypatch, valid):
    from types import SimpleNamespace
    now = [0.0]
    # Replace this module's clock only, not asyncio's platform timer.
    monkeypatch.setattr(llm_service, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(llm_service.settings, "llm_failover_deadline_seconds", 1.0)
    def expire(prompt):
        now[0] = 2.0
        if valid:return selection_for_prompt(prompt)
        raise failure()
    providers = install(monkeypatch, [expire, "valid", "valid"])
    with pytest.raises(LLMExplanationError, match="deadline_exceeded"):
        await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [1, 0, 0, 0]


def test_success_resets_consecutive_model_failures():
    registry = CooldownRegistry(lambda: 0.0)

    def finish(outcome):
        registry.finish("gemini", MODELS[0], outcome=outcome,
                        cooldown=15, threshold=2)

    assert registry.admit("gemini", MODELS[0]) is None
    finish("invalid_response")
    assert registry.admit("gemini", MODELS[0]) is None
    finish("success")
    assert registry.admit("gemini", MODELS[0]) is None
    finish("invalid_response")
    # The successful request broke the previous failure streak.
    assert registry.admit("gemini", MODELS[0]) is None
    finish("invalid_response")
    assert registry.admit("gemini", MODELS[0]) == "model_cooldown"
    assert registry.admit("gemini", MODELS[1]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["provider", "parser", "context"])
async def test_programming_errors_propagate_release_admission_without_failure(monkeypatch, stage):
    registry = CooldownRegistry(lambda: 0.0)
    monkeypatch.setattr(llm_service, "_COOLDOWNS", registry)
    # A wrongly counted programming error would trigger threshold-two cooldown.
    assert registry.admit("gemini", MODELS[0]) is None
    registry.finish("gemini", MODELS[0], outcome="invalid_response",
                    cooldown=15, threshold=2)
    error = RuntimeError("synthetic programming defect")
    providers = install(monkeypatch, ["synthetic response", "valid", "valid"])
    expected = object()

    def broken(*args):
        raise error

    parser = broken if stage == "parser" else lambda text: expected
    validator = broken if stage == "context" else None
    if stage == "provider":
        providers[0].value = error
    with pytest.raises(RuntimeError) as raised:
        await llm_service._call_providers_with_fallback(
            "synthetic request A", parse_completion=parser, validate_context=validator,
        )
    assert raised.value is error
    assert [len(p.calls) for p in providers] == [1, 0, 0, 0]
    assert registry.admit("gemini", MODELS[0]) is None
    registry.finish("gemini", MODELS[0], outcome="internal_error",
                    cooldown=15, threshold=2)
    providers[0].value = "synthetic response B"
    answer = await llm_service._call_providers_with_fallback(
        "synthetic request B", parse_completion=lambda text: (expected, text),
    )
    assert answer == (expected, "synthetic response B")
    assert [len(p.calls) for p in providers] == [2, 0, 0, 0]
    assert [call[0] for call in providers[0].calls] == [
        "synthetic request A", "synthetic request B",
    ]


@pytest.mark.asyncio
async def test_cancellation_does_not_increment_existing_failure_streak(monkeypatch):
    registry = CooldownRegistry(lambda: 0.0)
    monkeypatch.setattr(llm_service, "_COOLDOWNS", registry)
    assert registry.admit("gemini", MODELS[0]) is None
    registry.finish("gemini", MODELS[0], outcome="invalid_response",
                    cooldown=15, threshold=2)
    entered = asyncio.Event()

    async def hang(prompt):
        entered.set()
        await asyncio.sleep(100)

    providers = install(monkeypatch, [hang, "valid", "valid"])
    task = asyncio.create_task(llm_service.generate_explanation(*scenario()))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.admit("gemini", MODELS[0]) is None
    registry.finish("gemini", MODELS[0], outcome="cancelled",
                    cooldown=15, threshold=2)
    providers[0].value = "valid"
    await llm_service.generate_explanation(*scenario())
    assert [len(p.calls) for p in providers] == [2, 0, 0, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize("elapsed,expected_budget", [
    (0.25, 0.55), (0.8, None), (1.0, None), (0.7995, 0.0005),
])
async def test_retry_after_wakeup_rechecks_remaining_budget(monkeypatch, elapsed, expected_budget):
    from types import SimpleNamespace

    now = [0.0]
    monkeypatch.setattr(llm_providers, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(llm_providers.settings, "gemini_api_key", "synthetic-key")
    provider = GeminiProvider(model_id=MODELS[0])
    calls, sleeps = [], []
    original_error = failure("http_error", retryable=True, retry_after_seconds=0.25)

    async def request(prompt, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            now[0] = 0.2
            raise original_error
        return LLMCompletion("synthetic response")

    async def sleep(delay):
        sleeps.append(delay)
        now[0] += elapsed  # Controlled scheduling delay, no real waiting/network.

    monkeypatch.setattr(provider, "_request_once", request)
    monkeypatch.setattr(llm_providers, "_sleep", sleep)
    if expected_budget is None:
        with pytest.raises(LLMProviderError) as raised:
            await provider.complete("synthetic", timeout_seconds=1)
        assert raised.value is original_error
        assert calls == [1]
    else:
        answer = await provider.complete("synthetic", timeout_seconds=1)
        assert answer.text == "synthetic response"
        assert calls == pytest.approx([1, expected_budget])
    assert sleeps == [0.25]
