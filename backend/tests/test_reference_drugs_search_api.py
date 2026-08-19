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
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug
from app.db.session import AsyncSessionLocal
from app.main import app

client = TestClient(app)


def _override_current_user(user_id):
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


async def _insert_drug(
    name: str,
    *,
    rxcui: str | None = None,
    source: str | None = None,
    term_type: str | None = None,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    drug_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
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


def test_search_requires_authentication():
    resp = client.get("/api/v1/reference-drugs/search?q=war")
    assert resp.status_code == 401


def test_search_rejects_query_shorter_than_two_chars(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get("/api/v1/reference-drugs/search?q=a")
    assert resp.status_code == 422


def test_search_requires_q_param(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get("/api/v1/reference-drugs/search")
    assert resp.status_code == 422


def test_limit_below_minimum_returns_422(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get("/api/v1/reference-drugs/search?q=war&limit=0")
    assert resp.status_code == 422


def test_limit_exceeding_maximum_returns_422(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get("/api/v1/reference-drugs/search?q=war&limit=101")
    assert resp.status_code == 422


def test_default_limit_is_twenty(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get("/api/v1/reference-drugs/search?q=a")
    assert resp.status_code == 200
    assert len(resp.json()) <= 20


def test_limit_is_respected(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    for i in range(5):
        created_drug_ids.append(asyncio.run(_insert_drug(f"Zzlimittest{tag}-{i}")))

    resp = client.get(f"/api/v1/reference-drugs/search?q=zzlimittest{tag}&limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_search_is_case_insensitive_partial_match(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    created_drug_ids.append(asyncio.run(_insert_drug(f"Zzspirtest{tag}Spironolactone")))

    resp = client.get(f"/api/v1/reference-drugs/search?q=ZZSPIRTEST{tag.upper()}SPIR")
    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert f"Zzspirtest{tag}Spironolactone" in names


def test_search_matches_substring_anywhere_in_name(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    created_drug_ids.append(asyncio.run(_insert_drug(f"Prefix-{tag}-Suffix")))

    resp = client.get(f"/api/v1/reference-drugs/search?q={tag}")
    assert resp.status_code == 200
    assert f"Prefix-{tag}-Suffix" in {d["name"] for d in resp.json()}


def test_query_whitespace_is_ignored(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    created_drug_ids.append(asyncio.run(_insert_drug(f"Zzwhitespace{tag}Warfarin")))

    resp = client.get(f"/api/v1/reference-drugs/search?q=  zzwhitespace{tag}warfarin  ")
    assert resp.status_code == 200
    assert f"Zzwhitespace{tag}Warfarin" in {d["name"] for d in resp.json()}


def test_ordering_exact_then_prefix_then_alphabetical_substring(
    existing_auth_user_id, created_drug_ids
):
    """
    Confirms the required ranking: exact match first, then prefix
    matches (alphabetical among themselves), then substring-only matches
    (alphabetical among themselves).
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    query = f"zzq{tag}"

    exact_name = query  # exact match (queried in different case to prove case-insensitivity)
    prefix_b = f"{query}Bbb"
    prefix_a = f"{query}Aaa"
    substring_only = f"before-{query}-after"

    created_drug_ids.append(asyncio.run(_insert_drug(prefix_b)))
    created_drug_ids.append(asyncio.run(_insert_drug(substring_only)))
    created_drug_ids.append(asyncio.run(_insert_drug(exact_name)))
    created_drug_ids.append(asyncio.run(_insert_drug(prefix_a)))

    resp = client.get(f"/api/v1/reference-drugs/search?q={query.upper()}&limit=10")
    assert resp.status_code == 200
    names_in_order = [d["name"] for d in resp.json()]

    assert names_in_order == [exact_name, prefix_a, prefix_b, substring_only]


def test_response_includes_expected_fields_only(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    unique_name = f"Zzfieldstest-{uuid.uuid4()}"
    created_drug_ids.append(
        asyncio.run(_insert_drug(unique_name, rxcui="12345", source="RxNorm"))
    )

    resp = client.get(f"/api/v1/reference-drugs/search?q={unique_name}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    entry = body[0]

    # term_type is an additive nullable field: present in the response
    # contract, NULL for rows without a known TTY.
    assert set(entry.keys()) == {"id", "name", "rxcui", "source", "term_type"}
    assert entry["name"] == unique_name
    assert entry["rxcui"] == "12345"
    assert entry["source"] == "RxNorm"
    assert entry["term_type"] is None


def test_response_exposes_term_type(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    unique_name = f"Zztttest-{uuid.uuid4()}"
    created_drug_ids.append(
        asyncio.run(_insert_drug(unique_name, rxcui="67890", source="RxNorm", term_type="SCD"))
    )

    resp = client.get(f"/api/v1/reference-drugs/search?q={unique_name}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["term_type"] == "SCD"


def test_term_type_filter_limits_results(existing_auth_user_id, created_drug_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    tag = str(uuid.uuid4())[:8]
    in_name = f"Zzttfilter{tag}-Ingredient"
    scd_name = f"Zzttfilter{tag}-Clinical"
    created_drug_ids.append(
        asyncio.run(_insert_drug(in_name, rxcui=f"ttf-in-{tag}", source="RxNorm", term_type="IN"))
    )
    created_drug_ids.append(
        asyncio.run(_insert_drug(scd_name, rxcui=f"ttf-scd-{tag}", source="RxNorm", term_type="SCD"))
    )

    # No filter -> both TTYs visible (original behavior preserved)
    resp = client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # IN only -> just the ingredient
    resp = client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}&term_type=IN")
    assert resp.status_code == 200
    assert [d["name"] for d in resp.json()] == [in_name]

    # Multi-TTY filter, case-insensitive
    resp = client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}&term_type=in,scd")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Filter with no matching TTY -> empty
    resp = client.get(f"/api/v1/reference-drugs/search?q=zzttfilter{tag}&term_type=DF")
    assert resp.status_code == 200
    assert resp.json() == []


def test_term_type_filter_invalid_returns_422(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get("/api/v1/reference-drugs/search?q=war&term_type=NOT_A_TTY")
    assert resp.status_code == 422
    assert "NOT_A_TTY" in resp.json()["detail"]


def test_parse_term_type_filter_unit():
    # No DB needed — pure validation helper
    from app.api.v1.reference_drugs import _parse_term_type_filter
    from fastapi import HTTPException

    assert _parse_term_type_filter(None) == []
    assert _parse_term_type_filter("IN,SCD") == ["IN", "SCD"]
    assert _parse_term_type_filter("in, scd ") == ["IN", "SCD"]
    with pytest.raises(HTTPException) as ei:
        _parse_term_type_filter("IN,BOGUS")
    assert ei.value.status_code == 422
    assert "BOGUS" in ei.value.detail


def test_search_with_no_matches_returns_empty_list(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    resp = client.get(f"/api/v1/reference-drugs/search?q=zzznomatch{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == []
