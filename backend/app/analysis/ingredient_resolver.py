"""Resolve selected drug references to their ingredient-level RxCUI/IDs.

RxNorm ``rxnorm_concept_relations`` (Alembic 0003) stores relationship
edges as ``source_rxcui <relation_type> target_rxcui``. When a clinician
or patient selects a branded drug (SBD/BPCK/BN), a clinical drug form
(SCDF/SBDF), or a clinical drug component (SCDC/SBDC) for a medication,
the deterministic safety engines (ADR and drug-interaction) need to
match against rules keyed to the underlying *ingredient* (IN / PIN /
MIN) rather than the formulation that happens to be picked.

This module performs exactly that resolution:

* **Direction** -- ``source_rxcui -> target_rxcui`` (the relationship
  "has_ingredient X" on row (source=SBD, target=IN) means "the branded
  drug SBD contains ingredient IN"; resolving SBD therefore yields IN).
* **Edge filter** -- only ``has_ingredient`` and
  ``has_precise_ingredient`` edges are traversed; other relationship
  types (``has_tradename``, ``isa``, ``has_form``, ...) are explicitly
  ignored because they do not identify ingredients.
* **One hop only** -- resolution does not recurse (ingredient rows do
  not themselves have ingredient edges; preventing multi-hop traversal
  avoids accidentally climbing other hierarchies if future migrations
  add them).
* **LEFT JOIN semantics** -- the *selected* ID is always preserved in
  the output set, even when:
    * the selected drug has no RxCUI recorded (``reference_drugs.rxcui
      IS NULL`` for hand-curated rows),
    * the RxCUI is not present in ``rxnorm_concept_relations``
      (unimported / relationship edges not yet fetched via
      ``import_rxnorm.py --related``), or
    * no ``has_ingredient`` / ``has_precise_ingredient`` edge exists
      for that source (the selected drug *is* the ingredient itself).
  In those cases the output is just ``{selected_id}``, so downstream
  matching does not lose the user's choice.
* **Duplicate IDs deduplicated** -- multiple edges that resolve to the
  same ingredient RxCUI collapse to a single ID.
* **Pair count happens before resolution** -- callers (the drug
  interaction engine) count distinct selected pairs before resolution,
  because pairing two branded formulations of the same two ingredients
  must still produce exactly one interaction finding. This module does
  not do pairing itself; it only resolves a set of IDs to a
  (potentially larger) set that includes ingredient IDs for rule
  matching.

The resolver is pure read-only: it never writes, never caches across
sessions, and never falls back to LLM/network lookup -- missing edges
simply mean "keep the selected ID, don't invent ingredients."

DB-free unit tests live in ``backend/tests/test_ingredient_resolver.py``
and use a small in-memory fake that emulates the relevant
SELECT/LEFT-JOIN shape, so resolver behavior is deterministic without a
live Supabase.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReferenceDrug, RxnormConceptRelation

# Relationship types that identify ingredients of a drug. Kept as a
# frozenset so callers cannot mutate it at runtime; the order doesn't
# matter because we dedupe results.
INGREDIENT_RELATION_TYPES: frozenset[str] = frozenset(
    {"has_ingredient", "has_precise_ingredient"}
)


async def resolve_to_ingredient_ids(
    selected_drug_ids: Iterable[uuid.UUID],
    db: AsyncSession,
) -> set[uuid.UUID]:
    """Resolve the given reference_drug IDs to the set of ingredient IDs.

    Returns a set that always includes every selected ID (LEFT JOIN
    semantics), plus the reference_drug.id of every ingredient target
    reachable via one ``has_ingredient`` / ``has_precise_ingredient``
    edge from any selected drug's RxCUI.

    Missing-RxCUI / unimported / no-edge cases are silently preserved:
    a selected drug whose RxCUI has no ingredient edge simply contributes
    itself, nothing more. Duplicate IDs are deduplicated (as sets do).

    One-hop only: if the returned ingredient IDs themselves had outgoing
    ``has_ingredient`` edges (they don't in RxNorm today, but defensively)
    we do NOT traverse them.
    """
    selected = {did for did in selected_drug_ids if did is not None}
    if not selected:
        return set()

    # Pull RxCUIs for the selected drugs. Drugs with NULL rxcui cannot be
    # resolved further -- they stay in the set as-is via the |selected|
    # union below; the join simply finds nothing for them.
    rxcui_rows = (
        await db.execute(
            select(ReferenceDrug.id, ReferenceDrug.rxcui).where(
                ReferenceDrug.id.in_(selected)
            )
        )
    ).all()
    selected_rxcuis: list[str] = [rxcui for _id, rxcui in rxcui_rows if rxcui]

    resolved: set[uuid.UUID] = set(selected)  # LEFT JOIN: keep every selected ID.

    if not selected_rxcuis:
        return resolved

    # One-hop resolution: selected.rxcui = relation.source_rxcui ->
    # target_rxcui -> reference_drugs.id WHERE relation_type is an
    # ingredient relation. The LEFT JOIN semantics are achieved by
    # starting from `selected` and *adding* targets when they exist;
    # sources without a match contribute nothing extra (and themselves
    # are already in the set).
    target_alias = ReferenceDrug.__table__.alias("ingredient_drug")
    rows = (
        await db.execute(
            select(target_alias.c.id)
            .select_from(
                RxnormConceptRelation.__table__.join(
                    target_alias,
                    target_alias.c.rxcui == RxnormConceptRelation.target_rxcui,
                    isouter=True,
                )
            )
            .where(
                RxnormConceptRelation.source_rxcui.in_(selected_rxcuis),
                RxnormConceptRelation.relation_type.in_(INGREDIENT_RELATION_TYPES),
                # Defensive: ignore retired ingredient rows if any.
                target_alias.c.is_active.is_(True),
            )
        )
    ).all()

    for (ing_id,) in rows:
        if ing_id is not None:
            resolved.add(ing_id)

    return resolved


def resolve_selected_rxcuis_to_ingredient_rxcuis(
    selected_rxcuis: Iterable[str],
    edges: Sequence[tuple[str, str, str]],
) -> set[str]:
    """Pure-function, DB-free variant used by tests and offline tooling.

    Given an iterable of selected RxCUI strings and a sequence of
    ``(source_rxcui, relation_type, target_rxcui)`` edges, return the
    set of RXCUIs that includes every selected RXCUI plus any target
    RXCUI reachable in one hop via an ingredient edge.

    This mirrors :func:`resolve_to_ingredient_ids` but operates on
    RxCUI strings directly (no DB lookup) so it can be unit tested
    exhaustively without any database setup. The production DB-backed
    resolver should behave exactly like this function on equivalent
    inputs.
    """
    selected = {r.strip() for r in selected_rxcuis if r and r.strip()}
    resolved: set[str] = set(selected)  # LEFT JOIN: preserve every selected RxCUI.

    # Build a quick lookup: source_rxcui -> set[target_rxcui] for ingredient edges.
    ingredient_targets: dict[str, set[str]] = {}
    for src, rel, tgt in edges:
        if rel not in INGREDIENT_RELATION_TYPES:
            continue
        ingredient_targets.setdefault(src, set()).add(tgt)

    for src in selected:
        for tgt in ingredient_targets.get(src, ()):
            resolved.add(tgt)
        # One-hop only: do NOT recurse into `tgt`.

    return resolved
