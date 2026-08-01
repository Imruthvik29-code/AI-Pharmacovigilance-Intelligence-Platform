"""
Drug Interaction Engine (Phase 10).

Pure deterministic analysis service. Per CLAUDE.md's AI Responsibilities
section, the LLM must never invent drug interactions -- this module is
the sole source of truth for interaction findings, driven entirely by the
curated `interaction_rules` reference data (seeded in
supabase/migrations/002_seed_data.sql), never by an LLM.

Not exposed via any HTTP route yet. Per spec section 6's folder
structure, `api/v1/analysis.py` and the `POST /patients/{id}/analyze` /
`GET /patients/{id}/analysis` routes are wired in Phase 14 (LangGraph),
which will call into this engine as one of several deterministic
analysis nodes feeding the Safety Score Engine (Phase 12). This phase
only builds and tests the engine itself.

Scope decision (confirmed during Phase 10 planning): only medications
with `status == "active"` count as "the patient's drugs" for interaction
detection -- a paused/completed/discontinued medication is not currently
being taken, so it cannot be interacting with anything right now. This
mirrors the same `status == "active"` filter already used by
`GET /patients/{id}/doses/upcoming` (Phase 8) for a consistent notion of
"currently in effect."

`interaction_rules` rows are stored directionally (`drug_a_id`,
`drug_b_id`), but a drug interaction is symmetric in reality -- Warfarin
+ Aspirin is the same clinical fact regardless of which one is stored as
"a" vs "b" in a given rule row. Detection matches a rule whenever BOTH of
its drug ids are present among the patient's active drug ids -- this is
a pure set-membership check, so it is inherently direction-independent
and does not depend on the order in which the patient's medications were
created.

Severity Calculation scope (confirmed during Phase 10 planning): each
finding simply surfaces its matched rule's own `severity` value as-is
(no new severity is computed or invented here). `highest_severity()` is
a small convenience utility for reporting the single worst severity
across a set of findings -- it is NOT the Safety Score Engine (Phase 12),
which will combine this with ADR and adherence findings into a composite
score and risk_level.
"""
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import InteractionRule, Medication, ReferenceDrug

SeverityLevel = Literal["mild", "moderate", "severe"]

# Clinical ordering (matches severity_level in 001_initial_schema.sql) --
# used by highest_severity() below. Index position, not alphabetical
# order, determines "more severe."
_SEVERITY_ORDER: tuple[SeverityLevel, ...] = ("mild", "moderate", "severe")


@dataclass(frozen=True)
class DrugInteractionFinding:
    """
    One detected interaction between two of a patient's currently active
    drugs, denormalized with both drug names so callers (e.g. the future
    LLM explanation node) don't need a separate lookup.
    """

    interaction_rule_id: uuid.UUID
    drug_a_id: uuid.UUID
    drug_a_name: str
    drug_b_id: uuid.UUID
    drug_b_name: str
    severity: SeverityLevel
    mechanism: str | None
    recommendation: str | None
    source: str | None


async def _get_active_drug_ids(patient_id: uuid.UUID, db: AsyncSession) -> set[uuid.UUID]:
    """Distinct reference_drugs ids for a patient's currently active medications."""
    result = await db.execute(
        select(Medication.drug_id)
        .where(Medication.patient_id == patient_id, Medication.status == "active")
        .distinct()
    )
    return {row[0] for row in result.all()}


async def detect_drug_interactions(
    patient_id: uuid.UUID, db: AsyncSession
) -> list[DrugInteractionFinding]:
    """
    Detect all known drug interactions among a patient's active medications.

    Deterministic only -- every finding comes directly from a seeded
    `interaction_rules` row; nothing here is inferred, ranked, or
    generated beyond what that row already states.

    Returns an empty list if the patient has fewer than two distinct
    active drugs, or if none of their active drug pairs match a seeded
    rule.
    """
    active_drug_ids = await _get_active_drug_ids(patient_id, db)
    if len(active_drug_ids) < 2:
        return []

    drug_a = aliased(ReferenceDrug)
    drug_b = aliased(ReferenceDrug)

    result = await db.execute(
        select(InteractionRule, drug_a.name, drug_b.name)
        .join(drug_a, drug_a.id == InteractionRule.drug_a_id)
        .join(drug_b, drug_b.id == InteractionRule.drug_b_id)
        .where(
            InteractionRule.drug_a_id.in_(active_drug_ids),
            InteractionRule.drug_b_id.in_(active_drug_ids),
        )
    )

    return [
        DrugInteractionFinding(
            interaction_rule_id=rule.id,
            drug_a_id=rule.drug_a_id,
            drug_a_name=drug_a_name,
            drug_b_id=rule.drug_b_id,
            drug_b_name=drug_b_name,
            severity=rule.severity,
            mechanism=rule.mechanism,
            recommendation=rule.recommendation,
            source=rule.source,
        )
        for rule, drug_a_name, drug_b_name in result.all()
    ]


def highest_severity(findings: list[DrugInteractionFinding]) -> SeverityLevel | None:
    """
    Return the single highest severity among a list of findings, or None
    if the list is empty. Ordering follows the clinical severity scale
    (mild < moderate < severe), not alphabetical order.

    This is a simple reporting convenience -- it is NOT a composite
    safety score. The Safety Score Engine (Phase 12) will combine this
    with ADR and adherence findings into `analysis_runs.safety_score` /
    `risk_level`.
    """
    if not findings:
        return None
    return max(findings, key=lambda f: _SEVERITY_ORDER.index(f.severity)).severity
