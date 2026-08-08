"""
Phase 15 LLM service tests.

Covers prompt construction, response parsing/validation, and the
Gemini-then-OpenRouter fallback orchestration in
`app/services/llm_service.py`. Providers are mocked at the
`llm_service._PROVIDERS` seam -- no real network calls, no real API keys
needed. This mirrors the existing convention (e.g. test_auth_api.py) of
mocking the outermost I/O boundary rather than reaching into httpx.

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
from app.services.llm_providers import LLMProviderError
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
    """Minimal stand-in for GeminiProvider/OpenRouterProvider."""

    def __init__(self, name: str, *, raw: str | None = None, error: Exception | None = None):
        self.name = name
        self._raw = raw
        self._error = error
        self.call_count = 0

    async def complete(self, prompt: str, *, timeout_seconds: float) -> str:
        self.call_count += 1
        if self._error:
            raise self._error
        return self._raw


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
