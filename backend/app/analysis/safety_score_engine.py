"""
Safety Score Engine (Phase 12).

Composes the three deterministic analysis engines --
`drug_interaction_engine.py` (Phase 10), `adr_engine.py` (Phase 11), and
`adherence_engine.py` (Phase 12) -- into a single composite
`safety_score` (0-100) and `risk_level` (low/moderate/high), per spec
section 5's `analysis_runs.safety_score` / `risk_level` columns and
section 8's LangGraph "Safety Score Engine (merges above -> score +
risk_level)" node.

Per CLAUDE.md's AI Responsibilities section, the LLM must NEVER calculate
safety scores -- this module is the sole, 100% deterministic source of
truth for `safety_score`/`risk_level`. Nothing here is LLM-touched; the
LLM Explanation Node (Phase 15) will only ever *explain* this module's
already-computed output, never recompute or override it.

---

## On the constants below

None of the thresholds, weights, or point values in this module are
drawn from `pharmacovigilance-spec-v1.md`, a cited clinical guideline, or
an established pharmacovigilance scoring standard -- the frozen spec does
not define a scoring formula, and no such standard is referenced in it.
They are implementation defaults, confirmed with the project owner during
Phase 12 planning as a reasonable starting point, deliberately isolated
here as named constants (rather than embedded in conditional logic) so
they are easy to locate, audit, and revise later without touching control
flow. If a better clinically-validated basis becomes available, only this
section needs to change.

The one partial exception: the 80% "adequate adherence" cutoff is a
commonly-cited rule-of-thumb in medication-adherence outcomes research
for classifying a patient as "adherent" vs "non-adherent" -- the bands
*below* that cutoff (50%, 25%) are not similarly sourced and are purely
implementation defaults chosen to fill out a 3-band severity scale.

## On why adherence severity is classified *here* and not in
## `adherence_engine.py`

`adherence_engine.py` deliberately returns only counts/rates -- there is
no authoritative "adherence severity" reference table in the schema (the
way `interaction_rules.severity` / `adr_rules.severity` exist), so
classifying a rate as mild/moderate/severe is inherently a scoring
*policy* choice, not a lookup. This module is the single place in the
codebase that owns clinically-flavored policy choices, so that's where
this classification lives -- see `_classify_adherence_severity()` below.
"""
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.adherence_engine import AdherenceFinding, analyze_adherence
from app.analysis.adr_engine import ADRFinding, detect_adrs
from app.analysis.drug_interaction_engine import DrugInteractionFinding, detect_drug_interactions

SeverityLevel = Literal["mild", "moderate", "severe"]
RiskLevel = Literal["low", "moderate", "high"]
PenaltyCategory = Literal["drug_interaction", "adr", "adherence"]

# ---------------------------------------------------------------------
# Configuration constants -- implementation defaults, not spec/clinical
# citations. See module docstring for full rationale. Grouped here as
# the single, documented source of truth for every number this engine
# uses, per the confirmed Phase 12 design (no logic below should embed a
# bare numeric literal for a threshold or penalty -- always reference one
# of these constants).
# ---------------------------------------------------------------------

#: Starting point for every safety score before any penalties are applied.
BASE_SCORE = 100

#: Score is never allowed to go below this floor, regardless of how many
#: findings are present.
MIN_SCORE = 0

#: Points deducted per drug-interaction finding, keyed by the finding's
#: own `interaction_rules.severity` (surfaced as-is by
#: `drug_interaction_engine.py` -- this module does not alter that
#: severity, only assigns it a point cost).
INTERACTION_PENALTY_POINTS: dict[SeverityLevel, int] = {
    "mild": 5,
    "moderate": 15,
    "severe": 30,
}

#: Points deducted per ADR finding, keyed by the finding's own
#: `adr_rules.severity` (surfaced as-is by `adr_engine.py`).
ADR_PENALTY_POINTS: dict[SeverityLevel, int] = {
    "mild": 5,
    "moderate": 15,
    "severe": 30,
}

#: Adherence-rate cutoffs used to classify an `AdherenceFinding` into a
#: severity band, evaluated top-down: rate >= ADEQUATE -> no finding/no
#: penalty; MODERATE <= rate < ADEQUATE -> "mild"; SEVERE <= rate <
#: MODERATE -> "moderate"; rate < SEVERE -> "severe".
#:
#: ADHERENCE_ADEQUATE_THRESHOLD (0.80) is a commonly-cited rule-of-thumb
#: in medication-adherence outcomes research for "adherent" vs
#: "non-adherent" patients. The two bands below it are implementation
#: defaults with no external citation, chosen only to fill out a 3-tier
#: severity scale symmetric with interaction/ADR severity.
ADHERENCE_ADEQUATE_THRESHOLD = 0.80
ADHERENCE_MODERATE_THRESHOLD = 0.50
ADHERENCE_SEVERE_THRESHOLD = 0.25

#: Points deducted per adherence finding, keyed by the severity band
#: assigned via the thresholds above. Weighted slightly lower than
#: interaction/ADR penalties at the same severity label (e.g. "severe"
#: adherence costs 20 vs. 30 for a severe interaction/ADR) on the
#: reasoning that an active drug interaction/ADR is a currently-present
#: clinical risk, whereas poor adherence is a behavioral pattern that
#: *may* lead to risk -- this weighting is a judgment call, not a
#: derived value, and is a reasonable first candidate for revision if a
#: clinical reviewer disagrees.
ADHERENCE_PENALTY_POINTS: dict[SeverityLevel, int] = {
    "mild": 5,
    "moderate": 10,
    "severe": 20,
}

#: `risk_level` thresholds, evaluated top-down against the final
#: `safety_score` (after all penalties and the MIN_SCORE floor are
#: applied): score >= LOW -> "low"; MODERATE <= score < LOW -> "moderate";
#: score < MODERATE -> "high". Chosen only to partition the 0-100 scale
#: into three roughly even bands; not derived from any external standard.
RISK_LEVEL_LOW_THRESHOLD = 70
RISK_LEVEL_MODERATE_THRESHOLD = 40


@dataclass(frozen=True)
class PenaltyEntry:
    """
    One line item in the score's audit trail -- exactly one penalty
    deduction, with a reference back to the finding that produced it.

    `source` is intentionally the original finding object (not just an
    id), so a caller (e.g. the Phase 15 LLM explanation node, or a future
    report UI) can render a full human-readable explanation of *why* this
    penalty was applied without re-querying the database or recomputing
    anything -- the whole point of exposing this breakdown on
    `SafetyScoreResult` rather than only the final score.
    """

    category: PenaltyCategory
    description: str
    severity: SeverityLevel
    points: int
    source: DrugInteractionFinding | ADRFinding | AdherenceFinding


@dataclass(frozen=True)
class SafetyScoreResult:
    """
    Full, self-explanatory output of `calculate_safety_score()`.

    Exposes not just the final `safety_score`/`risk_level`, but every
    intermediate finding and penalty that produced them, so a later phase
    (Evidence Retrieval, the LLM explanation node, or a report view) can
    explain exactly how the score was derived without recomputing
    anything -- re-running `detect_drug_interactions`/`detect_adrs`/
    `analyze_adherence` a second time, or reverse-engineering the point
    math, should never be necessary.
    """

    safety_score: int
    risk_level: RiskLevel
    starting_score: int
    total_points_deducted: int
    interaction_findings: list[DrugInteractionFinding]
    adr_findings: list[ADRFinding]
    adherence_findings: list[AdherenceFinding]
    penalties: list[PenaltyEntry]


def _classify_adherence_severity(finding: AdherenceFinding) -> SeverityLevel | None:
    """
    Classify an AdherenceFinding's rate into a severity band, or None if
    adherence is adequate (no penalty warranted) or unmeasurable.

    This is the one place in the codebase that turns an adherence rate
    into a clinical-flavored judgment -- see module docstring for why
    that responsibility lives here rather than in `adherence_engine.py`.
    """
    if finding.adherence_rate is None:
        return None
    if finding.adherence_rate >= ADHERENCE_ADEQUATE_THRESHOLD:
        return None
    if finding.adherence_rate >= ADHERENCE_MODERATE_THRESHOLD:
        return "mild"
    if finding.adherence_rate >= ADHERENCE_SEVERE_THRESHOLD:
        return "moderate"
    return "severe"


def _interaction_penalties(findings: list[DrugInteractionFinding]) -> list[PenaltyEntry]:
    return [
        PenaltyEntry(
            category="drug_interaction",
            description=(
                f"{finding.drug_a_name} + {finding.drug_b_name} interaction "
                f"({finding.severity})"
            ),
            severity=finding.severity,
            points=INTERACTION_PENALTY_POINTS[finding.severity],
            source=finding,
        )
        for finding in findings
    ]


def _adr_penalties(findings: list[ADRFinding]) -> list[PenaltyEntry]:
    return [
        PenaltyEntry(
            category="adr",
            description=f"{finding.drug_name}: {finding.reaction_description} ({finding.severity})",
            severity=finding.severity,
            points=ADR_PENALTY_POINTS[finding.severity],
            source=finding,
        )
        for finding in findings
    ]


def _adherence_penalties(findings: list[AdherenceFinding]) -> list[PenaltyEntry]:
    penalties: list[PenaltyEntry] = []
    for finding in findings:
        severity = _classify_adherence_severity(finding)
        if severity is None:
            continue  # adequate adherence or nothing due yet -- no penalty
        rate_pct = round(finding.adherence_rate * 100) if finding.adherence_rate is not None else 0
        penalties.append(
            PenaltyEntry(
                category="adherence",
                description=(
                    f"{finding.drug_name}: {rate_pct}% adherence "
                    f"({finding.taken}/{finding.due} doses taken, {severity})"
                ),
                severity=severity,
                points=ADHERENCE_PENALTY_POINTS[severity],
                source=finding,
            )
        )
    return penalties


def _risk_level_for_score(score: int) -> RiskLevel:
    if score >= RISK_LEVEL_LOW_THRESHOLD:
        return "low"
    if score >= RISK_LEVEL_MODERATE_THRESHOLD:
        return "moderate"
    return "high"


async def calculate_safety_score(patient_id: uuid.UUID, db: AsyncSession) -> SafetyScoreResult:
    """
    Compute a patient's composite safety score by running all three
    deterministic analysis engines and combining their findings.

    Deterministic only -- calls `detect_drug_interactions()` (Phase 10),
    `detect_adrs()` (Phase 11), and `analyze_adherence()` (Phase 12),
    then applies this module's own documented point deductions and
    thresholds. Nothing here is LLM-generated or LLM-influenced.

    The returned `SafetyScoreResult` carries the full audit trail (every
    finding, every individual penalty) alongside the final score, per the
    confirmed Phase 12 design -- see `SafetyScoreResult`'s docstring.
    """
    interaction_findings = await detect_drug_interactions(patient_id, db)
    adr_findings = await detect_adrs(patient_id, db)
    adherence_findings = await analyze_adherence(patient_id, db)

    penalties = (
        _interaction_penalties(interaction_findings)
        + _adr_penalties(adr_findings)
        + _adherence_penalties(adherence_findings)
    )

    total_points_deducted = sum(entry.points for entry in penalties)
    safety_score = max(BASE_SCORE - total_points_deducted, MIN_SCORE)
    risk_level = _risk_level_for_score(safety_score)

    return SafetyScoreResult(
        safety_score=safety_score,
        risk_level=risk_level,
        starting_score=BASE_SCORE,
        total_points_deducted=total_points_deducted,
        interaction_findings=interaction_findings,
        adr_findings=adr_findings,
        adherence_findings=adherence_findings,
        penalties=penalties,
    )
