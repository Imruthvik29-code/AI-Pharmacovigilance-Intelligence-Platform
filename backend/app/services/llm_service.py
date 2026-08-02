"""
LLM Service (Phase 14 interface / Phase 15 implementation).

Defines the typed interface the LangGraph workflow's "LLM Explanation
Node" (spec section 8) calls. Per explicit project-owner direction
during Phase 14 planning, the actual LLM call (Gemini primary,
OpenRouter fallback -- spec section 4) is intentionally deferred to
Phase 15 ("Gemini Integration"). This module exists now so the graph can
be fully wired and tested end-to-end in Phase 14, with only this one
step producing no result yet.

Per CLAUDE.md's AI Responsibilities section, whatever Phase 15
implements here must ONLY explain the already-computed deterministic
result (safety score, findings, evidence, timeline context) -- it must
never diagnose, invent drug interactions/ADRs, or calculate a safety
score itself. The function signature below is shaped to make that
constraint structural: it receives already-computed
`SafetyScoreResult`/`EvidenceBundle`/`PatientContext`/`TimelineContext`
objects and nothing else.

`generate_explanation` deliberately raises `NotImplementedError` rather
than returning a fabricated "placeholder" summary/recommendation. A
fabricated result would either (a) look like real LLM output to a
caller that isn't checking carefully, or (b) require inventing
`confidence_score`/`confidence_level` values with no actual basis --
both worse than a clear, catchable exception. See
`app/services/langgraph_workflow.py`'s `llm_explanation_node`, which
catches exactly this exception and leaves the LLM-generated columns on
the persisted `analysis_runs` row `NULL` rather than failing the whole
analysis run.
"""
from dataclasses import dataclass
from typing import Literal

from app.analysis.safety_score_engine import SafetyScoreResult
from app.analysis.timeline_engine import TimelineContext
from app.services.evidence_retrieval import EvidenceBundle
from app.services.patient_context_builder import PatientContext

ConfidenceLevel = Literal["low", "moderate", "high"]


@dataclass(frozen=True)
class LLMExplanationResult:
    """
    Shape Phase 15's real implementation must return, matching
    `analysis_runs.llm_summary` / `llm_reasoning` / `llm_recommendations`
    / `confidence_score` / `confidence_level` (001_initial_schema.sql).
    """

    summary: str
    reasoning: str
    recommendations: str
    confidence_score: int
    confidence_level: ConfidenceLevel


async def generate_explanation(
    patient_context: PatientContext,
    safety_score_result: SafetyScoreResult,
    evidence_bundle: EvidenceBundle,
    timeline_context: TimelineContext,
) -> LLMExplanationResult:
    """
    Generate a plain-language explanation of an already-computed
    deterministic analysis result.

    Phase 15 will implement this as the real Gemini (primary) /
    OpenRouter (fallback) call per spec section 4/8. Intentionally
    unimplemented in Phase 14 -- see module docstring for why this
    raises rather than fabricates a result.
    """
    raise NotImplementedError(
        "LLM explanation generation is not implemented until Phase 15 "
        "(Gemini Integration). This interface exists so the Phase 14 "
        "LangGraph workflow can call it with the correct signature; the "
        "deterministic analysis pipeline persists successfully without "
        "it -- see app/services/langgraph_workflow.py's "
        "llm_explanation_node, which catches this exception and leaves "
        "the LLM-generated fields NULL on the persisted analysis_runs row."
    )
