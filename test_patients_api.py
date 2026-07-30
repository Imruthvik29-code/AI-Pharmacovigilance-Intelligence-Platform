"""
Phase 3 patient CRUD tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py). Authentication is bypassed via
a FastAPI dependency override on `get_current_user` -- these tests are
about patient CRUD + ownership logic, not JWT verification (already
covered by Phase 2's test_security.py / test_auth_api.py).

Run with:  pytest backend/tests/test_patients_api.py -v
Requires:  at least one row in auth.users (see conftest.py).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)


def _override_current_user(user_id):
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")

    return _fake_current_user


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_create_and_get_patient(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    create_resp = client.post(
        "/api/v1/patients",
        json={"name": "Jane Doe", "age": 62, "sex": "female", "weight_kg": 68.5},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Jane Doe"
    assert created["user_id"] == str(existing_auth_user_id)
    assert created["renal_flag"] is False

    get_resp = client.get(f"/api/v1/patients/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]


def test_list_patients_scoped_to_current_user(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    client.post("/api/v1/patients", json={"name": "List Test Patient"})
    list_resp = client.get("/api/v1/patients")

    assert list_resp.status_code == 200
    patients = list_resp.json()
    assert all(p["user_id"] == str(existing_auth_user_id) for p in patients)
    assert any(p["name"] == "List Test Patient" for p in patients)


def test_update_patient_partial_fields(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    created = client.post("/api/v1/patients", json={"name": "Update Me", "age": 30}).json()

    update_resp = client.put(f"/api/v1/patients/{created['id']}", json={"age": 31})
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["age"] == 31
    assert updated["name"] == "Update Me"  # untouched field preserved
    assert updated["updated_at"] != created["updated_at"]


def test_get_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_patient_owned_by_another_user_is_not_visible(existing_auth_user_id):
    """
    Create a patient as user A, then attempt to fetch it while
    authenticated as a different (fabricated) user B. Must 404, not 403 --
    existence of the record should not be confirmed to a non-owner.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    created = client.post("/api/v1/patients", json={"name": "Owned By A"}).json()

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.get(f"/api/v1/patients/{created['id']}")
    assert resp.status_code == 404


def test_no_delete_endpoint_exists(existing_auth_user_id):
    """
    Confirms the deliberate decision (per project owner) to omit
    DELETE /patients/{id} since it is not in the frozen API contract.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    created = client.post("/api/v1/patients", json={"name": "No Delete"}).json()

    resp = client.delete(f"/api/v1/patients/{created['id']}")
    assert resp.status_code == 405  # Method Not Allowed -- route doesn't exist
