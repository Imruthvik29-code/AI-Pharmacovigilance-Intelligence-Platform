"""
Analysis endpoints (spec section 7):

    POST /patients/{id}/analyze
    GET  /patients/{id}/analysis

Phase 14 wires these onto the full LangGraph workflow
(`app/services/langgraph_workflow.py`'s `run_analysis`), which composes
Phases 10-13's deterministic engines (via the Safety Score Engine), the
Timeline Engine, attempts the Phase 15 LLM explanation (Gemini primary,
OpenRouter fallback -- see `llm_service.py`), and persists a row to
`analysis_runs` regardless of whether the LLM step succeeded.

The LLM step is strictly additive: `safety_score`, `risk_level`, and
`deterministic_result` are computed by the deterministic engines alone
and are byte-identical whether the LLM succeeds, falls back, or fails
outright. When every provider fails, the run still persists with the
`llm_*`/`confidence_*` columns left NULL.

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
    Run the full deterministic analysis pipeline (+ attempted LLM
    explanation) for a patient owned by the caller, and persist the
    result as a new `analysis_runs` row.

    The LLM explanation step is expected to be unavailable until Phase
    15 -- this does not fail the request; the persisted row's
    `llm_summary`/`llm_reasoning`/`llm_recommendations`/
    `confidence_score`/`confidence_level` are simply null in that case.
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
