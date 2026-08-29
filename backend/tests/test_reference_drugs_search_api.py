"""
Reference-drug search endpoint tests.

Integration tests against a live Supabase Postgres instance (same
requirement as every other API test module -- see conftest.py). This
endpoint is read-only and NOT patient/user-scoped (reference_drugs is
shared reference data across all authenticated users), so these tests
only need `get_current_user` overridden for authentication -- no patient
fixtures required.

Rows created by these tests use distinctive, uuid-tagged names and are
cleaned up via a local fixture -- deliberately NOT added to conftest.py.

Run with:  pytest backend/tests/test_reference_drugs_search_api.py -v
Requires:  at least one row in auth.users (see conftest.py), and the
           rxcui/source/source_updated_at columns already present on
           reference_drugs (003_reference_drugs_external_reference.sql).

NOTE: This module uses its own test-specific async engine/sessionmaker to avoid
"Event loop is closed" errors with pytest-asyncio asyncio_mode=auto. The global
AsyncSessionLocal from app.db.session shares a single engine across all tests,
which causes connections bound to one test's closed event loop to be reused by
a subsequent test. This module creates its own engine for each test to ensure each
test's connections are bound to its own pytest-managed event loop.
"""
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug
from app.main import app

# Test-specific DB engine/sessionmaker to avoid cross-test event-loop issues.
# Each test gets its own pytest-managed event loop with asyncio_mode=auto.
# The global engine from app.db.session is shared and can have connections
# bound to closed event loops. This module creates a fresh engine for each test.
_test_engine = None


@pytest.fixture(autouse=True)
async def _test_db_engine():
    """Create and dispose a test-specific async engine for each test."""
    global _test_engine
    settings = get_settings()
    _test_engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    yield _test_engine
    await _test_engine.dispose()
    _test_engine = None


@pytest.fixture
def test_sessionmaker(_test_db_engine):
    """Provide a test-specific async_sessionmaker bound to the test's engine."""
    return async_sessionmaker(
        bind=_test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _make_override_current_user(user_id):
    """Build the FastAPI auth override used by these integration tests."""
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")

    return _fake_current_user


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def created_drug_ids() -> list[uuid.UUID]:
    return []


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


async def _insert_drug(
    name: str,
    *,
    rxcui: str | None = None,
    source: str | None = None,
    term_type: str | None = None,
    sessionmaker=None,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    drug_id = uuid.uuid4()
    async with sessionmaker() as session:
        session.add(
            ReferenceDrug(
                id=drug_id, name=name, generic_name=None, drug_class=None,
                rxcui=rxcui, source=source, source_updated_at=now if source else None,
                term_type=term_type,
                created_at=now, updated_at=now,
            )
        )
        await session.commit()
    return drug_id


@pytest.fixture(autouse=True)
async def _cleanup_created_drugs(created_drug_ids: list[uuid.UUID], test_sessionmaker):
    yield
    if not created_drug_ids:
        return
    async with test_sessionmaker() as session:
        for drug_id in created_drug_ids:
            result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.id == drug_id))
            drug = result.scalar_one_or_none()
            if drug is not None:
                await session.delete(drug)
        await session.commit()


@pytest.mark.asyncio
async def test_search_requires_authentication(client):
    resp = await client.get("/api/v1/reference-drugs/search?q=war")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_rejects_query_shorter_than_two_chars(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get("/api/v1/reference-drugs/search?q=a")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_requires_q_param(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get("/api/v1/reference-drugs/search")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_limit_below_minimum_returns_422(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get("/api/v1/reference-drugs/search?q=war&limit=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_limit_exceeding_maximum_returns_422(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get("/api/v1/reference-drugs/search?q=war&limit=101")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_default_limit_is_twenty(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get("/api/v1/reference-drugs/search?q=war")
    assert resp.status_code == 200
    assert len(resp.json()) <= 20


@pytest.mark.asyncio
async def test_limit_is_respected(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    for i in range(5):
        created_drug_ids.append(await _insert_drug(f"Zzlimittest{tag}-{i}", sessionmaker=test_sessionmaker))

    resp = await client.get(f"/api/v1/reference-drugs/search?q=zzlimittest{tag}&limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_search_is_case_insensitive_partial_match(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    created_drug_ids.append(await _insert_drug(f"Zzspirtest{tag}Spironolactone", sessionmaker=test_sessionmaker))

    resp = await client.get(f"/api/v1/reference-drugs/search?q=ZZSPIRTEST{tag.upper()}SPIR")
    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert f"Zzspirtest{tag}Spironolactone" in names


@pytest.mark.asyncio
async def test_search_matches_substring_anywhere_in_name(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    created_drug_ids.append(await _insert_drug(f"Prefix-{tag}-Suffix", sessionmaker=test_sessionmaker))

    resp = await client.get(f"/api/v1/reference-drugs/search?q={tag}")
    assert resp.status_code == 200
    assert f"Prefix-{tag}-Suffix" in {d["name"] for d in resp.json()}


@pytest.mark.asyncio
async def test_query_whitespace_is_ignored(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    created_drug_ids.append(await _insert_drug(f"Zzwhitespace{tag}Warfarin", sessionmaker=test_sessionmaker))

    resp = await client.get(f"/api/v1/reference-drugs/search?q=  zzwhitespace{tag}warfarin  ")
    assert resp.status_code == 200
    assert f"Zzwhitespace{tag}Warfarin" in {d["name"] for d in resp.json()}


@pytest.mark.asyncio
async def test_ordering_exact_then_prefix_then_alphabetical_substring(
    existing_auth_user_id, created_drug_ids, client, test_sessionmaker
):
    """
    Confirms the required ranking: exact match first, then prefix
    matches (alphabetical among themselves), then substring-only matches
    (alphabetical among themselves).
    """
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    query = f"zzq{tag}"

    exact_name = query
    prefix_b = f"{query}Bbb"
    prefix_a = f"{query}Aaa"
    substring_only = f"before-{query}-after"

    created_drug_ids.append(await _insert_drug(prefix_b, sessionmaker=test_sessionmaker))
    created_drug_ids.append(await _insert_drug(substring_only, sessionmaker=test_sessionmaker))
    created_drug_ids.append(await _insert_drug(exact_name, sessionmaker=test_sessionmaker))
    created_drug_ids.append(await _insert_drug(prefix_a, sessionmaker=test_sessionmaker))

    resp = await client.get(f"/api/v1/reference-drugs/search?q={query.upper()}&limit=10")
    assert resp.status_code == 200
    names_in_order = [d["name"] for d in resp.json()]

    assert names_in_order == [exact_name, prefix_a, prefix_b, substring_only]


@pytest.mark.asyncio
async def test_response_includes_expected_fields_only(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    unique_name = f"Zzfieldstest-{uuid.uuid4()}"
    created_drug_ids.append(
        await _insert_drug(unique_name, rxcui="12345", source="RxNorm", sessionmaker=test_sessionmaker)
    )

    resp = await client.get(f"/api/v1/reference-drugs/search?q={unique_name}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    entry = body[0]

    assert set(entry.keys()) == {"id", "name", "rxcui", "source", "term_type"}
    assert entry["name"] == unique_name
    assert entry["rxcui"] == "12345"
    assert entry["source"] == "RxNorm"
    assert entry["term_type"] is None


@pytest.mark.asyncio
async def test_response_exposes_term_type(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    unique_name = f"Zztttest-{uuid.uuid4()}"
    created_drug_ids.append(
        await _insert_drug(unique_name, rxcui="67890", source="RxNorm", term_type="SCD", sessionmaker=test_sessionmaker)
    )

    resp = await client.get(f"/api/v1/reference-drugs/search?q={unique_name}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["term_type"] == "SCD"


@pytest.mark.asyncio
async def test_term_type_filter_limits_results(existing_auth_user_id, created_drug_ids, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    in_name = f"Zzttfilter{tag}-Ingredient"
    scd_name = f"Zzttfilter{tag}-Clinical"
    created_drug_ids.append(
        await _insert_drug(in_name, rxcui=f"ttf-in-{tag}", source="RxNorm", term_type="IN", sessionmaker=test_sessionmaker)
    )
    created_drug_ids.append(
        await _insert_drug(scd_name, rxcui=f"ttf-scd-{tag}", source="RxNorm", term_type="SCD", sessionmaker=test_sessionmaker)
    )

    resp = await client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = await client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}&term_type=IN")
    assert resp.status_code == 200
    assert [d["name"] for d in resp.json()] == [in_name]

    resp = await client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}&term_type=in,scd")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = await client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}&term_type=DF")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_term_type_filter_invalid_returns_422(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get("/api/v1/reference-drugs/search?q=war&term_type=NOT_A_TTY")
    assert resp.status_code == 422
    assert "NOT_A_TTY" in resp.json()["detail"]


def test_parse_term_type_filter_unit():
    from app.api.v1.reference_drugs import _parse_term_type_filter
    from fastapi import HTTPException

    assert _parse_term_type_filter(None) == []
    assert _parse_term_type_filter("IN,SCD") == ["IN", "SCD"]
    assert _parse_term_type_filter("in, scd ") == ["IN", "SCD"]
    with pytest.raises(HTTPException) as ei:
        _parse_term_type_filter("IN,BOGUS")
    assert ei.value.status_code == 422
    assert "BOGUS" in ei.value.detail


@pytest.mark.asyncio
async def test_search_with_no_matches_returns_empty_list(existing_auth_user_id, client, test_sessionmaker):
    app.dependency_overrides[get_current_user] = _make_override_current_user(existing_auth_user_id)
    resp = await client.get(f"/api/v1/reference-drugs/search?q=zzznomatch{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == []
