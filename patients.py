"""
Patient endpoints (spec section 7):

    GET    /patients
    POST   /patients
    GET    /patients/{id}
    PUT    /patients/{id}

No DELETE /patients/{id} -- not part of the frozen API contract (confirmed
with the project owner during Phase 3 planning; PROJECT_PHASES.md's
"Delete Patient" subtask is treated as informational only).

Ownership: patients.user_id is always taken from the verified JWT, never
from the request body. Every lookup filters by (id, user_id) together, so
a patient owned by another user returns 404 rather than 403 -- this avoids
confirming to a caller that a given patient id exists at all.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Patient
from app.db.session import get_db
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])
logger = logging.getLogger("app.patients")


async def _get_owned_patient(
    patient_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> Patient:
    """Fetch a patient by id, scoped to the current user, or raise 404."""
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.user_id == current_user.id)
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found.",
        )
    return patient


@router.get("", response_model=list[PatientResponse])
async def list_patients(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Patient]:
    """List all patients belonging to the authenticated user."""
    result = await db.execute(
        select(Patient).where(Patient.user_id == current_user.id).order_by(Patient.created_at)
    )
    return list(result.scalars().all())


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    """Create a new patient owned by the authenticated user."""
    now = datetime.now(timezone.utc)
    patient = Patient(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=payload.name,
        age=payload.age,
        sex=payload.sex,
        weight_kg=payload.weight_kg,
        renal_flag=payload.renal_flag,
        hepatic_flag=payload.hepatic_flag,
        created_at=now,
        updated_at=now,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    logger.info(
        "Patient created",
        extra={"patient_id": patient.id, "user_id": current_user.id},
    )
    return patient


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    """Fetch a single patient by id (must be owned by the caller)."""
    return await _get_owned_patient(patient_id, current_user, db)


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    """
    Update a patient.

    PUT semantics note: the frozen spec (section 7) declares `PUT
    /patients/{id}` but does not define full-replacement vs. partial-update
    semantics. This implementation is intentionally partial -- only fields
    present in the request body are changed (via `exclude_unset=True`),
    everything else is left as-is. This was a deliberate choice, not an
    oversight: a strict full-replace PUT would force clients to resend the
    entire patient record on every edit (including fields like renal_flag/
    hepatic_flag that are rarely touched), which is unnecessary friction
    for a medical record the frontend edits field-by-field. If stricter
    full-replace semantics are ever required, that's a spec change to
    request explicitly, not something to guess at here.
    """
    patient = await _get_owned_patient(patient_id, current_user, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(patient, field, value)
    patient.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(patient)

    logger.info(
        "Patient updated",
        extra={"patient_id": patient.id, "user_id": current_user.id},
    )
    return patient
