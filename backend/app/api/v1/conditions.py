"""
Condition endpoints (spec section 7):

    POST   /patients/{id}/conditions
    PUT    /conditions/{id}

No GET or DELETE routes -- confirmed with the project owner during Phase 5
planning that the frozen spec (section 7) lists only these two routes for
conditions, and that this is implemented strictly as written rather than
adding a GET endpoint (unlike medications, which has full CRUD minus
delete). If a GET route is wanted later, that is a deliberate addition to
request explicitly, not something to add here.

Ownership: every condition is scoped through its parent patient's
user_id, mirroring medications.py -- a condition or patient not owned by
the caller (or not existing) returns 404, never 403 (existence is never
confirmed to a non-owner). The ownership helpers here are kept local
rather than imported from patients.py/medications.py, since those
modules' helpers are private to their own files.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Condition, Patient
from app.db.session import get_db
from app.schemas.condition import ConditionCreate, ConditionResponse, ConditionUpdate

router = APIRouter(tags=["conditions"])
logger = logging.getLogger("app.conditions")


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


async def _get_owned_condition(
    condition_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> Condition:
    """Fetch a condition by id, scoped to the current user via its parent
    patient, or raise 404."""
    result = await db.execute(
        select(Condition)
        .join(Patient, Patient.id == Condition.patient_id)
        .where(Condition.id == condition_id, Patient.user_id == current_user.id)
    )
    condition = result.scalar_one_or_none()
    if condition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Condition not found.",
        )
    return condition


@router.post(
    "/patients/{patient_id}/conditions",
    response_model=ConditionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_condition(
    patient_id: uuid.UUID,
    payload: ConditionCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Condition:
    """Create a new condition for a patient owned by the caller."""
    await _assert_patient_owned(patient_id, current_user, db)

    now = datetime.now(timezone.utc)
    condition = Condition(
        id=uuid.uuid4(),
        patient_id=patient_id,
        name=payload.name,
        status=payload.status,
        reason=payload.reason,
        diagnosed_date=payload.diagnosed_date,
        resolved_date=payload.resolved_date,
        notes=payload.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(condition)
    await db.commit()
    await db.refresh(condition)

    logger.info(
        "Condition created",
        extra={
            "condition_id": condition.id,
            "patient_id": patient_id,
            "user_id": current_user.id,
        },
    )
    return condition


@router.put("/conditions/{condition_id}", response_model=ConditionResponse)
async def update_condition(
    condition_id: uuid.UUID,
    payload: ConditionUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Condition:
    """
    Update a condition.

    PUT semantics note: partial update only (fields present in the request
    body are changed via exclude_unset=True), matching the precedent set
    in patients.py's and medications.py's PUT endpoints -- the frozen spec
    (section 7) declares the route but not full-replace-vs-partial
    semantics.

    No status-transition validation is applied: the spec does not define
    a condition lifecycle state machine, so `status` may be set to any of
    the five enum values regardless of its current value. Likewise,
    setting status to "resolved" does not auto-populate resolved_date --
    that remains an explicit client-supplied field.
    """
    condition = await _get_owned_condition(condition_id, current_user, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(condition, field, value)
    condition.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(condition)

    logger.info(
        "Condition updated",
        extra={"condition_id": condition.id, "user_id": current_user.id},
    )
    return condition
