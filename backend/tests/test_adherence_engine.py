"""
Phase 12 adherence engine tests.

Integration tests against a live Supabase Postgres instance (same
requirement as prior phase test modules) -- `analyze_adherence` queries
`medications` and `medication_doses` directly, so a real DB with the
Phase 1 seed data (002_seed_data.sql) is required.

Same approach as Phase 10/11: no HTTP endpoint exists yet for this engine
(wired in Phase 14/LangGraph), so these tests call
`app.analysis.adherence_engine.analyze_adherence` directly against an
`AsyncSessionLocal` session. Patient/medication/schedule fixtures are
created through the existing, already-tested API endpoints via
`TestClient` (Phase 3/4/8), and explicit dose marking uses Phase 9's
`POST /doses/{id}/mark` endpoint. Overdue-unmarked-dose scenarios
deliberately do NOT call `GET /patients/{id}/doses/upcoming` or
`POST /doses/{id}/mark` first -- the whole point of these tests is to
confirm `analyze_adherence()` counts overdue unmarked doses as missed on
its own, independent of whether the Phase 9 lazy sweep has run (see
adherence_engine.py's module docstring for the rationale).

No dedicated cleanup fixture is needed beyond the existing
`created_patient_ids` (from conftest.py) -- medications/schedules/doses
cascade away via `ON DELETE CASCADE` when the patient is deleted, and
this engine performs no writes of its own.

Run with:  pytest backend/tests/test_adherence_engine.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs from 002_seed_data.sql.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.analysis.adherence_engine import AdherenceFinding, analyze_adherence
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


def _create_patient(name: str = "Adherence Test Patient") -> dict:
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


def _generate_schedule(medication_id: str) -> list[dict]:
    resp = client.post(f"/api/v1/medications/{medication_id}/schedule")
    assert resp.status_code == 201
    return resp.json()


def _mark_dose(dose_id: str, status: str) -> dict:
    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": status})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------
# analyze_adherence
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_active_medications_returns_empty(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Medications Adherence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_medication_with_no_due_doses_is_excluded(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    A medication starting tomorrow has doses generated, but none of them
    are due yet -- it must be entirely absent from the results (not
    present with due=0), since there's nothing to measure yet.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Due Doses Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    tomorrow = date.today() + timedelta(days=1)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(tomorrow),
        times_per_day=2,
        duration_days=2,
    )
    _generate_schedule(medication["id"])

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_all_due_doses_unmarked_counts_as_fully_missed(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    Doses scheduled well in the past, never explicitly marked and never
    swept (no call to GET .../doses/upcoming or POST .../mark first),
    must still be counted as missed -- confirming analyze_adherence()
    does not depend on the Phase 9 lazy sweep having run.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Fully Missed Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=3)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(past_start),
        times_per_day=2,
        duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    assert all(d["status"] is None for d in doses)  # confirm still unswept

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, AdherenceFinding)
    assert finding.medication_id == uuid.UUID(medication["id"])
    assert finding.due == 2
    assert finding.taken == 0
    assert finding.missed == 2
    assert finding.skipped == 0
    assert finding.adherence_rate == 0.0


@pytest.mark.asyncio
async def test_mixed_taken_missed_skipped_counts_correctly(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Mixed Adherence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=2)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(past_start),
        times_per_day=3,
        duration_days=1,
    )
    doses = sorted(_generate_schedule(medication["id"]), key=lambda d: d["scheduled_time"])
    assert len(doses) == 3

    _mark_dose(doses[0]["id"], "taken")
    _mark_dose(doses[1]["id"], "missed")
    _mark_dose(doses[2]["id"], "skipped")

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.due == 3
    assert finding.taken == 1
    assert finding.missed == 1
    assert finding.skipped == 1
    assert finding.adherence_rate == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_fully_adherent_medication_rate_is_one(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Fully Adherent Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=1)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(past_start),
        times_per_day=2,
        duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    for dose in doses:
        _mark_dose(dose["id"], "taken")

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.taken == 2
    assert finding.missed == 0
    assert finding.skipped == 0
    assert finding.adherence_rate == 1.0


@pytest.mark.asyncio
async def test_excludes_non_active_medications(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    A discontinued medication's dose history must not be considered "the
    patient's current adherence picture" -- mirrors Phase 10/11's same
    status == "active" scope decision.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Discontinued Excluded Adherence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=2)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(past_start),
        times_per_day=1,
        duration_days=1,
    )
    _generate_schedule(medication["id"])

    client.put(f"/api/v1/medications/{medication['id']}", json={"status": "discontinued"})

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_multiple_active_medications_each_get_own_finding(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Multiple Medications Adherence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=2)

    # Need a second distinct seeded drug for the second medication.
    from sqlalchemy import select

    from app.db.models import ReferenceDrug

    async def _second_drug_id():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ReferenceDrug.id).where(ReferenceDrug.id != existing_drug_id).limit(1)
            )
            return result.scalar_one()

    second_drug_id = await _second_drug_id()

    med_a = _create_medication(
        patient["id"], str(existing_drug_id), start_date=str(past_start),
        times_per_day=1, duration_days=1,
    )
    med_b = _create_medication(
        patient["id"], str(second_drug_id), start_date=str(past_start),
        times_per_day=2, duration_days=1,
    )
    _generate_schedule(med_a["id"])
    _generate_schedule(med_b["id"])

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    medication_ids = {f.medication_id for f in findings}
    assert medication_ids == {uuid.UUID(med_a["id"]), uuid.UUID(med_b["id"])}
    dues = {f.medication_id: f.due for f in findings}
    assert dues[uuid.UUID(med_a["id"])] == 1
    assert dues[uuid.UUID(med_b["id"])] == 2


@pytest.mark.asyncio
async def test_adherence_scoped_to_patient(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Adherence Scoped Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Adherence Scoped Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    past_start = date.today() - timedelta(days=1)

    med_a = _create_medication(
        patient_a["id"], str(existing_drug_id), start_date=str(past_start),
        times_per_day=1, duration_days=1,
    )
    med_b = _create_medication(
        patient_b["id"], str(existing_drug_id), start_date=str(past_start),
        times_per_day=1, duration_days=1,
    )
    _generate_schedule(med_a["id"])
    _generate_schedule(med_b["id"])

    async with AsyncSessionLocal() as session:
        findings_a = await analyze_adherence(uuid.UUID(patient_a["id"]), session)
        findings_b = await analyze_adherence(uuid.UUID(patient_b["id"]), session)

    assert len(findings_a) == 1
    assert findings_a[0].medication_id == uuid.UUID(med_a["id"])
    assert len(findings_b) == 1
    assert findings_b[0].medication_id == uuid.UUID(med_b["id"])
