"""Synthetic grounding regressions; no database or external providers."""
import copy
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from app.analysis.adr_engine import ADRFinding
from app.analysis.safety_score_engine import PenaltyEntry, SafetyScoreResult
from app.analysis.timeline_engine import TimelineContext, TimelineEntry
from app.services import llm_service
from app.services.evidence_retrieval import EvidenceBundle, EvidenceItem, FindingEvidence
from app.services.llm_providers import LLMCompletion, LLMProviderError
from app.services.llm_service import LLMExplanationError, generate_explanation
from app.services.patient_context_builder import MedicationSummary, PatientContext, SymptomSummary

ORIGINAL_CLAIM = (
    "Because both medications were initiated together, the combined risks "
    "compound, leading to the overall high risk score."
)


def response(text, **changes):
    data = dict(summary="The recorded analysis is available.", reasoning=text,
                recommendations="Discuss the recorded findings with your clinician.",
                confidence_score=40, confidence_level="low")
    data.update(changes)
    return json.dumps(data)


class Provider:
    def __init__(self, name, raw=None, error=None):
        self.name, self.model, self.raw, self.error = name, "synthetic-test", raw, error
        self.prompts = []

    async def complete(self, prompt, *, timeout_seconds):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return LLMCompletion(text=self.raw(prompt) if callable(self.raw) else self.raw)


def scenario(assessment=None, contradictory=False):
    pid, mid, drug = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    context = PatientContext(
        patient_id=pid, name="Synthetic fixture", age=None, sex=None, weight_kg=None,
        renal_flag=False, hepatic_flag=False, active_conditions=[],
        active_medications=[MedicationSummary(
            id=mid, drug_id=drug, drug_name="Synthetic Drug A", condition_id=None,
            purpose_text=None, dose=None, times_per_day=None, interval_hours=None,
            duration_days=None, status="active", start_date=date(2026, 1, 1), end_date=None)],
        active_symptoms=[SymptomSummary(
            id=uuid.uuid4(), description="Synthetic symptom report", severity="mild",
            condition_id=None, medication_id=mid, onset_date=date(2026, 1, 3),
            resolved_date=None)])
    finding = ADRFinding(uuid.uuid4(), drug, "Synthetic Drug A", "Synthetic rash risk",
                         "mild", None, "Synthetic rule fixture, not medical advice")
    # Recorded deterministic rule match; no inference about this patient's symptom.
    result = SafetyScoreResult(95, "low", 100, 5, [], [finding], [], [
        PenaltyEntry("adr", "Synthetic rash risk", "mild", 5, finding)])
    personal = [EvidenceItem("personal", "Recorded medication start; no causal assessment.",
                             None, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    if assessment:
        personal.append(EvidenceItem("personal", assessment, "Synthetic clinician note",
                                     datetime(2026, 1, 4, tzinfo=timezone.utc)))
    if contradictory:
        personal.append(EvidenceItem("personal", "Conflicting note: symptom predates medication.",
                                     "Synthetic conflicting note", None))
    bundle = EvidenceBundle([], [FindingEvidence("adr", finding, [EvidenceItem(
        "medical", "Synthetic rash risk is listed by the supplied rule.",
        "Synthetic rule fixture", None)], personal)], [])
    timeline = TimelineContext(pid, [TimelineEntry(
        uuid.uuid4(), "symptom_reported", None, "Synthetic symptom recorded",
        assessment, datetime(2026, 1, 4, tzinfo=timezone.utc), None)])
    return context, result, bundle, timeline


from dataclasses import replace
from app.services.explanation_evidence import (
    EvidenceSelectionError, build_catalog, render_selection,
)
def selection_for_prompt(prompt):
    """A compliant synthetic provider response, bound to this request catalog."""
    catalog = json.loads(prompt.split("EVIDENCE_CATALOG\n", 1)[1])
    return json.dumps({
        "scope": catalog["scope"],
        **{section: [s["id"] for s in catalog["statements"]
                     if s["section"] == section]
           for section in ("summary", "reasoning", "recommendations")},
        "confidence_score": 40, "confidence_level": "low",
    })





UNSUPPORTED = [
    ORIGINAL_CLAIM,
    "The patient has a rash.",
    "The patient takes Metformin.",
    "Synthetic Drug A is taken at 500 mg daily.",
    "Synthetic Drug A treats diabetes.",
    "Synthetic Drug A interacts with Metformin.",
    "The patient experienced anaphylaxis.",
    "The medicine started first, so it caused the symptom.",
    "The symptom followed treatment, establishing a clinical association.",
    "The documented suspicion proves the medicine caused the reaction.",
    "The safety score is 100.",
    "The risk level is high.",
    "No interaction or ADR findings exist.",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("claim", UNSUPPORTED)
async def test_unbound_claims_rejected_with_bounded_valid_fallback(monkeypatch, claim):
    primary = Provider("gemini", response(claim))
    fallback = Provider("openrouter", selection_for_prompt)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (primary, fallback))
    fixture = scenario()
    before = copy.deepcopy(fixture)
    result = await generate_explanation(*fixture)
    assert len(primary.prompts) == len(fallback.prompts) == 1
    assert primary.prompts == fallback.prompts
    assert claim not in result.reasoning
    assert "Recorded symptom: \"Synthetic symptom report\"" in result.reasoning
    assert "cannot independently establish a cause" in result.reasoning
    assert fixture == before


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    "", " ", "not JSON", "[]", "null", "{}", response("Unsupported rash."),
    '{"scope":"one","scope":"two"}',
])
async def test_invalid_output_and_total_failure_are_unavailable(monkeypatch, raw):
    primary = Provider("gemini", raw)
    fallback = Provider("openrouter", error=LLMProviderError("openrouter", "failure"))
    monkeypatch.setattr(llm_service, "_PROVIDERS", (primary, fallback))
    with pytest.raises(LLMExplanationError):
        await generate_explanation(*scenario())
    assert len(primary.prompts) == len(fallback.prompts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("assessment,contradictory", [
    (None, False),
    ("Clinician documents a suspected reaction; causality has not been confirmed.", False),
    ("Clinician assessed that Synthetic Drug A caused the symptom.", False),
    ("Clinician suspects Synthetic Drug A.", True),
])
async def test_records_and_assessments_are_exact_attributed_quotes(monkeypatch, assessment, contradictory):
    fixture = scenario(assessment, contradictory)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", selection_for_prompt),))
    answer = await generate_explanation(*fixture)
    assert "2026-01-01" in answer.reasoning and "2026-01-03" in answer.reasoning
    assert "not independently verified" in answer.reasoning
    assert "not model-proven conclusions" in answer.reasoning
    if assessment:
        assert json.dumps(assessment) in answer.reasoning
    if contradictory:
        assert "Conflicting note: symptom predates medication." in answer.reasoning
        assert "conflicting evidence remains unresolved" in answer.reasoning
    assert "Recorded symptom: \"Synthetic symptom report\"" in answer.reasoning
    assert "Recorded symptom: \"Synthetic rash risk\"" not in answer.reasoning


@pytest.mark.asyncio
async def test_missing_evidence_remains_unknown_and_provider_failure_falls_back(monkeypatch):
    context, score, _, timeline = scenario()
    primary = Provider("gemini", error=LLMProviderError("gemini", "failure"))
    fallback = Provider("openrouter", selection_for_prompt)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (primary, fallback))
    answer = await generate_explanation(context, score, EvidenceBundle([], [], []), timeline)
    assert "Missing evidence remains unknown" in answer.reasoning
    assert len(fallback.prompts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"summary": ["unsupported symptom: rash"]},
    {"reasoning": ["score"]},
    {"scope": "other-patient-or-analysis"},
    {"reasoning": []},
    {"summary": ["score", "score"]},
    {"summary": [True]},
    {"summary": "score"},
    {"extra": "The patient has a rash."},
    {"confidence_score": True},
    {"confidence_score": 101},
    {"confidence_level": "certain"},
])
async def test_claim_binding_and_strict_schema_fail_closed(monkeypatch, change):
    def bad(prompt):
        data = json.loads(selection_for_prompt(prompt)); data.update(change)
        return json.dumps(data)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", bad),))
    with pytest.raises(LLMExplanationError):
        await generate_explanation(*scenario())


@pytest.mark.asyncio
async def test_required_findings_and_conflicting_notes_cannot_be_omitted(monkeypatch):
    def bad(prompt):
        data = json.loads(selection_for_prompt(prompt))
        data["reasoning"] = ["limits"]
        return json.dumps(data)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", bad),))
    with pytest.raises(LLMExplanationError):
        await generate_explanation(*scenario("Suspected reaction", True))


def test_cross_patient_context_and_unrelated_finding_rejected():
    fixture = scenario()
    with pytest.raises(EvidenceSelectionError, match="scope"):
        build_catalog(*fixture[:3], replace(fixture[3], patient_id=uuid.uuid4()))
    other = scenario()[2]
    with pytest.raises(EvidenceSelectionError, match="binding"):
        build_catalog(fixture[0], fixture[1], other, fixture[3])


@pytest.mark.asyncio
async def test_previous_analysis_response_cannot_be_replayed(monkeypatch):
    saved = []
    def capture(prompt):
        saved.append(selection_for_prompt(prompt)); return saved[-1]
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", capture),))
    fixture = scenario(); await generate_explanation(*fixture)
    changed = (fixture[0], replace(fixture[1], safety_score=20, risk_level="high"), *fixture[2:])
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", saved[0]),))
    with pytest.raises(LLMExplanationError):
        await generate_explanation(*changed)


@pytest.mark.asyncio
async def test_no_provider_or_source_text_is_logged(monkeypatch, caplog):
    secret_claim = "Unsupported private synthetic symptom"
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", response(secret_claim)),))
    with pytest.raises(LLMExplanationError):
        await generate_explanation(*scenario())
    assert secret_claim not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [
    "success", "fallback", "rejected", "empty", "malformed", "failed",
])
async def test_persistence_keeps_all_deterministic_outputs_and_exact_patient_run(
    monkeypatch, outcome,
):
    from dataclasses import replace
    from app.analysis.adherence_engine import AdherenceFinding
    from app.analysis.drug_interaction_engine import DrugInteractionFinding
    from app.analysis.safety_score_engine import PenaltyEntry
    from app.db.models import AnalysisRun, TimelineEvent
    from app.services.langgraph_workflow import (
        _llm_explanation_node, _persist_node, _serialize_safety_score_result,
    )

    context, score, bundle, timeline = scenario()
    interaction = DrugInteractionFinding(
        uuid.uuid4(), context.active_medications[0].drug_id, "Synthetic Drug A",
        uuid.uuid4(), "Synthetic Drug B", "severe", "Synthetic rule mechanism.",
        "Discuss the recorded finding with a clinician.", "Synthetic rule fixture")
    adherence = AdherenceFinding(
        context.active_medications[0].id, "Synthetic Drug A", 1, 1, 0, 2, 0.5,
    )
    context = replace(context, active_medications=context.active_medications + [replace(
        context.active_medications[0], id=uuid.uuid4(), drug_id=interaction.drug_b_id,
        drug_name="Synthetic Drug B")])
    score = replace(score, safety_score=60, risk_level="moderate", total_points_deducted=40,
        interaction_findings=[interaction], adherence_findings=[adherence],
        penalties=score.penalties + [
            PenaltyEntry("interaction", "Synthetic interaction", "severe", 30, interaction),
            PenaltyEntry("adherence", "Synthetic adherence", "mild", 5, adherence),
        ])
    before = copy.deepcopy(_serialize_safety_score_result(score))
    good = selection_for_prompt
    bad = {"rejected": response(ORIGINAL_CLAIM), "empty": "", "malformed": "not JSON"}
    if outcome == "success":
        providers = (Provider("gemini", good),)
    elif outcome == "fallback":
        providers = (Provider("gemini", response(ORIGINAL_CLAIM)), Provider("openrouter", good))
    elif outcome == "failed":
        providers = (Provider("gemini", error=LLMProviderError("gemini", "synthetic failure")),)
    else:
        providers = (Provider("gemini", bad[outcome]),)
    monkeypatch.setattr(llm_service, "_PROVIDERS", providers)

    class Session:
        def __init__(self):
            self.rows = []
            self.commits = 0

        def add(self, row):
            self.rows.append(row)

        async def commit(self):
            self.commits += 1

        async def refresh(self, row):
            pass

        async def execute(self, *args, **kwargs):
            raise AssertionError("No database allowed")

    db = Session()
    state = dict(patient_id=context.patient_id, patient_context=context,
                 safety_score_result=score, evidence_bundle=bundle, timeline_context=timeline)
    state.update(await _llm_explanation_node(db)(state))
    persisted = await _persist_node(db)(state)
    row = next(row for row in db.rows if isinstance(row, AnalysisRun))
    event = next(row for row in db.rows if isinstance(row, TimelineEvent))
    assert db.commits == 1
    assert row.patient_id == context.patient_id == event.patient_id
    assert persisted["analysis_run_id"] == row.id == event.ref_id
    assert row.deterministic_result == before == _serialize_safety_score_result(score)
    assert row.safety_score == 60 and row.risk_level == "moderate"
    if outcome in ["success", "fallback"]:
        assert "Recorded engine interaction finding" in row.llm_reasoning
        assert "Recorded engine adr finding" in row.llm_reasoning
        assert "Recorded engine adherence finding" in row.llm_reasoning
        assert "cannot independently establish a cause" in row.llm_reasoning
        assert state["llm_error"] is None
    else:
        assert state["llm_error"]
        assert all(getattr(row, field) is None for field in [
            "llm_summary", "llm_reasoning", "llm_recommendations",
            "confidence_score", "confidence_level",
        ])




@pytest.mark.asyncio
@pytest.mark.parametrize("claim", [
    "The patient has a rash.",
    "The medication is responsible for the patient's symptoms.",
])
async def test_before_after_pattern_pass_is_not_evidence_support(monkeypatch, claim):
    # The former free-prose screen accepted these structure-valid assertions.
    assert llm_service._parse_and_validate(response(claim)).reasoning == claim
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", response(claim)),))
    with pytest.raises(LLMExplanationError):
        await generate_explanation(*scenario())


@pytest.mark.asyncio
async def test_duplicate_field_even_in_otherwise_valid_selection_is_rejected(monkeypatch):
    def duplicate(prompt):
        raw = selection_for_prompt(prompt)
        return raw[:-1] + ', "confidence_score": 40}'
    monkeypatch.setattr(llm_service, "_PROVIDERS", (Provider("gemini", duplicate),))
    with pytest.raises(LLMExplanationError, match="invalid_response"):
        await generate_explanation(*scenario())


@pytest.fixture(autouse=True)
def _isolated_model_cooldowns(monkeypatch):
    # Each unit case owns fresh process state; concurrency/recovery across
    # requests is exercised explicitly in test_llm_failover.py.
    from app.services.llm_failover import CooldownRegistry
    monkeypatch.setattr(llm_service, "_COOLDOWNS", CooldownRegistry())
