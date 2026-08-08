"""
Phase 14 analysis API tests.

Integration tests against a live Supabase Postgres instance (same
requirement as all prior phase API test modules). Authentication is
bypassed via a FastAPI dependency override on `get_current_user`, same
as prior phases.

Per the confirmed frozen-spec scope for Phase 14, the full API contract
(spec section 7) is implemented:

    POST /patients/{id}/analyze
    GET  /patients/{id}/analysis

`GET /patients/{id}/analysis` returns the full history, most recent
first (confirmed with the project owner during Phase 14 planning).

Phase 15 addition: `test_analyze_populates_llm_fields_when_provider_succeeds`
mocks `app.services.langgraph_workflow.generate_explanation` so the HTTP
layer's handling of real (non-null) llm_* fields is covered end-to-end,
without a real network call to Gemini/OpenRouter. All other tests in this
file are unchanged from Phase 14 -- they continue to pass unmodified
because, with no GEMINI_API_KEY/OPENROUTER_API_KEY configured in the test
environment, both providers fail closed on missing configuration and the
analysis run persists with NULL llm_* fields exactly as before.

Run with:  pytest backend/tests/test_analysis_api.py -v
Requires:  at least one row in auth.users (see conftest.py).
"""
import uuid

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


def _create_patient(name: str = "Analysis API Test Patient") -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def test_analyze_creates_persisted_run(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Analyze Endpoint Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    resp = client.post(f"/api/v1/patients/{patient['id']}/analyze")
    assert resp.status_code == 201
    body = resp.json()

    assert body["patient_id"] == patient["id"]
    assert body["analysis_version"] == "v1.0"
    assert body["safety_score"] == 100
    assert body["risk_level"] == "low"
    assert body["deterministic_result"] is not None
    # LLM fields null -- no GEMINI_API_KEY/OPENROUTER_API_KEY configured
    # in the test environment, so both providers fail closed.
    assert body["llm_summary"] is None
    assert body["llm_reasoning"] is None
    assert body["llm_recommendations"] is None
    assert body["confidence_score"] is None
    assert body["confidence_level"] is None


def test_analyze_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.post(f"/api/v1/patients/{uuid.uuid4()}/analyze")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_analyze_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A Analyze Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.post(f"/api/v1/patients/{patient['id']}/analyze")
    assert resp.status_code == 404


def test_list_analysis_runs_ordered_most_recent_first(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("List Analysis Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    first = client.post(f"/api/v1/patients/{patient['id']}/analyze")
    assert first.status_code == 201
    second = client.post(f"/api/v1/patients/{patient['id']}/analyze")
    assert second.status_code == 201

    resp = client.get(f"/api/v1/patients/{patient['id']}/analysis")
    assert resp.status_code == 200
    runs = resp.json()

    assert len(runs) == 2
    assert runs[0]["id"] == second.json()["id"]  # most recent first
    assert runs[1]["id"] == first.json()["id"]


def test_list_analysis_runs_for_nonexistent_patient_returns_404(existing_auth_user_id):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/analysis")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found."


def test_list_analysis_runs_for_patient_owned_by_another_user_returns_404(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    patient = _create_patient("Owned By A List Analysis Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)

    resp = client.get(f"/api/v1/patients/{patient['id']}/analysis")
    assert resp.status_code == 404


def test_list_analysis_runs_empty_for_patient_never_analyzed(
    existing_auth_user_id, created_patient_ids
):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("Never Analyzed Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    resp = client.get(f"/api/v1/patients/{patient['id']}/analysis")
    assert resp.status_code == 200
    assert resp.json() == []


def test_analyze_populates_llm_fields_when_provider_succeeds(
    existing_auth_user_id, created_patient_ids, monkeypatch
):
    """
    Phase 15 API-level coverage: with the LLM provider layer mocked to
    succeed, POST /patients/{id}/analyze must persist and return real
    llm_* fields, not NULLs -- confirms the mocking approach already
    used at the workflow level (test_langgraph_workflow.py) also holds
    end-to-end through the HTTP layer.
    """
    import app.services.langgraph_workflow as workflow_module
    from app.services.llm_service import LLMExplanationResult

    fake_result = LLMExplanationResult(
        summary="API-level fake summary.",
        reasoning="API-level fake reasoning.",
        recommendations="API-level fake recommendations.",
        confidence_score=77,
        confidence_level="moderate",
    )

    async def _fake_generate_explanation(**kwargs):
        return fake_result

    monkeypatch.setattr(workflow_module, "generate_explanation", _fake_generate_explanation)
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)

    patient = _create_patient("LLM Success API Patient")
    created_patient_ids.append(uuid.UUID(patient["id"]))

    resp = client.post(f"/api/v1/patients/{patient['id']}/analyze")
    assert resp.status_code == 201
    body = resp.json()

    assert body["llm_summary"] == "API-level fake summary."
    assert body["llm_reasoning"] == "API-level fake reasoning."
    assert body["llm_recommendations"] == "API-level fake recommendations."
    assert body["confidence_score"] == 77
    assert body["confidence_level"] == "moderate"
