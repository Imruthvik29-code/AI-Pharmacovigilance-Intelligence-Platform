"""
Medication endpoints (spec section 7):

    GET    /patients/{id}/medications
    POST   /patients/{id}/medications
    PUT    /medications/{id}
    DELETE /medications/{id}

Ownership: every medication is scoped through its parent patient's
user_id. A patient not owned by the caller (or not existing) returns 404
from the /patients/{id}/medications routes. A medication not owned by the
caller (or not existing) returns 404 from the /medications/{id} routes --
this mirrors patients.py's approach of never confirming resource
existence to a non-owner via a 403. The ownership helpers here are kept
local rather than imported from patients.py, since that module's helper
is private (underscore-prefixed) to its own file.

condition_id validation: if provided, the referenced condition must exist
and belong to the same patient. This is a data-integrity guard consistent
with the spec ("linked to a condition or free-text purpose"), not a new
business rule -- Condition CRUD itself lands in Phase 5, so this issues a
direct SELECT against the conditions table rather than calling into
unbuilt Phase 5 code.

drug_id validation: must reference an existing reference_drugs row,
otherwise 404 -- the curated drug list (spec section 3/10) is meant to be
selected from GET-able reference data, not free-typed.

Phase 7 addition: medication creation logs a `medication_started` timeline
event, and updating a medication's status to `discontinued` (from any
other status) logs a `medication_discontinued` event -- both via
app/services/timeline_writer.py, added to the same DB session/transaction
as the medication write itself so the two are always persisted together.
Hard `DELETE` does not log an event -- the spec's event_type list (section
5) has no "medication deleted" value, only "medication_discontinued"
(a status transition), so deletion is intentionally left unlogged rather
than inventing a new event type.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Condition, Medication, Patient, ReferenceDrug
from app.db.session import get_db
from app.schemas.medication import MedicationCreate, MedicationResponse, MedicationUpdate
from app.services.timeline_writer import log_timeline_event

router = APIRouter(tags=["medications"])
logger = logging.getLogger("app.medications")


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


async def _get_owned_medication(
    medication_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> Medication:
    """Fetch a medication by id, scoped to the current user via its parent
    patient, or raise 404."""
    result = await db.execute(
        select(Medication)
        .join(Patient, Patient.id == Medication.patient_id)
        .where(Medication.id == medication_id, Patient.user_id == current_user.id)
    )
    medication = result.scalar_one_or_none()
    if medication is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found.",
        )
    return medication


async def _assert_drug_exists(drug_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(ReferenceDrug.id).where(ReferenceDrug.id == drug_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference drug not found.",
        )


async def _get_drug_name(drug_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Best-effort drug name lookup for timeline titles. Returns None if
    somehow missing rather than raising -- a missing name shouldn't block
    the medication/timeline write, since drug_id existence is already
    validated separately via _assert_drug_exists."""
    result = await db.execute(select(ReferenceDrug.name).where(ReferenceDrug.id == drug_id))
    return result.scalar_one_or_none()


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


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationResponse])
async def list_medications(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Medication]:
    """List all medications for a patient owned by the authenticated user."""
    await _assert_patient_owned(patient_id, current_user, db)

    result = await db.execute(
        select(Medication)
        .where(Medication.patient_id == patient_id)
        .order_by(Medication.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/patients/{patient_id}/medications",
    response_model=MedicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_medication(
    patient_id: uuid.UUID,
    payload: MedicationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Medication:
    """Create a new medication course for a patient owned by the caller.

    Each call creates a new row -- re-prescribing the same drug later
    creates a separate course rather than overwriting an old one, per the
    schema's design note (spec section 5).
    """
    await _assert_patient_owned(patient_id, current_user, db)
    await _assert_drug_exists(payload.drug_id, db)
    if payload.condition_id is not None:
        await _assert_condition_belongs_to_patient(payload.condition_id, patient_id, db)

    now = datetime.now(timezone.utc)
    medication = Medication(
        id=uuid.uuid4(),
        patient_id=patient_id,
        condition_id=payload.condition_id,
        purpose_text=payload.purpose_text,
        drug_id=payload.drug_id,
        dose=payload.dose,
        times_per_day=payload.times_per_day,
        interval_hours=payload.interval_hours,
        duration_days=payload.duration_days,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_at=now,
        updated_at=now,
    )
    db.add(medication)

    drug_name = await _get_drug_name(payload.drug_id, db)
    await log_timeline_event(
        db,
        patient_id=patient_id,
        event_type="medication_started",
        ref_id=medication.id,
        event_title=f"Started {drug_name}" if drug_name else "Medication started",
        event_description=payload.dose,
        payload={
            "drug_id": str(payload.drug_id),
            "dose": payload.dose,
            "status": payload.status,
        },
    )

    await db.commit()
    await db.refresh(medication)

    logger.info(
        "Medication created",
        extra={
            "medication_id": medication.id,
            "patient_id": patient_id,
            "user_id": current_user.id,
        },
    )
    return medication


@router.put("/medications/{medication_id}", response_model=MedicationResponse)
async def update_medication(
    medication_id: uuid.UUID,
    payload: MedicationUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Medication:
    """
    Update a medication.

    PUT semantics note: partial update only (fields present in the request
    body are changed via exclude_unset=True), matching the precedent set
    in patients.py's PUT endpoint -- the frozen spec (section 7) declares
    the route but not full-replace-vs-partial semantics, and forcing
    clients to resend every field (dose, schedule, status...) on every
    edit is unnecessary friction for iterative updates.
    """
    medication = await _get_owned_medication(medication_id, current_user, db)
    previous_status = medication.status

    updates = payload.model_dump(exclude_unset=True)

    if updates.get("drug_id") is not None:
        await _assert_drug_exists(updates["drug_id"], db)

    if updates.get("condition_id") is not None:
        await _assert_condition_belongs_to_patient(
            updates["condition_id"], medication.patient_id, db
        )

    for field, value in updates.items():
        setattr(medication, field, value)
    medication.updated_at = datetime.now(timezone.utc)

    # Phase 7: log medication_discontinued only on a genuine transition
    # into "discontinued" -- avoids duplicate events on repeated PUTs.
    if updates.get("status") == "discontinued" and previous_status != "discontinued":
        drug_name = await _get_drug_name(medication.drug_id, db)
        await log_timeline_event(
            db,
            patient_id=medication.patient_id,
            event_type="medication_discontinued",
            ref_id=medication.id,
            event_title=f"Discontinued {drug_name}" if drug_name else "Medication discontinued",
            payload={"previous_status": previous_status, "new_status": "discontinued"},
        )

    await db.commit()
    await db.refresh(medication)

    logger.info(
        "Medication updated",
        extra={"medication_id": medication.id, "user_id": current_user.id},
    )
    return medication


@router.delete("/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_medication(
    medication_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a medication course.

    Unlike patients (spec explicitly omits DELETE /patients/{id} -- see
    patients.py), DELETE /medications/{id} IS in the frozen API contract
    (spec section 7), so this is a genuine hard delete rather than a
    status change. medication_schedule and medication_doses rows cascade
    away via the ON DELETE CASCADE constraints already defined in
    001_initial_schema.sql -- no migration change needed.

    No timeline event is logged here (see Phase 7 module docstring) --
    the spec's event_type list has no "medication deleted" value.
    """
    medication = await _get_owned_medication(medication_id, current_user, db)
    await db.delete(medication)
    await db.commit()

    logger.info(
        "Medication deleted",
        extra={"medication_id": medication_id, "user_id": current_user.id},
    )
