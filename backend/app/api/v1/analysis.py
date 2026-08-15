"""
Analysis endpoints (spec section 7):

    POST /patients/{id}/analyze
    GET /patients/{id}/analysis

Phase 14 wires these onto the full LangGraph workflow
(`app/services/langgraph_workflow.py`'s `run_analysis`), which composes
Phases 10-13's deterministic engines (via the Safety Score Engine), the
Timeline Engine, Phase 15 LLM explanation (Gemini primary, OpenRouter
fallback, structured JSON explanation, fail-closed without hardcoded
secrets), and persists a row to `analysis_runs` regardless of whether
the LLM step succeeded (deterministic fields always present, LLM fields
nullable — explanation is additive).

Ownership: scoped through the parent patient, mirroring every other
patient-scoped resource in this codebase (`conditions.py`/
`medications.py`/`symptoms.py`/`timeline.py`/`schedule.py`) -- a patient
not owned by the caller (or not existing) returns 404, never 403.

`GET /patients/{id}/analysis` returns the full analysis history (spec
section 2: "Analysis report view ... versioned"), ordered
`created_at DESC` (most recent first) -- confirmed with the project
owner during Phase 14 planning.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import AnalysisRun, Patient
from app.db.session import get_db
from app.schemas.analysis import AnalysisRunResponse
from app.services.langgraph_workflow import run_analysis

router = APIRouter(tags=["analysis"])
logger = logging.getLogger("app.analysis")


async def _assert_patient_owned(
    patient_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> None:
    """Confirm the patient exists and is owned by the caller, or raise 404."""
    result = await db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.user_id == current_user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found.",
        )


@router.post(
    "/patients/{patient_id}/analyze",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisRun:
    """
    Run the full deterministic analysis pipeline (+ LLM explanation) for a
    patient owned by the caller, and persist the result as a new
    `analysis_runs` row.

    Phase 15 implemented: LLM explanation via Gemini primary / OpenRouter
    fallback with structured JSON output (summary, reasoning, recommendations,
    confidence_score, confidence_level). If every LLM provider fails or returns
    unusable output, the request does NOT fail — the persisted row's
    deterministic fields (safety_score, risk_level, deterministic_result)
    are always present, while llm_* fields are NULL and
    llm_explanation_available is False. Deterministic persistence always
    succeeds regardless of LLM outcome.
    """
    await _assert_patient_owned(patient_id, current_user, db)

    final_state = await run_analysis(patient_id, db)

    result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.id == final_state["analysis_run_id"])
    )
    analysis_run = result.scalar_one()

    logger.info(
        "Analysis run completed",
        extra={
            "analysis_run_id": analysis_run.id,
            "patient_id": patient_id,
            "user_id": current_user.id,
            "llm_explanation_available": final_state.get("llm_result") is not None,
        },
    )
    return analysis_run


@router.get("/patients/{patient_id}/analysis", response_model=list[AnalysisRunResponse])
async def list_analysis_runs(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisRun]:
    """List all analysis runs for a patient owned by the authenticated user, most recent first."""
    await _assert_patient_owned(patient_id, current_user, db)

    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.patient_id == patient_id)
        .order_by(AnalysisRun.created_at.desc())
    )
    return list(result.scalars().all())
