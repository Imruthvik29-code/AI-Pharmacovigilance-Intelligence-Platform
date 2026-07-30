"""
Phase 4 medication CRUD tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py and Phase 3's
test_patients_api.py). Authentication is bypassed via a FastAPI dependency
override on `get_current_user`, same as Phase 3 -- these tests are about
medication CRUD + ownership + validation logic, not JWT verification.

Every test that creates a patient/medication appends its id to the
`created_patient_ids` / `created_medication_ids` fixtures so the autouse
cleanup fixtures in conftest.py delete them afterward.

Run with:  pytest backend/tests/test_medications_api.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs from 002_seed_data.sql.
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

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


def _create_patient(name: str = "Med Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def test_create_and_list_medications(existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient()
    created_patient_ids.append(uuid.UUID(patient["id"]))

    create_resp = client.post(
        f"/api/v1/patients/{patient['id']}/medications",
        json={
            "drug_id": str(existing_drug_id),
            "purpose_text": "Pain relief",
            "dose": "500mg",
            "times_per_day": 2,
            "start_date": str(date.today()),
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_medication_ids.append(uuid.UUID(created["id"]))

    assert created["patient_id"] == patient["id"]
    assert created["drug_id"] == str(existing_drug_id)
    assert created["status"] == "active"  # default applied

    list_resp = client.get(f"/api/v1/patients/{patient['id']}/medications")
    assert list_resp.status_code == 200
    meds = list_resp.json()
    assert any(m["id"] == created["id"] for m in meds)


def test_create_medication_invalid_drug_returns_404(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Invalid Drug Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    resp = client.post(
        f"/api/v1/patients/{patient['id']}/medications",
        json={"drug_id": str(uuid.uuid4()), "start_date": str(date.today())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Reference drug not found."


def test_create_medication_for_nonexistent_patient_returns_404(existing_auth_user_id, existing_drug_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(
        f"/api/v1/patients/{uuid.uuid4()}/medications",
        json={"drug_id": str(existing_drug_id), "start_date": str(date.today())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_create_medication_with_mismatched_condition_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    Creates two patients (A, B) and a condition belonging to patient B,
    then attempts to attach a medication for patient A referencing B's
    condition_id. Must be rejected -- condition_id must belong to the
    same patient the medication is being created for.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    now = datetime.now(timezone.utc)
    condition_id = uuid.uuid4()
    async_engine_condition = Condition(
        id=condition_id,
        patient_id=uuid.UUID(patient_b["id"]),
        name="Hypertension",
        diagnosed_date=date.today(),
        created_at=now,
        updated_at=now,
    )

    import asyncio

    async def _insert_condition():
        async with AsyncSessionLocal() as session:
            session.add(async_engine_condition)
            await session.commit()

    asyncio.run(_insert_condition())

    resp = client.post(
        f"/api/v1/patients/{patient_a['id']}/medications",
        json={
            "drug_id": str(existing_drug_id),
            "condition_id": str(condition_id),
            "start_date": str(date.today()),
        },
    )
    assert resp.status_code == 400
    assert "condition_id" in resp.json()["detail"]


def test_update_medication_partial_fields(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Update Med Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    created = client.post(
        f"/api/v1/patients/{patient['id']}/medications",
        json={
            "drug_id": str(existing_drug_id),
            "dose": "10mg",
            "status": "active",
            "start_date": str(date.today()),
        },
    ).json()
    created_medication_ids.append(uuid.UUID(created["id"]))

    update_resp = client.put(
        f"/api/v1/medications/{created['id']}", json={"status": "paused"}
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["status"] == "paused"
    assert updated["dose"] == "10mg"  # untouched field preserved
    assert updated["updated_at"] != created["updated_at"]


def test_medication_owned_by_another_user_is_not_visible(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Owned By A Med Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    created = client.post(
        f"/api/v1/patients/{patient['id']}/medications",
        json={"drug_id": str(existing_drug_id), "start_date": str(date.today())},
    ).json()
    created_medication_ids.append(uuid.UUID(created["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    update_resp = client.put(f"/api/v1/medications/{created['id']}", json={"status": "paused"})
    assert update_resp.status_code == 404

    delete_resp = client.delete(f"/api/v1/medications/{created['id']}")
    assert delete_resp.status_code == 404


def test_delete_medication(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Delete Med Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    created = client.post(
        f"/api/v1/patients/{patient['id']}/medications",
        json={"drug_id": str(existing_drug_id), "start_date": str(date.today())},
    ).json()

    delete_resp = client.delete(f"/api/v1/medications/{created['id']}")
    assert delete_resp.status_code == 204

    # Confirm it's actually gone (not soft-deleted) -- subsequent update 404s.
    update_resp = client.put(f"/api/v1/medications/{created['id']}", json={"status": "paused"})
    assert update_resp.status_code == 404
    # Not added to created_medication_ids since it's already deleted --
    # cleanup fixture would otherwise no-op harmlessly on a missing id anyway.


def test_list_medications_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/medications")
    assert resp.status_code == 404
