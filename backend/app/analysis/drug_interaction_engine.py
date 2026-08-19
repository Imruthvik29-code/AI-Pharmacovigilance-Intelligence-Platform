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
its drug ids are present among the patient's active drug ids (after
ingredient resolution -- see below) -- this is a pure set-membership
check, so it is inherently direction-independent and does not depend on
the order in which the patient's medications were created.

Ingredient resolution (added alongside 0003 / rxnorm_concept_relations):
the *pair count* of "the patient is taking N distinct active drugs" is
computed BEFORE resolution (so two branded formulations of the same two
ingredients still count as one pair), but the rule match is performed
against the resolved set of drug IDs that includes ingredients reachable
via one ``has_ingredient`` / ``has_precise_ingredient`` edge. Resolution
uses LEFT JOIN semantics (selected IDs are always preserved; missing /
unimported / NULL rxcui rows resolve to themselves), one-hop only, and
is performed by :mod:`app.analysis.ingredient_resolver`. This lets a
rule keyed to two IN-level ingredients match when the patient is
prescribed branded/clinical-drug formulations of those ingredients.

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

from app.analysis.ingredient_resolver import INGREDIENT_RELATION_TYPES, resolve_to_ingredient_ids
from app.db.models import InteractionRule, Medication, ReferenceDrug, RxnormConceptRelation

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
    # Pair count happens BEFORE ingredient resolution: the clinical
    # question "is this patient taking >=2 drugs?" is about what they
    # are actually prescribed, not about ingredient fan-out. Two
    # formulations of the same monotherapy still don't produce a
    # drug-drug interaction pair.
    if len(active_drug_ids) < 2:
        return []

    # Resolve selected IDs to ingredient IDs for rule matching. LEFT
    # JOIN semantics (selected IDs preserved), one-hop only, deduped.
    # See ingredient_resolver.py for the full contract.
    resolved_ids = await resolve_to_ingredient_ids(active_drug_ids, db)

    # Map each resolved (ingredient-or-selected) ID back to the set of
    # original active selected IDs that reach it, so we can enforce that
    # a matched rule's two drug IDs come from *different* selected drugs
    # (not from ingredient fan-out of a single medication).
    source_map = await _build_source_map(active_drug_ids, resolved_ids, db)

    drug_a = aliased(ReferenceDrug)
    drug_b = aliased(ReferenceDrug)

    result = await db.execute(
        select(InteractionRule, drug_a.name, drug_b.name)
        .join(drug_a, drug_a.id == InteractionRule.drug_a_id)
        .join(drug_b, drug_b.id == InteractionRule.drug_b_id)
        .where(
            InteractionRule.drug_a_id.in_(resolved_ids),
            InteractionRule.drug_b_id.in_(resolved_ids),
        )
    )

    findings: list[DrugInteractionFinding] = []
    seen_rule_ids: set[uuid.UUID] = set()
    for rule, drug_a_name, drug_b_name in result.all():
        if rule.id in seen_rule_ids:
            continue
        sources_a = source_map.get(rule.drug_a_id, set())
        sources_b = source_map.get(rule.drug_b_id, set())
        # Require that the two sides of the rule trace to disjoint sets
        # of the patient's selected drugs (otherwise the two IDs could
        # both be ingredients of the *same* single medication).
        if not (sources_a and sources_b and sources_a.isdisjoint(sources_b)):
            continue
        seen_rule_ids.add(rule.id)
        findings.append(
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
        )
    return findings


async def _build_source_map(
    active_drug_ids: set[uuid.UUID],
    resolved_ids: set[uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Return {resolved_id: {selected_id, ...}} for all resolved IDs.

    Every selected ID maps to itself (LEFT JOIN preservation). For each
    selected drug whose rxcui has a ``has_ingredient`` /
    ``has_precise_ingredient`` edge, the resolved ingredient ID also maps
    back to that selected ID.

    One-hop only -- we do not traverse from ingredient to anything else.
    """
    source_map: dict[uuid.UUID, set[uuid.UUID]] = {
        did: {did} for did in active_drug_ids
    }

    # Pull rxcuis for the active selected drugs.
    rxcui_rows = (
        await db.execute(
            select(ReferenceDrug.id, ReferenceDrug.rxcui).where(
                ReferenceDrug.id.in_(active_drug_ids)
            )
        )
    ).all()
    rxcui_by_id: dict[uuid.UUID, str] = {
        did: rxcui for did, rxcui in rxcui_rows if rxcui
    }
    if not rxcui_by_id:
        return source_map

    # Find targets of ingredient edges sourced from those rxcuis, then
    # map target_rxcui -> reference_drugs.id and record the source.
    target_rows = (
        await db.execute(
            select(
                RxnormConceptRelation.source_rxcui,
                ReferenceDrug.id,
            )
            .join(
                ReferenceDrug,
                ReferenceDrug.rxcui == RxnormConceptRelation.target_rxcui,
                isouter=True,
            )
            .where(
                RxnormConceptRelation.source_rxcui.in_(rxcui_by_id.values()),
                RxnormConceptRelation.relation_type.in_(INGREDIENT_RELATION_TYPES),
                ReferenceDrug.id.isnot(None),
                ReferenceDrug.is_active.is_(True),
            )
        )
    ).all()

    # Invert rxcui_by_id to id-by-rxcui for source lookup.
    id_by_rxcui: dict[str, set[uuid.UUID]] = {}
    for did, rxcui in rxcui_by_id.items():
        id_by_rxcui.setdefault(rxcui, set()).add(did)

    for src_rxcui, ing_id in target_rows:
        if ing_id is None:
            continue
        source_map.setdefault(ing_id, set())
        for sel_id in id_by_rxcui.get(src_rxcui, ()):
            source_map[ing_id].add(sel_id)

    return source_map


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
