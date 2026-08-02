"""
Phase 14 timeline engine tests.

Integration tests against a live Supabase Postgres instance (same
requirement as all prior phase test modules) -- `build_timeline_context`
queries `timeline_events` directly, relying on Phase 7's automatic event
logging (exercised here via the already-tested symptoms/medications
API endpoints).

No HTTP endpoint exists for this engine (it is a LangGraph workflow
node), so these tests call
`app.analysis.timeline_engine.build_timeline_context` directly against
an `AsyncSessionLocal` session, mirroring Phases 10-13's testing
approach.

Run with:  pytest backend/tests/test_timeline_engine.py -v
Requires:  at least one row in auth.users (see conftest.py).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.analysis.timeline_engine import TimelineContext, build_timeline_context
from app.core.security import CurrentUser, get_current_user
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


def _create_patient(name: str = "Timeline Engine Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_symptom(patient_id: str, description: str) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/symptoms", json={"description": description}
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_empty_patient_returns_no_entries(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Empty Timeline Engine Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        context = await build_timeline_context(uuid.UUID(patient["id"]), session)

    assert isinstance(context, TimelineContext)
    assert context.entries == []


@pytest.mark.asyncio
async def test_entries_ordered_chronologically_ascending(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Chronological Timeline Engine Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    first = _create_symptom(patient["id"], "First symptom")
    second = _create_symptom(patient["id"], "Second symptom")

    async with AsyncSessionLocal() as session:
        context = await build_timeline_context(uuid.UUID(patient["id"]), session)

    ref_ids_in_order = [e.ref_id for e in context.entries if e.ref_id is not None]
    assert ref_ids_in_order.index(uuid.UUID(first["id"])) < ref_ids_in_order.index(
        uuid.UUID(second["id"])
    )
    event_times = [e.event_time for e in context.entries]
    assert event_times == sorted(event_times)  # ascending, unlike GET /timeline's DESC order


@pytest.mark.asyncio
async def test_context_scoped_to_patient(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Scoped Timeline Engine Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Scoped Timeline Engine Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    own_symptom = _create_symptom(patient_a["id"], "Mine")
    other_symptom = _create_symptom(patient_b["id"], "Not mine")

    async with AsyncSessionLocal() as session:
        context_a = await build_timeline_context(uuid.UUID(patient_a["id"]), session)

    ref_ids = {e.ref_id for e in context_a.entries}
    assert uuid.UUID(own_symptom["id"]) in ref_ids
    assert uuid.UUID(other_symptom["id"]) not in ref_ids


@pytest.mark.asyncio
async def test_entry_fields_match_source_timeline_event(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Field Mapping Timeline Engine Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    symptom = _create_symptom(patient["id"], "Dizziness")

    async with AsyncSessionLocal() as session:
        context = await build_timeline_context(uuid.UUID(patient["id"]), session)

    entry = next(e for e in context.entries if e.ref_id == uuid.UUID(symptom["id"]))
    assert entry.event_type == "symptom_reported"
    assert "Dizziness" in entry.event_title
    assert entry.payload is not None
