"""
Unit tests for backend/scripts/import_rxnorm.py.

RxNav HTTP calls are mocked (no real network call, no dependency on RxNav
uptime) -- `fetch_all_concepts` and `select_batch` are pure/local-I/O-only
and are tested in full isolation.

`import_batch`'s upsert logic (new-insert / rxcui-match / name-backfill /
ambiguous-skip / dry-run) is exercised against the live test database
(same convention as every other test module in this repo -- see
tests/conftest.py's docstring), since it is genuine DB upsert logic, not
something meaningfully unit-testable against a mock session. This file
defines its own local cleanup fixtures rather than modifying conftest.py.

Run with:  pytest backend/tests/test_import_rxnorm.py -v
Requires:  the rxcui/source/source_updated_at columns already present on
           reference_drugs (003_reference_drugs_external_reference.sql).
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.db.models import ReferenceDrug
from app.db.session import AsyncSessionLocal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import import_rxnorm  # noqa: E402


@pytest.fixture
def created_drug_ids() -> list[uuid.UUID]:
    return []


@pytest.fixture(autouse=True)
async def _cleanup_created_drugs(created_drug_ids: list[uuid.UUID]):
    yield
    if not created_drug_ids:
        return
    async with AsyncSessionLocal() as session:
        for drug_id in created_drug_ids:
            result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.id == drug_id))
            drug = result.scalar_one_or_none()
            if drug is not None:
                await session.delete(drug)
        await session.commit()


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Redirect the script's cache/checkpoint dir to a per-test tmp dir."""
    monkeypatch.setattr(import_rxnorm, "CACHE_DIR", tmp_path)


def _fake_allconcepts_response(concepts: list[tuple[str, str]]) -> dict:
    return {
        "minConceptGroup": {
            "minConcept": [{"rxcui": rxcui, "name": name, "tty": "IN"} for rxcui, name in concepts]
        }
    }


class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


# ---------------------------------------------------------------------
# fetch_all_concepts -- mocked HTTP
# ---------------------------------------------------------------------


def test_fetch_all_concepts_parses_response(monkeypatch):
    fake_data = _fake_allconcepts_response([("11289", "Warfarin"), ("1191", "Aspirin")])

    def _fake_get(url, params=None, timeout=None):
        assert "allconcepts.json" in url
        assert params == {"tty": "IN"}
        return _FakeResponse(fake_data)

    monkeypatch.setattr(httpx, "get", _fake_get)

    concepts = import_rxnorm.fetch_all_concepts("IN")
    assert {c.name for c in concepts} == {"Warfarin", "Aspirin"}
    assert all(isinstance(c.rxcui, str) for c in concepts)


def test_fetch_all_concepts_sorts_deterministically(monkeypatch):
    fake_data = _fake_allconcepts_response(
        [("3", "Zolpidem"), ("1", "Amoxicillin"), ("2", "Metformin")]
    )
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse(fake_data))

    concepts = import_rxnorm.fetch_all_concepts("IN")
    assert [c.name for c in concepts] == ["Amoxicillin", "Metformin", "Zolpidem"]


def test_fetch_all_concepts_uses_cache_on_second_call(monkeypatch):
    fake_data = _fake_allconcepts_response([("11289", "Warfarin")])
    call_count = {"n": 0}

    def _fake_get(*a, **kw):
        call_count["n"] += 1
        return _FakeResponse(fake_data)

    monkeypatch.setattr(httpx, "get", _fake_get)

    import_rxnorm.fetch_all_concepts("IN")
    import_rxnorm.fetch_all_concepts("IN")  # should hit the on-disk cache

    assert call_count["n"] == 1


def test_fetch_all_concepts_refresh_cache_forces_refetch(monkeypatch):
    fake_data = _fake_allconcepts_response([("11289", "Warfarin")])
    call_count = {"n": 0}

    def _fake_get(*a, **kw):
        call_count["n"] += 1
        return _FakeResponse(fake_data)

    monkeypatch.setattr(httpx, "get", _fake_get)

    import_rxnorm.fetch_all_concepts("IN")
    import_rxnorm.fetch_all_concepts("IN", refresh_cache=True)

    assert call_count["n"] == 2


def test_fetch_all_concepts_skips_malformed_entries(monkeypatch):
    fake_data = {
        "minConceptGroup": {
            "minConcept": [
                {"rxcui": "1", "name": "Valid Drug", "tty": "IN"},
                {"rxcui": "2"},  # missing name -- must be skipped, not raise
                {"name": "No RxCUI Drug"},  # missing rxcui -- must be skipped
            ]
        }
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse(fake_data))

    concepts = import_rxnorm.fetch_all_concepts("IN")
    assert [c.name for c in concepts] == ["Valid Drug"]


# ---------------------------------------------------------------------
# select_batch -- pure client-side pagination
# ---------------------------------------------------------------------


def _make_concepts(n: int) -> list:
    return [import_rxnorm.RxNormConcept(rxcui=str(i), name=f"Drug {i}", tty="IN") for i in range(n)]


def test_select_batch_applies_offset_and_limit():
    batch = import_rxnorm.select_batch(_make_concepts(10), offset=2, limit=3)
    assert [c.name for c in batch] == ["Drug 2", "Drug 3", "Drug 4"]


def test_select_batch_no_limit_returns_remainder():
    batch = import_rxnorm.select_batch(_make_concepts(5), offset=3, limit=None)
    assert [c.name for c in batch] == ["Drug 3", "Drug 4"]


def test_select_batch_offset_past_end_returns_empty():
    assert import_rxnorm.select_batch(_make_concepts(3), offset=10, limit=5) == []


# ---------------------------------------------------------------------
# checkpoint read/write -- pure local file I/O
# ---------------------------------------------------------------------


def test_checkpoint_defaults_to_zero_when_absent():
    assert import_rxnorm._read_checkpoint("IN") == 0


def test_checkpoint_round_trip():
    import_rxnorm._write_checkpoint("IN", 250)
    assert import_rxnorm._read_checkpoint("IN") == 250


# ---------------------------------------------------------------------
# import_batch -- upsert logic against the live test database
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_batch_inserts_new_drug(created_drug_ids):
    unique_name = f"Test Import Drug {uuid.uuid4()}"
    concept = import_rxnorm.RxNormConcept(rxcui=f"rx-{uuid.uuid4()}", name=unique_name, tty="IN")

    stats = await import_rxnorm.import_batch([concept], dry_run=False)
    assert stats.inserted_new == 1
    assert stats.updated_existing_by_rxcui == 0
    assert stats.backfilled_existing_by_name == 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.rxcui == concept.rxcui))
        drug = result.scalar_one()
        created_drug_ids.append(drug.id)

    assert drug.name == unique_name
    assert drug.source == "RxNorm"
    assert drug.source_updated_at is not None


@pytest.mark.asyncio
async def test_import_batch_backfills_existing_row_preserving_id(created_drug_ids):
    """Simulates backfilling one of the original curated seed drugs: an
    existing row with a matching name and no rxcui must be UPDATED in
    place (same id preserved), never re-inserted as a duplicate."""
    unique_name = f"Test Backfill Drug {uuid.uuid4()}"
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        existing = ReferenceDrug(
            id=uuid.uuid4(), name=unique_name, generic_name=None, drug_class=None,
            created_at=now, updated_at=now,
        )
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        original_id = existing.id
    created_drug_ids.append(original_id)

    concept = import_rxnorm.RxNormConcept(rxcui=f"rx-{uuid.uuid4()}", name=unique_name, tty="IN")
    stats = await import_rxnorm.import_batch([concept], dry_run=False)

    assert stats.backfilled_existing_by_name == 1
    assert stats.inserted_new == 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.id == original_id))
        refreshed = result.scalar_one()

    assert refreshed.id == original_id  # FK-preserving -- same primary key
    assert refreshed.rxcui == concept.rxcui
    assert refreshed.source == "RxNorm"


@pytest.mark.asyncio
async def test_import_batch_is_idempotent_on_rerun(created_drug_ids):
    unique_name = f"Test Idempotent Drug {uuid.uuid4()}"
    concept = import_rxnorm.RxNormConcept(rxcui=f"rx-{uuid.uuid4()}", name=unique_name, tty="IN")

    first = await import_rxnorm.import_batch([concept], dry_run=False)
    assert first.inserted_new == 1

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.rxcui == concept.rxcui))
        created_drug_ids.append(result.scalar_one().id)

    second = await import_rxnorm.import_batch([concept], dry_run=False)
    assert second.inserted_new == 0
    assert second.updated_existing_by_rxcui == 1

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.rxcui == concept.rxcui))
        assert len(result.scalars().all()) == 1  # never duplicated on rerun


@pytest.mark.asyncio
async def test_import_batch_skips_ambiguous_name_match(created_drug_ids):
    unique_name = f"Test Ambiguous Drug {uuid.uuid4()}"
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        existing = ReferenceDrug(
            id=uuid.uuid4(), name=unique_name, generic_name=None, drug_class=None,
            rxcui="already-set-rxcui", source="RxNorm", source_updated_at=now,
            created_at=now, updated_at=now,
        )
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
    created_drug_ids.append(existing.id)

    conflicting = import_rxnorm.RxNormConcept(rxcui="a-different-rxcui", name=unique_name, tty="IN")
    stats = await import_rxnorm.import_batch([conflicting], dry_run=False)

    assert stats.skipped_ambiguous == 1
    assert stats.inserted_new == 0
    assert stats.backfilled_existing_by_name == 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.id == existing.id))
        assert result.scalar_one().rxcui == "already-set-rxcui"  # untouched


@pytest.mark.asyncio
async def test_import_batch_dry_run_writes_nothing():
    unique_name = f"Test Dry Run Drug {uuid.uuid4()}"
    concept = import_rxnorm.RxNormConcept(rxcui=f"rx-{uuid.uuid4()}", name=unique_name, tty="IN")

    stats = await import_rxnorm.import_batch([concept], dry_run=True)
    assert stats.inserted_new == 1  # counted, but not persisted

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.rxcui == concept.rxcui))
        assert result.scalar_one_or_none() is None
