"""
LLM Service (Phase 14 interface / Phase 15 implementation).

Implements the typed interface the LangGraph workflow's "LLM Explanation
Node" (spec section 8) calls. Per CLAUDE.md's AI Responsibilities section,
this module ONLY explains the already-computed deterministic result
(safety score, findings, evidence, timeline context) -- it never
diagnoses, invents drug interactions/ADRs, or calculates a safety score
itself. `generate_explanation`'s signature enforces this structurally: it
only ever receives already-computed `SafetyScoreResult`/`EvidenceBundle`/
`PatientContext`/`TimelineContext` objects, never raw DB access.

## Provider strategy (spec section 4)

Gemini is the primary provider, OpenRouter is the fallback -- both called
over plain REST via `app/services/llm_providers.py` (httpx only, no SDK
dependency). A single request is attempted against Gemini; if that call
fails OR its response fails schema validation, OpenRouter is attempted
next with the same prompt. Only if both attempts fail does this module
raise `LLMExplanationError`.

Falling back on malformed output (not just on network/HTTP failure) is a
deliberate, approved design choice: a provider that responds successfully
but produces unusable content is, for this purpose, no more useful than
one that doesn't respond at all -- so both failure modes get the same
fallback treatment.

`GeminiProvider` additionally retries once, internally, for transient
failures (HTTP 429/500/502/503/504 or a network timeout) before this
module's fallback to OpenRouter ever comes into play -- see
`llm_providers.py`'s module docstring for the retry rules. This module
doesn't know or care whether a given Gemini attempt already included a
retry; it only ever sees the final success or failure of that provider.

## Logging

On a successful call (provider responded AND its output passed schema
validation), this module logs one structured, operational-only record:
`provider_used`, `model_used`, `latency_ms`, `fallback_used`, and
`prompt_tokens`/`completion_tokens`/`total_tokens` when the provider
reported them (omitted entirely, not logged as null, when unavailable).
Never logged: patient identifiers, prompts, medical history, evidence
text, or the generated explanation itself -- only the metadata above.

## Grounding strategy

Grounding is enforced at the prompt level only (the model is instructed
to explain solely the supplied deterministic findings/evidence, never to
invent new interactions/ADRs/diagnoses/dosages) plus structural schema
validation of the response shape. No semantic/keyword-overlap grounding
check is performed against the evidence text -- per the approved design,
that was deliberately scoped out as unreliable for an MVP.

## Confidence

`confidence_score`/`confidence_level` are self-reported by the model (per
a rubric embedded in the prompt) and validated only for well-formedness
(integer 0-100, one of the three enum values). Per the approved design,
this module does NOT recompute, clamp, or override the model's confidence
value -- deterministic confidence clamping was evaluated and explicitly
removed from scope. If a response is genuinely poorly evidenced, the
prompt instructs the model to self-report a low value; this module trusts
that report once it passes basic validation.

## Failure behavior

`generate_explanation` raises `LLMExplanationError` (never fabricates a
result) when every configured provider fails. `app/services/
langgraph_workflow.py`'s `llm_explanation` node catches this alongside
`NotImplementedError` and leaves the LLM-generated columns on
`analysis_runs` NULL rather than failing the whole analysis run -- the
deterministic pipeline always persists regardless of this step's outcome.
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

from app.analysis.safety_score_engine import SafetyScoreResult
from app.analysis.timeline_engine import TimelineContext
from app.core.config import get_settings
from app.services.evidence_retrieval import EvidenceBundle
from app.services.llm_providers import (
    GeminiProvider,
    LLMCompletion,
    LLMProvider,
    LLMProviderError,
    OpenRouterProvider,
)
from app.services.patient_context_builder import PatientContext

logger = logging.getLogger("app.llm_service")
settings = get_settings()

ConfidenceLevel = Literal["low", "moderate", "high"]

_VALID_CONFIDENCE_LEVELS = ("low", "moderate", "high")

# Most recent N timeline entries included in the prompt. TimelineContext
# itself has no cap (matches GET /timeline's no-pagination precedent),
# but an unbounded prompt is a real cost/latency concern for a free-tier
# LLM call, so truncation happens here, at prompt-construction time only
# -- it does not alter timeline_engine.py's own behavior.
_MAX_TIMELINE_ENTRIES_IN_PROMPT = 30

_SYSTEM_INSTRUCTIONS = """\
You are a medication safety explanation assistant. You are given an \
ALREADY-COMPUTED, deterministic medication safety analysis for one \
patient. Your only job is to explain that analysis in plain language.

Hard rules, never violate these:
- Do NOT invent, alter, or second-guess any drug interaction, adverse \
drug reaction, or safety score/risk level. Treat every finding given to \
you as an established fact.
- Do NOT diagnose any disease or condition.
- Do NOT calculate or restate a different safety score or risk level \
than the one given to you.
- Do NOT recommend a new medication, a new dosage, or a dosage change. \
Recommendations must stay general (e.g. "discuss this with your \
prescriber or pharmacist"), never prescriptive.
- Base every statement only on the patient snapshot, findings, and \
evidence given below -- do not introduce outside medical claims beyond \
explaining terms that already appear in the findings.

Respond with ONLY a single JSON object, no markdown fences, no text \
before or after it, matching exactly this shape:
{
  "summary": "2-4 sentences, plain language, for a patient to read first",
  "reasoning": "longer-form explanation connecting the findings to the evidence given",
  "recommendations": "general, non-prescriptive guidance",
  "confidence_score": <integer 0-100>,
  "confidence_level": "low" | "moderate" | "high"
}

Confidence rubric -- self-assess honestly using this scale:
- high (80-100): every finding you're explaining has both a medical \
source (a cited mechanism/reaction fact) and personal evidence (something \
from the patient's own history) backing it.
- moderate (50-79): most findings have some supporting evidence, but some \
rely on only one type of evidence (medical or personal, not both).
- low (0-49): evidence is sparse relative to the findings, or the \
patient's own history has little bearing on the findings.
If there are no findings at all (a clean result), say so reassuringly \
and report high confidence, since there is nothing ambiguous to explain.
"""


@dataclass(frozen=True)
class LLMExplanationResult:
    """
    Shape this module returns, matching `analysis_runs.llm_summary` /
    `llm_reasoning` / `llm_recommendations` / `confidence_score` /
    `confidence_level` (001_initial_schema.sql). Unchanged from the Phase
    14 interface `app/services/langgraph_workflow.py` was already built
    against -- Phase 15 only implements the function that returns this,
    it does not alter the shape.
    """

    summary: str
    reasoning: str
    recommendations: str
    confidence_score: int
    confidence_level: ConfidenceLevel


class LLMExplanationError(Exception):
    """
    Raised when every configured provider fails to produce a usable
    explanation -- either a provider call itself failed
    (`LLMProviderError`) or its response failed schema validation.

    `app/services/langgraph_workflow.py`'s `llm_explanation` node catches
    this (alongside `NotImplementedError`) and persists the analysis run
    with NULL LLM fields rather than failing the whole run.
    """


# ---------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------


def _format_patient_snapshot(patient_context: PatientContext) -> str:
    lines = [
        f"Age: {patient_context.age if patient_context.age is not None else 'unknown'}",
        f"Sex: {patient_context.sex or 'unknown'}",
        f"Renal impairment flag: {patient_context.renal_flag}",
        f"Hepatic impairment flag: {patient_context.hepatic_flag}",
    ]

    if patient_context.active_conditions:
        lines.append("Active conditions:")
        for c in patient_context.active_conditions:
            lines.append(f"  - {c.name} (status: {c.status}, reason: {c.reason})")
    else:
        lines.append("Active conditions: none")

    if patient_context.active_medications:
        lines.append("Active medications:")
        for m in patient_context.active_medications:
            purpose = m.purpose_text or ("linked to a condition above" if m.condition_id else "unspecified purpose")
            lines.append(f"  - {m.drug_name} ({m.dose or 'dose unspecified'}) -- {purpose}")
    else:
        lines.append("Active medications: none")

    if patient_context.active_symptoms:
        lines.append("Active (unresolved) symptoms:")
        for s in patient_context.active_symptoms:
            lines.append(f"  - {s.description} (severity: {s.severity})")
    else:
        lines.append("Active symptoms: none")

    return "\n".join(lines)


def _format_findings(safety_score_result: SafetyScoreResult) -> str:
    lines = [
        f"Safety score: {safety_score_result.safety_score}/100",
        f"Risk level: {safety_score_result.risk_level}",
    ]

    if not safety_score_result.penalties:
        lines.append("No safety findings were detected.")
        return "\n".join(lines)

    lines.append("Findings:")
    for p in safety_score_result.penalties:
        lines.append(
            f"  - [{p.category}] {p.description} (severity: {p.severity}, -{p.points} pts)"
        )

    return "\n".join(lines)


def _format_evidence(evidence_bundle: EvidenceBundle) -> str:
    sections: list[str] = []
    for label, findings in (
        ("Drug interaction evidence", evidence_bundle.interaction_evidence),
        ("ADR evidence", evidence_bundle.adr_evidence),
        ("Adherence evidence", evidence_bundle.adherence_evidence),
    ):
        if not findings:
            continue
        lines = [f"{label}:"]
        for fe in findings:
            for item in fe.medical_evidence:
                source = f" (source: {item.source})" if item.source else ""
                lines.append(f"  - [medical] {item.statement}{source}")
            for item in fe.personal_evidence:
                when = f" ({item.occurred_at.isoformat()})" if item.occurred_at else ""
                lines.append(f"  - [personal]{when} {item.statement}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "No supporting evidence available."


def _format_timeline(timeline_context: TimelineContext) -> str:
    entries = timeline_context.entries
    if not entries:
        return "No timeline history available."

    # entries is ascending (oldest -> newest); the tail is the most recent.
    recent = entries[-_MAX_TIMELINE_ENTRIES_IN_PROMPT:]
    omitted = len(entries) - len(recent)

    lines: list[str] = []
    if omitted > 0:
        lines.append(f"({omitted} earlier events omitted for brevity)")
    for e in recent:
        desc = f" -- {e.event_description}" if e.event_description else ""
        lines.append(f"  - {e.event_time.isoformat()}: {e.event_title}{desc}")

    return "\n".join(lines)


def _build_prompt(
    patient_context: PatientContext,
    safety_score_result: SafetyScoreResult,
    evidence_bundle: EvidenceBundle,
    timeline_context: TimelineContext,
) -> str:
    """Build the single structured prompt sent to the LLM provider."""
    return (
        f"{_SYSTEM_INSTRUCTIONS}\n\n"
        f"=== Patient snapshot ===\n{_format_patient_snapshot(patient_context)}\n\n"
        f"=== Deterministic findings (do not alter) ===\n{_format_findings(safety_score_result)}\n\n"
        f"=== Supporting evidence ===\n{_format_evidence(evidence_bundle)}\n\n"
        f"=== Patient timeline ===\n{_format_timeline(timeline_context)}\n"
    )


# ---------------------------------------------------------------------
# Response parsing / validation
# ---------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Best-effort recovery if the model wraps its JSON in ```json fences
    despite being told not to. Purely mechanical string handling -- no
    second LLM call, no semantic interpretation."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def _extract_json_object(text: str) -> str:
    """Locate the outermost {...} span in `text` via bracket matching, in
    case the model added stray prose around the JSON despite instructions.
    Returns `text` unchanged if no braces are found."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def _parse_and_validate(raw: str) -> LLMExplanationResult:
    """
    Parse a provider's raw text response into a validated
    `LLMExplanationResult`. Raises `LLMExplanationError` on any schema
    violation -- this is the one place response shape is enforced,
    regardless of which provider produced it. Does not clamp or modify
    a well-formed confidence value; only rejects malformed ones.
    """
    candidate = _extract_json_object(_strip_markdown_fences(raw))

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMExplanationError(f"response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LLMExplanationError("response JSON was not an object.")

    for field in ("summary", "reasoning", "recommendations"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise LLMExplanationError(f"'{field}' is missing or empty.")

    score = data.get("confidence_score")
    # bool is a subclass of int in Python -- explicitly excluded so
    # `true`/`false` can't slip through as 1/0.
    if isinstance(score, bool) or not isinstance(score, int) or not (0 <= score <= 100):
        raise LLMExplanationError(
            f"'confidence_score' must be an integer 0-100, got {score!r}."
        )

    level = data.get("confidence_level")
    if level not in _VALID_CONFIDENCE_LEVELS:
        raise LLMExplanationError(
            f"'confidence_level' must be one of {_VALID_CONFIDENCE_LEVELS}, got {level!r}."
        )

    return LLMExplanationResult(
        summary=data["summary"].strip(),
        reasoning=data["reasoning"].strip(),
        recommendations=data["recommendations"].strip(),
        confidence_score=score,
        confidence_level=level,
    )


# ---------------------------------------------------------------------
# Provider orchestration
# ---------------------------------------------------------------------

# Ordered primary -> fallback, per spec section 4. A plain module-level
# tuple (not a factory function) is sufficient -- both provider classes
# read configuration lazily from `get_settings()` on each call, so there
# is no per-request state to construct. Tests monkeypatch this tuple
# directly (see tests/test_llm_service.py) to inject fake providers
# without touching real network calls or settings.
_PROVIDERS: tuple[LLMProvider, ...] = (GeminiProvider(), OpenRouterProvider())


def _log_successful_completion(
    provider: LLMProvider,
    completion: LLMCompletion,
    *,
    latency_ms: int,
    fallback_used: bool,
) -> None:
    """
    Log one structured, operational-only record for a successful LLM call.

    Only metadata -- never the prompt, the patient snapshot/evidence that
    fed it, the generated explanation, or any patient identifier. Token
    usage fields are added to `extra` only when the provider actually
    reported them, so a provider/model that omits usage data simply
    produces a record without those keys, rather than `None` values.
    """
    extra: dict[str, object] = {
        "provider_used": provider.name,
        "model_used": provider.model,
        "latency_ms": latency_ms,
        "fallback_used": fallback_used,
    }
    if completion.prompt_tokens is not None:
        extra["prompt_tokens"] = completion.prompt_tokens
    if completion.completion_tokens is not None:
        extra["completion_tokens"] = completion.completion_tokens
    if completion.total_tokens is not None:
        extra["total_tokens"] = completion.total_tokens

    logger.info("LLM explanation generated", extra=extra)


async def _call_providers_with_fallback(prompt: str) -> LLMExplanationResult:
    """
    Try each provider in order. A provider "counts" as failed for
    fallback purposes if EITHER the call itself fails (`LLMProviderError`)
    OR its response fails schema validation (`LLMExplanationError` from
    `_parse_and_validate`) -- malformed-but-successful output is treated
    the same as an unreachable provider, since neither yields a usable
    result (approved Phase 15 design decision). Only if every provider
    fails does this raise, combining all per-provider failure messages so
    the eventual `llm_error` string is diagnostic rather than generic.

    `fallback_used` (for logging) is True whenever the provider that
    ultimately succeeds is not the first one in `_PROVIDERS` -- i.e.
    Gemini (including its own internal retry) did not produce a usable
    result and OpenRouter was used instead.
    """
    failures: list[str] = []

    for index, provider in enumerate(_PROVIDERS):
        started = time.monotonic()
        try:
            completion = await provider.complete(
                prompt, timeout_seconds=settings.llm_timeout_seconds
            )
        except LLMProviderError as exc:
            logger.warning("LLM provider call failed: %s", exc)
            failures.append(str(exc))
            continue
        latency_ms = round((time.monotonic() - started) * 1000)

        try:
            result = _parse_and_validate(completion.text)
        except LLMExplanationError as exc:
            logger.warning(
                "LLM provider '%s' returned unusable output: %s", provider.name, exc
            )
            failures.append(f"{provider.name}: {exc}")
            continue

        _log_successful_completion(
            provider, completion, latency_ms=latency_ms, fallback_used=index > 0
        )
        return result

    raise LLMExplanationError(
        "All configured LLM providers failed: " + "; ".join(failures)
    )


# ---------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------


async def generate_explanation(
    patient_context: PatientContext,
    safety_score_result: SafetyScoreResult,
    evidence_bundle: EvidenceBundle,
    timeline_context: TimelineContext,
) -> LLMExplanationResult:
    """
    Generate a plain-language explanation of an already-computed
    deterministic analysis result.

    Tries Gemini first, then OpenRouter (spec section 4), attempting the
    full call-and-parse cycle against each before moving on. Raises
    `LLMExplanationError` if both fail -- callers (the LangGraph
    workflow's `llm_explanation` node) must catch this and persist the
    analysis run with NULL LLM fields rather than treat it as a fatal
    error; see this module's docstring.
    """
    prompt = _build_prompt(
        patient_context, safety_score_result, evidence_bundle, timeline_context
    )
    return await _call_providers_with_fallback(prompt)
