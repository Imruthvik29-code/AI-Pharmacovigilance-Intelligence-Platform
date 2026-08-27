"""
Phase 12 adherence engine tests.

Integration tests against a live Supabase Postgres instance. The engine is
called directly against AsyncSessionLocal; patient/medication/schedule
fixtures use the existing API endpoints and explicit dose marking uses
POST /doses/{id}/mark.

Explicitly marked doses are created in the future so the Phase 9 lazy
missed-dose sweep cannot convert them to `missed` before the explicit mark.
After marking, the test moves the marked dose rows into the past so
analyze_adherence() includes them in due-dose statistics. Separate tests
continue to verify that overdue unmarked doses are counted as missed by the
engine itself.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.analysis.adherence_engine import AdherenceFinding, analyze_adherence
from app.core.security import CurrentUser, get_current_user
from app.db.models import MedicationDose, ReferenceDrug
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


async def _move_marked_doses_into_due_window(dose_ids: list[str]) -> None:
    """Age explicitly marked test doses after the mark endpoint has run.

    This is test data preparation, not production behavior. Updating only
    the dose timestamp is sufficient because analyze_adherence() reads
    medication_doses; the production schedule remains untouched.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        for offset, dose_id in enumerate(dose_ids, start=1):
            await session.execute(
                update(MedicationDose)
                .where(MedicationDose.id == uuid.UUID(dose_id))
                .values(scheduled_time=now - timedelta(minutes=offset))
            )
        await session.commit()


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
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("No Due Doses Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    tomorrow = date.today() + timedelta(days=1)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), start_date=str(tomorrow),
        times_per_day=2, duration_days=2,
    )
    _generate_schedule(medication["id"])

    async with AsyncSessionLocal() as session:
        findings = await analyze_adherence(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_all_due_doses_unmarked_counts_as_fully_missed(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Fully Missed Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=3)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), start_date=str(past_start),
        times_per_day=2, duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    assert all(d["status"] is None for d in doses)

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

    # Keep the doses future-dated while the mark endpoint is called. The
    # endpoint's lazy sweep must not preemptively mark them as missed.
    future_start = date.today() + timedelta(days=1)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), start_date=str(future_start),
        times_per_day=3, duration_days=1,
    )
    doses = sorted(_generate_schedule(medication["id"]), key=lambda d: d["scheduled_time"])
    assert len(doses) == 3

    _mark_dose(doses[0]["id"], "taken")
    _mark_dose(doses[1]["id"], "missed")
    _mark_dose(doses[2]["id"], "skipped")
    await _move_marked_doses_into_due_window([d["id"] for d in doses])

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

    future_start = date.today() + timedelta(days=1)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), start_date=str(future_start),
        times_per_day=2, duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    for dose in doses:
        _mark_dose(dose["id"], "taken")
    await _move_marked_doses_into_due_window([d["id"] for d in doses])

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
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Discontinued Excluded Adherence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=2)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), start_date=str(past_start),
        times_per_day=1, duration_days=1,
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
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ReferenceDrug.id).where(ReferenceDrug.id != existing_drug_id).limit(1)
        )
        second_drug_id = result.scalar_one()

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
