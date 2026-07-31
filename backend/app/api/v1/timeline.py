"""
Timeline endpoint (spec section 7):

    GET /patients/{id}/timeline

Read-only -- timeline events are never written directly through this
route. They are produced as a side effect of other endpoints (medication
creation, condition status changes, symptom logging, etc.) via
app/services/timeline_writer.py.

Ownership: scoped through the parent patient, mirroring
conditions.py/medications.py/symptoms.py -- a patient not owned by the
caller (or not existing) returns 404, never 403.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Patient, TimelineEvent
from app.db.session import get_db
from app.schemas.timeline import TimelineEventResponse

router = APIRouter(tags=["timeline"])


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


@router.get("/patients/{patient_id}/timeline", response_model=list[TimelineEventResponse])
async def get_timeline(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TimelineEvent]:
    """List all timeline events for a patient owned by the authenticated user.

    Ordered most-recent-first (event_time DESC), matching the existing
    idx_timeline_patient(patient_id, event_time desc) index from
    001_initial_schema.sql.
    """
    await _assert_patient_owned(patient_id, current_user, db)

    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.patient_id == patient_id)
        .order_by(TimelineEvent.event_time.desc())
    )
    return list(result.scalars().all())
