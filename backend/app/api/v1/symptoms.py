"""
Symptom endpoints (spec section 7):

    POST   /patients/{id}/symptoms
    GET    /patients/{id}/symptoms

No PUT or DELETE routes -- the frozen spec (section 7) lists only these
two routes for symptoms, mirroring how conditions.py (Phase 5) implements
strictly what the spec declares rather than adding extra CRUD surface.

Ownership: every symptom is scoped through its parent patient's user_id,
mirroring conditions.py/medications.py -- a symptom or patient not owned
by the caller (or not existing) returns 404, never 403 (existence is
never confirmed to a non-owner). The ownership helpers here are kept
local rather than imported from sibling modules, since those modules'
helpers are private to their own files (same rationale documented in
conditions.py and medications.py).

condition_id / medication_id validation: if provided, each must reference
a row that exists and belongs to the same patient the symptom is being
logged for. This is the same data-integrity guard pattern used for
medications.condition_id in Phase 4 -- a mismatch is a 400, not a 404,
since the id is well-formed and exists, just not applicable to this
patient.
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
    """List all symptoms for a patient owned by the authenticated user.

    Ordered chronologically by onset_date (then created_at as a tiebreaker
    for same-day entries), since a symptom log is most useful read in the
    order things happened.
    """
    await _assert_patient_owned(patient_id, current_user, db)

    result = await db.execute(
        select(Symptom)
        .where(Symptom.patient_id == patient_id)
        .order_by(Symptom.onset_date, Symptom.created_at)
    )
    return list(result.scalars().all())
