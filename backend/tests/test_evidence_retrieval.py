"""
Phase 13 evidence retrieval tests.

Integration tests against a live Supabase Postgres instance (same
requirement as all prior phase test modules) -- `retrieve_evidence`
queries `medications` and `timeline_events` directly, and consumes a
real `SafetyScoreResult` from Phase 12's `calculate_safety_score()`, so a
real DB with the Phase 1 seed data (002_seed_data.sql) is required.

Same approach as Phases 10-12: no HTTP endpoint exists yet for this
service (wired in Phase 14/LangGraph), so these tests call
`app.services.evidence_retrieval.retrieve_evidence` directly against an
`AsyncSessionLocal` session. Patient/medication/schedule/dose/symptom/
condition fixtures are created through the existing, already-tested API
endpoints via `TestClient`, which also exercises Phase 7's automatic
timeline logging -- the exact events these tests assert `retrieve_evidence`
picks up (or correctly excludes).

Seed data relied on (002_seed_data.sql):
  - Warfarin + Aspirin interaction -> severe, with a seeded mechanism,
    recommendation, and source.
  - Warfarin ADR: Bleeding / bruising -> severe, common, FDA Label.

No dedicated cleanup fixture is needed beyond the existing
`created_patient_ids`/`created_condition_ids`/`created_symptom_ids`
(from conftest.py) -- this service performs no writes of its own.

Run with:  pytest backend/tests/test_evidence_retrieval.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs/interaction_rules/adr_rules from
           002_seed_data.sql.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.analysis.safety_score_engine import calculate_safety_score
from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.evidence_retrieval import EvidenceBundle, retrieve_evidence

client = TestClient(app)


def _override_current_user(user_id):
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")

    return _fake_current_user


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _create_patient(name: str = "Evidence Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_condition(patient_id: str, name: str = "Atrial Fibrillation", **kwargs) -> dict:
    resp = client.post(f"/api/v1/patients/{patient_id}/conditions", json={"name": name, **kwargs})
    assert resp.status_code == 201
    return resp.json()


def _create_active_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    payload = {"drug_id": drug_id, "start_date": str(date.today()), "status": "active", **kwargs}
    resp = client.post(f"/api/v1/patients/{patient_id}/medications", json=payload)
    assert resp.status_code == 201
    return resp.json()


def _create_symptom(patient_id: str, medication_id: str, description: str) -> dict:
    resp = client.post(
        f"/api/v1/patients/{patient_id}/symptoms",
        json={"description": description, "medication_id": medication_id},
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


async def _drug_id_by_name(name: str) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug.id).where(ReferenceDrug.name == name))
        return result.scalar_one()


# ---------------------------------------------------------------------
# retrieve_evidence -- empty case
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_findings_yields_empty_bundle(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Clean Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    assert isinstance(bundle, EvidenceBundle)
    assert bundle.interaction_evidence == []
    assert bundle.adr_evidence == []
    assert bundle.adherence_evidence == []


# ---------------------------------------------------------------------
# Medical evidence -- structured from existing finding fields
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interaction_medical_evidence_includes_mechanism_and_recommendation(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Interaction Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    assert len(bundle.interaction_evidence) == 1
    finding_evidence = bundle.interaction_evidence[0]
    assert finding_evidence.category == "drug_interaction"
    assert finding_evidence.finding in score_result.interaction_findings

    statements = {item.statement for item in finding_evidence.medical_evidence}
    assert len(finding_evidence.medical_evidence) == 2
    assert all(item.source == "FDA Label" for item in finding_evidence.medical_evidence)
    assert all(item.kind == "medical" for item in finding_evidence.medical_evidence)
    assert all(item.occurred_at is None for item in finding_evidence.medical_evidence)
    assert len(statements) == 2


@pytest.mark.asyncio
async def test_adr_medical_evidence_includes_reaction_and_frequency(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("ADR Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    _create_active_medication(patient["id"], str(warfarin_id))

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    assert len(bundle.adr_evidence) == 1
    finding_evidence = bundle.adr_evidence[0]
    assert finding_evidence.category == "adr"
    assert len(finding_evidence.medical_evidence) == 1
    item = finding_evidence.medical_evidence[0]
    assert "Bleeding / bruising" in item.statement
    assert "common" in item.statement
    assert item.source == "FDA Label"


@pytest.mark.asyncio
async def test_adherence_finding_has_no_medical_evidence(
    existing_auth_user_id, existing_drug_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Adherence No Medical Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    past_start = date.today() - timedelta(days=2)
    medication = _create_active_medication(
        patient["id"], str(existing_drug_id), start_date=str(past_start),
        times_per_day=2, duration_days=1,
    )
    _generate_schedule(medication["id"])

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    assert len(bundle.adherence_evidence) == 1
    assert bundle.adherence_evidence[0].category == "adherence"
    assert bundle.adherence_evidence[0].medical_evidence == []


# ---------------------------------------------------------------------
# Personal evidence -- scoped timeline retrieval
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personal_evidence_includes_medication_started_event(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Medication Started Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    finding_evidence = bundle.interaction_evidence[0]
    personal_statements = " ".join(item.statement for item in finding_evidence.personal_evidence)
    assert "Started" in personal_statements
    assert all(item.kind == "personal" for item in finding_evidence.personal_evidence)
    assert all(item.occurred_at is not None for item in finding_evidence.personal_evidence)


@pytest.mark.asyncio
async def test_personal_evidence_includes_dose_events(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Dose Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    medication = _create_active_medication(
        patient["id"], str(warfarin_id), start_date=str(date.today() + timedelta(days=1)),
        times_per_day=1, duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    _mark_dose(doses[0]["id"], "taken")

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    finding_evidence = bundle.adr_evidence[0]
    personal_statements = " ".join(item.statement for item in finding_evidence.personal_evidence)
    assert "Took" in personal_statements or "dose" in personal_statements.lower()


@pytest.mark.asyncio
async def test_personal_evidence_includes_linked_symptom(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Symptom Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    medication = _create_active_medication(patient["id"], str(warfarin_id))
    _create_symptom(patient["id"], medication["id"], "Unusual bruising on arms")

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    finding_evidence = bundle.adr_evidence[0]
    personal_statements = " ".join(item.statement for item in finding_evidence.personal_evidence)
    assert "bruising" in personal_statements.lower()


@pytest.mark.asyncio
async def test_personal_evidence_includes_linked_condition_status_change(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Condition Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    condition = _create_condition(patient["id"], "Atrial Fibrillation", status="active")

    warfarin_id = await _drug_id_by_name("Warfarin")
    medication = _create_active_medication(
        patient["id"], str(warfarin_id), condition_id=condition["id"]
    )

    client.put(f"/api/v1/conditions/{condition['id']}", json={"status": "improving"})

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    finding_evidence = bundle.adr_evidence[0]
    personal_statements = " ".join(item.statement for item in finding_evidence.personal_evidence)
    assert "improving" in personal_statements.lower()


@pytest.mark.asyncio
async def test_personal_evidence_excludes_unrelated_medication_events(
    existing_auth_user_id, created_patient_ids
):
    """
    A third, unrelated active medication's events must not leak into the
    Warfarin+Aspirin interaction finding's personal evidence -- confirms
    scoping is per-finding, not per-patient.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Scoping Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    metformin_id = await _drug_id_by_name("Metformin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))
    _create_active_medication(patient["id"], str(metformin_id))

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    interaction_evidence = bundle.interaction_evidence[0]
    personal_statements = " ".join(item.statement for item in interaction_evidence.personal_evidence)
    assert "Metformin" not in personal_statements


@pytest.mark.asyncio
async def test_personal_evidence_scoped_to_active_medication_for_adherence_finding(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Adherence Personal Evidence Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    medication = _create_active_medication(
        patient["id"],
        str(await _drug_id_by_name("Levothyroxine")),
        start_date=str(date.today() + timedelta(days=1)),
        times_per_day=1,
        duration_days=1,
    )
    doses = _generate_schedule(medication["id"])
    _mark_dose(doses[0]["id"], "missed")

    async with AsyncSessionLocal() as session:
        score_result = await calculate_safety_score(uuid.UUID(patient["id"]), session)
        bundle = await retrieve_evidence(uuid.UUID(patient["id"]), session, score_result)

    finding_evidence = bundle.adherence_evidence[0]
    assert finding_evidence.finding.medication_id == uuid.UUID(medication["id"])
    personal_statements = " ".join(item.statement for item in finding_evidence.personal_evidence)
    assert "Missed" in personal_statements or "Started" in personal_statements
