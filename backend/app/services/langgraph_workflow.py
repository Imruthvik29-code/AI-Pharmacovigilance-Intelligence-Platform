"""
LangGraph Workflow (Phase 14).

Wires the full analysis pipeline described in spec section 8 into a
single `langgraph.graph.StateGraph`, composing every deterministic
service built in Phases 10-14:

    [Input: patient_id]
            |
            v
    Patient Context Builder Node   (patient_context_builder.py)
            |
            v
    Safety Score Node              (safety_score_engine.calculate_safety_score)
            |
            v
    Evidence Retrieval Node        (evidence_retrieval.retrieve_evidence)
            |
            v
    Timeline Engine Node           (timeline_engine.build_timeline_context)
            |
            v
    LLM Explanation Node           (llm_service.generate_explanation)
            |
            v
    Persist Node                   (writes analysis_runs + analysis_run
                                     timeline event)
            |
            v
        [Output]

## Why the Safety Score node is not "three separate engine calls"

Spec section 8's diagram shows a "Deterministic Analysis Layer" box
containing the Drug Interaction / ADR / Adherence / Timeline engines,
merged by the Safety Score Engine. Phase 12's `calculate_safety_score()`
already internally calls `detect_drug_interactions()`, `detect_adrs()`,
and `analyze_adherence()`, and its returned `SafetyScoreResult` exposes
all three raw finding lists alongside the composite score. Calling those
three engines again directly in this graph would duplicate work Phase 12
already does and was explicitly designed to expose (see
`SafetyScoreResult`'s docstring). This graph therefore has a single
"Safety Score" node that stands in for that whole merged sub-layer --
confirmed with the project owner during Phase 14 planning. The Timeline
Engine is kept genuinely separate (see below) since Phase 12 does not
merge it.

## Why the Timeline Engine node runs after Evidence Retrieval

Confirmed with the project owner during Phase 14 planning: timeline
context is explanatory/narrative context for the LLM step, not an input
to deterministic scoring. Evidence Retrieval (Phase 13) already supplies
finding-scoped personal evidence; the Timeline Engine supplies the
broader, unscoped patient narrative. Running it after Evidence Retrieval
(rather than in parallel with the other analysis engines) keeps the
graph's linear structure simple and keeps "things that feed the score"
separate from "things that only feed the eventual explanation."

## Persistence scope

Per project-owner direction: the Persist Node writes only the
deterministic findings/penalties/score/risk_level to
`analysis_runs.deterministic_result` -- `timeline_context` is
deliberately NOT included in that JSONB blob. The `timeline_events`
table is already the single source of truth for timeline data; a second,
denormalized copy inside `deterministic_result` would create a second
source of truth for the same facts. `timeline_context` exists only
in-memory, as an input to the LLM Explanation Node.

## LLM Explanation Node behavior

Calls `llm_service.generate_explanation()` (Phase 15). This node catches
`NotImplementedError` (retained defensively; no longer raised by the
Phase 15 implementation, but kept in case a future change to
llm_service.py reintroduces an unimplemented path) and
`LLMExplanationError` (Phase 15's real failure mode -- every configured
provider either failed or returned output that failed schema
validation). Any other, unexpected exception propagates and fails the
whole graph run, since that would indicate a genuine bug rather than a
documented failure mode. On either caught exception, the node stores
`llm_result: None` and a human-readable `llm_error` message in state;
nothing is fabricated, and the deterministic pipeline still persists via
the Persist Node regardless of this step's outcome.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.adherence_engine import AdherenceFinding
from app.analysis.adr_engine import ADRFinding
from app.analysis.drug_interaction_engine import DrugInteractionFinding
from app.analysis.safety_score_engine import PenaltyEntry, SafetyScoreResult, calculate_safety_score
from app.analysis.timeline_engine import TimelineContext, build_timeline_context
from app.db.models import AnalysisRun
from app.services.evidence_retrieval import EvidenceBundle, retrieve_evidence
from app.services.llm_service import LLMExplanationError, LLMExplanationResult, generate_explanation
from app.services.patient_context_builder import PatientContext, build_patient_context
from app.services.timeline_writer import log_timeline_event

logger = logging.getLogger("app.langgraph_workflow")


class AnalysisState(TypedDict, total=False):
    """
    Strongly typed state threaded through every node of the workflow.

    `total=False` since fields populate progressively as each node
    completes -- only `patient_id` is guaranteed present on the initial
    invocation. The DB session is intentionally NOT part of this state
    (it is a resource/dependency, not analysis data) -- node functions
    close over it instead, via `_build_graph`'s factory functions below.
    """

    patient_id: uuid.UUID
    patient_context: PatientContext
    safety_score_result: SafetyScoreResult
    evidence_bundle: EvidenceBundle
    timeline_context: TimelineContext
    llm_result: LLMExplanationResult | None
    llm_error: str | None
    analysis_run_id: uuid.UUID


# ---------------------------------------------------------------------
# Serialization -- SafetyScoreResult -> JSON-safe dict for
# analysis_runs.deterministic_result. Excludes PenaltyEntry.source (the
# live finding object reference) since it is not JSON-serializable and
# is only needed for in-memory traceability (Phase 12/13's design);
# the penalty's own `description` field already documents the "why" in
# readable prose, and the full finding is separately present in this
# same dict under interaction_findings/adr_findings/adherence_findings.
# ---------------------------------------------------------------------


def _serialize_interaction_finding(finding: DrugInteractionFinding) -> dict:
    return {
        "interaction_rule_id": str(finding.interaction_rule_id),
        "drug_a_id": str(finding.drug_a_id),
        "drug_a_name": finding.drug_a_name,
        "drug_b_id": str(finding.drug_b_id),
        "drug_b_name": finding.drug_b_name,
        "severity": finding.severity,
        "mechanism": finding.mechanism,
        "recommendation": finding.recommendation,
        "source": finding.source,
    }


def _serialize_adr_finding(finding: ADRFinding) -> dict:
    return {
        "adr_rule_id": str(finding.adr_rule_id),
        "drug_id": str(finding.drug_id),
        "drug_name": finding.drug_name,
        "reaction_description": finding.reaction_description,
        "severity": finding.severity,
        "frequency_class": finding.frequency_class,
        "source": finding.source,
    }


def _serialize_adherence_finding(finding: AdherenceFinding) -> dict:
    return {
        "medication_id": str(finding.medication_id),
        "drug_name": finding.drug_name,
        "taken": finding.taken,
        "missed": finding.missed,
        "skipped": finding.skipped,
        "due": finding.due,
        "adherence_rate": finding.adherence_rate,
    }


def _serialize_penalty(penalty: PenaltyEntry) -> dict:
    return {
        "category": penalty.category,
        "description": penalty.description,
        "severity": penalty.severity,
        "points": penalty.points,
    }


def _serialize_safety_score_result(result: SafetyScoreResult) -> dict:
    """Build the exact JSON-safe dict persisted to `analysis_runs.deterministic_result`."""
    return {
        "safety_score": result.safety_score,
        "risk_level": result.risk_level,
        "starting_score": result.starting_score,
        "total_points_deducted": result.total_points_deducted,
        "interaction_findings": [
            _serialize_interaction_finding(f) for f in result.interaction_findings
        ],
        "adr_findings": [_serialize_adr_finding(f) for f in result.adr_findings],
        "adherence_findings": [
            _serialize_adherence_finding(f) for f in result.adherence_findings
        ],
        "penalties": [_serialize_penalty(p) for p in result.penalties],
    }


# ---------------------------------------------------------------------
# Node factories -- each returns an async node function closing over the
# request-scoped `db` session, so `AnalysisState` itself stays pure data.
# ---------------------------------------------------------------------


def _patient_context_node(db: AsyncSession):
    async def node(state: AnalysisState) -> dict:
        context = await build_patient_context(state["patient_id"], db)
        return {"patient_context": context}

    return node


def _safety_score_node(db: AsyncSession):
    async def node(state: AnalysisState) -> dict:
        result = await calculate_safety_score(state["patient_id"], db)
        return {"safety_score_result": result}

    return node


def _evidence_retrieval_node(db: AsyncSession):
    async def node(state: AnalysisState) -> dict:
        bundle = await retrieve_evidence(state["patient_id"], db, state["safety_score_result"])
        return {"evidence_bundle": bundle}

    return node


def _timeline_engine_node(db: AsyncSession):
    async def node(state: AnalysisState) -> dict:
        context = await build_timeline_context(state["patient_id"], db)
        return {"timeline_context": context}

    return node


def _llm_explanation_node(db: AsyncSession):
    async def node(state: AnalysisState) -> dict:
        try:
            result = await generate_explanation(
                patient_context=state["patient_context"],
                safety_score_result=state["safety_score_result"],
                evidence_bundle=state["evidence_bundle"],
                timeline_context=state["timeline_context"],
            )
        except (NotImplementedError, LLMExplanationError) as exc:
            # NotImplementedError: retained defensively in case a future
            # llm_service.py change reintroduces an unimplemented path.
            # LLMExplanationError (Phase 15): every configured provider
            # either failed or returned output that failed schema
            # validation. Either way, the deterministic pipeline still
            # persists successfully -- see llm_service.py's docstring.
            logger.warning(
                "LLM explanation unavailable for this analysis run: %s",
                exc,
                extra={"patient_id": state["patient_id"]},
            )
            return {"llm_result": None, "llm_error": str(exc)}
        return {"llm_result": result, "llm_error": None}

    return node


def _persist_node(db: AsyncSession):
    async def node(state: AnalysisState) -> dict:
        safety_score_result = state["safety_score_result"]
        llm_result = state.get("llm_result")

        now = datetime.now(timezone.utc)
        analysis_run = AnalysisRun(
            id=uuid.uuid4(),
            patient_id=state["patient_id"],
            analysis_version="v1.0",
            deterministic_result=_serialize_safety_score_result(safety_score_result),
            safety_score=safety_score_result.safety_score,
            risk_level=safety_score_result.risk_level,
            llm_summary=llm_result.summary if llm_result else None,
            llm_reasoning=llm_result.reasoning if llm_result else None,
            llm_recommendations=llm_result.recommendations if llm_result else None,
            confidence_score=llm_result.confidence_score if llm_result else None,
            confidence_level=llm_result.confidence_level if llm_result else None,
            created_at=now,
        )
        db.add(analysis_run)

        await log_timeline_event(
            db,
            patient_id=state["patient_id"],
            event_type="analysis_run",
            ref_id=analysis_run.id,
            event_title=(
                f"Safety analysis run: {safety_score_result.risk_level} risk "
                f"({safety_score_result.safety_score}/100)"
            ),
            payload={
                "safety_score": safety_score_result.safety_score,
                "risk_level": safety_score_result.risk_level,
                "llm_explanation_available": llm_result is not None,
            },
        )

        await db.commit()
        await db.refresh(analysis_run)

        return {"analysis_run_id": analysis_run.id}

    return node


def _build_graph(db: AsyncSession):
    """
    Build and compile the LangGraph StateGraph for one analysis run, bound to `db`.

    Node names are deliberately distinct from every `AnalysisState` field
    name (e.g. "patient_context_builder" rather than "patient_context") --
    LangGraph rejects a node whose name collides with an existing state
    key (`ValueError: '<name>' is already being used as a state key`).
    Discovered and fixed during Phase 14's own node-by-node verification
    (spec section 10: "wire all nodes, test each independently before
    connecting").
    """
    builder = StateGraph(AnalysisState)

    builder.add_node("patient_context_builder", _patient_context_node(db))
    builder.add_node("safety_score_engine", _safety_score_node(db))
    builder.add_node("evidence_retrieval", _evidence_retrieval_node(db))
    builder.add_node("timeline_engine", _timeline_engine_node(db))
    builder.add_node("llm_explanation", _llm_explanation_node(db))
    builder.add_node("persist", _persist_node(db))

    builder.add_edge(START, "patient_context_builder")
    builder.add_edge("patient_context_builder", "safety_score_engine")
    builder.add_edge("safety_score_engine", "evidence_retrieval")
    builder.add_edge("evidence_retrieval", "timeline_engine")
    builder.add_edge("timeline_engine", "llm_explanation")
    builder.add_edge("llm_explanation", "persist")
    builder.add_edge("persist", END)

    return builder.compile()


async def run_analysis(patient_id: uuid.UUID, db: AsyncSession) -> AnalysisState:
    """
    Run the full analysis pipeline for a patient and persist the result.

    Callers (the API layer) are responsible for verifying the patient
    exists and is owned by the requesting user before calling this --
    mirrors the same assumption already documented in
    `patient_context_builder.py`/`evidence_retrieval.py`.

    Returns the final `AnalysisState`, including `analysis_run_id` for
    the caller to re-fetch the persisted row.
    """
    graph = _build_graph(db)
    initial_state: AnalysisState = {"patient_id": patient_id}
    final_state = await graph.ainvoke(initial_state)
    return final_state
