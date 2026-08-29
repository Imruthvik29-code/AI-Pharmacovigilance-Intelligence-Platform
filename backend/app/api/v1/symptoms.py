"""
Symptom endpoints (spec section 7):

    POST   /patients/{id}/symptoms
    GET    /patients/{id}/symptoms

Symptoms are intentionally immutable through the API. PUT/DELETE item
routes therefore exist only as explicit method guards and return 405 rather
than the less informative 404 that FastAPI otherwise returns for an entirely
unregistered path.

Ownership: every symptom is scoped through its parent patient's user_id,
mirroring conditions.py/medications.py -- a symptom or patient not owned by
the caller (or not existing) returns 404, never 403.

condition_id / medication_id validation: if provided, each must reference a
row that exists and belongs to the same patient the symptom is being logged
for. A mismatch is a 400 because the id is well-formed and exists, but is not
applicable to this patient.

Phase 7 addition: every created symptom logs a `symptom_reported` timeline
event via app/services/timeline_writer.py, added to the same DB
session/transaction as the symptom insert itself.
"""
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Condition, Medication, Patient, Symptom
from app.db.session import get_db
from app.schemas.symptom import SymptomCreate, SymptomResponse
from app.services.timeline_writer import log_timeline_event

router = APIRouter(tags=["symptoms"])
logger = logging.getLogger("app.symptoms")


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


async def _assert_condition_belongs_to_patient(
    condition_id: uuid.UUID, patient_id: uuid.UUID, db: AsyncSession
) -> None:
    result = await db.execute(
        select(Condition.id).where(
            Condition.id == condition_id, Condition.patient_id == patient_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="condition_id does not reference a condition owned by this patient.",
        )


async def _assert_medication_belongs_to_patient(
    medication_id: uuid.UUID, patient_id: uuid.UUID, db: AsyncSession
) -> None:
    result = await db.execute(
        select(Medication.id).where(
            Medication.id == medication_id, Medication.patient_id == patient_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="medication_id does not reference a medication owned by this patient.",
        )


@router.post(
    "/patients/{patient_id}/symptoms",
    response_model=SymptomResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_symptom(
    patient_id: uuid.UUID,
    payload: SymptomCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Symptom:
    """Log a new symptom for a patient owned by the caller."""
    await _assert_patient_owned(patient_id, current_user, db)

    if payload.condition_id is not None:
        await _assert_condition_belongs_to_patient(payload.condition_id, patient_id, db)

    if payload.medication_id is not None:
        await _assert_medication_belongs_to_patient(payload.medication_id, patient_id, db)

    now = datetime.now(timezone.utc)
    symptom = Symptom(
        id=uuid.uuid4(),
        patient_id=patient_id,
        condition_id=payload.condition_id,
        medication_id=payload.medication_id,
        description=payload.description,
        severity=payload.severity,
        onset_date=payload.onset_date or date.today(),
        resolved_date=payload.resolved_date,
        created_at=now,
        updated_at=now,
    )
    db.add(symptom)

    await log_timeline_event(
        db,
        patient_id=patient_id,
        event_type="symptom_reported",
        ref_id=symptom.id,
        event_title=f"Symptom reported: {payload.description[:80]}",
        payload={
            "severity": payload.severity,
            "condition_id": str(payload.condition_id) if payload.condition_id else None,
            "medication_id": str(payload.medication_id) if payload.medication_id else None,
        },
    )

    await db.commit()
    await db.refresh(symptom)

    logger.info(
        "Symptom created",
        extra={
            "symptom_id": symptom.id,
            "patient_id": patient_id,
            "user_id": current_user.id,
        },
    )
    return symptom


@router.get("/patients/{patient_id}/symptoms", response_model=list[SymptomResponse])
async def list_symptoms(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Symptom]:
    """List all symptoms for a patient owned by the authenticated user."""
    await _assert_patient_owned(patient_id, current_user, db)

    result = await db.execute(
        select(Symptom)
        .where(Symptom.patient_id == patient_id)
        .order_by(Symptom.onset_date, Symptom.created_at)
    )
    return list(result.scalars().all())


@router.put("/symptoms/{symptom_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def update_symptom_not_allowed(symptom_id: uuid.UUID):
    """Symptoms are immutable; updates are intentionally unsupported."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Symptoms cannot be updated.",
        headers={"Allow": "GET"},
    )


@router.delete("/symptoms/{symptom_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def delete_symptom_not_allowed(symptom_id: uuid.UUID):
    """Symptoms are retained as an audit record and cannot be deleted."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Symptoms cannot be deleted.",
        headers={"Allow": "GET"},
    )
