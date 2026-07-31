"""
Phase 8 dose scheduling tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py and all prior phase API test
modules). Authentication is bypassed via a FastAPI dependency override on
`get_current_user`, same as prior phases.

Per the confirmed frozen-spec scope for Phase 8, only
POST /medications/{id}/schedule and GET /patients/{id}/doses/upcoming are
implemented -- POST /doses/{id}/mark is explicitly Phase 9 (Adherence)
and is not tested here beyond confirming the route doesn't exist yet.

No `created_*_ids` fixture is needed for generated schedule/dose rows --
both medication_schedule.medication_id and medication_doses.medication_id
have ON DELETE CASCADE, so rows are removed automatically when a test's
created_patient_ids cleanup deletes the patient (cascading through
medications).

Run with:  pytest backend/tests/test_schedule_api.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs from 002_seed_data.sql.
"""
import uuid
from datetime import date

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


def _create_patient(name: str = "Schedule Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/medications",
        json={"drug_id": drug_id, "start_date": str(date.today()), **kwargs},
    )
    assert resp.status_code == 201
    return resp.json()


def test_generate_schedule_creates_expected_dose_count(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient()
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=2, duration_days=3
    )

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 201
    doses = resp.json()

    assert len(doses) == 6  # times_per_day (2) * duration_days (3)
    assert all(d["medication_id"] == medication["id"] for d in doses)
    assert all(d["status"] is None for d in doses)
    assert all(d["schedule_id"] is not None for d in doses)


def test_generate_schedule_spacing_defaults_to_even_daily_spread(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Even Spread Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=2, duration_days=1
    )

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 201
    doses = sorted(resp.json(), key=lambda d: d["scheduled_time"])

    from datetime import datetime

    t0 = datetime.fromisoformat(doses[0]["scheduled_time"])
    t1 = datetime.fromisoformat(doses[1]["scheduled_time"])
    assert (t1 - t0).total_seconds() == 12 * 3600  # 24h / 2 doses = 12h apart


def test_generate_schedule_respects_explicit_interval_hours(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Explicit Interval Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        times_per_day=1,
        duration_days=2,
        interval_hours=8,
    )

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 201
    doses = sorted(resp.json(), key=lambda d: d["scheduled_time"])
    assert len(doses) == 2

    from datetime import datetime

    t0 = datetime.fromisoformat(doses[0]["scheduled_time"])
    t1 = datetime.fromisoformat(doses[1]["scheduled_time"])
    assert (t1 - t0).total_seconds() == 8 * 3600


def test_generate_schedule_missing_times_per_day_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Missing Times Per Day Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id), duration_days=3)

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 400
    assert "times_per_day" in resp.json()["detail"]


def test_generate_schedule_missing_duration_days_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Missing Duration Days Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id), times_per_day=2)

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 400
    assert "duration_days" in resp.json()["detail"]


def test_generate_schedule_twice_returns_409(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Duplicate Schedule Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )

    first_resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert first_resp.status_code == 201

    second_resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert second_resp.status_code == 409


def test_generate_schedule_exceeding_max_doses_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Exceeds Max Doses Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    # 24 * 200 = 4800 > MAX_GENERATED_DOSES (3650)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=24, duration_days=200
    )

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 400
    assert "exceeding" in resp.json()["detail"]


def test_generate_schedule_for_nonexistent_medication_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(f"/api/v1/medications/{uuid.uuid4()}/schedule")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Medication not found."


def test_generate_schedule_for_medication_owned_by_another_user_returns_404(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Owned By A Schedule Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 404


def test_upcoming_doses_returns_future_unmarked_doses_ordered(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Upcoming Doses Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=3, duration_days=2
    )
    client.post(f"/api/v1/medications/{medication['id']}/schedule")

    resp = client.get(f"/api/v1/patients/{patient['id']}/doses/upcoming")
    assert resp.status_code == 200
    upcoming = resp.json()

    assert len(upcoming) > 0
    assert all(d["medication_id"] == medication["id"] for d in upcoming)
    assert all("drug_name" in d and d["drug_name"] for d in upcoming)

    scheduled_times = [d["scheduled_time"] for d in upcoming]
    assert scheduled_times == sorted(scheduled_times)


def test_upcoming_doses_excludes_inactive_medication(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Inactive Medication Upcoming Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=5
    )
    client.post(f"/api/v1/medications/{medication['id']}/schedule")

    # Discontinue the medication -- its future doses should no longer appear.
    client.put(f"/api/v1/medications/{medication['id']}", json={"status": "discontinued"})

    resp = client.get(f"/api/v1/patients/{patient['id']}/doses/upcoming")
    assert resp.status_code == 200
    upcoming = resp.json()

    assert not any(d["medication_id"] == medication["id"] for d in upcoming)


def test_upcoming_doses_scoped_to_patient(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Upcoming Scoped Patient A")
    created_patient_ids.append(uuid.UUID(patient["id"]))
    other_patient = _create_patient("Upcoming Scoped Patient B")
    created_patient_ids.append(uuid.UUID(other_patient["id"]))

    medication_a = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=2
    )
    client.post(f"/api/v1/medications/{medication_a['id']}/schedule")

    medication_b = _create_medication(
        other_patient["id"], str(existing_drug_id), times_per_day=1, duration_days=2
    )
    client.post(f"/api/v1/medications/{medication_b['id']}/schedule")

    resp = client.get(f"/api/v1/patients/{patient['id']}/doses/upcoming")
    assert resp.status_code == 200
    upcoming = resp.json()

    assert all(d["medication_id"] == medication_a["id"] for d in upcoming)
    assert not any(d["medication_id"] == medication_b["id"] for d in upcoming)


def test_upcoming_doses_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/doses/upcoming")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_upcoming_doses_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A Upcoming Doses Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.get(f"/api/v1/patients/{patient['id']}/doses/upcoming")
    assert resp.status_code == 404


def test_mark_endpoint_not_yet_implemented(existing_auth_user_id):
    """
    Confirms POST /doses/{id}/mark is out of scope for Phase 8 -- it is
    explicitly Phase 9 (Adherence) per spec section 10, and is not
    registered on any router yet, so the route simply doesn't exist
    (FastAPI returns 404 for an unregistered path, not 405).
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(f"/api/v1/doses/{uuid.uuid4()}/mark", json={"status": "taken"})
    assert resp.status_code == 404
