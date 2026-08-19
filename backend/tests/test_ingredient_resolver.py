"""DB-free unit tests for the ingredient resolver.

These tests exercise the pure-function
:func:`resolve_selected_rxcuis_to_ingredient_rxcuis` exhaustively
(no DB, no network, no env vars), and also verify that the DB-backed
:func:`resolve_to_ingredient_ids` issues exactly the queries implied
by the LEFT-JOIN / one-hop contract by driving it against a small
in-memory fake session.

Run with:
    pytest backend/tests/test_ingredient_resolver.py -v
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.analysis.ingredient_resolver import (
    INGREDIENT_RELATION_TYPES,
    resolve_selected_rxcuis_to_ingredient_rxcuis,
    resolve_to_ingredient_ids,
)


# ---------------------------------------------------------------------------
# Pure-function tests (resolve_selected_rxcuis_to_ingredient_rxcuis)
# ---------------------------------------------------------------------------


def test_preserves_selected_id_when_no_edges():
    """LEFT JOIN semantics: selected RxCUI is always kept, even with zero edges."""
    assert resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], []) == {"123"}


def test_resolves_has_ingredient_to_target():
    edges = [("123", "has_ingredient", "456")]
    assert resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges) == {"123", "456"}


def test_resolves_has_precise_ingredient():
    edges = [("123", "has_precise_ingredient", "789")]
    assert resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges) == {"123", "789"}


def test_ignores_non_ingredient_relation_types():
    """has_tradename / isa / has_form etc. must NOT be traversed."""
    for rel in ("has_tradename", "isa", "has_form", "has_dose_form", "has_part", "consists_of"):
        edges = [("123", rel, "456")]
        assert resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges) == {"123"}


def test_ingredient_relation_types_are_exactly_the_two_expected():
    assert INGREDIENT_RELATION_TYPES == {"has_ingredient", "has_precise_ingredient"}


def test_one_hop_only_does_not_recurse():
    """If an ingredient itself has an outgoing edge, we must NOT follow it."""
    edges = [
        ("123", "has_ingredient", "456"),
        ("456", "has_ingredient", "999"),  # must NOT be traversed
    ]
    assert resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges) == {"123", "456"}


def test_deduplicates_duplicate_targets():
    """Two edges pointing at the same ingredient collapse to one."""
    edges = [
        ("123", "has_ingredient", "456"),
        ("123", "has_precise_ingredient", "456"),
    ]
    out = resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges)
    assert out == {"123", "456"}


def test_multiple_selected_drugs_all_preserved():
    edges = [("123", "has_ingredient", "456")]
    out = resolve_selected_rxcuis_to_ingredient_rxcuis(["123", "777"], edges)
    assert out == {"123", "456", "777"}


def test_missing_unimported_or_null_targets_preserve_selected_id():
    """When the selected RxCUI has no ingredient edges (edges unimported
    or the drug IS the ingredient), only the selected RxCUI is returned."""
    edges = [("999", "has_ingredient", "888")]  # unrelated edge
    out = resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges)
    assert out == {"123"}


def test_empty_input_returns_empty_set():
    assert resolve_selected_rxcuis_to_ingredient_rxcuis([], []) == set()
    assert resolve_selected_rxcuis_to_ingredient_rxcuis([], [("a", "has_ingredient", "b")]) == set()


def test_filters_out_empty_string_rxcuis():
    assert resolve_selected_rxcuis_to_ingredient_rxcuis(["", "  "], []) == set()


def test_source_to_target_direction_is_source_to_target_not_reverse():
    """Edge direction is source->target; we do NOT traverse target->source."""
    edges = [
        # ingredient -> drug (tradename-style direction in reverse)
        ("456", "has_tradename", "123"),
    ]
    # Selected is drug 123, edge is from ingredient 456 to 123 -- must NOT
    # be traversed as a reverse lookup.
    out = resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges)
    assert out == {"123"}


def test_multiple_ingredients_per_drug_all_resolved():
    edges = [
        ("123", "has_ingredient", "456"),
        ("123", "has_ingredient", "789"),
    ]
    out = resolve_selected_rxcuis_to_ingredient_rxcuis(["123"], edges)
    assert out == {"123", "456", "789"}


def test_multiple_drugs_sharing_same_ingredient_deduplicates():
    edges = [
        ("123", "has_ingredient", "456"),
        ("789", "has_ingredient", "456"),
    ]
    out = resolve_selected_rxcuis_to_ingredient_rxcuis(["123", "789"], edges)
    assert out == {"123", "789", "456"}


# ---------------------------------------------------------------------------
# DB-backed resolver: contract tests using a fake session
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Minimal async session stub that captures executed SELECT statements
    and replays pre-programmed rows per call site (identified by the
    columns/froms the statement touches)."""

    def __init__(self, rxcui_rows=None, relation_rows=None):
        # rxcui_rows: list of (id, rxcui) rows returned for the
        #   ReferenceDrug rxcui lookup (used to resolve selected ids).
        # relation_rows: list of (target_id,) rows returned for the join
        #   against rxnorm_concept_relations -> reference_drugs (ingredient).
        self.rxcui_rows = rxcui_rows or []
        self.relation_rows = relation_rows or []
        self.calls: list[Any] = []

    async def execute(self, stmt):
        self.calls.append(stmt)
        # Naive routing: if the compiled statement references
        # rxnorm_concept_relations, serve relation_rows; else serve rxcui_rows.
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "rxnorm_concept_relations" in compiled.lower():
            return FakeResult(self.relation_rows)
        return FakeResult(self.rxcui_rows)


def _id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_db_resolver_preserves_selected_ids_when_no_rxcui():
    selected = [_id(), _id()]
    # No rxcuis on any selected drug -> no relation lookup performed,
    # output is exactly the selected set.
    db = FakeSession(rxcui_rows=[(selected[0], None), (selected[1], None)], relation_rows=[])
    out = await resolve_to_ingredient_ids(selected, db)
    assert out == set(selected)


@pytest.mark.asyncio
async def test_db_resolver_resolves_to_ingredient_id_via_join():
    selected_id = _id()
    ing_id = _id()
    db = FakeSession(
        rxcui_rows=[(selected_id, "123")],
        relation_rows=[(ing_id,)],
    )
    out = await resolve_to_ingredient_ids([selected_id], db)
    assert out == {selected_id, ing_id}
    # Must have issued exactly two SELECTs: one for rxcui lookup, one
    # for the relation join.
    assert len(db.calls) == 2


@pytest.mark.asyncio
async def test_db_resolver_handles_null_targets_in_relation_join():
    """If a LEFT JOIN yields a NULL target id (ingredient not imported),
    that NULL must be silently ignored, not crash, and the selected id
    is still in the output."""
    selected_id = _id()
    db = FakeSession(
        rxcui_rows=[(selected_id, "123")],
        relation_rows=[(None,), (_id(),)],  # NULL + valid ingredient
    )
    out = await resolve_to_ingredient_ids([selected_id], db)
    # selected_id plus the non-NULL ingredient id
    assert selected_id in out
    assert len(out) == 2


@pytest.mark.asyncio
async def test_db_resolver_empty_input_returns_empty_set():
    db = FakeSession()
    out = await resolve_to_ingredient_ids([], db)
    assert out == set()
    assert db.calls == []  # no queries for empty input


@pytest.mark.asyncio
async def test_db_resolver_deduplicates_duplicate_ingredient_rows():
    selected_id = _id()
    ing_id = _id()
    db = FakeSession(
        rxcui_rows=[(selected_id, "123")],
        relation_rows=[(ing_id,), (ing_id,), (ing_id,)],
    )
    out = await resolve_to_ingredient_ids([selected_id], db)
    assert out == {selected_id, ing_id}


@pytest.mark.asyncio
async def test_db_resolver_does_not_recurse():
    """One-hop only: after finding an ingredient id, we do not issue a
    second query to see if *that* id has its own ingredients."""
    selected_id = _id()
    ing_id = _id()
    db = FakeSession(
        rxcui_rows=[(selected_id, "123")],
        relation_rows=[(ing_id,)],
    )
    await resolve_to_ingredient_ids([selected_id], db)
    # Two calls total: rxcui lookup + one relation join. A recursive
    # implementation would issue a third call to look up rxcui for ing_id.
    assert len(db.calls) == 2


@pytest.mark.asyncio
async def test_db_resolver_filters_by_ingredient_relation_types_only():
    """The generated SQL must include an IN clause restricted to the
    ingredient relation types."""
    selected_id = _id()
    db = FakeSession(
        rxcui_rows=[(selected_id, "123")],
        relation_rows=[],
    )
    await resolve_to_ingredient_ids([selected_id], db)
    assert len(db.calls) == 2
    relation_stmt = str(db.calls[1].compile(compile_kwargs={"literal_binds": True}))
    assert "has_ingredient" in relation_stmt
    assert "has_precise_ingredient" in relation_stmt
    # Make sure unrelated relation types are NOT in the IN list.
    for non_ing in ("has_tradename", "isa", "has_form", "has_dose_form", "has_part"):
        assert non_ing not in relation_stmt
