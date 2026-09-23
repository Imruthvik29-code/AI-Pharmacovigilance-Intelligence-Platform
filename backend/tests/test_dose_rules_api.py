"""
Phase 2 dose-rule tests.

Integration tests against a live Postgres instance, same requirement and
cleanup convention as test_medications_api.py -- every medication created
here is appended to `created_medication_ids` so conftest's autouse cleanup
removes it (dose rules and generated doses follow via ON DELETE CASCADE).

Covers the parts of the frozen Phase 2 contract that are only observable
through the API: whole-collection replacement semantics, sequence
validation, the anchor/offset rules, rule-based generation against the
patient's routine, DST handling, and the dose snapshot.

Run with:  pytest backend/tests/test_dose_rules_api.py -v
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)


def _utc(value: str) -> datetime:
    """Parse an API timestamp as UTC.

    datetime.fromisoformat only accepts a 'Z' suffix from Python 3.11, and
    this suite runs on 3.10, so normalise it first.
    """
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _override_current_user(user_id):
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")

    return _fake_current_user


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    return existing_auth_user_id


def _make_patient(created_patient_ids, **routine) -> str:
    body = {"name": "Dose Rule Patient", **routine}
    resp = client.post("/api/v1/patients", json=body)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    created_patient_ids.append(uuid.UUID(pid))
    return pid


def _routine() -> dict:
    return {
        "timezone": "Asia/Kolkata",
        "breakfast_time": "08:00:00",
        "lunch_time": "13:00:00",
        "dinner_time": "20:00:00",
    }


def _make_medication(patient_id, drug_id, created_medication_ids, **over) -> dict:
    body = {
        "drug_id": str(drug_id),
        "start_date": "2026-10-01",
        "dose": "1 tablet",
        "duration_days": 2,
        "times_per_day": 2,
        **over,
    }
    resp = client.post(f"/api/v1/patients/{patient_id}/medications", json=body)
    assert resp.status_code == 201, resp.text
    med = resp.json()
    created_medication_ids.append(uuid.UUID(med["id"]))
    return med


MEAL_RULES = [
    {"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "after", "offset_minutes": 30},
    {"sequence": 2, "anchor_type": "dinner", "anchor_relation": "with"},
]


# ── creation / replacement semantics ─────────────────────────────────────


def test_create_medication_with_dose_rules(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)

    assert [r["sequence"] for r in med["dose_rules"]] == [1, 2]
    assert med["dose_rules"][0]["anchor_type"] == "breakfast"
    assert med["dose_rules"][0]["offset_minutes"] == 30
    assert med["dose_rules"][1]["anchor_relation"] == "with"
    assert med["dose_rules"][1]["offset_minutes"] is None


def test_create_without_dose_rules_yields_empty_list(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids)
    med = _make_medication(pid, existing_drug_id, created_medication_ids)
    assert med["dose_rules"] == []


def test_absent_dose_rules_leaves_existing_rules_untouched(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)

    # A PUT that does not mention dose_rules must not disturb them.
    resp = client.put(f"/api/v1/medications/{med['id']}", json={"dose": "2 tablets"})
    assert resp.status_code == 200
    assert resp.json()["dose"] == "2 tablets"
    assert [r["sequence"] for r in resp.json()["dose_rules"]] == [1, 2]


def test_empty_list_clears_dose_rules(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)

    resp = client.put(f"/api/v1/medications/{med['id']}", json={"dose_rules": []})
    assert resp.status_code == 200
    assert resp.json()["dose_rules"] == []


def test_replacement_shrinks_collection_and_reassigns_ids(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """3 rules -> 2 rules in one request; ids are not preserved."""
    pid = _make_patient(created_patient_ids, **_routine())
    three = [
        {"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"},
        {"sequence": 2, "anchor_type": "lunch", "anchor_relation": "with"},
        {"sequence": 3, "anchor_type": "dinner", "anchor_relation": "with"},
    ]
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids, times_per_day=3, dose_rules=three
    )
    original_ids = {r["id"] for r in med["dose_rules"]}

    two = [
        {"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"},
        {"sequence": 2, "anchor_type": "dinner", "anchor_relation": "with"},
    ]
    resp = client.put(f"/api/v1/medications/{med['id']}", json={"dose_rules": two})
    assert resp.status_code == 200
    rules = resp.json()["dose_rules"]
    assert [r["anchor_type"] for r in rules] == ["breakfast", "dinner"]
    assert not (original_ids & {r["id"] for r in rules})


# ── validation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rules",
    [
        pytest.param(
            [{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"},
             {"sequence": 1, "anchor_type": "dinner", "anchor_relation": "with"}],
            id="duplicate-sequence",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"},
             {"sequence": 3, "anchor_type": "dinner", "anchor_relation": "with"}],
            id="non-contiguous",
        ),
        pytest.param(
            [{"sequence": 2, "anchor_type": "breakfast", "anchor_relation": "with"}],
            id="does-not-start-at-1",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with",
              "offset_minutes": 30}],
            id="with-plus-offset",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "before"}],
            id="before-without-offset",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "clock_time", "anchor_relation": "after",
              "offset_minutes": 10, "clock_time": "14:00:00"}],
            id="clock-time-with-relation",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "clock_time"}],
            id="clock-time-without-time",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "after",
              "offset_minutes": 0}],
            id="offset-zero",
        ),
        pytest.param(
            [{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "after",
              "offset_minutes": 61}],
            id="offset-above-max",
        ),
    ],
)
def test_invalid_rule_collections_are_rejected(
    auth, existing_drug_id, created_patient_ids, rules
):
    pid = _make_patient(created_patient_ids, **_routine())
    resp = client.post(
        f"/api/v1/patients/{pid}/medications",
        json={
            "drug_id": str(existing_drug_id),
            "start_date": "2026-10-01",
            "duration_days": 2,
            "times_per_day": len(rules),
            "dose_rules": rules,
        },
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_per_rule_routes_are_method_not_allowed(auth, method):
    resp = getattr(client, method)(f"/api/v1/dose-rules/{uuid.uuid4()}")
    assert resp.status_code == 405
    assert "managed as a set" in resp.json()["detail"]


# ── generation ───────────────────────────────────────────────────────────


def test_rule_based_generation_uses_patient_routine_and_timezone(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)

    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 201, resp.text
    doses = resp.json()
    assert len(doses) == 4  # 2 rules x 2 days

    times = sorted(_utc(d["scheduled_time"]) for d in doses)
    # Asia/Kolkata is UTC+5:30 with no DST: 08:30 local -> 03:00Z,
    # 20:00 local -> 14:30Z.
    assert [t.strftime("%H:%M") for t in times[:2]] == ["03:00", "14:30"]
    assert times[0].date().isoformat() == "2026-10-01"


def test_generation_snapshots_resolved_dose_with_rule_override(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    rules = [
        {"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"},
        {"sequence": 2, "anchor_type": "dinner", "anchor_relation": "with",
         "dose": "half tablet"},
    ]
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids, duration_days=1, dose_rules=rules
    )
    assert client.post(f"/api/v1/medications/{med['id']}/schedule").status_code == 201

    upcoming = client.get(f"/api/v1/patients/{pid}/doses/upcoming")
    assert upcoming.status_code == 200
    by_time = sorted(upcoming.json(), key=lambda d: d["scheduled_time"])
    # Rule 1 inherits the course dose; rule 2 overrides it.
    assert [d["dose"] for d in by_time] == ["1 tablet", "half tablet"]

    # Editing the medication afterwards must not rewrite the snapshot.
    assert client.put(
        f"/api/v1/medications/{med['id']}", json={"dose": "CHANGED"}
    ).status_code == 200
    after = sorted(
        client.get(f"/api/v1/patients/{pid}/doses/upcoming").json(),
        key=lambda d: d["scheduled_time"],
    )
    assert [d["dose"] for d in after] == ["1 tablet", "half tablet"]


def test_generation_rejects_rules_plus_interval_hours(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        interval_hours=8, dose_rules=MEAL_RULES,
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400
    assert "interval_hours" in resp.json()["detail"]


def test_generation_rejects_rule_count_mismatch(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        times_per_day=3, dose_rules=MEAL_RULES,  # 3 declared, 2 defined
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400
    assert "times_per_day" in resp.json()["detail"]


def test_generation_requires_patient_timezone(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids)  # no routine recorded
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400
    assert "timezone" in resp.json()["detail"]


def test_generation_requires_the_referenced_meal_time(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(
        created_patient_ids, timezone="Asia/Kolkata", breakfast_time="08:00:00"
    )  # dinner_time deliberately absent
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400
    assert "dinner_time" in resp.json()["detail"]


def test_generation_rejects_nonexistent_dst_local_time(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """2026-03-08 02:30 does not exist in America/New_York (spring forward)."""
    pid = _make_patient(
        created_patient_ids, timezone="America/New_York", breakfast_time="02:30:00"
    )
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        start_date="2026-03-08", duration_days=1, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400
    assert "does not exist" in resp.json()["detail"]


def test_ambiguous_dst_local_time_resolves_to_first_occurrence(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """2026-11-01 01:30 occurs twice in America/New_York; fold=0 wins (EDT, 05:30Z)."""
    pid = _make_patient(
        created_patient_ids, timezone="America/New_York", breakfast_time="01:30:00"
    )
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        start_date="2026-11-01", duration_days=1, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 201, resp.text
    when = _utc(resp.json()[0]["scheduled_time"])
    assert when.strftime("%H:%M") == "05:30"


def test_clock_time_rule_generates_at_that_local_time(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        duration_days=1, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "clock_time", "clock_time": "14:00:00"}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 201, resp.text
    when = _utc(resp.json()[0]["scheduled_time"])
    assert when.strftime("%H:%M") == "08:30"  # 14:00 IST = 08:30Z


def test_before_offset_subtracts_from_the_anchor(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        duration_days=1, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "lunch", "anchor_relation": "before",
                     "offset_minutes": 30}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 201, resp.text
    when = _utc(resp.json()[0]["scheduled_time"])
    assert when.strftime("%H:%M") == "07:00"  # 12:30 IST = 07:00Z


def test_interval_mode_is_unaffected_by_phase_2(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """No rules -> the original 08:00 UTC anchor and even spread are kept."""
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids, duration_days=1, times_per_day=2
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 201, resp.text
    times = sorted(_utc(d["scheduled_time"]) for d in resp.json())
    assert [t.strftime("%H:%M") for t in times] == ["08:00", "20:00"]


# ── audit follow-ups: D1-D4 and the two locked scheduling decisions ──────


def test_null_dose_rules_is_rejected(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """null is neither 'unchanged' nor 'clear' -- it must not silently clear."""
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(pid, existing_drug_id, created_medication_ids, dose_rules=MEAL_RULES)

    resp = client.put(f"/api/v1/medications/{med['id']}", json={"dose_rules": None})
    assert resp.status_code == 422, resp.text

    still = client.get(f"/api/v1/patients/{pid}/medications").json()[0]
    assert [r["sequence"] for r in still["dose_rules"]] == [1, 2]


def test_rule_mode_dose_cap_is_checked_before_building_the_schedule(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """24 clock rules x 200 days = 4800 > cap.

    The patient has no routine recorded, so if the cap were checked after the
    schedule was built this would fail on the missing timezone instead.
    """
    pid = _make_patient(created_patient_ids)
    rules = [
        {"sequence": i + 1, "anchor_type": "clock_time", "clock_time": f"{i:02d}:00:00"}
        for i in range(24)
    ]
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        duration_days=200, times_per_day=24, dose_rules=rules,
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400, resp.text
    assert "exceeding the maximum" in resp.json()["detail"]


def test_interval_mode_huge_range_is_rejected_promptly(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """876,000,000 doses must be refused arithmetically, not materialised.

    Before the fix this allocated the whole list first: ~18 minutes and many
    gigabytes. The elapsed-time assertion is the regression signal.
    """
    import time as _time

    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        duration_days=3650, times_per_day=None, interval_hours=0.0001,
    )
    started = _time.perf_counter()
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    elapsed = _time.perf_counter() - started

    assert resp.status_code == 400, resp.text
    assert "exceeding the maximum" in resp.json()["detail"]
    assert elapsed < 30, f"cap was not checked arithmetically (took {elapsed:.1f}s)"


def test_huge_duration_returns_400_not_a_date_overflow_500(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """10,000,000 days overflows `date` ~2.9M days in; the cap must come first."""
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        duration_days=10_000_000, times_per_day=1,
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400, resp.text
    assert "exceeding the maximum" in resp.json()["detail"]


def test_replacing_rules_after_generation_leaves_generated_doses_untouched(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids, duration_days=1, dose_rules=MEAL_RULES
    )
    assert client.post(f"/api/v1/medications/{med['id']}/schedule").status_code == 201
    before = sorted(
        (d["scheduled_time"], d["dose"])
        for d in client.get(f"/api/v1/patients/{pid}/doses/upcoming").json()
    )
    assert before

    replacement = [
        {"sequence": 1, "anchor_type": "clock_time", "clock_time": "05:00:00", "dose": "NEW"},
        {"sequence": 2, "anchor_type": "clock_time", "clock_time": "06:00:00", "dose": "NEW"},
    ]
    assert client.put(
        f"/api/v1/medications/{med['id']}", json={"dose_rules": replacement}
    ).status_code == 200

    after = sorted(
        (d["scheduled_time"], d["dose"])
        for d in client.get(f"/api/v1/patients/{pid}/doses/upcoming").json()
    )
    assert after == before


def test_legacy_dose_with_null_snapshot_falls_back_to_medication_dose(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """Rows generated before 0007 have dose IS NULL and must read through."""
    import asyncio

    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids, duration_days=1, dose_rules=MEAL_RULES
    )
    assert client.post(f"/api/v1/medications/{med['id']}/schedule").status_code == 201

    async def _blank_snapshots() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE medication_doses SET dose = NULL WHERE medication_id = :m"),
                {"m": med["id"]},
            )
            await session.commit()

    asyncio.run(_blank_snapshots())

    upcoming = client.get(f"/api/v1/patients/{pid}/doses/upcoming").json()
    assert upcoming
    assert {d["dose"] for d in upcoming} == {"1 tablet"}

    assert client.put(
        f"/api/v1/medications/{med['id']}", json={"dose": "2 tablets"}
    ).status_code == 200
    after = client.get(f"/api/v1/patients/{pid}/doses/upcoming").json()
    assert {d["dose"] for d in after} == {"2 tablets"}


def test_interval_generated_dose_stores_the_snapshot(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids, duration_days=1, times_per_day=2
    )
    assert client.post(f"/api/v1/medications/{med['id']}/schedule").status_code == 201
    assert {d["dose"] for d in client.get(f"/api/v1/patients/{pid}/doses/upcoming").json()} == {
        "1 tablet"
    }

    assert client.put(
        f"/api/v1/medications/{med['id']}", json={"dose": "CHANGED"}
    ).status_code == 200
    assert {d["dose"] for d in client.get(f"/api/v1/patients/{pid}/doses/upcoming").json()} == {
        "1 tablet"
    }


def test_duplicate_resolved_instants_are_rejected(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """Two rules on the same meal with no offset collide exactly."""
    pid = _make_patient(created_patient_ids, **_routine())
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        duration_days=1, times_per_day=2,
        dose_rules=[
            {"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"},
            {"sequence": 2, "anchor_type": "breakfast", "anchor_relation": "with"},
        ],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "resolve to" in detail
    assert "1" in detail and "2" in detail


def test_window_is_evaluated_in_local_time_not_utc(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """03:00 in Asia/Kolkata is 21:30 UTC the previous day -- still in course.

    A window checked against the UTC date would wrongly reject this.
    """
    pid = _make_patient(
        created_patient_ids, timezone="Asia/Kolkata", breakfast_time="03:00:00"
    )
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        start_date="2026-10-01", duration_days=1, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "breakfast", "anchor_relation": "with"}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 201, resp.text
    when = _utc(resp.json()[0]["scheduled_time"])
    assert when.strftime("%Y-%m-%d %H:%M") == "2026-09-30 21:30"


def test_dose_before_start_date_is_rejected(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """Breakfast recorded just after midnight, minus an offset, leaves the course."""
    pid = _make_patient(
        created_patient_ids, timezone="Asia/Kolkata", breakfast_time="00:20:00"
    )
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        start_date="2026-10-01", duration_days=2, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "breakfast",
                     "anchor_relation": "before", "offset_minutes": 30}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400, resp.text
    assert "outside the course window" in resp.json()["detail"]
    assert "2026-09-30" in resp.json()["detail"]


def test_dose_after_final_course_date_is_rejected(
    auth, existing_drug_id, created_patient_ids, created_medication_ids
):
    """Dinner recorded just before midnight, plus an offset, leaves the course."""
    pid = _make_patient(
        created_patient_ids, timezone="Asia/Kolkata", dinner_time="23:40:00"
    )
    med = _make_medication(
        pid, existing_drug_id, created_medication_ids,
        start_date="2026-10-01", duration_days=2, times_per_day=1,
        dose_rules=[{"sequence": 1, "anchor_type": "dinner",
                     "anchor_relation": "after", "offset_minutes": 30}],
    )
    resp = client.post(f"/api/v1/medications/{med['id']}/schedule")
    assert resp.status_code == 400, resp.text
    assert "outside the course window" in resp.json()["detail"]
    assert "2026-10-03" in resp.json()["detail"]


def test_get_on_the_guarded_path_is_405_with_an_honest_allow_header(auth):
    resp = client.get(f"/api/v1/dose-rules/{uuid.uuid4()}")
    assert resp.status_code == 405
    assert resp.headers.get("allow", "") == ""
    assert "managed as a set" in resp.json()["detail"]
