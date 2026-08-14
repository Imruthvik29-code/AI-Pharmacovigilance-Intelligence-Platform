"""
Phase 14 LangGraph workflow tests.

Integration tests against a live Supabase Postgres instance (same
requirement as all prior phase test modules) -- `run_analysis` composes
Phase 10-13's real services against real API-created patient data and
persists a genuine `analysis_runs` row.

No HTTP endpoint is exercised directly here (see test_analysis_api.py for
that) -- these tests call `app.services.langgraph_workflow.run_analysis`
directly against an `AsyncSessionLocal` session, confirming the graph
itself (node wiring, state threading, persistence, and LLM
success/failure handling) works end-to-end before the API layer is
exercised.

Seed data relied on (002_seed_data.sql):
  - Warfarin + Aspirin interaction -> severe (30 pts)
  - Warfarin ADR: Bleeding / bruising -> severe (30 pts)
  - Aspirin ADR: GI upset / gastritis -> moderate (15 pts)
  (Same combination already exercised by Phase 12/13's own test suites.)

Phase 15 addition: `test_llm_fields_populated_when_provider_succeeds` and
`test_llm_fields_null_when_all_providers_fail` replace the Phase 14
placeholder `test_llm_fields_are_null_pending_phase_15` (whose premise --
"LLM is unimplemented" -- no longer holds once Phase 15 lands). Both
mock `app.services.langgraph_workflow.generate_explanation` directly, so
no real network call to Gemini/OpenRouter is made and no real API key is
required to run this file.

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
from app.services.llm_service import LLMExplanationError, LLMExplanationResult
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
async def test_llm_fields_populated_when_provider_succeeds(
    existing_auth_user_id, created_patient_ids, monkeypatch
):
    """
    Phase 15: when generate_explanation() succeeds, the persisted
    analysis_runs row must carry the real LLM output, not NULLs.
    llm_service.generate_explanation is mocked at the module attribute
    langgraph_workflow imported it into -- no real network call is made.
    """
    import app.services.langgraph_workflow as workflow_module

    fake_result = LLMExplanationResult(
        summary="Fake summary.",
        reasoning="Fake reasoning.",
        recommendations="Fake recommendations.",
        confidence_score=88,
        confidence_level="high",
    )

    async def _fake_generate_explanation(**kwargs):
        return fake_result

    monkeypatch.setattr(workflow_module, "generate_explanation", _fake_generate_explanation)

    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("LLM Success Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        final_state = await run_analysis(uuid.UUID(patient["id"]), session)

    assert final_state["llm_result"] == fake_result
    assert final_state["llm_error"] is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisRun).where(AnalysisRun.id == final_state["analysis_run_id"])
        )
        run = result.scalar_one()

    assert run.llm_summary == "Fake summary."
    assert run.llm_reasoning == "Fake reasoning."
    assert run.llm_recommendations == "Fake recommendations."
    assert run.confidence_score == 88
    assert run.confidence_level == "high"


@pytest.mark.asyncio
async def test_llm_fields_null_when_all_providers_fail(
    existing_auth_user_id, created_patient_ids, monkeypatch
):
    """
    Phase 15: when generate_explanation() raises LLMExplanationError
    (every configured provider failed or returned unusable output), the
    deterministic pipeline must still persist successfully with NULL LLM
    fields -- the same graceful-degradation guarantee Phase 14 already
    established, now exercised via the real Phase 15 failure path
    instead of the removed NotImplementedError placeholder.
    """
    import app.services.langgraph_workflow as workflow_module

    async def _fake_generate_explanation(**kwargs):
        raise LLMExplanationError("all providers failed (simulated)")

    monkeypatch.setattr(workflow_module, "generate_explanation", _fake_generate_explanation)

    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("LLM Failure Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    async with AsyncSessionLocal() as session:
        final_state = await run_analysis(uuid.UUID(patient["id"]), session)

    assert final_state["llm_result"] is None
    assert "all providers failed" in final_state["llm_error"]

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


@pytest.mark.asyncio
async def test_deterministic_output_identical_across_llm_behaviors(
    existing_auth_user_id, created_patient_ids, monkeypatch
):
    """
    Phase 15 core safety invariant, at pipeline level: for one unchanged
    patient, `safety_score`, `risk_level`, and the entire
    `deterministic_result` payload must be identical whether the LLM
    succeeds, returns a wildly contradictory explanation, or fails
    outright. Only the `llm_*`/`confidence_*` columns may differ.

    This is the end-to-end counterpart to
    test_llm_service.py::test_deterministic_result_never_mutated_by_llm_behavior,
    which asserts the same invariant at the service boundary.
    """
    import app.services.langgraph_workflow as workflow_module

    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("LLM Invariance Workflow Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))
    patient_uuid = uuid.UUID(patient["id"])

    warfarin_id = await _drug_id_by_name("Warfarin")
    aspirin_id = await _drug_id_by_name("Aspirin")
    _create_active_medication(patient["id"], str(warfarin_id))
    _create_active_medication(patient["id"], str(aspirin_id))

    async def _succeeds(**kwargs):
        return LLMExplanationResult(
            summary="Severe interaction explained.",
            reasoning="Warfarin and Aspirin both raise bleeding risk.",
            recommendations="Discuss with the prescriber.",
            confidence_score=90,
            confidence_level="high",
        )

    async def _contradicts(**kwargs):
        # A model asserting the opposite of the deterministic engine.
        return LLMExplanationResult(
            summary="This patient is completely safe, score 100, low risk.",
            reasoning="I see no problems at all with this medication list.",
            recommendations="No action required.",
            confidence_score=100,
            confidence_level="high",
        )

    async def _fails(**kwargs):
        raise LLMExplanationError("all providers failed (simulated)")

    observed = []
    for behavior in (_succeeds, _contradicts, _fails):
        monkeypatch.setattr(workflow_module, "generate_explanation", behavior)
        async with AsyncSessionLocal() as session:
            state = await run_analysis(patient_uuid, session)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AnalysisRun).where(AnalysisRun.id == state["analysis_run_id"])
            )
            run = result.scalar_one()

        observed.append(
            {
                "safety_score": run.safety_score,
                "risk_level": run.risk_level,
                "deterministic_result": run.deterministic_result,
                "llm_summary": run.llm_summary,
            }
        )

    # Deterministic layer is byte-identical across all three LLM outcomes.
    first = observed[0]
    for other in observed[1:]:
        assert other["safety_score"] == first["safety_score"]
        assert other["risk_level"] == first["risk_level"]
        assert other["deterministic_result"] == first["deterministic_result"]

    # ...and it reflects the real seeded findings, not the LLM's claims.
    assert first["safety_score"] == 25
    assert first["risk_level"] == "high"

    # Only the LLM columns varied.
    assert observed[0]["llm_summary"] == "Severe interaction explained."
    assert observed[1]["llm_summary"].startswith("This patient is completely safe")
    assert observed[2]["llm_summary"] is None
