"""
Phase 6 symptom tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py, Phase 3's test_patients_api.py,
Phase 4's test_medications_api.py, and Phase 5's test_conditions_api.py).
Authentication is bypassed via a FastAPI dependency override on
`get_current_user`, same as prior phases.

Per the confirmed frozen-spec scope for Phase 6, only
POST /patients/{id}/symptoms and GET /patients/{id}/symptoms exist --
there is no PUT or DELETE route, so update/delete behavior is not tested
here (there is nothing to test).

Every test that creates a patient/condition/medication/symptom appends
its id to the corresponding `created_*_ids` fixture so the autouse
cleanup fixtures in conftest.py delete them afterward.

Run with:  pytest backend/tests/test_symptoms_api.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs from 002_seed_data.sql (for the
           medication-linkage tests).
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


def _create_patient(name: str = "Symptom Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_condition(patient_id: str, name: str = "Migraine") -> dict:
    resp = client.post(f"/api/v1/patients/{patient_id}/conditions", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_medication(patient_id: str, drug_id: str) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/medications",
        json={"drug_id": drug_id, "start_date": str(date.today())},
    )
    assert resp.status_code == 201
    return resp.json()


def test_create_symptom_applies_defaults(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient()
    created_patient_ids.append(uuid.UUID(patient["id"]))

    create_resp = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Persistent dry cough"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_symptom_ids.append(uuid.UUID(created["id"]))

    assert created["patient_id"] == patient["id"]
    assert created["description"] == "Persistent dry cough"
    assert created["severity"] == "mild"  # default applied
    assert created["onset_date"] == str(date.today())  # default applied
    assert created["condition_id"] is None
    assert created["medication_id"] is None
    assert created["resolved_date"] is None


def test_create_symptom_with_explicit_fields(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Explicit Fields Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    create_resp = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={
            "description": "Severe muscle pain",
            "severity": "severe",
            "onset_date": "2026-07-01",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_symptom_ids.append(uuid.UUID(created["id"]))

    assert created["severity"] == "severe"
    assert created["onset_date"] == "2026-07-01"


def test_create_symptom_linked_to_condition(
    existing_auth_user_id, created_patient_ids, created_condition_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Condition-Linked Symptom Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    condition = _create_condition(patient["id"])
    created_condition_ids.append(uuid.UUID(condition["id"]))

    create_resp = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Aura before headache", "condition_id": condition["id"]},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_symptom_ids.append(uuid.UUID(created["id"]))

    assert created["condition_id"] == condition["id"]


def test_create_symptom_linked_to_medication(
    existing_auth_user_id,
    existing_drug_id,
    created_patient_ids,
    created_medication_ids,
    created_symptom_ids,
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Medication-Linked Symptom Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id))
    created_medication_ids.append(uuid.UUID(medication["id"]))

    create_resp = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Nausea after dose", "medication_id": medication["id"]},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_symptom_ids.append(uuid.UUID(created["id"]))

    assert created["medication_id"] == medication["id"]


def test_create_symptom_with_condition_from_another_patient_returns_400(
    existing_auth_user_id, created_patient_ids, created_condition_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Symptom Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Symptom Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    condition_b = _create_condition(patient_b["id"], "Patient B's condition")
    created_condition_ids.append(uuid.UUID(condition_b["id"]))

    resp = client.post(
        f"/api/v1/patients/{patient_a['id']}/symptoms",
        json={"description": "Mismatched condition test", "condition_id": condition_b["id"]},
    )
    assert resp.status_code == 400
    assert "condition_id" in resp.json()["detail"]


def test_create_symptom_with_medication_from_another_patient_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids, created_medication_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Symptom Med Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Symptom Med Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    medication_b = _create_medication(patient_b["id"], str(existing_drug_id))
    created_medication_ids.append(uuid.UUID(medication_b["id"]))

    resp = client.post(
        f"/api/v1/patients/{patient_a['id']}/symptoms",
        json={"description": "Mismatched medication test", "medication_id": medication_b["id"]},
    )
    assert resp.status_code == 400
    assert "medication_id" in resp.json()["detail"]


def test_create_symptom_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(
        f"/api/v1/patients/{uuid.uuid4()}/symptoms",
        json={"description": "Should not be created"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_create_symptom_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A Symptom Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Should not be visible"},
    )
    assert resp.status_code == 404


def test_list_symptoms_scoped_to_patient(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("List Symptoms Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_patient = _create_patient("Other List Symptoms Patient")
    created_patient_ids.append(uuid.UUID(other_patient["id"]))

    created_1 = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "First symptom", "onset_date": "2026-07-01"},
    ).json()
    created_symptom_ids.append(uuid.UUID(created_1["id"]))

    created_2 = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Second symptom", "onset_date": "2026-07-15"},
    ).json()
    created_symptom_ids.append(uuid.UUID(created_2["id"]))

    other_created = client.post(
        f"/api/v1/patients/{other_patient['id']}/symptoms",
        json={"description": "Other patient's symptom"},
    ).json()
    created_symptom_ids.append(uuid.UUID(other_created["id"]))

    list_resp = client.get(f"/api/v1/patients/{patient['id']}/symptoms")
    assert list_resp.status_code == 200
    symptoms = list_resp.json()

    ids = {s["id"] for s in symptoms}
    assert created_1["id"] in ids
    assert created_2["id"] in ids
    assert other_created["id"] not in ids  # scoped to the requested patient only

    # Ordered chronologically by onset_date.
    descriptions_in_order = [s["description"] for s in symptoms]
    assert descriptions_in_order.index("First symptom") < descriptions_in_order.index(
        "Second symptom"
    )


def test_list_symptoms_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/symptoms")
    assert resp.status_code == 404


def test_list_symptoms_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A List Symptoms Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.get(f"/api/v1/patients/{patient['id']}/symptoms")
    assert resp.status_code == 404


def test_no_update_or_delete_endpoints_exist(
    existing_auth_user_id, created_patient_ids, created_symptom_ids
):
    """
    Confirms the deliberate decision to implement only POST and GET for
    symptoms, per the frozen spec (section 7) -- mirrors Phase 3's
    test_no_delete_endpoint_exists and Phase 5's route-scope confirmation.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Update Delete Symptom Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    created = client.post(
        f"/api/v1/patients/{patient['id']}/symptoms",
        json={"description": "Immutable via API"},
    ).json()
    created_symptom_ids.append(uuid.UUID(created["id"]))

    put_resp = client.put(
        f"/api/v1/symptoms/{created['id']}", json={"severity": "severe"}
    )
    assert put_resp.status_code == 405  # Method Not Allowed -- route doesn't exist

    delete_resp = client.delete(f"/api/v1/symptoms/{created['id']}")
    assert delete_resp.status_code == 405  # Method Not Allowed -- route doesn't exist
