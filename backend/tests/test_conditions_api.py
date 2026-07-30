"""
Phase 5 condition tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py, Phase 3's test_patients_api.py,
and Phase 4's test_medications_api.py). Authentication is bypassed via a
FastAPI dependency override on `get_current_user`, same as prior phases.

Per the confirmed frozen-spec scope for Phase 5, only
POST /patients/{id}/conditions and PUT /conditions/{id} exist -- there is
no GET route. Persistence is therefore verified with a direct DB query
(mirroring Phase 1's test_database.py style) rather than round-tripping
through a read endpoint.

Every test that creates a patient/condition appends its id to the
`created_patient_ids` / `created_condition_ids` fixtures so the autouse
cleanup fixtures in conftest.py delete them afterward.

Run with:  pytest backend/tests/test_conditions_api.py -v
Requires:  at least one row in auth.users (see conftest.py).
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import CurrentUser, get_current_user
from app.db.models import Condition
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


def _create_patient(name: str = "Condition Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def _fetch_condition(condition_id: uuid.UUID) -> Condition:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Condition).where(Condition.id == condition_id))
        return result.scalar_one()


def test_create_condition_applies_defaults(existing_auth_user_id, created_patient_ids, created_condition_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient()
    created_patient_ids.append(uuid.UUID(patient["id"]))

    create_resp = client.post(
        f"/api/v1/patients/{patient['id']}/conditions",
        json={"name": "Hypertension", "diagnosed_date": str(date.today())},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_condition_ids.append(uuid.UUID(created["id"]))

    assert created["patient_id"] == patient["id"]
    assert created["name"] == "Hypertension"
    assert created["status"] == "active"  # default applied
    assert created["reason"] == "unknown"  # default applied

    import asyncio

    persisted = asyncio.run(_fetch_condition(uuid.UUID(created["id"])))
    assert persisted.name == "Hypertension"
    assert persisted.status == "active"
    assert persisted.reason == "unknown"


def test_create_condition_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(
        f"/api/v1/patients/{uuid.uuid4()}/conditions",
        json={"name": "Diabetes"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_create_condition_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.post(
        f"/api/v1/patients/{patient['id']}/conditions",
        json={"name": "Asthma"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_update_condition_partial_fields(existing_auth_user_id, created_patient_ids, created_condition_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Update Condition Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    created = client.post(
        f"/api/v1/patients/{patient['id']}/conditions",
        json={"name": "Hypertension", "status": "active", "reason": "doctor_diagnosis"},
    ).json()
    created_condition_ids.append(uuid.UUID(created["id"]))

    update_resp = client.put(
        f"/api/v1/conditions/{created['id']}",
        json={"status": "improving", "resolved_date": str(date.today())},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["status"] == "improving"
    assert updated["resolved_date"] == str(date.today())
    assert updated["name"] == "Hypertension"  # untouched field preserved
    assert updated["reason"] == "doctor_diagnosis"  # untouched field preserved
    assert updated["updated_at"] != created["updated_at"]


def test_update_nonexistent_condition_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.put(f"/api/v1/conditions/{uuid.uuid4()}", json={"status": "resolved"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Condition not found."


def test_condition_owned_by_another_user_is_not_updatable(
    existing_auth_user_id, created_patient_ids, created_condition_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Owned By A Condition Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    created = client.post(
        f"/api/v1/patients/{patient['id']}/conditions",
        json={"name": "Owned Condition"},
    ).json()
    created_condition_ids.append(uuid.UUID(created["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.put(f"/api/v1/conditions/{created['id']}", json={"status": "resolved"})
    assert resp.status_code == 404


def test_medication_condition_id_now_validated_against_a_real_created_condition(
    existing_auth_user_id, created_patient_ids, created_condition_ids
):
    """
    Phase 4's medication-creation endpoint validates that a supplied
    condition_id both exists and belongs to the same patient. Until now
    that could only be tested by inserting a Condition row directly via
    the DB session (no condition-creation endpoint existed). With Phase 5
    live, this exercises that same validation end-to-end through the
    real POST /patients/{id}/conditions endpoint.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Condition+Medication Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    condition = client.post(
        f"/api/v1/patients/{patient['id']}/conditions",
        json={"name": "Hypertension"},
    ).json()
    created_condition_ids.append(uuid.UUID(condition["id"]))

    # Fetch a real seeded drug id directly, since existing_drug_id fixture
    # isn't a dependency of this test module.
    async def _fetch_drug_id():
        async with AsyncSessionLocal() as session:
            from app.db.models import ReferenceDrug

            result = await session.execute(select(ReferenceDrug.id).limit(1))
            return result.scalar_one()

    import asyncio

    drug_id = asyncio.run(_fetch_drug_id())

    med_resp = client.post(
        f"/api/v1/patients/{patient['id']}/medications",
        json={
            "drug_id": str(drug_id),
            "condition_id": condition["id"],
            "start_date": str(date.today()),
        },
    )
    assert med_resp.status_code == 201
    assert med_resp.json()["condition_id"] == condition["id"]
