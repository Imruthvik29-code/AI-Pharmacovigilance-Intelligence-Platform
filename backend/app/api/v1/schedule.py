"""
Dose scheduling endpoints (spec section 7):

    POST /medications/{id}/schedule
    GET  /patients/{id}/doses/upcoming

NOTE: `POST /doses/{id}/mark` is also listed in the frozen API contract
but is explicitly scoped to Phase 9 (Adherence -- Taken/Missed/Skipped
per spec section 10) and is intentionally NOT implemented here.

Ownership: both routes are scoped through the parent patient, mirroring
conditions.py/medications.py/symptoms.py/timeline.py -- a medication or
patient not owned by the caller (or not existing) returns 404, never 403.

Schedule generation design (see Phase 8 module docstring in
PROJECT_PHASES.md / CHANGELOG.md for full rationale):
  - Requires `times_per_day` AND `duration_days` to already be set on the
    medication (400 otherwise) -- no invented defaults for clinically
    meaningful quantities.
  - Dose spacing uses `interval_hours` if set, else `24 / times_per_day`
    hours (even daily spread).
  - The first dose anchors at 08:00 UTC on `start_date` (documented
    convention, not a silent guess).
  - Generates `times_per_day * duration_days` doses total, spaced evenly
    from that anchor.
  - Rejects (409) if a schedule already exists for the medication --
    regeneration/rescheduling is not defined by the spec.
  - Caps total generated doses at MAX_GENERATED_DOSES as a defensive
    guard against pathological inputs (not a spec requirement).

Upcoming doses design:
  - Only future (scheduled_time >= now), unmarked (status IS NULL) doses.
  - Only for medications with status == "active" -- doses for
    paused/discontinued/completed medications are excluded.
  - Ordered ascending by scheduled_time.
  - Enriched with drug_name/dose (joined from reference_drugs/medications)
    so the response is directly usable by a "take your medication" UI
    without a client-side re-lookup.
"""
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Medication, MedicationDose, MedicationSchedule, Patient, ReferenceDrug
from app.db.session import get_db
from app.schemas.schedule import MedicationDoseResponse, UpcomingDoseResponse

router = APIRouter(tags=["schedule"])
logger = logging.getLogger("app.schedule")

# Defensive cap on total doses generated in a single call -- guards against
# pathological inputs (e.g. times_per_day=24 with a multi-year
# duration_days) producing tens of thousands of rows. Not a spec
# requirement; purely a safety guard.
MAX_GENERATED_DOSES = 3650

# Anchor time-of-day for the first generated dose, since Medication only
# stores a date (start_date), not a datetime, but scheduled_time is a
# timestamptz. Documented default, not a silent guess.
DEFAULT_FIRST_DOSE_TIME = time(hour=8, tzinfo=timezone.utc)


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


@router.post(
    "/medications/{medication_id}/schedule",
    response_model=list[MedicationDoseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_schedule(
    medication_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MedicationDose]:
    """Generate the dose schedule for a medication owned by the caller."""
    medication = await _get_owned_medication(medication_id, current_user, db)

    if medication.times_per_day is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "medication.times_per_day must be set before a schedule can be "
                "generated. Update the medication first via PUT /medications/{id}."
            ),
        )
    if medication.duration_days is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "medication.duration_days must be set before a schedule can be "
                "generated. Update the medication first via PUT /medications/{id}."
            ),
        )

    existing = await db.execute(
        select(MedicationSchedule.id).where(MedicationSchedule.medication_id == medication_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A schedule already exists for this medication.",
        )

    total_doses = medication.times_per_day * medication.duration_days
    if total_doses > MAX_GENERATED_DOSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested schedule would generate {total_doses} doses, exceeding "
                f"the maximum of {MAX_GENERATED_DOSES}. Reduce times_per_day or "
                "duration_days."
            ),
        )

    interval_hours = medication.interval_hours or (24 / medication.times_per_day)
    anchor = datetime.combine(medication.start_date, DEFAULT_FIRST_DOSE_TIME)

    now = datetime.now(timezone.utc)
    created_doses: list[MedicationDose] = []
    for i in range(total_doses):
        scheduled_time = anchor + timedelta(hours=float(interval_hours) * i)

        schedule_row = MedicationSchedule(
            id=uuid.uuid4(),
            medication_id=medication_id,
            scheduled_time=scheduled_time,
            created_at=now,
        )
        db.add(schedule_row)

        dose_row = MedicationDose(
            id=uuid.uuid4(),
            medication_id=medication_id,
            schedule_id=schedule_row.id,
            scheduled_time=scheduled_time,
            status=None,
            actual_time=None,
            created_at=now,
            updated_at=now,
        )
        db.add(dose_row)
        created_doses.append(dose_row)

    await db.commit()
    for dose_row in created_doses:
        await db.refresh(dose_row)

    logger.info(
        "Schedule generated",
        extra={
            "medication_id": medication_id,
            "dose_count": len(created_doses),
            "user_id": current_user.id,
        },
    )
    return created_doses


@router.get("/patients/{patient_id}/doses/upcoming", response_model=list[UpcomingDoseResponse])
async def list_upcoming_doses(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UpcomingDoseResponse]:
    """List upcoming (future, unmarked) doses for a patient's active medications."""
    await _assert_patient_owned(patient_id, current_user, db)

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(
            MedicationDose.id,
            MedicationDose.medication_id,
            MedicationDose.scheduled_time,
            ReferenceDrug.name,
            Medication.dose,
        )
        .join(Medication, Medication.id == MedicationDose.medication_id)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(
            Medication.patient_id == patient_id,
            Medication.status == "active",
            MedicationDose.status.is_(None),
            MedicationDose.scheduled_time >= now,
        )
        .order_by(MedicationDose.scheduled_time)
    )

    return [
        UpcomingDoseResponse(
            id=row[0],
            medication_id=row[1],
            scheduled_time=row[2],
            drug_name=row[3],
            dose=row[4],
        )
        for row in result.all()
    ]
