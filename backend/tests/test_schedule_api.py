"""
Phase 8 dose scheduling tests + Phase 9 adherence tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py and all prior phase API test
modules). Authentication is bypassed via a FastAPI dependency override on
`get_current_user`, same as prior phases.

Phase 8 scope: POST /medications/{id}/schedule, GET
/patients/{id}/doses/upcoming, including the interval_hours-only
refinement (schedule generation without an explicit times_per_day).

Phase 9 scope: POST /doses/{id}/mark (taken/missed/skipped), plus the
lazy missed-dose sweep (`_sweep_missed_doses` in
app/api/v1/schedule.py) that runs at the top of both
`list_upcoming_doses` and `mark_dose`. There is no job scheduler in the
tech stack, so this substitutes for the "missed-dose background check"
described in spec section 10 -- overdue, unmarked doses are only ever
flipped to "missed" as a side effect of one of these two routes being
called for the owning patient, not on a real timer. The previous Phase 8
placeholder test asserting `POST /doses/{id}/mark` was unregistered has
been removed and replaced with real coverage now that the route exists.

No `created_*_ids` fixture is needed for generated schedule/dose rows --
both medication_schedule.medication_id and medication_doses.medication_id
have ON DELETE CASCADE, so rows are removed automatically when a test's
created_patient_ids cleanup deletes the patient.

Run with:  pytest backend/tests/test_schedule_api.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs from 002_seed_data.sql.
"""
import uuid
from datetime import date, datetime, timedelta

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
        json={"drug_id": drug_id, "start_date": str(date.today() + timedelta(days=1)), **kwargs},
    )
    assert resp.status_code == 201
    return resp.json()


def _generate_schedule(medication_id: str) -> list[dict]:
    resp = client.post(f"/api/v1/medications/{medication_id}/schedule")
    assert resp.status_code == 201
    return resp.json()


def _get_timeline(patient_id: str) -> list[dict]:
    resp = client.get(f"/api/v1/patients/{patient_id}/timeline")
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------
# Phase 8 -- schedule generation
# ---------------------------------------------------------------------


def test_generate_schedule_creates_expected_dose_count(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient()
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=2, duration_days=3
    )

    doses = _generate_schedule(medication["id"])

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

    doses = sorted(_generate_schedule(medication["id"]), key=lambda d: d["scheduled_time"])

    t0 = datetime.fromisoformat(doses[0]["scheduled_time"].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(doses[1]["scheduled_time"].replace("Z", "+00:00"))
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

    doses = sorted(_generate_schedule(medication["id"]), key=lambda d: d["scheduled_time"])
    assert len(doses) == 2

    t0 = datetime.fromisoformat(doses[0]["scheduled_time"].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(doses[1]["scheduled_time"].replace("Z", "+00:00"))
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

    _generate_schedule(medication["id"])

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


def test_generate_schedule_with_interval_hours_only_creates_expected_dose_count(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    times_per_day is omitted entirely; interval_hours + duration_days alone
    must be sufficient to generate a schedule (the Phase 8 refinement).
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Interval Only Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), duration_days=1, interval_hours=8
    )
    assert medication["times_per_day"] is None

    doses = _generate_schedule(medication["id"])

    # floor(1 day * 24h / 8h) = 3 doses (hours 0, 8, 16 after anchor).
    assert len(doses) == 3
    assert all(d["medication_id"] == medication["id"] for d in doses)
    assert all(d["status"] is None for d in doses)


def test_generate_schedule_with_interval_hours_only_spacing_matches_interval(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Interval Only Spacing Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), duration_days=2, interval_hours=6
    )

    doses = sorted(_generate_schedule(medication["id"]), key=lambda d: d["scheduled_time"])

    t0 = datetime.fromisoformat(doses[0]["scheduled_time"].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(doses[1]["scheduled_time"].replace("Z", "+00:00"))
    assert (t1 - t0).total_seconds() == 6 * 3600

    # floor(2 days * 24h / 6h) = 8 doses.
    assert len(doses) == 8


def test_generate_schedule_with_interval_hours_only_floors_partial_dose(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    duration_days=1, interval_hours=5 -> 24/5 = 4.8 doses would fit, so the
    schedule must floor to 4, never round up to a dose that falls outside
    the duration window.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Interval Only Floor Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), duration_days=1, interval_hours=5
    )

    doses = _generate_schedule(medication["id"])
    assert len(doses) == 4


def test_generate_schedule_missing_both_times_per_day_and_interval_hours_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    Neither times_per_day nor interval_hours is set -- must 400 with a
    message referencing both fields, distinct from the duration_days
    missing-field error.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Missing Both Fields Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(patient["id"], str(existing_drug_id), duration_days=3)

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "times_per_day" in detail
    assert "interval_hours" in detail


def test_generate_schedule_interval_hours_only_exceeding_max_doses_returns_400(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Interval Only Exceeds Max Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    # floor(400 days * 24h / 1h) = 9600 > MAX_GENERATED_DOSES (3650)
    medication = _create_medication(
        patient["id"], str(existing_drug_id), duration_days=400, interval_hours=1
    )

    resp = client.post(f"/api/v1/medications/{medication['id']}/schedule")
    assert resp.status_code == 400
    assert "exceeding" in resp.json()["detail"]


def test_upcoming_doses_returns_future_unmarked_doses_ordered(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Upcoming Doses Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=3, duration_days=2
    )
    _generate_schedule(medication["id"])

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
    _generate_schedule(medication["id"])

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
    _generate_schedule(medication_a["id"])

    medication_b = _create_medication(
        other_patient["id"], str(existing_drug_id), times_per_day=1, duration_days=2
    )
    _generate_schedule(medication_b["id"])

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


# ---------------------------------------------------------------------
# Phase 9 -- mark dose (taken/missed/skipped)
# ---------------------------------------------------------------------


def test_mark_dose_taken_sets_status_and_defaults_actual_time(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Mark Taken Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "taken"})
    assert resp.status_code == 200
    marked = resp.json()

    assert marked["status"] == "taken"
    assert marked["actual_time"] is not None  # defaulted to now()
    assert marked["updated_at"] != doses[0]["updated_at"]


def test_mark_dose_taken_respects_explicit_actual_time(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Mark Taken Explicit Time Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    explicit_time = "2026-07-31T09:15:00+00:00"
    resp = client.post(
        f"/api/v1/doses/{dose_id}/mark",
        json={"status": "taken", "actual_time": explicit_time},
    )
    assert resp.status_code == 200
    assert resp.json()["actual_time"] == explicit_time


def test_mark_dose_missed_leaves_actual_time_null(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Mark Missed Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "missed"})
    assert resp.status_code == 200
    marked = resp.json()

    assert marked["status"] == "missed"
    assert marked["actual_time"] is None


def test_mark_dose_skipped_leaves_actual_time_null(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Mark Skipped Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "skipped"})
    assert resp.status_code == 200
    marked = resp.json()

    assert marked["status"] == "skipped"
    assert marked["actual_time"] is None


@pytest.mark.parametrize(
    "mark_status,event_type",
    [("taken", "dose_taken"), ("missed", "dose_missed"), ("skipped", "dose_skipped")],
)
def test_mark_dose_logs_corresponding_timeline_event(
    existing_auth_user_id, existing_drug_id, created_patient_ids, mark_status, event_type
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient(f"Mark Timeline {mark_status} Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": mark_status})
    assert resp.status_code == 200

    events = _get_timeline(patient["id"])
    matching = [e for e in events if e["event_type"] == event_type and e["ref_id"] == dose_id]
    assert len(matching) == 1
    assert matching[0]["payload"]["medication_id"] == medication["id"]


def test_mark_dose_twice_returns_409(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Mark Twice Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    first = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "taken"})
    assert first.status_code == 200

    second = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "missed"})
    assert second.status_code == 409
    assert "already marked as 'taken'" in second.json()["detail"]


def test_mark_nonexistent_dose_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(f"/api/v1/doses/{uuid.uuid4()}/mark", json={"status": "taken"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Dose not found."


def test_mark_dose_owned_by_another_user_returns_404(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Owned By A Mark Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "taken"})
    assert resp.status_code == 404


def test_mark_dose_invalid_status_returns_422(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Invalid Status Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=1
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "snoozed"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------
# Phase 9 -- lazy missed-dose sweep
# ---------------------------------------------------------------------


def test_upcoming_doses_sweeps_overdue_unmarked_doses_to_missed(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    A medication scheduled entirely in the past should have all its
    unmarked doses flipped to "missed" as a side effect of calling
    GET /patients/{id}/doses/upcoming, and a dose_missed timeline event
    logged for each.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Sweep Via Upcoming Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=2)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(past_start),
        times_per_day=2,
        duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    dose_ids = {d["id"] for d in doses}
    assert all(d["status"] is None for d in doses)  # not yet swept

    upcoming_resp = client.get(f"/api/v1/patients/{patient['id']}/doses/upcoming")
    assert upcoming_resp.status_code == 200
    # All doses are in the past -- none should show up as "upcoming".
    assert not any(d["medication_id"] == medication["id"] for d in upcoming_resp.json())

    # Confirm the sweep actually persisted "missed": a subsequent explicit
    # mark attempt on any of these doses must now 409 as already marked.
    for dose_id in dose_ids:
        mark_resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "taken"})
        assert mark_resp.status_code == 409
        assert "already marked as 'missed'" in mark_resp.json()["detail"]

    events = _get_timeline(patient["id"])
    missed_events = [
        e for e in events if e["event_type"] == "dose_missed" and e["ref_id"] in dose_ids
    ]
    assert len(missed_events) == len(dose_ids)
    assert all(e["payload"]["auto_detected"] is True for e in missed_events)


def test_mark_dose_sweeps_overdue_dose_before_processing_the_mark(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """
    Calling POST /doses/{id}/mark directly on an overdue, unmarked dose
    (without ever calling GET .../doses/upcoming first) must still trigger
    the sweep -- the sweep runs at the top of mark_dose too, so the
    explicit mark attempt sees the dose as already "missed" and 409s.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Sweep Via Mark Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=3)
    medication = _create_medication(
        patient["id"],
        str(existing_drug_id),
        start_date=str(past_start),
        times_per_day=1,
        duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[0]["id"]

    resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "taken"})
    assert resp.status_code == 409
    assert "already marked as 'missed'" in resp.json()["detail"]

    events = _get_timeline(patient["id"])
    missed_events = [
        e for e in events if e["event_type"] == "dose_missed" and e["ref_id"] == dose_id
    ]
    assert len(missed_events) == 1


def test_sweep_does_not_affect_future_doses(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    """A dose scheduled in the future must remain unmarked after a sweep-
    triggering call, and must still be explicitly markable afterward."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Sweep Future Unaffected Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_medication(
        patient["id"], str(existing_drug_id), times_per_day=1, duration_days=5
    )
    doses = _generate_schedule(medication["id"])
    dose_id = doses[-1]["id"]  # last dose, several days out

    client.get(f"/api/v1/patients/{patient['id']}/doses/upcoming")

    mark_resp = client.post(f"/api/v1/doses/{dose_id}/mark", json={"status": "taken"})
    assert mark_resp.status_code == 200
    assert mark_resp.json()["status"] == "taken"
