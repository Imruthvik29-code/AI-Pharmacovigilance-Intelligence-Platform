"""
Phase 7 timeline tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py and all prior phase API test
modules). Authentication is bypassed via a FastAPI dependency override on
`get_current_user`, same as prior phases.

Per the confirmed frozen-spec scope for Phase 7, only
GET /patients/{id}/timeline exists -- there is no POST/PUT/DELETE route,
since timeline events are only ever produced as a side effect of other
endpoints (medications, conditions, symptoms). These tests therefore
exercise automatic event logging through those endpoints, then verify the
resulting rows via the timeline GET route.

No `created_timeline_ids` fixture is used -- timeline_events.patient_id
has ON DELETE CASCADE (001_initial_schema.sql), so timeline rows are
cleaned up automatically whenever a test's `created_patient_ids` cleanup
deletes the patient.

Run with:  pytest backend/tests/test_timeline_api.py -v
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


def _create_patient(name: str = "Timeline Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_condition(patient_id: str, name: str = "Migraine", **kwargs) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/conditions", json={"name": name, **kwargs}
    )
    assert resp.status_code == 201
    return resp.json()


def _create_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/medications",
        json={"drug_id": drug_id, "start_date": str(date.today()), **kwargs},
    )
    assert resp.status_code == 201
    return resp.json()


def _get_timeline(patient_id: str) -> list[dict]:
    resp = client.get(f"/api/v1/patients/{patient_id}/timeline")
    assert resp.status_code == 200
    return resp.json()


def test_medication_creation_logs_medication_started_event(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient()
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id), dose="10mg")
    created_medication_ids.append(uuid.UUID(medication["id"]))

    events = _get_timeline(patient["id"])
    started_events = [e for e in events if e["event_type"] == "medication_started"]
    assert len(started_events) == 1
    assert started_events[0]["ref_id"] == medication["id"]
    assert started_events[0]["payload"]["dose"] == "10mg"


def test_medication_status_change_to_discontinued_logs_event(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Discontinue Med Timeline Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id))
    created_medication_ids.append(uuid.UUID(medication["id"]))

    update_resp = client.put(
        f"/api/v1/medications/{medication['id']}", json={"status": "discontinued"}
    )
    assert update_resp.status_code == 200

    events = _get_timeline(patient["id"])
    discontinued_events = [e for e in events if e["event_type"] == "medication_discontinued"]
    assert len(discontinued_events) == 1
    assert discontinued_events[0]["ref_id"] == medication["id"]
    assert discontinued_events[0]["payload"]["new_status"] == "discontinued"


def test_repeated_discontinued_put_does_not_duplicate_event(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Duplicate Event Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id))
    created_medication_ids.append(uuid.UUID(medication["id"]))

    client.put(f"/api/v1/medications/{medication['id']}", json={"status": "discontinued"})
    # Resend the same status -- should not log a second event.
    client.put(f"/api/v1/medications/{medication['id']}", json={"status": "discontinued"})

    events = _get_timeline(patient["id"])
    discontinued_events = [e for e in events if e["event_type"] == "medication_discontinued"]
    assert len(discontinued_events) == 1


def test_medication_delete_does_not_log_event(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Delete No Event Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id))

    delete_resp = client.delete(f"/api/v1/medications/{medication['id']}")
    assert delete_resp.status_code == 204

    events = _get_timeline(patient["id"])
    assert not any(e["ref_id"] == medication["id"] and e["event_type"] not in
                    ("medication_started",) for e in events)


def test_condition_status_change_logs_event(
    existing_auth_user_id, created_patient_ids, created_condition_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Condition Timeline Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    condition = _create_condition(patient["id"], "Hypertension", status="active")
    created_condition_ids.append(uuid.UUID(condition["id"]))

    update_resp = client.put(
        f"/api/v1/conditions/{condition['id']}", json={"status": "improving"}
    )
    assert update_resp.status_code == 200

    events = _get_timeline(patient["id"])
    status_events = [e for e in events if e["event_type"] == "condition_status_changed"]
    assert len(status_events) == 1
    assert status_events[0]["ref_id"] == condition["id"]
    assert status_events[0]["payload"]["previous_status"] == "active"
    assert status_events[0]["payload"]["new_status"] == "improving"


def test_condition_update_with_same_status_does_not_log_event(
    existing_auth_user_id, created_patient_ids, created_condition_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Same Status Condition Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    condition = _create_condition(patient["id"], "Asthma", status="active")
    created_condition_ids.append(uuid.UUID(condition["id"]))

    # Resend the same status, alongside an unrelated field change.
    update_resp = client.put(
        f"/api/v1/conditions/{condition['id']}",
        json={"status": "active", "notes": "unrelated update"},
    )
    assert update_resp.status_code == 200

    events = _get_timeline(patient["id"])
    status_events = [e for e in events if e["event_type"] == "condition_status_changed"]
    assert len(status_events) == 0


def test_symptom_creation_logs_symptom_reported_event(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Symptom Timeline Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    symptom_resp = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Dizziness", "severity": "moderate"},
    )
    assert symptom_resp.status_code == 201
    symptom = symptom_resp.json()
    created_symptom_ids.append(uuid.UUID(symptom["id"]))

    events = _get_timeline(patient["id"])
    symptom_events = [e for e in events if e["event_type"] == "symptom_reported"]
    assert len(symptom_events) == 1
    assert symptom_events[0]["ref_id"] == symptom["id"]
    assert symptom_events[0]["payload"]["severity"] == "moderate"


def test_timeline_ordered_most_recent_first(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Timeline Order Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    first = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms", json={"description": "First"}
    ).json()
    created_symptom_ids.append(uuid.UUID(first["id"]))

    second = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms", json={"description": "Second"}
    ).json()
    created_symptom_ids.append(uuid.UUID(second["id"]))

    events = _get_timeline(patient["id"])
    # Most recent event (Second) should come before the earlier one (First).
    event_times = [e["event_time"] for e in events]
    assert event_times == sorted(event_times, reverse=True)


def test_timeline_scoped_to_patient(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Scoped Timeline Patient A")
    created_patient_ids.append(uuid.UUID(patient["id"]))
    other_patient = _create_patient("Scoped Timeline Patient B")
    created_patient_ids.append(uuid.UUID(other_patient["id"]))

    own_symptom = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms", json={"description": "Mine"}
    ).json()
    created_symptom_ids.append(uuid.UUID(own_symptom["id"]))

    other_symptom = client.post(
        f"/api/v1/patients/{other_patient['id']}/symptoms", json={"description": "Not mine"}
    ).json()
    created_symptom_ids.append(uuid.UUID(other_symptom["id"]))

    events = _get_timeline(patient["id"])
    ref_ids = {e["ref_id"] for e in events}
    assert own_symptom["id"] in ref_ids
    assert other_symptom["id"] not in ref_ids


def test_timeline_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/timeline")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_timeline_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A Timeline Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.get(f"/api/v1/patients/{patient['id']}/timeline")
    assert resp.status_code == 404


def test_no_post_put_delete_endpoints_exist(existing_auth_user_id, created_patient_ids):
    """
    Confirms the deliberate decision to implement only GET for the
    timeline route, per the frozen spec (section 7) -- timeline events
    are produced only as side effects of other writes.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Write Routes Timeline Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    post_resp = client.post(
        f"/api/v1/patients/{patient['id']}/timeline", json={"event_type": "custom"}
    )
    assert post_resp.status_code == 405

    put_resp = client.put(f"/api/v1/patients/{patient['id']}/timeline", json={})
    assert put_resp.status_code == 405

    delete_resp = client.delete(f"/api/v1/patients/{patient['id']}/timeline")
    assert delete_resp.status_code == 405
