"""
Phase 12 safety score engine tests.

Two kinds of tests, mirroring the split already used in
test_drug_interaction_engine.py (Phase 10) for `highest_severity`:

  1. Isolated, DB-free unit tests for the pure threshold/classification
     functions (`_classify_adherence_severity`, `_risk_level_for_score`)
     -- these encode the Phase 12 scoring policy exactly, so boundary
     values (e.g. adherence_rate == 0.80 landing on the "adequate" side,
     not "mild") are worth pinning down precisely and cheaply, without a
     live DB.
  2. Integration tests against a live Supabase Postgres instance (same
     requirement as all prior phase test modules) for
     `calculate_safety_score()` end-to-end, composing real
     `detect_drug_interactions` / `detect_adrs` / `analyze_adherence`
     output through real API-created patients/medications/doses.

Seed data relied on (002_seed_data.sql):
  - Warfarin + Aspirin interaction -> severe (30 points)
  - Warfarin ADR: Bleeding / bruising -> severe (30 points)
  - Aspirin ADR: GI upset / gastritis -> moderate (15 points)

No dedicated cleanup fixture is needed beyond the existing
`created_patient_ids` (from conftest.py) -- this engine performs no
writes of its own; all cascades are inherited from prior phases.

Run with:  pytest backend/tests/test_safety_score_engine.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs/interaction_rules/adr_rules from
           002_seed_data.sql.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.analysis.adherence_engine import AdherenceFinding
from app.analysis.safety_score_engine import (
    ADHERENCE_ADEQUATE_THRESHOLD,
    ADHERENCE_MODERATE_THRESHOLD,
    ADHERENCE_SEVERE_THRESHOLD,
    RISK_LEVEL_LOW_THRESHOLD,
    RISK_LEVEL_MODERATE_THRESHOLD,
    SafetyScoreResult,
    _classify_adherence_severity,
    _risk_level_for_score,
    calculate_safety_score,
)
from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug
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


def _create_patient(name: str = "Safety Score Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_active_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    payload = {"drug_id": drug_id, "start_date": str(date.today()), "status": "active", **kwargs}
    resp = client.post(f"/api/v1/patients/{patient_id}/medications", json=payload)
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


async def _drug_id_by_name(name: str) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug.id).where(ReferenceDrug.name == name))
        return result.scalar_one()


async def _drug_id_without_adr_rule() -> uuid.UUID:
    """Return a seeded reference drug without an ADR rule.

    Adherence-only integration tests must not accidentally inherit a
    drug-specific ADR penalty merely because `LIMIT 1` happens to return
    Warfarin (or another drug with seeded ADR data).
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT rd.id
                FROM reference_drugs AS rd
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM adr_rules AS ar
                    WHERE ar.drug_id = rd.id
                )
                LIMIT 1
                """
            )
        )
        drug_id = result.scalar_one_or_none()
    if drug_id is None:
        pytest.skip("No seeded reference_drugs row without an ADR rule is available")
    return drug_id


# ---------------------------------------------------------------------
# _classify_adherence_severity -- pure, isolated, no DB
# ---------------------------------------------------------------------


def _make_adherence_finding(rate: float | None, due: int = 4, taken: int = 0) -> AdherenceFinding:
    return AdherenceFinding(
        medication_id=uuid.uuid4(),
        drug_name="Test Drug",
        taken=taken,
        missed=due - taken,
        skipped=0,
        due=due,
        adherence_rate=rate,
    )


def test_classify_adherence_none_rate_returns_none():
    """due == 0 -> adherence_rate is None -> nothing to classify."""
    assert _classify_adherence_severity(_make_adherence_finding(None, due=0, taken=0)) is None


def test_classify_adherence_at_adequate_threshold_is_none():
    """Exactly 0.80 must land on the adequate (no-penalty) side, inclusive."""
    assert _classify_adherence_severity(_make_adherence_finding(ADHERENCE_ADEQUATE_THRESHOLD)) is None


def test_classify_adherence_just_below_adequate_is_mild():
    assert (
        _classify_adherence_severity(_make_adherence_finding(ADHERENCE_ADEQUATE_THRESHOLD - 0.01))
        == "mild"
    )


def test_classify_adherence_at_moderate_threshold_is_mild():
    """Exactly 0.50 lands on the "mild" side, inclusive."""
    assert _classify_adherence_severity(_make_adherence_finding(ADHERENCE_MODERATE_THRESHOLD)) == "mild"


def test_classify_adherence_just_below_moderate_threshold_is_moderate():
    assert (
        _classify_adherence_severity(_make_adherence_finding(ADHERENCE_MODERATE_THRESHOLD - 0.01))
        == "moderate"
    )


def test_classify_adherence_at_severe_threshold_is_moderate():
    """Exactly 0.25 lands on the "moderate" side, inclusive."""
    assert _classify_adherence_severity(_make_adherence_finding(ADHERENCE_SEVERE_THRESHOLD)) == "moderate"


def test_classify_adherence_just_below_severe_threshold_is_severe():
    assert (
        _classify_adherence_severity(_make_adherence_finding(ADHERENCE_SEVERE_THRESHOLD - 0.01))
        == "severe"
    )


def test_classify_adherence_zero_rate_is_severe():
    assert _classify_adherence_severity(_make_adherence_finding(0.0)) == "severe"


# ---------------------------------------------------------------------
# _risk_level_for_score -- pure, isolated, no DB
# ---------------------------------------------------------------------


def test_risk_level_at_low_threshold_is_low():
    assert _risk_level_for_score(RISK_LEVEL_LOW_THRESHOLD) == "low"


def test_risk_level_just_below_low_threshold_is_moderate():
    assert _risk_level_for_score(RISK_LEVEL_LOW_THRESHOLD - 1) == "moderate"


def test_risk_level_at_moderate_threshold_is_moderate():
    assert _risk_level_for_score(RISK_LEVEL_MODERATE_THRESHOLD) == "moderate"


def test_risk_level_just_below_moderate_threshold_is_high():
    assert _risk_level_for_score(RISK_LEVEL_MODERATE_THRESHOLD - 1) == "high"


def test_risk_level_perfect_score_is_low():
    assert _risk_level_for_score(100) == "low"


def test_risk_level_zero_score_is_high():
    assert _risk_level_for_score(0) == "high"


# ---------------------------------------------------------------------
# calculate_safety_score -- integration, live DB
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_findings_yields_perfect_score(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Perfect Score Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    assert isinstance(result, SafetyScoreResult)
    assert result.safety_score == 100
    assert result.risk_level == "low"
    assert result.starting_score == 100
    assert result.total_points_deducted == 0
    assert result.interaction_findings == []
    assert result.adr_findings == []
    assert result.adherence_findings == []
    assert result.penalties == []


@pytest.mark.asyncio
async def test_single_severe_interaction_deducts_thirty_points(
    existing_auth_user_id, created_patient_ids
):
    """Warfarin + Aspirin -> severe interaction only (30 points)."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Single Interaction Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    interaction_penalties = [p for p in result.penalties if p.category == "drug_interaction"]
    assert len(interaction_penalties) == 1
    assert interaction_penalties[0].severity == "severe"
    assert interaction_penalties[0].points == 30


@pytest.mark.asyncio
async def test_combined_interaction_and_adr_findings_compose_correctly(
    existing_auth_user_id, created_patient_ids
):
    """
    Warfarin + Aspirin together produce: 1 severe interaction (30 pts),
    1 severe ADR for Warfarin (Bleeding/bruising, 30 pts), 1 moderate ADR
    for Aspirin (GI upset/gastritis, 15 pts). Total deducted = 75,
    score = 25, risk_level = "high" (< 40).
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Combined Findings Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    assert len(result.interaction_findings) == 1
    assert len(result.adr_findings) == 2
    assert result.total_points_deducted == 75
    assert result.safety_score == 25
    assert result.risk_level == "high"
    assert len(result.penalties) == 3
    assert {p.category for p in result.penalties} == {"drug_interaction", "adr"}


@pytest.mark.asyncio
async def test_adherence_penalty_included_when_below_adequate_threshold(
    existing_auth_user_id, created_patient_ids
):
    """
    A medication with 0% adherence (all due doses unmarked, never swept)
    must produce a "severe" adherence penalty (20 pts) even with no
    interaction/ADR findings present.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Poor Adherence Only Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    adherence_test_drug_id = await _drug_id_without_adr_rule()
    past_start = date.today() - timedelta(days=2)
    medication = _create_active_medication(
        patient["id"],
        str(adherence_test_drug_id),
        start_date=str(past_start),
        times_per_day=2,
        duration_days=1,
    )
    _generate_schedule(medication["id"])

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    adherence_penalties = [p for p in result.penalties if p.category == "adherence"]
    assert len(adherence_penalties) == 1
    assert adherence_penalties[0].severity == "severe"
    assert adherence_penalties[0].points == 20
    assert result.total_points_deducted == 20
    assert result.safety_score == 80
    assert result.risk_level == "low"


@pytest.mark.asyncio
async def test_adequate_adherence_produces_no_penalty(
    existing_auth_user_id, created_patient_ids
):
    """
    Full adherence (100% taken) must appear in `adherence_findings` (the
    raw measurement is always returned) but must NOT produce a penalty
    entry -- adequate adherence isn't a safety finding.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Adequate Adherence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    adherence_test_drug_id = await _drug_id_without_adr_rule()
    past_start = date.today() - timedelta(days=1)
    medication = _create_active_medication(
        patient["id"],
        str(adherence_test_drug_id),
        start_date=str(past_start),
        times_per_day=2,
        duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    for dose in doses:
        _mark_dose(dose["id"], "taken")

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    assert len(result.adherence_findings) == 1
    assert result.adherence_findings[0].adherence_rate == 1.0
    assert [p for p in result.penalties if p.category == "adherence"] == []
    assert result.safety_score == 100
    assert result.risk_level == "low"


@pytest.mark.asyncio
async def test_penalty_entries_reference_their_source_finding(
    existing_auth_user_id, created_patient_ids
):
    """
    Each PenaltyEntry.source must be the actual originating finding
    object (not just an id/string), so a caller can render a full
    explanation without recomputation -- per the confirmed Phase 12
    design requirement.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Penalty Source Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    interaction_penalty = next(p for p in result.penalties if p.category == "drug_interaction")
    assert interaction_penalty.source in result.interaction_findings

    for adr_penalty in (p for p in result.penalties if p.category == "adr"):
        assert adr_penalty.source in result.adr_findings
