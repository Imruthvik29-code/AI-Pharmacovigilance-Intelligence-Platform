"""
Phase 14 LangGraph workflow tests.

Integration tests against a live Supabase Postgres instance (same
requirement as all prior phase test modules) -- `run_analysis` composes
Phase 10-13's real services against real API-created patient data and
persists a genuine `analysis_runs` row.

No HTTP endpoint is exercised directly here (see test_analysis_api.py for
that) -- these tests call `app.services.langgraph_workflow.run_analysis`
directly against an `AsyncSessionLocal` session, confirming the graph
itself (node wiring, state threading, persistence, and the documented
LLM-NotImplementedError handling) works end-to-end before the API layer
is exercised.

Seed data relied on (002_seed_data.sql):
  - Warfarin + Aspirin interaction -> severe (30 pts)
  - Warfarin ADR: Bleeding / bruising -> severe (30 pts)
  - Aspirin ADR: GI upset / gastritis -> moderate (15 pts)
  (Same combination already exercised by Phase 12/13's own test suites.)

Run with:  pytest backend/tests/test_langgraph_workflow.py -v
Requires:  at least one row in auth.users (see conftest.py) and the
           seeded reference_drugs/interaction_rules/adr_rules from
           002_seed_data.sql.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import CurrentUser, get_current_user
from app.db.models import AnalysisRun, ReferenceDrug
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.langgraph_workflow import run_analysis

client = TestClient(app)


def _override_current_user(user_id):
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")

    return _fake_current_user


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _create_patient(name: str = "Workflow Test Patient") -> dict:
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


def _get_timeline(patient_id: str) -> list[dict]:
    resp = client.get(f"/api/v1/patients/{patient_id}/timeline")
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_clean_patient_yields_perfect_score_run(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Clean Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        final_state = await run_analysis(uuid.UUID(patient["id"]), session)

    assert "analysis_run_id" in final_state
    assert final_state["safety_score_result"].safety_score == 100
    assert final_state["safety_score_result"].risk_level == "low"

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisRun).where(AnalysisRun.id == final_state["analysis_run_id"])
        )
        run = result.scalar_one()

    assert run.safety_score == 100
    assert run.risk_level == "low"
    assert run.analysis_version == "v1.0"


@pytest.mark.asyncio
async def test_llm_fields_are_null_pending_phase_15(
    existing_auth_user_id, created_patient_ids
):
    """
    The LLM Explanation Node must not fabricate output -- llm_service.py
    raises NotImplementedError, which the graph catches, leaving the
    LLM-generated columns NULL on the persisted row.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("LLM Pending Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        final_state = await run_analysis(uuid.UUID(patient["id"]), session)

    assert final_state["llm_result"] is None
    assert final_state["llm_error"] is not None
    assert "Phase 15" in final_state["llm_error"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisRun).where(AnalysisRun.id == final_state["analysis_run_id"])
        )
        run = result.scalar_one()

    assert run.llm_summary is None
    assert run.llm_reasoning is None
    assert run.llm_recommendations is None
    assert run.confidence_score is None
    assert run.confidence_level is None


@pytest.mark.asyncio
async def test_deterministic_result_contains_expected_findings_and_excludes_timeline(
    existing_auth_user_id, created_patient_ids
):
    """
    Warfarin + Aspirin -> 1 severe interaction + 2 ADRs, matching Phase
    12's own already-verified combined-findings scenario. Also confirms
    `deterministic_result` does NOT include a `timeline_context` key, per
    the confirmed Phase 14 persistence-scope decision.
    """
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Interaction Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async with AsyncSessionLocal() as session:
        final_state = await run_analysis(uuid.UUID(patient["id"]), session)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisRun).where(AnalysisRun.id == final_state["analysis_run_id"])
        )
        run = result.scalar_one()

    det = run.deterministic_result
    assert "timeline_context" not in det
    assert len(det["interaction_findings"]) == 1
    assert len(det["adr_findings"]) == 2
    assert det["total_points_deducted"] == 75
    assert det["safety_score"] == 25
    assert det["risk_level"] == "high"
    assert len(det["penalties"]) == 3
    # penalties are JSON-safe (no raw finding object reference persisted)
    for penalty in det["penalties"]:
        assert set(penalty.keys()) == {"category", "description", "severity", "points"}


@pytest.mark.asyncio
async def test_analysis_run_logs_timeline_event(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Timeline Event Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        final_state = await run_analysis(uuid.UUID(patient["id"]), session)

    events = _get_timeline(patient["id"])
    analysis_events = [e for e in events if e["event_type"] == "analysis_run"]
    assert len(analysis_events) == 1
    assert analysis_events[0]["ref_id"] == str(final_state["analysis_run_id"])
    assert analysis_events[0]["payload"]["safety_score"] == 100
    assert analysis_events[0]["payload"]["llm_explanation_available"] is False


@pytest.mark.asyncio
async def test_running_twice_creates_two_separate_versioned_runs(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Repeated Run Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        first_state = await run_analysis(uuid.UUID(patient["id"]), session)
    async with AsyncSessionLocal() as session:
        second_state = await run_analysis(uuid.UUID(patient["id"]), session)

    assert first_state["analysis_run_id"] != second_state["analysis_run_id"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisRun).where(AnalysisRun.patient_id == uuid.UUID(patient["id"]))
        )
        runs = result.scalars().all()

    assert len(runs) == 2
