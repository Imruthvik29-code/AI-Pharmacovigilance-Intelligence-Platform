"""
Phase 3 patient CRUD tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py). Authentication is bypassed via
a FastAPI dependency override on `get_current_user` -- these tests are
about patient CRUD + ownership logic, not JWT verification (already
covered by Phase 2's test_security.py / test_auth_api.py).

Every test that creates a patient appends its id to the `created_patient_ids`
fixture so the autouse cleanup in conftest.py can delete it afterward --
see conftest.py's docstring for why explicit cleanup was chosen over
transactional rollback here.

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
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_create_and_get_patient(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    create_resp = client.post(
        "/api/v1/patients",
        json={"name": "Jane Doe", "age": 62, "sex": "female", "weight_kg": 68.5},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    assert created["name"] == "Jane Doe"
    assert created["user_id"] == str(existing_auth_user_id)
    assert created["renal_flag"] is False

    get_resp = client.get(f"/api/v1/patients/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]


def test_list_patients_scoped_to_current_user(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    created = client.post("/api/v1/patients", json={"name": "List Test Patient"}).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    list_resp = client.get("/api/v1/patients")

    assert list_resp.status_code == 200
    patients = list_resp.json()
    assert all(p["user_id"] == str(existing_auth_user_id) for p in patients)
    assert any(p["name"] == "List Test Patient" for p in patients)


def test_update_patient_partial_fields(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    created = client.post("/api/v1/patients", json={"name": "Update Me", "age": 30}).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

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


def test_patient_owned_by_another_user_is_not_visible(existing_auth_user_id, created_patient_ids):
    """
    Create a patient as user A, then attempt to fetch it while
    authenticated as a different (fabricated) user B. Must 404, not 403 --
    existence of the record should not be confirmed to a non-owner.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    created = client.post("/api/v1/patients", json={"name": "Owned By A"}).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.get(f"/api/v1/patients/{created['id']}")
    assert resp.status_code == 404


def test_no_delete_endpoint_exists(existing_auth_user_id, created_patient_ids):
    """
    Confirms the deliberate decision (per project owner) to omit
    DELETE /patients/{id} since it is not in the frozen API contract.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    created = client.post("/api/v1/patients", json={"name": "No Delete"}).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    resp = client.delete(f"/api/v1/patients/{created['id']}")
    assert resp.status_code == 405  # Method Not Allowed -- route doesn't exist


# --- Phase 1: patient daily routine (timezone + meal times) -----------------
#
# Routine fields are optional context, never inferred. These tests pin that
# they round-trip, that omitting them leaves a patient valid, that partial
# update reaches them, and that an invalid IANA zone is refused.


def test_create_patient_with_routine_fields(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(
        "/api/v1/patients",
        json={
            "name": "Routine Patient",
            "timezone": "Asia/Kolkata",
            "breakfast_time": "08:00:00",
            "lunch_time": "13:30:00",
            "dinner_time": "20:15:00",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    assert created["timezone"] == "Asia/Kolkata"
    assert created["breakfast_time"] == "08:00:00"
    assert created["lunch_time"] == "13:30:00"
    assert created["dinner_time"] == "20:15:00"


def test_create_patient_without_routine_fields_leaves_them_null(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post("/api/v1/patients", json={"name": "No Routine"})
    assert resp.status_code == 201
    created = resp.json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    # Absent routine must stay absent -- nothing is guessed on the patient's behalf.
    assert created["timezone"] is None
    assert created["breakfast_time"] is None
    assert created["lunch_time"] is None
    assert created["dinner_time"] is None


def test_update_patient_routine_preserves_other_fields(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    created = client.post("/api/v1/patients", json={"name": "Edit Routine", "age": 44}).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    resp = client.put(
        f"/api/v1/patients/{created['id']}",
        json={"timezone": "Europe/London", "breakfast_time": "07:45:00"},
    )
    assert resp.status_code == 200
    updated = resp.json()

    assert updated["timezone"] == "Europe/London"
    assert updated["breakfast_time"] == "07:45:00"
    # Fields the request did not mention are untouched.
    assert updated["name"] == "Edit Routine"
    assert updated["age"] == 44
    assert updated["lunch_time"] is None


def test_update_patient_can_clear_a_meal_time(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    created = client.post(
        "/api/v1/patients",
        json={"name": "Clear Meal", "timezone": "UTC", "lunch_time": "12:00:00"},
    ).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    resp = client.put(f"/api/v1/patients/{created['id']}", json={"lunch_time": None})
    assert resp.status_code == 200
    assert resp.json()["lunch_time"] is None
    assert resp.json()["timezone"] == "UTC"


@pytest.mark.parametrize("bad_zone", ["Asia/Kolkatta", "Not/AZone", "kolkata", ""])
def test_invalid_timezone_is_rejected(existing_auth_user_id, bad_zone):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post("/api/v1/patients", json={"name": "Bad TZ", "timezone": bad_zone})
    assert resp.status_code == 422


def test_invalid_timezone_is_rejected_on_update(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    created = client.post("/api/v1/patients", json={"name": "Bad TZ Update"}).json()
    created_patient_ids.append(uuid.UUID(created["id"]))

    resp = client.put(f"/api/v1/patients/{created['id']}", json={"timezone": "Mars/Olympus"})
    assert resp.status_code == 422


def test_routine_does_not_require_meal_ordering(existing_auth_user_id, created_patient_ids):
    """A night-shift routine is valid: no clinical ordering rule is invented."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(
        "/api/v1/patients",
        json={
            "name": "Night Shift",
            "timezone": "UTC",
            "breakfast_time": "20:00:00",
            "lunch_time": "01:00:00",
            "dinner_time": "10:00:00",
        },
    )
    assert resp.status_code == 201
    created_patient_ids.append(uuid.UUID(resp.json()["id"]))
