"""
Phase 15 LLM service tests.

Covers prompt construction, response parsing/validation, and the
Gemini-then-OpenRouter fallback orchestration in
`app/services/llm_service.py`. Providers are mocked at the
`llm_service._PROVIDERS` seam -- no real network calls, no real API keys
needed. This mirrors the existing convention (e.g. test_auth_api.py) of
mocking the outermost I/O boundary rather than reaching into httpx.

Phase 15 improvement additions:
  - `_FakeProvider` now returns an `LLMCompletion` (matching the real
    providers' updated return type) instead of a bare string.
  - New tests cover the structured success-log record (fields present,
    fallback_used true/false, graceful omission of token fields when a
    provider doesn't report usage) and that no patient/prompt/medical
    content ever appears in that log record.
  - New tests confirm `_build_prompt` is deterministic given the same
    (or equal-but-freshly-constructed) inputs.

Run with:  pytest backend/tests/test_llm_service.py -v
"""
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app.analysis.safety_score_engine import PenaltyEntry, SafetyScoreResult
from app.analysis.drug_interaction_engine import DrugInteractionFinding
from app.analysis.timeline_engine import TimelineContext, TimelineEntry
from app.services import llm_service
from app.services.evidence_retrieval import EvidenceBundle, EvidenceItem, FindingEvidence
from app.services.llm_providers import LLMCompletion, LLMProviderError
from app.services.llm_service import (
    LLMExplanationError,
    LLMExplanationResult,
    _build_prompt,
    _parse_and_validate,
    generate_explanation,
)
from app.services.patient_context_builder import (
    ConditionSummary,
    MedicationSummary,
    PatientContext,
)


class _FakeProvider:
    """Minimal stand-in for GeminiProvider/OpenRouterProvider. Returns an
    `LLMCompletion` (not a bare string), matching the real providers'
    `complete()` contract."""

    def __init__(
        self,
        name: str,
        *,
        raw: str | None = None,
        error: Exception | None = None,
        model: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ):
        self.name = name
        self.model = model or f"fake-{name}-model"
        self._raw = raw
        self._error = error
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._total_tokens = total_tokens
        self.call_count = 0

    async def complete(self, prompt: str, *, timeout_seconds: float) -> LLMCompletion:
        self.call_count += 1
        if self._error:
            raise self._error
        return LLMCompletion(
            text=self._raw,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            total_tokens=self._total_tokens,
        )


def _empty_patient_context() -> PatientContext:
    return PatientContext(
        patient_id=uuid.uuid4(),
        name="Test Patient",
        age=50,
        sex="female",
        weight_kg=None,
        renal_flag=False,
        hepatic_flag=False,
        active_conditions=[],
        active_medications=[],
        active_symptoms=[],
    )


def _empty_safety_score_result() -> SafetyScoreResult:
    return SafetyScoreResult(
        safety_score=100,
        risk_level="low",
        starting_score=100,
        total_points_deducted=0,
        interaction_findings=[],
        adr_findings=[],
        adherence_findings=[],
        penalties=[],
    )


def _empty_evidence_bundle() -> EvidenceBundle:
    return EvidenceBundle(interaction_evidence=[], adr_evidence=[], adherence_evidence=[])


def _empty_timeline_context() -> TimelineContext:
    return TimelineContext(patient_id=uuid.uuid4(), entries=[])


VALID_JSON = (
    '{"summary": "All clear.", "reasoning": "No findings were detected for this patient.", '
    '"recommendations": "Continue routine monitoring.", "confidence_score": 95, '
    '"confidence_level": "high"}'
)


# ---------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------


def test_build_prompt_includes_all_sections():
    prompt = _build_prompt(
        _empty_patient_context(),
        _empty_safety_score_result(),
        _empty_evidence_bundle(),
        _empty_timeline_context(),
    )
    assert "Patient snapshot" in prompt
    assert "Deterministic findings" in prompt
    assert "Supporting evidence" in prompt
    assert "Patient timeline" in prompt
    assert "Safety score: 100/100" in prompt
    assert "No safety findings were detected." in prompt


def test_build_prompt_includes_active_medications_and_conditions():
    ctx = PatientContext(
        patient_id=uuid.uuid4(),
        name="Test Patient",
        age=60,
        sex="male",
        weight_kg=80.0,
        renal_flag=True,
        hepatic_flag=False,
        active_conditions=[
            ConditionSummary(
                id=uuid.uuid4(),
                name="Hypertension",
                status="active",
                reason="doctor_diagnosis",
                diagnosed_date=date.today(),
                resolved_date=None,
                notes=None,
            )
        ],
        active_medications=[
            MedicationSummary(
                id=uuid.uuid4(),
                drug_id=uuid.uuid4(),
                drug_name="Warfarin",
                condition_id=None,
                purpose_text="Anticoagulation",
                dose="5mg",
                times_per_day=1,
                interval_hours=None,
                duration_days=None,
                status="active",
                start_date=date.today(),
                end_date=None,
            )
        ],
        active_symptoms=[],
    )
    prompt = _build_prompt(
        ctx, _empty_safety_score_result(), _empty_evidence_bundle(), _empty_timeline_context()
    )
    assert "Hypertension" in prompt
    assert "Warfarin" in prompt
    assert "Anticoagulation" in prompt


def test_build_prompt_truncates_long_timeline():
    entries = [
        TimelineEntry(
            id=uuid.uuid4(),
            event_type="symptom_reported",
            ref_id=uuid.uuid4(),
            event_title=f"Event {i}",
            event_description=None,
            event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            payload=None,
        )
        for i in range(50)
    ]
    timeline = TimelineContext(patient_id=uuid.uuid4(), entries=entries)

    prompt = _build_prompt(
        _empty_patient_context(), _empty_safety_score_result(), _empty_evidence_bundle(), timeline
    )
    assert "omitted for brevity" in prompt
    assert "Event 0" not in prompt  # oldest entries truncated away
    assert "Event 49" in prompt  # most recent entry retained


def test_build_prompt_includes_findings_and_evidence():
    finding = DrugInteractionFinding(
        interaction_rule_id=uuid.uuid4(),
        drug_a_id=uuid.uuid4(),
        drug_a_name="Warfarin",
        drug_b_id=uuid.uuid4(),
        drug_b_name="Aspirin",
        severity="severe",
        mechanism="Additive bleeding risk.",
        recommendation="Avoid combination.",
        source="FDA Label",
    )
    penalty = PenaltyEntry(
        category="drug_interaction",
        description="Warfarin + Aspirin interaction (severe)",
        severity="severe",
        points=30,
        source=finding,
    )
    result = SafetyScoreResult(
        safety_score=70,
        risk_level="moderate",
        starting_score=100,
        total_points_deducted=30,
        interaction_findings=[finding],
        adr_findings=[],
        adherence_findings=[],
        penalties=[penalty],
    )
    bundle = EvidenceBundle(
        interaction_evidence=[
            FindingEvidence(
                category="drug_interaction",
                finding=finding,
                medical_evidence=[
                    EvidenceItem(
                        kind="medical",
                        statement="Additive bleeding risk.",
                        source="FDA Label",
                        occurred_at=None,
                    )
                ],
                personal_evidence=[
                    EvidenceItem(
                        kind="personal",
                        statement="Started Warfarin",
                        source=None,
                        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                ],
            )
        ],
        adr_evidence=[],
        adherence_evidence=[],
    )

    prompt = _build_prompt(_empty_patient_context(), result, bundle, _empty_timeline_context())
    assert "Warfarin + Aspirin interaction (severe)" in prompt
    assert "Additive bleeding risk." in prompt
    assert "Started Warfarin" in prompt


# ---------------------------------------------------------------------
# _parse_and_validate
# ---------------------------------------------------------------------


def test_parse_valid_json():
    result = _parse_and_validate(VALID_JSON)
    assert isinstance(result, LLMExplanationResult)
    assert result.confidence_score == 95
    assert result.confidence_level == "high"


def test_parse_recovers_from_markdown_fences():
    fenced = f"```json\n{VALID_JSON}\n```"
    result = _parse_and_validate(fenced)
    assert result.confidence_level == "high"


def test_parse_recovers_stray_prose_around_json():
    wrapped = f"Here is the result:\n{VALID_JSON}\nHope that helps!"
    result = _parse_and_validate(wrapped)
    assert result.confidence_level == "high"


def test_parse_rejects_unparseable_json():
    with pytest.raises(LLMExplanationError):
        _parse_and_validate("not json at all {{{")


def test_parse_rejects_missing_field():
    bad = '{"summary": "x", "reasoning": "y", "confidence_score": 50, "confidence_level": "low"}'
    with pytest.raises(LLMExplanationError):
        _parse_and_validate(bad)


def test_parse_rejects_empty_string_field():
    bad = VALID_JSON.replace('"All clear."', '""')
    with pytest.raises(LLMExplanationError):
        _parse_and_validate(bad)


@pytest.mark.parametrize("bad_score", [-1, 101, "85", True])
def test_parse_rejects_invalid_confidence_score(bad_score):
    data = json.loads(VALID_JSON)
    data["confidence_score"] = bad_score
    with pytest.raises(LLMExplanationError):
        _parse_and_validate(json.dumps(data))


def test_parse_rejects_invalid_confidence_level():
    bad = VALID_JSON.replace('"high"', '"very high"')
    with pytest.raises(LLMExplanationError):
        _parse_and_validate(bad)


def test_parse_permits_unknown_extra_keys():
    data = json.loads(VALID_JSON)
    data["extra_metadata"] = "harmless"
    result = _parse_and_validate(json.dumps(data))
    assert result.confidence_level == "high"


def test_parse_does_not_clamp_confidence_score():
    """
    Approved Phase 15 design: deterministic confidence clamping was
    removed from scope. A schema-valid, self-reported low confidence
    score/level must pass through completely unmodified.
    """
    data = json.loads(VALID_JSON)
    data["confidence_score"] = 12
    data["confidence_level"] = "low"
    result = _parse_and_validate(json.dumps(data))
    assert result.confidence_score == 12
    assert result.confidence_level == "low"


# ---------------------------------------------------------------------
# generate_explanation -- provider fallback orchestration
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_success_openrouter_never_called(monkeypatch):
    gemini = _FakeProvider("gemini", raw=VALID_JSON)
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    result = await generate_explanation(
        _empty_patient_context(),
        _empty_safety_score_result(),
        _empty_evidence_bundle(),
        _empty_timeline_context(),
    )

    assert isinstance(result, LLMExplanationResult)
    assert gemini.call_count == 1
    assert openrouter.call_count == 0


@pytest.mark.asyncio
async def test_gemini_provider_error_falls_back_to_openrouter(monkeypatch):
    gemini = _FakeProvider("gemini", error=LLMProviderError("gemini", "unreachable"))
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    result = await generate_explanation(
        _empty_patient_context(),
        _empty_safety_score_result(),
        _empty_evidence_bundle(),
        _empty_timeline_context(),
    )

    assert isinstance(result, LLMExplanationResult)
    assert gemini.call_count == 1
    assert openrouter.call_count == 1


@pytest.mark.asyncio
async def test_gemini_malformed_output_falls_back_to_openrouter(monkeypatch):
    """
    Approved Phase 15 design: malformed-but-successful provider output
    must trigger fallback, the same as a network/HTTP failure would.
    """
    gemini = _FakeProvider("gemini", raw="not valid json")
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    result = await generate_explanation(
        _empty_patient_context(),
        _empty_safety_score_result(),
        _empty_evidence_bundle(),
        _empty_timeline_context(),
    )

    assert isinstance(result, LLMExplanationResult)
    assert gemini.call_count == 1
    assert openrouter.call_count == 1


@pytest.mark.asyncio
async def test_both_providers_failing_raises_llm_explanation_error(monkeypatch):
    gemini = _FakeProvider("gemini", error=LLMProviderError("gemini", "unreachable"))
    openrouter = _FakeProvider("openrouter", error=LLMProviderError("openrouter", "unreachable"))
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(LLMExplanationError):
        await generate_explanation(
            _empty_patient_context(),
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )


@pytest.mark.asyncio
async def test_both_providers_malformed_output_raises_llm_explanation_error(monkeypatch):
    gemini = _FakeProvider("gemini", raw="garbage")
    openrouter = _FakeProvider("openrouter", raw="also garbage")
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(LLMExplanationError):
        await generate_explanation(
            _empty_patient_context(),
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )


@pytest.mark.asyncio
async def test_error_message_includes_both_provider_failures(monkeypatch):
    gemini = _FakeProvider("gemini", error=LLMProviderError("gemini", "rate limited"))
    openrouter = _FakeProvider("openrouter", error=LLMProviderError("openrouter", "timed out"))
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(LLMExplanationError) as exc_info:
        await generate_explanation(
            _empty_patient_context(),
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )

    message = str(exc_info.value)
    assert "gemini" in message
    assert "openrouter" in message


# ---------------------------------------------------------------------
# Structured logging (Phase 15 improvement)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_call_logs_structured_metadata(monkeypatch, caplog):
    gemini = _FakeProvider(
        "gemini",
        raw=VALID_JSON,
        model="gemini-test-model",
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
    )
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini,))

    with caplog.at_level("INFO", logger="app.llm_service"):
        await generate_explanation(
            _empty_patient_context(),
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )

    records = [r for r in caplog.records if r.message == "LLM explanation generated"]
    assert len(records) == 1
    record = records[0]

    assert record.provider_used == "gemini"
    assert record.model_used == "gemini-test-model"
    assert isinstance(record.latency_ms, int)
    assert record.latency_ms >= 0
    assert record.fallback_used is False
    assert record.prompt_tokens == 100
    assert record.completion_tokens == 20
    assert record.total_tokens == 120


@pytest.mark.asyncio
async def test_fallback_call_logs_fallback_used_true(monkeypatch, caplog):
    gemini = _FakeProvider("gemini", error=LLMProviderError("gemini", "unreachable"))
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON, model="openrouter-test-model")
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with caplog.at_level("INFO", logger="app.llm_service"):
        await generate_explanation(
            _empty_patient_context(),
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )

    records = [r for r in caplog.records if r.message == "LLM explanation generated"]
    assert len(records) == 1
    assert records[0].provider_used == "openrouter"
    assert records[0].model_used == "openrouter-test-model"
    assert records[0].fallback_used is True


@pytest.mark.asyncio
async def test_successful_call_log_omits_token_fields_when_unavailable(monkeypatch, caplog):
    """Token usage fields must be entirely absent from the log record
    (not present as None) when a provider doesn't report usage."""
    gemini = _FakeProvider("gemini", raw=VALID_JSON)  # no token counts supplied
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini,))

    with caplog.at_level("INFO", logger="app.llm_service"):
        await generate_explanation(
            _empty_patient_context(),
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )

    record = next(r for r in caplog.records if r.message == "LLM explanation generated")
    assert not hasattr(record, "prompt_tokens")
    assert not hasattr(record, "completion_tokens")
    assert not hasattr(record, "total_tokens")


@pytest.mark.asyncio
async def test_no_patient_or_prompt_content_appears_in_logs(monkeypatch, caplog):
    """
    Only operational metadata may be logged -- never patient identifiers,
    prompts, medical history, evidence text, or the generated explanation
    itself. Uses a non-empty patient/finding/evidence set so there is
    real sensitive content that would leak if the logging implementation
    ever regresses to including it.
    """
    patient_context = PatientContext(
        patient_id=uuid.uuid4(),
        name="Sensitive Patient Name",
        age=60,
        sex="female",
        weight_kg=70.0,
        renal_flag=False,
        hepatic_flag=False,
        active_conditions=[],
        active_medications=[],
        active_symptoms=[],
    )
    gemini = _FakeProvider("gemini", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini,))

    with caplog.at_level("INFO", logger="app.llm_service"):
        await generate_explanation(
            patient_context,
            _empty_safety_score_result(),
            _empty_evidence_bundle(),
            _empty_timeline_context(),
        )

    full_text = caplog.text
    assert "Sensitive Patient Name" not in full_text
    assert str(patient_context.patient_id) not in full_text
    assert "All clear." not in full_text  # the generated summary text
    assert "No findings were detected" not in full_text  # the generated reasoning text


# ---------------------------------------------------------------------
# Prompt determinism (Phase 15 improvement -- verification, per the
# requirement that _build_prompt must be deterministic given the same
# inputs. No code change was required here: _build_prompt and its
# helpers only ever iterate already-ordered input lists/tuples and never
# call datetime.now()/random/uuid -- these tests lock that in.)
# ---------------------------------------------------------------------


def test_build_prompt_is_deterministic_for_the_same_inputs():
    ctx = PatientContext(
        patient_id=uuid.uuid4(),
        name="Determinism Patient",
        age=45,
        sex="female",
        weight_kg=70.0,
        renal_flag=False,
        hepatic_flag=True,
        active_conditions=[
            ConditionSummary(
                id=uuid.uuid4(),
                name="Hypertension",
                status="active",
                reason="doctor_diagnosis",
                diagnosed_date=date.today(),
                resolved_date=None,
                notes=None,
            )
        ],
        active_medications=[
            MedicationSummary(
                id=uuid.uuid4(),
                drug_id=uuid.uuid4(),
                drug_name="Lisinopril",
                condition_id=None,
                purpose_text="BP control",
                dose="10mg",
                times_per_day=1,
                interval_hours=None,
                duration_days=None,
                status="active",
                start_date=date.today(),
                end_date=None,
            )
        ],
        active_symptoms=[],
    )
    result = _empty_safety_score_result()
    bundle = _empty_evidence_bundle()
    timeline = _empty_timeline_context()

    prompt_1 = _build_prompt(ctx, result, bundle, timeline)
    prompt_2 = _build_prompt(ctx, result, bundle, timeline)

    assert prompt_1 == prompt_2


def test_build_prompt_is_deterministic_across_separately_constructed_equal_inputs():
    """
    Same logical content, but freshly (separately) constructed input
    objects for each call -- proves determinism isn't an artifact of
    reusing the same object instance. `PatientContext.patient_id` and
    `TimelineContext.patient_id` intentionally differ between the two
    calls (fresh `uuid.uuid4()` each time in the `_empty_*` helpers)
    since neither is ever rendered into the prompt text.
    """
    prompt_a = _build_prompt(
        _empty_patient_context(),
        _empty_safety_score_result(),
        _empty_evidence_bundle(),
        _empty_timeline_context(),
    )
    prompt_b = _build_prompt(
        _empty_patient_context(),
        _empty_safety_score_result(),
        _empty_evidence_bundle(),
        _empty_timeline_context(),
    )

    assert prompt_a == prompt_b
