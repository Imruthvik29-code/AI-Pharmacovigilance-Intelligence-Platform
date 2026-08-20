"""
DB-free regression tests for the LLM explanation node's fail-closed contract.

Why this file exists
--------------------
`app/services/langgraph_workflow.py`'s `llm_explanation` node sits between
the deterministic analysis layer and the Persist Node. Everything upstream
of it (patient context, safety score, evidence, timeline) is already
computed by the time it runs, and everything downstream of it (the
`analysis_runs` row + its `analysis_run` timeline event) is the product of
record. The node therefore has one hard contract:

    **No failure of the LLM layer -- documented or not -- may prevent the
    deterministic analysis from being persisted.**

Before this suite, the node caught only `NotImplementedError` and
`LLMExplanationError`. Anything else (a raw `httpx.ConnectError` that
escaped `llm_service.py`'s normalization, a `TypeError`/`RuntimeError`
from a bug in the explanation path, a misbehaving provider client)
propagated out of `graph.ainvoke()` and aborted the run *before* the
Persist Node executed -- discarding a perfectly valid deterministic
result: no `analysis_runs` row, no timeline event, no `analysis_run_id`.
These tests pin the hardened behavior so that regression cannot return.

The one exception that must STILL propagate is `asyncio.CancelledError`
(a `BaseException` since Python 3.8): swallowing it would break
cooperative task cancellation and leave callers awaiting a task that
believes it was cancelled. Hence the node uses `except Exception`, never
a bare `except` -- and `test_cancelled_error_is_not_swallowed_*` proves it.

Test strategy (no database, no network, no API keys)
----------------------------------------------------
- The four deterministic node dependencies (`build_patient_context`,
  `calculate_safety_score`, `retrieve_evidence`, `build_timeline_context`)
  are monkeypatched at the `langgraph_workflow` module attributes they were
  imported into, returning fixed in-memory dataclasses. No engine runs, no
  query is issued.
- `_FakeSession` stands in for `AsyncSession`, capturing `add()`ed ORM
  objects and `commit()` calls -- the same minimal in-memory fake-session
  approach already used by `test_ingredient_resolver.py` and
  `test_import_rxnorm.py`. Its `execute()` fails loudly, which is itself an
  assertion that this suite never touches the database.
- LLM behavior is injected at the `langgraph_workflow.generate_explanation`
  seam, matching the existing convention in `test_langgraph_workflow.py`.
- The `llm_service`-level tests at the bottom mock the
  `llm_service._PROVIDERS` seam, matching `test_llm_service.py`.

Run with:  pytest backend/tests/test_langgraph_llm_failure_handling.py -v
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
import pytest

from app.analysis.adherence_engine import AdherenceFinding
from app.analysis.adr_engine import ADRFinding
from app.analysis.drug_interaction_engine import DrugInteractionFinding
from app.analysis.safety_score_engine import PenaltyEntry, SafetyScoreResult
from app.analysis.timeline_engine import TimelineContext
from app.db.models import AnalysisRun, TimelineEvent
from app.services import langgraph_workflow as workflow_module
from app.services import llm_service
from app.services.evidence_retrieval import EvidenceBundle
from app.services.langgraph_workflow import (
    _llm_explanation_node,
    _serialize_safety_score_result,
    run_analysis,
)
from app.services.llm_providers import LLMCompletion, LLMProviderError
from app.services.llm_service import LLMExplanationError, LLMExplanationResult
from app.services.patient_context_builder import PatientContext

PATIENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ---------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------


class _FakeSession:
    """
    Minimal async stand-in for `AsyncSession`, capturing what the Persist
    Node writes without a database.

    Only the three methods `_persist_node` actually uses are implemented
    (`add`, `commit`, `refresh`). `execute()` raises: this suite must never
    issue a query, so a query attempt is a test-design bug, not a silent
    no-op.
    """

    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.refreshed: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)

    async def execute(self, *args, **kwargs):  # pragma: no cover - guard
        raise AssertionError(
            "_FakeSession.execute() called -- these tests are DB-free and must "
            "not issue queries."
        )

    # -- convenience accessors -------------------------------------------------

    @property
    def analysis_runs(self) -> list[AnalysisRun]:
        return [o for o in self.added if isinstance(o, AnalysisRun)]

    @property
    def timeline_events(self) -> list[TimelineEvent]:
        return [o for o in self.added if isinstance(o, TimelineEvent)]


class _CallCounter:
    """
    Wraps an LLM behavior so tests can assert `generate_explanation` was
    invoked exactly once -- i.e. the hardened node does not retry, re-enter,
    or double-call the LLM on the failure path.
    """

    def __init__(self, behavior):
        self.calls: list[dict] = []
        self._behavior = behavior

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return await self._behavior(**kwargs)

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _raises(exc_factory):
    """Build an async `generate_explanation` stand-in that raises."""

    async def _behavior(**kwargs):
        raise exc_factory()

    return _behavior


def _returns(result: LLMExplanationResult):
    """Build an async `generate_explanation` stand-in that succeeds."""

    async def _behavior(**kwargs):
        return result

    return _behavior


# ---------------------------------------------------------------------
# Deterministic fixture data -- a non-trivial result so the persisted
# payload is worth asserting on (1 interaction + 1 ADR + 1 adherence
# finding, 3 penalties, score 25 / high risk).
# ---------------------------------------------------------------------


def _patient_context() -> PatientContext:
    return PatientContext(
        patient_id=PATIENT_ID,
        name="Fail-Closed Test Patient",
        age=72,
        sex="female",
        weight_kg=64.0,
        renal_flag=False,
        hepatic_flag=False,
        active_conditions=[],
        active_medications=[],
        active_symptoms=[],
    )


def _interaction_finding() -> DrugInteractionFinding:
    return DrugInteractionFinding(
        interaction_rule_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        drug_a_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        drug_a_name="Warfarin",
        drug_b_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        drug_b_name="Aspirin",
        severity="severe",
        mechanism="Additive anticoagulant effect increases bleeding risk.",
        recommendation="Discuss with the prescriber.",
        source="seed",
    )


def _adr_finding() -> ADRFinding:
    return ADRFinding(
        adr_rule_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        drug_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        drug_name="Warfarin",
        reaction_description="Bleeding / bruising",
        severity="severe",
        frequency_class="common",
        source="seed",
    )


def _adherence_finding() -> AdherenceFinding:
    return AdherenceFinding(
        medication_id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
        drug_name="Warfarin",
        taken=6,
        missed=4,
        skipped=0,
        due=10,
        adherence_rate=0.6,
    )


def _safety_score_result() -> SafetyScoreResult:
    interaction = _interaction_finding()
    adr = _adr_finding()
    adherence = _adherence_finding()
    return SafetyScoreResult(
        safety_score=25,
        risk_level="high",
        starting_score=100,
        total_points_deducted=75,
        interaction_findings=[interaction],
        adr_findings=[adr],
        adherence_findings=[adherence],
        penalties=[
            PenaltyEntry(
                category="interaction",
                description="Severe interaction: Warfarin + Aspirin",
                severity="severe",
                points=30,
                source=interaction,
            ),
            PenaltyEntry(
                category="adr",
                description="Severe ADR risk: Bleeding / bruising (Warfarin)",
                severity="severe",
                points=30,
                source=adr,
            ),
            PenaltyEntry(
                category="adherence",
                description="Adherence 60% for Warfarin",
                severity="moderate",
                points=15,
                source=adherence,
            ),
        ],
    )


def _evidence_bundle() -> EvidenceBundle:
    return EvidenceBundle(interaction_evidence=[], adr_evidence=[], adherence_evidence=[])


def _timeline_context() -> TimelineContext:
    return TimelineContext(patient_id=PATIENT_ID, entries=[])


def _successful_llm_result() -> LLMExplanationResult:
    return LLMExplanationResult(
        summary="Two of your medicines together raise bleeding risk.",
        reasoning="Warfarin and Aspirin have an additive anticoagulant effect.",
        recommendations="Discuss this with your prescriber or pharmacist.",
        confidence_score=85,
        confidence_level="high",
    )


def _node_state() -> dict:
    """The exact state slice `_llm_explanation_node` reads."""
    return {
        "patient_id": PATIENT_ID,
        "patient_context": _patient_context(),
        "safety_score_result": _safety_score_result(),
        "evidence_bundle": _evidence_bundle(),
        "timeline_context": _timeline_context(),
    }


@pytest.fixture
def deterministic_nodes(monkeypatch):
    """
    Replace every DB-touching node dependency with a pure in-memory stub so
    the whole graph can run without a database. Patched at the
    `langgraph_workflow` module attributes (the names the node factories
    actually resolve at call time), mirroring how `test_langgraph_workflow.py`
    patches `generate_explanation`.
    """

    async def _build_patient_context(patient_id, db):
        return _patient_context()

    async def _calculate_safety_score(patient_id, db):
        return _safety_score_result()

    async def _retrieve_evidence(patient_id, db, safety_score_result):
        return _evidence_bundle()

    async def _build_timeline_context(patient_id, db):
        return _timeline_context()

    monkeypatch.setattr(workflow_module, "build_patient_context", _build_patient_context)
    monkeypatch.setattr(workflow_module, "calculate_safety_score", _calculate_safety_score)
    monkeypatch.setattr(workflow_module, "retrieve_evidence", _retrieve_evidence)
    monkeypatch.setattr(workflow_module, "build_timeline_context", _build_timeline_context)


# Every LLM failure mode the node must absorb. `NotImplementedError` and
# `LLMExplanationError` were already handled (regression guard: they must
# stay handled); `httpx.ConnectError` and `RuntimeError` are the previously
# fatal cases this PR fixes.
FAILURE_MODES = [
    pytest.param(
        lambda: LLMExplanationError("All configured LLM providers failed: gemini: HTTP 503"),
        "all configured llm providers failed",
        id="LLMExplanationError",
    ),
    pytest.param(
        lambda: NotImplementedError("LLM explanation is not implemented yet."),
        "not implemented",
        id="NotImplementedError",
    ),
    pytest.param(
        lambda: httpx.ConnectError("[Errno 111] Connection refused"),
        "connect",
        id="httpx.ConnectError",
    ),
    pytest.param(
        lambda: RuntimeError("provider client exploded"),
        "runtime",
        id="RuntimeError",
    ),
]


# =====================================================================
# 1. Node-level: every failure mode becomes the fail-closed result
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_factory, expected_fragment", FAILURE_MODES)
async def test_node_returns_fail_closed_result_for_every_failure_mode(
    exc_factory, expected_fragment, monkeypatch
):
    """`llm_result is None` + a non-empty, informative `llm_error`."""
    monkeypatch.setattr(workflow_module, "generate_explanation", _raises(exc_factory))
    node = _llm_explanation_node(_FakeSession())

    out = await node(_node_state())

    assert out["llm_result"] is None
    assert isinstance(out["llm_error"], str)
    assert out["llm_error"].strip() != ""
    assert expected_fragment in out["llm_error"].lower()


@pytest.mark.asyncio
async def test_node_success_path_is_unchanged(monkeypatch):
    """The hardening must not disturb the happy path."""
    expected = _successful_llm_result()
    monkeypatch.setattr(workflow_module, "generate_explanation", _returns(expected))
    node = _llm_explanation_node(_FakeSession())

    out = await node(_node_state())

    assert out["llm_result"] == expected
    assert out["llm_error"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory",
    [
        pytest.param(lambda: RuntimeError(), id="RuntimeError-no-message"),
        pytest.param(lambda: ValueError(""), id="ValueError-empty-message"),
        pytest.param(lambda: KeyError(), id="KeyError-no-message"),
    ],
)
async def test_node_llm_error_is_non_empty_even_for_messageless_exceptions(
    exc_factory, monkeypatch
):
    """
    `llm_error` is the only in-state signal distinguishing "the explanation
    failed" from "no explanation was attempted", so it must never collapse
    to an empty string just because `str(exc)` is empty.
    """
    monkeypatch.setattr(workflow_module, "generate_explanation", _raises(exc_factory))
    node = _llm_explanation_node(_FakeSession())

    out = await node(_node_state())

    assert out["llm_result"] is None
    assert out["llm_error"].strip() != ""
    # Class name is always present so the message stays diagnostic.
    assert exc_factory().__class__.__name__ in out["llm_error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory",
    [
        pytest.param(lambda: TypeError("unhashable type"), id="TypeError"),
        pytest.param(lambda: AttributeError("'NoneType' has no attribute 'strip'"), id="AttributeError"),
        pytest.param(lambda: httpx.ReadTimeout("timed out"), id="httpx.ReadTimeout"),
        pytest.param(lambda: httpx.HTTPStatusError("500", request=None, response=None), id="httpx.HTTPStatusError"),
        pytest.param(lambda: LLMProviderError("gemini", "unnormalized"), id="LLMProviderError"),
        pytest.param(lambda: ZeroDivisionError("division by zero"), id="ZeroDivisionError"),
    ],
)
async def test_node_absorbs_any_unexpected_exception_type(exc_factory, monkeypatch):
    """The catch is by category (`Exception`), not an enumerated allow-list."""
    monkeypatch.setattr(workflow_module, "generate_explanation", _raises(exc_factory))
    node = _llm_explanation_node(_FakeSession())

    out = await node(_node_state())

    assert set(out) == {"llm_result", "llm_error"}
    assert out["llm_result"] is None
    assert out["llm_error"].strip() != ""


# =====================================================================
# 2. Node-level: CancelledError must NOT be swallowed
# =====================================================================


@pytest.mark.asyncio
async def test_cancelled_error_is_not_swallowed_by_the_node(monkeypatch):
    """
    `asyncio.CancelledError` is a `BaseException` (Python 3.8+). Because the
    node catches `Exception` rather than using a bare `except`, cancellation
    still propagates -- swallowing it would break cooperative cancellation
    and strand the caller.
    """
    monkeypatch.setattr(
        workflow_module, "generate_explanation", _raises(asyncio.CancelledError)
    )
    node = _llm_explanation_node(_FakeSession())

    with pytest.raises(asyncio.CancelledError):
        await node(_node_state())


@pytest.mark.asyncio
async def test_other_base_exceptions_are_not_swallowed_by_the_node(monkeypatch):
    """Same reasoning as cancellation: `BaseException`s are not ours to eat."""
    monkeypatch.setattr(
        workflow_module, "generate_explanation", _raises(KeyboardInterrupt)
    )
    node = _llm_explanation_node(_FakeSession())

    with pytest.raises(KeyboardInterrupt):
        await node(_node_state())


@pytest.mark.asyncio
async def test_real_task_cancellation_still_cancels_the_node(monkeypatch):
    """
    End-to-end proof of the same property via the real cancellation
    machinery (not just a manually raised `CancelledError`): a task awaiting
    the node must actually end up cancelled.
    """
    started = asyncio.Event()

    async def _hangs(**kwargs):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(workflow_module, "generate_explanation", _hangs)
    node = _llm_explanation_node(_FakeSession())

    task = asyncio.create_task(node(_node_state()))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


# =====================================================================
# 3. Node-level: logging behavior
# =====================================================================


@pytest.mark.asyncio
async def test_unexpected_exception_is_logged_with_logger_exception(caplog, monkeypatch):
    """
    Unexpected failures are still bugs: they must be logged at ERROR with a
    full traceback (`logger.exception`), not quietly downgraded to the
    WARNING used for the two documented failure modes.
    """
    monkeypatch.setattr(
        workflow_module, "generate_explanation", _raises(lambda: RuntimeError("boom"))
    )
    node = _llm_explanation_node(_FakeSession())

    with caplog.at_level(logging.DEBUG, logger="app.langgraph_workflow"):
        out = await node(_node_state())

    assert out["llm_result"] is None
    records = [r for r in caplog.records if r.name == "app.langgraph_workflow"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None  # logger.exception() attaches the traceback
    assert record.exc_info[0] is RuntimeError
    assert getattr(record, "patient_id", None) == PATIENT_ID


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory",
    [
        pytest.param(lambda: LLMExplanationError("all providers failed"), id="LLMExplanationError"),
        pytest.param(lambda: NotImplementedError("nope"), id="NotImplementedError"),
    ],
)
async def test_documented_failures_still_log_at_warning_without_traceback(
    exc_factory, caplog, monkeypatch
):
    """Existing behavior for the two documented modes is preserved exactly."""
    monkeypatch.setattr(workflow_module, "generate_explanation", _raises(exc_factory))
    node = _llm_explanation_node(_FakeSession())

    with caplog.at_level(logging.DEBUG, logger="app.langgraph_workflow"):
        await node(_node_state())

    records = [r for r in caplog.records if r.name == "app.langgraph_workflow"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is None


# =====================================================================
# 4. Node-level: generate_explanation is called exactly once
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_factory, _expected_fragment", FAILURE_MODES)
async def test_node_calls_generate_explanation_exactly_once_on_failure(
    exc_factory, _expected_fragment, monkeypatch
):
    """No hidden retry loop: one failed attempt, one fail-closed result."""
    counter = _CallCounter(_raises(exc_factory))
    monkeypatch.setattr(workflow_module, "generate_explanation", counter)

    node = _llm_explanation_node(_FakeSession())
    await node(_node_state())

    assert counter.call_count == 1


@pytest.mark.asyncio
async def test_node_calls_generate_explanation_exactly_once_on_success(monkeypatch):
    counter = _CallCounter(_returns(_successful_llm_result()))
    monkeypatch.setattr(workflow_module, "generate_explanation", counter)

    node = _llm_explanation_node(_FakeSession())
    await node(_node_state())

    assert counter.call_count == 1


@pytest.mark.asyncio
async def test_node_passes_all_four_deterministic_inputs_to_the_llm(monkeypatch):
    """Guards the keyword contract the node calls `generate_explanation` with."""
    counter = _CallCounter(_raises(lambda: RuntimeError("boom")))
    monkeypatch.setattr(workflow_module, "generate_explanation", counter)

    node = _llm_explanation_node(_FakeSession())
    state = _node_state()
    await node(state)

    assert set(counter.calls[0]) == {
        "patient_context",
        "safety_score_result",
        "evidence_bundle",
        "timeline_context",
    }
    assert counter.calls[0]["safety_score_result"] is state["safety_score_result"]


# =====================================================================
# 5. Workflow-level: deterministic persistence survives any LLM failure
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_factory, expected_fragment", FAILURE_MODES)
async def test_workflow_persists_deterministic_result_despite_llm_failure(
    exc_factory, expected_fragment, deterministic_nodes, monkeypatch
):
    """
    The core contract of this PR. For every LLM failure mode the complete
    graph must still reach the Persist Node and write the analysis run.

    Before the fix, `httpx.ConnectError` and `RuntimeError` propagated out of
    `run_analysis`, leaving `db.added == []` and `commit_count == 0`.
    """
    counter = _CallCounter(_raises(exc_factory))
    monkeypatch.setattr(workflow_module, "generate_explanation", counter)
    db = _FakeSession()

    final_state = await run_analysis(PATIENT_ID, db)

    # -- the run was persisted ------------------------------------------------
    assert db.commit_count == 1
    assert len(db.analysis_runs) == 1
    run = db.analysis_runs[0]
    assert run.patient_id == PATIENT_ID
    assert run.analysis_version == "v1.0"

    # -- with the full, untouched deterministic payload -----------------------
    assert run.safety_score == 25
    assert run.risk_level == "high"
    assert run.deterministic_result == _serialize_safety_score_result(_safety_score_result())
    assert len(run.deterministic_result["interaction_findings"]) == 1
    assert len(run.deterministic_result["adr_findings"]) == 1
    assert len(run.deterministic_result["adherence_findings"]) == 1
    assert len(run.deterministic_result["penalties"]) == 3
    assert run.deterministic_result["total_points_deducted"] == 75
    assert "timeline_context" not in run.deterministic_result

    # -- and NULL LLM columns, never fabricated content -----------------------
    assert run.llm_summary is None
    assert run.llm_reasoning is None
    assert run.llm_recommendations is None
    assert run.confidence_score is None
    assert run.confidence_level is None

    # -- the failure is reported in state, not hidden -------------------------
    assert final_state["llm_result"] is None
    assert expected_fragment in final_state["llm_error"].lower()

    # -- exactly one LLM attempt ---------------------------------------------
    assert counter.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_factory, _expected_fragment", FAILURE_MODES)
async def test_workflow_returns_analysis_run_id_despite_llm_failure(
    exc_factory, _expected_fragment, deterministic_nodes, monkeypatch
):
    """
    `analysis_run_id` is how the API layer re-fetches the persisted row, so
    the workflow must still produce it -- and it must match the row actually
    added to the session.
    """
    monkeypatch.setattr(workflow_module, "generate_explanation", _raises(exc_factory))
    db = _FakeSession()

    final_state = await run_analysis(PATIENT_ID, db)

    assert "analysis_run_id" in final_state
    assert isinstance(final_state["analysis_run_id"], uuid.UUID)
    assert final_state["analysis_run_id"] == db.analysis_runs[0].id
    assert db.refreshed == [db.analysis_runs[0]]


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_factory, _expected_fragment", FAILURE_MODES)
async def test_workflow_logs_timeline_event_despite_llm_failure(
    exc_factory, _expected_fragment, deterministic_nodes, monkeypatch
):
    """
    The `analysis_run` timeline event is written in the same transaction as
    the run itself -- an LLM failure must not cost us that either, and the
    event must honestly report that no explanation is available.
    """
    monkeypatch.setattr(workflow_module, "generate_explanation", _raises(exc_factory))
    db = _FakeSession()

    final_state = await run_analysis(PATIENT_ID, db)

    assert len(db.timeline_events) == 1
    event = db.timeline_events[0]
    assert event.event_type == "analysis_run"
    assert event.patient_id == PATIENT_ID
    assert event.ref_id == final_state["analysis_run_id"]
    assert event.payload["safety_score"] == 25
    assert event.payload["risk_level"] == "high"
    assert event.payload["llm_explanation_available"] is False


@pytest.mark.asyncio
async def test_workflow_deterministic_payload_identical_across_all_llm_outcomes(
    deterministic_nodes, monkeypatch
):
    """
    Safety invariant, extended to the previously-fatal failure modes: the
    persisted deterministic layer is byte-identical whether the LLM succeeds,
    fails in a documented way, or blows up unexpectedly. Only the `llm_*`
    columns may differ.
    """
    behaviors = [
        ("success", _returns(_successful_llm_result())),
        ("llm_explanation_error", _raises(lambda: LLMExplanationError("all providers failed"))),
        ("not_implemented", _raises(lambda: NotImplementedError("nope"))),
        ("connect_error", _raises(lambda: httpx.ConnectError("refused"))),
        ("runtime_error", _raises(lambda: RuntimeError("boom"))),
    ]

    observed = []
    for _label, behavior in behaviors:
        monkeypatch.setattr(workflow_module, "generate_explanation", behavior)
        db = _FakeSession()
        await run_analysis(PATIENT_ID, db)
        run = db.analysis_runs[0]
        observed.append(
            {
                "safety_score": run.safety_score,
                "risk_level": run.risk_level,
                "deterministic_result": run.deterministic_result,
                "llm_summary": run.llm_summary,
            }
        )

    first = observed[0]
    for other in observed[1:]:
        assert other["safety_score"] == first["safety_score"]
        assert other["risk_level"] == first["risk_level"]
        assert other["deterministic_result"] == first["deterministic_result"]

    # Only the LLM column varied: populated on success, NULL on every failure.
    assert observed[0]["llm_summary"] == _successful_llm_result().summary
    assert all(o["llm_summary"] is None for o in observed[1:])


@pytest.mark.asyncio
async def test_workflow_success_path_still_persists_llm_columns(
    deterministic_nodes, monkeypatch
):
    """Regression guard: hardening the failure path did not break the happy path."""
    expected = _successful_llm_result()
    monkeypatch.setattr(workflow_module, "generate_explanation", _returns(expected))
    db = _FakeSession()

    final_state = await run_analysis(PATIENT_ID, db)
    run = db.analysis_runs[0]

    assert final_state["llm_error"] is None
    assert run.llm_summary == expected.summary
    assert run.llm_reasoning == expected.reasoning
    assert run.llm_recommendations == expected.recommendations
    assert run.confidence_score == expected.confidence_score
    assert run.confidence_level == expected.confidence_level
    assert db.timeline_events[0].payload["llm_explanation_available"] is True


@pytest.mark.asyncio
async def test_workflow_propagates_cancellation_and_does_not_persist(
    deterministic_nodes, monkeypatch
):
    """
    Cancellation is not a "failure to explain" -- it is the caller tearing the
    run down. It must propagate out of `run_analysis`, and precisely because
    it is not absorbed, nothing is persisted.
    """
    monkeypatch.setattr(
        workflow_module, "generate_explanation", _raises(asyncio.CancelledError)
    )
    db = _FakeSession()

    with pytest.raises(asyncio.CancelledError):
        await run_analysis(PATIENT_ID, db)

    assert db.added == []
    assert db.commit_count == 0


# =====================================================================
# 6. llm_service-level: anticipated failures normalize to
#    LLMExplanationError so the node's safety net stays a formality
# =====================================================================


class _FakeProvider:
    """
    Same seam and shape as `test_llm_service.py::_FakeProvider` -- a minimal
    stand-in for GeminiProvider/OpenRouterProvider.
    """

    def __init__(self, name: str, *, raw=None, error: Exception | None = None):
        self.name = name
        self.model = f"fake-{name}-model"
        self._raw = raw
        self._error = error
        self.call_count = 0

    async def complete(self, prompt: str, *, timeout_seconds: float) -> LLMCompletion:
        self.call_count += 1
        if self._error is not None:
            raise self._error
        return LLMCompletion(text=self._raw)


async def _generate() -> LLMExplanationResult:
    return await llm_service.generate_explanation(
        patient_context=_patient_context(),
        safety_score_result=_safety_score_result(),
        evidence_bundle=_evidence_bundle(),
        timeline_context=_timeline_context(),
    )


VALID_JSON = (
    '{"summary": "All clear.", "reasoning": "No findings were detected.", '
    '"recommendations": "Continue routine monitoring.", "confidence_score": 95, '
    '"confidence_level": "high"}'
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transport_error",
    [
        pytest.param(httpx.ConnectError("connection refused"), id="ConnectError"),
        pytest.param(httpx.ReadTimeout("read timed out"), id="ReadTimeout"),
        pytest.param(httpx.ConnectTimeout("connect timed out"), id="ConnectTimeout"),
        pytest.param(httpx.RemoteProtocolError("peer closed connection"), id="RemoteProtocolError"),
    ],
)
async def test_unnormalized_transport_error_from_every_provider_becomes_llm_explanation_error(
    transport_error, monkeypatch
):
    """
    `llm_providers.py` normalizes httpx errors to `LLMProviderError` today, so
    this is defense in depth: if a provider ever leaks a raw httpx error,
    `generate_explanation` must still raise only `LLMExplanationError` --
    the single exception type its callers are documented to expect.
    """
    gemini = _FakeProvider("gemini", error=transport_error)
    openrouter = _FakeProvider("openrouter", error=transport_error)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(LLMExplanationError) as excinfo:
        await _generate()

    assert "All configured LLM providers failed" in str(excinfo.value)
    assert gemini.call_count == 1
    assert openrouter.call_count == 1


@pytest.mark.asyncio
async def test_unnormalized_transport_error_still_falls_back_to_the_next_provider(
    monkeypatch,
):
    """A leaked httpx error must not short-circuit the fallback chain."""
    gemini = _FakeProvider("gemini", error=httpx.ConnectError("refused"))
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    result = await _generate()

    assert result.summary == "All clear."
    assert gemini.call_count == 1
    assert openrouter.call_count == 1


@pytest.mark.asyncio
async def test_non_string_response_text_is_a_parse_failure_not_an_attribute_error(
    monkeypatch,
):
    """
    A provider returning a non-`str` payload is a parse failure, not a crash:
    without the guard, `raw.strip()` would raise a bare `AttributeError`,
    which would both skip the fallback provider and escape the documented
    `LLMExplanationError` contract.
    """
    gemini = _FakeProvider("gemini", raw={"unexpected": "structure"})
    openrouter = _FakeProvider("openrouter", raw=None)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(LLMExplanationError):
        await _generate()

    assert gemini.call_count == 1
    assert openrouter.call_count == 1


@pytest.mark.asyncio
async def test_non_string_response_text_still_falls_back_to_the_next_provider(monkeypatch):
    gemini = _FakeProvider("gemini", raw=12345)
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    result = await _generate()

    assert result.confidence_score == 95
    assert openrouter.call_count == 1


@pytest.mark.asyncio
async def test_provider_error_and_parse_error_still_normalize_as_before(monkeypatch):
    """The pre-existing normalization paths are untouched by this PR."""
    gemini = _FakeProvider("gemini", error=LLMProviderError("gemini", "HTTP 503", retryable=True))
    openrouter = _FakeProvider("openrouter", raw="not json at all")
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(LLMExplanationError) as excinfo:
        await _generate()

    message = str(excinfo.value)
    assert "gemini: HTTP 503" in message
    assert "openrouter" in message


@pytest.mark.asyncio
async def test_llm_service_does_not_swallow_cancellation(monkeypatch):
    """
    The service-level catches are narrow (`LLMProviderError`,
    `httpx.HTTPError`, `LLMExplanationError`) -- cancellation passes straight
    through rather than being reported as "all providers failed".
    """
    gemini = _FakeProvider("gemini", error=asyncio.CancelledError())
    openrouter = _FakeProvider("openrouter", raw=VALID_JSON)
    monkeypatch.setattr(llm_service, "_PROVIDERS", (gemini, openrouter))

    with pytest.raises(asyncio.CancelledError):
        await _generate()

    assert openrouter.call_count == 0  # chain aborted, not continued
