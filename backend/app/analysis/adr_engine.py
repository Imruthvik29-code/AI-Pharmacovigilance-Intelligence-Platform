"""
ADR (Adverse Drug Reaction) Engine (Phase 11).

Pure deterministic analysis service. Per CLAUDE.md's AI Responsibilities
section, the LLM must never invent ADRs -- this module is the sole source
of truth for ADR findings, driven entirely by the curated `adr_rules`
reference data (seeded in supabase/migrations/002_seed_data.sql), never
by an LLM.

Not exposed via any HTTP route yet -- same as Phase 10's
drug_interaction_engine.py. Per spec section 6's folder structure,
`api/v1/analysis.py` and the `POST /patients/{id}/analyze` /
`GET /patients/{id}/analysis` routes are wired in Phase 14 (LangGraph),
which will call into this engine as one of several deterministic
analysis nodes feeding the Safety Score Engine (Phase 12). This phase
only builds and tests the engine itself.

Scope decision (consistent with Phase 10's drug_interaction_engine.py,
applied here for the same underlying reason): only medications with
`status == "active"` count as "the patient's drugs" for ADR detection --
a paused/completed/discontinued medication is not currently being taken,
so it cannot currently be producing an adverse reaction. This mirrors the
same `status == "active"` filter already used by
`GET /patients/{id}/doses/upcoming` (Phase 8) and
`detect_drug_interactions` (Phase 10).

Unlike drug interactions (which require a *pair* of drugs to both be
present), an ADR is a property of a single drug -- a patient's active
drug set can surface zero, one, or multiple ADR findings *per drug*
(e.g. Lisinopril has two seeded ADR rules: "Dry cough" and
"Hyperkalemia" -- both are returned as separate findings). Detection is
therefore a simple `adr_rules.drug_id IN (patient's active drug ids)`
membership query, with no directionality concerns (unlike
`interaction_rules`' drug_a/drug_b pairing).

Severity Calculation scope (mirrors Phase 10's confirmed scope): each
finding simply surfaces its matched rule's own `severity` value as-is (no
new severity is computed or invented here). `highest_severity()` is a
small convenience utility for reporting the single worst severity across
a set of findings -- it is NOT the Safety Score Engine (Phase 12), which
will combine this with drug-interaction and adherence findings into a
composite score and risk_level.

The small ownership/query helpers below (`_get_active_drug_ids`,
`highest_severity`) are intentionally re-implemented locally rather than
imported from `drug_interaction_engine.py`, matching this codebase's
existing convention of keeping small per-module helpers private to their
own file (see the documented rationale in `conditions.py`/`medications.py`/
`symptoms.py`) -- it keeps the `analysis/` engines independent siblings
that don't reach into each other's internals.
"""
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdrRule, Medication, ReferenceDrug

SeverityLevel = Literal["mild", "moderate", "severe"]

# Clinical ordering (matches severity_level in 001_initial_schema.sql) --
# used by highest_severity() below. Index position, not alphabetical
# order, determines "more severe."
_SEVERITY_ORDER: tuple[SeverityLevel, ...] = ("mild", "moderate", "severe")


@dataclass(frozen=True)
class ADRFinding:
    """
    One known adverse drug reaction for a drug the patient is currently
    (actively) taking, denormalized with the drug's name so callers (e.g.
    the future LLM explanation node) don't need a separate lookup.
    """

    adr_rule_id: uuid.UUID
    drug_id: uuid.UUID
    drug_name: str
    reaction_description: str
    severity: SeverityLevel
    frequency_class: str | None
    source: str | None


async def _get_active_drug_ids(patient_id: uuid.UUID, db: AsyncSession) -> set[uuid.UUID]:
    """Distinct reference_drugs ids for a patient's currently active medications."""
    result = await db.execute(
        select(Medication.drug_id)
        .where(Medication.patient_id == patient_id, Medication.status == "active")
        .distinct()
    )
    return {row[0] for row in result.all()}


async def detect_adrs(patient_id: uuid.UUID, db: AsyncSession) -> list[ADRFinding]:
    """
    Detect all known adverse drug reactions for a patient's active medications.

    Deterministic only -- every finding comes directly from a seeded
    `adr_rules` row; nothing here is inferred, ranked, or generated
    beyond what that row already states.

    Returns an empty list if the patient has no active medications, or if
    none of their active drugs have a seeded ADR rule. A single drug may
    contribute multiple findings if it has more than one seeded ADR rule
    (e.g. Lisinopril -> "Dry cough" and "Hyperkalemia").
    """
    active_drug_ids = await _get_active_drug_ids(patient_id, db)
    if not active_drug_ids:
        return []

    result = await db.execute(
        select(AdrRule, ReferenceDrug.name)
        .join(ReferenceDrug, ReferenceDrug.id == AdrRule.drug_id)
        .where(AdrRule.drug_id.in_(active_drug_ids))
    )

    return [
        ADRFinding(
            adr_rule_id=rule.id,
            drug_id=rule.drug_id,
            drug_name=drug_name,
            reaction_description=rule.reaction_description,
            severity=rule.severity,
            frequency_class=rule.frequency_class,
            source=rule.source,
        )
        for rule, drug_name in result.all()
    ]


def highest_severity(findings: list[ADRFinding]) -> SeverityLevel | None:
    """
    Return the single highest severity among a list of findings, or None
    if the list is empty. Ordering follows the clinical severity scale
    (mild < moderate < severe), not alphabetical order.

    This is a simple reporting convenience -- it is NOT a composite
    safety score. The Safety Score Engine (Phase 12) will combine this
    with drug-interaction and adherence findings into
    `analysis_runs.safety_score` / `risk_level`.
    """
    if not findings:
        return None
    return max(findings, key=lambda f: _SEVERITY_ORDER.index(f.severity)).severity
