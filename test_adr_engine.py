"""
Phase 11 ADR engine tests.

Integration tests against a live Supabase Postgres instance (same
requirement as Phase 1's test_database.py and all prior phase test
modules) -- `detect_adrs` queries `medications` and `adr_rules` directly,
so a real DB with the Phase 1 seed data (002_seed_data.sql) is required.

Same pattern as Phase 10's test_drug_interaction_engine.py: there is no
HTTP endpoint to exercise yet (the engine is not wired into any route
until Phase 14/LangGraph) -- these tests call
`app.analysis.adr_engine` functions directly against an
`AsyncSessionLocal` session. Patient/medication fixtures are still
created through the existing, already-tested API endpoints via
`TestClient` (simplest way to get valid, owned rows), then the engine is
exercised directly with an async DB session.

Seed data relied on (002_seed_data.sql):
  - Warfarin       -> 1 ADR rule:  Bleeding / bruising (severe, common)
  - Lisinopril      -> 2 ADR rules: Dry cough (mild, common),
                                     Hyperkalemia (moderate, uncommon)
  - Simvastatin     -> 2 ADR rules: Myopathy / muscle pain (moderate,
                                     uncommon), Rhabdomyolysis (severe, rare)
  - Metformin        -> 2 ADR rules: GI upset / diarrhea (mild, common),
                                      Lactic acidosis (severe, rare)
  - Levothyroxine, Omeprazole -> no seeded ADR rules -- used as "no
    findings" negative controls.

No dedicated cleanup fixture is needed beyond the existing
`created_patient_ids` (from conftest.py) -- medications cascade away via
`ON DELETE CASCADE` when the patient is deleted, and this engine performs
no writes of its own.

Run with:  pytest backend/tests/test_adr_engine.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs/adr_rules from 002_seed_data.sql.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.analysis.adr_engine import ADRFinding, detect_adrs, highest_severity
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


def _create_patient(name: str = "ADR Test Patient") -> dict:
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
# detect_adrs
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_active_medications_returns_empty(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No Medications ADR Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_single_drug_single_adr_rule(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Warfarin ADR Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    _create_active_medication(patient["id"], str(warfarin_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, ADRFinding)
    assert finding.drug_name == "Warfarin"
    assert finding.reaction_description == "Bleeding / bruising"
    assert finding.severity == "severe"
    assert finding.frequency_class == "common"
    assert finding.source == "FDA Label"


@pytest.mark.asyncio
async def test_single_drug_with_multiple_adr_rules_returns_all(
    existing_auth_user_id, created_patient_ids
):
    """
    Lisinopril has two seeded ADR rules (Dry cough, Hyperkalemia) -- both
    must be returned as separate findings for a single active medication,
    unlike drug interactions which need a pair of drugs.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Lisinopril ADR Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    lisinopril_id = await _drug_id_by_name("Lisinopril")
    _create_active_medication(patient["id"], str(lisinopril_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    assert len(findings) == 2
    reactions = {f.reaction_description for f in findings}
    assert reactions == {"Dry cough", "Hyperkalemia"}
    assert all(f.drug_name == "Lisinopril" for f in findings)


@pytest.mark.asyncio
async def test_drug_with_no_adr_rules_returns_empty(
    existing_auth_user_id, created_patient_ids
):
    """Levothyroxine has no seeded adr_rules row."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("No ADR Rules Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    levothyroxine_id = await _drug_id_by_name("Levothyroxine")
    _create_active_medication(patient["id"], str(levothyroxine_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_excludes_non_active_medications(
    existing_auth_user_id, created_patient_ids
):
    """
    A discontinued medication must not be considered "the patient's
    drugs" for ADR detection, mirroring Phase 10's same scope decision --
    only status == "active" medications count.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Discontinued Excluded ADR Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    discontinued_warfarin = _create_active_medication(patient["id"], str(warfarin_id))

    client.put(
        f"/api/v1/medications/{discontinued_warfarin['id']}",
        json={"status": "discontinued"},
    )

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    assert findings == []


@pytest.mark.asyncio
async def test_multiple_active_drugs_combine_all_findings(
    existing_auth_user_id, created_patient_ids
):
    """
    Warfarin (1 ADR rule) + Simvastatin (2 ADR rules) active together
    should surface all 3 findings combined.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Multiple ADRs Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    simvastatin_id = await _drug_id_by_name("Simvastatin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(simvastatin_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    assert len(findings) == 3
    reactions = {f.reaction_description for f in findings}
    assert reactions == {"Bleeding / bruising", "Myopathy / muscle pain", "Rhabdomyolysis"}


@pytest.mark.asyncio
async def test_adrs_scoped_to_patient(
    existing_auth_user_id, created_patient_ids
):
    """A different patient's active drugs must not leak into this patient's findings."""
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient_a = _create_patient("ADR Scoped Patient A")
    created_patient_ids.append(uuid.UUID(patient_a["id"]))
    patient_b = _create_patient("ADR Scoped Patient B")
    created_patient_ids.append(uuid.UUID(patient_b["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    metformin_id = await _drug_id_by_name("Metformin")

    # Patient A gets only Warfarin; Patient B gets Warfarin + Metformin.
    _create_active_medication(patient_a["id"], str(warfarin_id))
    _create_active_medication(patient_b["id"], str(warfarin_id))
    _create_active_medication(patient_b["id"], str(metformin_id))

    async with AsyncSessionLocal() as session:
        findings_a = await detect_adrs(uuid.UUID(patient_a["id"]), session)
        findings_b = await detect_adrs(uuid.UUID(patient_b["id"]), session)

    assert len(findings_a) == 1
    assert len(findings_b) == 3  # 1 (Warfarin) + 2 (Metformin)


# ---------------------------------------------------------------------
# highest_severity
# ---------------------------------------------------------------------


def _make_finding(severity: str) -> ADRFinding:
    return ADRFinding(
        adr_rule_id=uuid.uuid4(),
        drug_id=uuid.uuid4(),
        drug_name="Drug A",
        reaction_description="Some reaction",
        severity=severity,
        frequency_class=None,
        source=None,
    )


def test_highest_severity_empty_list_returns_none():
    assert highest_severity([]) is None


def test_highest_severity_single_finding():
    assert highest_severity([_make_finding("mild")]) == "mild"


def test_highest_severity_picks_most_severe_regardless_of_order():
    findings = [_make_finding("moderate"), _make_finding("severe"), _make_finding("mild")]
    assert highest_severity(findings) == "severe"


def test_highest_severity_all_same_severity():
    findings = [_make_finding("moderate"), _make_finding("moderate")]
    assert highest_severity(findings) == "moderate"
