"""
Phase 14 patient context builder tests.

Integration tests against a live Supabase Postgres instance (same
requirement as all prior phase test modules) -- `build_patient_context`
queries `patients`/`conditions`/`medications`/`symptoms` directly.

No HTTP endpoint exists for this service (it is a LangGraph workflow
node, wired in `app/services/langgraph_workflow.py`), so these tests call
`app.services.patient_context_builder.build_patient_context` directly
against an `AsyncSessionLocal` session, mirroring Phases 10-13's testing
approach. Patient/condition/medication/symptom fixtures are created
through the existing, already-tested API endpoints via `TestClient`.

Run with:  pytest backend/tests/test_patient_context_builder.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs from 002_seed_data.sql.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.patient_context_builder import PatientContext, build_patient_context

client = TestClient(app)


def _override_current_user(user_id):
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")

    return _fake_current_user


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _create_patient(name: str = "Context Test Patient", **kwargs) -> dict:
    resp = client.post("/api/v1/patients", json={"name": name, **kwargs})
    assert resp.status_code == 201
    return resp.json()


def _create_condition(patient_id: str, name: str = "Hypertension", **kwargs) -> dict:
    resp = client.post(f"/api/v1/patients/{patient_id}/conditions", json={"name": name, **kwargs})
    assert resp.status_code == 201
    return resp.json()


def _create_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/medications",
        json={"drug_id": drug_id, "start_date": str(date.today()), **kwargs},
    )
    assert resp.status_code == 201
    return resp.json()


def _create_symptom(patient_id: str, description: str = "Headache", **kwargs) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/symptoms", json={"description": description, **kwargs}
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_empty_patient_has_empty_lists_and_demographics(
    existing_auth_user_id, created_patient_ids
):
    app_override = _override_current_user(existing_auth_user_id)
    from app.main import app as _app

    _app.dependency_overrides[get_current_user] = app_override

    patient = _create_patient("Empty Context Patient", age=50, sex="male")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        context = await build_patient_context(uuid.UUID(patient["id"]), session)

    assert isinstance(context, PatientContext)
    assert context.name == "Empty Context Patient"
    assert context.age == 50
    assert context.sex == "male"
    assert context.active_conditions == []
    assert context.active_medications == []
    assert context.active_symptoms == []


@pytest.mark.asyncio
async def test_active_medication_included_discontinued_excluded(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Medication Context Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    active_med = _create_medication(patient["id"], str(existing_drug_id), dose="10mg")
    discontinued_med = _create_medication(patient["id"], str(existing_drug_id), dose="20mg")
    client.put(f"/api/v1/medications/{discontinued_med['id']}", json={"status": "discontinued"})

    async with AsyncSessionLocal() as session:
        context = await build_patient_context(uuid.UUID(patient["id"]), session)

    med_ids = {m.id for m in context.active_medications}
    assert uuid.UUID(active_med["id"]) in med_ids
    assert uuid.UUID(discontinued_med["id"]) not in med_ids
    active_entry = next(m for m in context.active_medications if m.id == uuid.UUID(active_med["id"]))
    assert active_entry.dose == "10mg"
    assert active_entry.drug_name  # denormalized drug name populated


@pytest.mark.asyncio
async def test_resolved_condition_excluded_others_included(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Condition Context Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    active_condition = _create_condition(patient["id"], "Active Condition", status="active")
    improving_condition = _create_condition(patient["id"], "Improving Condition", status="improving")
    resolved_condition = _create_condition(patient["id"], "Resolved Condition", status="active")
    client.put(f"/api/v1/conditions/{resolved_condition['id']}", json={"status": "resolved"})

    async with AsyncSessionLocal() as session:
        context = await build_patient_context(uuid.UUID(patient["id"]), session)

    condition_ids = {c.id for c in context.active_conditions}
    assert uuid.UUID(active_condition["id"]) in condition_ids
    assert uuid.UUID(improving_condition["id"]) in condition_ids
    assert uuid.UUID(resolved_condition["id"]) not in condition_ids


@pytest.mark.asyncio
async def test_resolved_symptom_excluded_unresolved_included(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Symptom Context Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    unresolved_symptom = _create_symptom(patient["id"], "Ongoing symptom")
    resolved_symptom = _create_symptom(
        patient["id"], "Resolved symptom", resolved_date=str(date.today())
    )

    async with AsyncSessionLocal() as session:
        context = await build_patient_context(uuid.UUID(patient["id"]), session)

    symptom_ids = {s.id for s in context.active_symptoms}
    assert uuid.UUID(unresolved_symptom["id"]) in symptom_ids
    assert uuid.UUID(resolved_symptom["id"]) not in symptom_ids


@pytest.mark.asyncio
async def test_context_scoped_to_patient(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Scoped Context Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Scoped Context Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    _create_condition(patient_b["id"], "Patient B's condition")

    async with AsyncSessionLocal() as session:
        context_a = await build_patient_context(uuid.UUID(patient_a["id"]), session)

    assert context_a.active_conditions == []
