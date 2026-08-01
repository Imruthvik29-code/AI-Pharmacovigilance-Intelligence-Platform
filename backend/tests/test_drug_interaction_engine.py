"""
Phase 10 drug interaction engine tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py and all prior phase test
modules) -- `detect_drug_interactions` queries `medications` and
`interaction_rules` directly, so a real DB with the Phase 1 seed data
(002_seed_data.sql) is required.

Unlike prior phase test files, there is no HTTP endpoint to exercise yet
(the engine is not wired into any route until Phase 14/LangGraph) -- these
tests call `app.analysis.drug_interaction_engine` functions directly
against an `AsyncSessionLocal` session. Patient/medication fixtures are
still created through the existing, already-tested API endpoints via
`TestClient` (simplest way to get valid, owned rows), then the engine is
exercised directly with an async DB session.

Seed data relied on (002_seed_data.sql):
  - Warfarin + Aspirin   -> severe   (FDA Label)
  - Warfarin + Ibuprofen -> severe   (FDA Label)
  - Warfarin + Omeprazole -> mild    (FDA Label; rule stored as
    Omeprazole/Warfarin, confirming direction-independence)
  - Lisinopril + Spironolactone -> moderate (FDA Label)
  - Metformin + Levothyroxine: no seeded rule between these two --
    used as a "no interaction" negative control.

No dedicated cleanup fixture is needed beyond the existing
`created_patient_ids` (from conftest.py) -- medications cascade away via
`ON DELETE CASCADE` when the patient is deleted, and this engine performs
no writes of its own.

Run with:  pytest backend/tests/test_drug_interaction_engine.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs/interaction_rules from 002_seed_data.sql.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.analysis.drug_interaction_engine import (
    DrugInteractionFinding,
    detect_drug_interactions,
    highest_severity,
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


def _create_patient(name: str = "Interaction Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_active_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    payload = {"drug_id": drug_id, "start_date": str(date.today()), "status": "active", **kwargs}
    resp = client.post(f"/api/v1/patients/{patient_id}/medications", json=payload)
    assert resp.status_code == 201
    return resp.json()


async def _drug_id_by_name(name: str) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug.id).where(ReferenceDrug.name == name))
        return result.scalar_one()


# ---------------------------------------------------------------------
# detect_drug_interactions
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_active_medications_returns_empty(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Medications Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_single_active_medication_returns_empty(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Single Medication Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    _create_active_medication(patient["id"], str(warfarin_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert findings == []  # fewer than two distinct active drugs


@pytest.mark.asyncio
async def test_detects_known_severe_interaction(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Warfarin Aspirin Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, DrugInteractionFinding)
    assert finding.severity == "severe"
    assert {finding.drug_a_name, finding.drug_b_name} == {"Warfarin", "Aspirin"}
    assert finding.mechanism is not None
    assert finding.recommendation is not None
    assert finding.source == "FDA Label"


@pytest.mark.asyncio
async def test_detection_is_direction_independent(
    existing_auth_user_id, created_patient_ids
):
    """
    The Warfarin+Omeprazole rule is seeded as drug_a=Omeprazole,
    drug_b=Warfarin (see 002_seed_data.sql). Creating the patient's
    medications in the OPPOSITE order (Warfarin first, then Omeprazole)
    must still detect the interaction, proving detection is a pure
    set-membership check rather than depending on creation order or the
    rule's stored direction.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Direction Independence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    omeprazole_id = await _drug_id_by_name("Omeprazole")
    # Warfarin created first, Omeprazole second -- reverse of the rule's
    # own drug_a/drug_b storage order.
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(omeprazole_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert len(findings) == 1
    assert findings[0].severity == "mild"
    assert {findings[0].drug_a_name, findings[0].drug_b_name} == {"Warfarin", "Omeprazole"}


@pytest.mark.asyncio
async def test_no_rule_between_drugs_returns_empty(
    existing_auth_user_id, created_patient_ids
):
    """Metformin + Levothyroxine has no seeded interaction_rules row."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Interaction Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    metformin_id = await _drug_id_by_name("Metformin")
    levothyroxine_id = await _drug_id_by_name("Levothyroxine")
    _create_active_medication(patient["id"], str(metformin_id))
    _create_active_medication(patient["id"], str(levothyroxine_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_excludes_non_active_medications(
    existing_auth_user_id, created_patient_ids
):
    """
    A discontinued medication must not be considered "the patient's
    drugs" for interaction detection, per the Phase 10 scope decision --
    only status == "active" medications count.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Discontinued Excluded Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    discontinued_aspirin = _create_active_medication(patient["id"], str(aspirin_id))

    client.put(
        f"/api/v1/medications/{discontinued_aspirin['id']}",
        json={"status": "discontinued"},
    )

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_detects_multiple_simultaneous_interactions(
    existing_auth_user_id, created_patient_ids
):
    """
    Warfarin, Aspirin, and Ibuprofen all active together should surface
    BOTH the Warfarin+Aspirin and Warfarin+Ibuprofen rules.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Multiple Interactions Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    ibuprofen_id = await _drug_id_by_name("Ibuprofen")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))
    _create_active_medication(patient["id"], str(ibuprofen_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert len(findings) == 2
    pairs_found = {frozenset({f.drug_a_name, f.drug_b_name}) for f in findings}
    assert frozenset({"Warfarin", "Aspirin"}) in pairs_found
    assert frozenset({"Warfarin", "Ibuprofen"}) in pairs_found
    assert all(f.severity == "severe" for f in findings)


@pytest.mark.asyncio
async def test_interactions_scoped_to_patient(
    existing_auth_user_id, created_patient_ids
):
    """A different patient's active drugs must not leak into this patient's findings."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("Scoped Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("Scoped Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")

    # Patient A gets only Warfarin; Patient B gets Warfarin + Aspirin.
    _create_active_medication(patient_a["id"], str(warfarin_id))
    _create_active_medication(patient_b["id"], str(warfarin_id))
    _create_active_medication(patient_b["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        findings_a = await detect_drug_interactions(uuid.UUID(patient_a["id"]), session)
        findings_b = await detect_drug_interactions(uuid.UUID(patient_b["id"]), session)

    assert findings_a == []
    assert len(findings_b) == 1


# ---------------------------------------------------------------------
# highest_severity
# ---------------------------------------------------------------------


def _make_finding(severity: str) -> DrugInteractionFinding:
    return DrugInteractionFinding(
        interaction_rule_id=uuid.uuid4(),
        drug_a_id=uuid.uuid4(),
        drug_a_name="Drug A",
        drug_b_id=uuid.uuid4(),
        drug_b_name="Drug B",
        severity=severity,
        mechanism=None,
        recommendation=None,
        source=None,
    )


def test_highest_severity_empty_list_returns_none():
    assert highest_severity([]) is None


def test_highest_severity_single_finding():
    assert highest_severity([_make_finding("mild")]) == "mild"


def test_highest_severity_picks_most_severe_regardless_of_order():
    findings = [_make_finding("mild"), _make_finding("severe"), _make_finding("moderate")]
    assert highest_severity(findings) == "severe"


def test_highest_severity_all_same_severity():
    findings = [_make_finding("moderate"), _make_finding("moderate")]
    assert highest_severity(findings) == "moderate"
