"""
Dose scheduling and adherence endpoints (spec section 7):

    POST /medications/{id}/schedule
    GET  /patients/{id}/doses/upcoming
    POST /doses/{id}/mark

Ownership: all three routes are scoped through the parent patient,
mirroring conditions.py/medications.py/symptoms.py/timeline.py -- a
medication, dose, or patient not owned by the caller (or not existing)
returns 404, never 403.

Schedule generation design (Phase 8, refined to support interval_hours
without times_per_day):
  - Requires `duration_days` AND at least one of (`times_per_day`,
    `interval_hours`) to already be set on the medication (400 otherwise)
    -- no invented defaults for clinically meaningful quantities.
  - If `times_per_day` is set, dose count is `times_per_day * duration_days`
    and spacing uses `interval_hours` if also set, else an even daily
    spread of `24 / times_per_day` hours.
  - If `times_per_day` is NOT set (only `interval_hours` is provided),
    spacing uses `interval_hours` directly, and dose count is derived as
    `floor(duration_days * 24 / interval_hours)` (minimum 1).
  - The first dose anchors at 08:00 UTC on `start_date` (documented
    convention, not a silent guess) in both branches.
  - Rejects (409) if a schedule already exists for the medication.
  - Caps total generated doses at MAX_GENERATED_DOSES as a defensive
    guard against pathological inputs.

Upcoming doses design:
  - Only future (scheduled_time >= now), unmarked (status IS NULL) doses.
  - Only for medications with status == "active".
  - Ordered ascending by scheduled_time.
  - Enriched with drug_name/dose so the response is directly usable by a
    "take your medication" UI without a client-side re-lookup.
  - Phase 9 addition: runs the missed-dose sweep (see below) before
    querying, so overdue unmarked doses are reflected as "missed" rather
    than lingering as unmarked forever.

Phase 9 -- Adherence (mark taken/missed/skipped):
  - `POST /doses/{id}/mark` sets a dose's status exactly once. If the dose
    is already marked (whether by a prior explicit mark or by the
    automatic sweep below), the request is rejected with 409 -- there is
    no spec-defined "correct a mark" flow, so this is treated as
    immutable once set, consistent with the "schedule already exists"
    409 precedent for schedule generation.
  - `actual_time` defaults to `now()` when marking "taken" if the client
    omits it, and is left null for "missed"/"skipped" (there's no
    meaningful "actual" time for a dose that wasn't taken).
  - Logs `dose_taken` / `dose_missed` / `dose_skipped` timeline events via
    app/services/timeline_writer.py, in the same transaction as the dose
    update.

  Missed-dose background check (spec section 10, Phase 9): the tech stack
  (spec section 4) has no job scheduler/cron component, so this is
  implemented as a **lazy, query-time sweep** rather than a true
  background job -- `_sweep_missed_doses()` flips any dose belonging to
  the given patient whose `scheduled_time` has already passed and is
  still unmarked (`status IS NULL`) to `missed`, logging a `dose_missed`
  timeline event per affected dose. This runs (and its changes are
  committed) at the start of both `list_upcoming_doses` and `mark_dose`,
  so any read or write touching a patient's doses first brings their
  overdue doses up to date. The sweep considers doses for medications in
  any status (active/paused/discontinued/etc.) -- a dose scheduled before
  a medication was paused is still either taken or missed in reality,
  independent of the medication's current status.

  Adherence statistics (e.g. taken/missed/skipped counts or an adherence
  percentage) are explicitly deferred -- not part of the frozen section 7
  API contract, and confirmed out of scope for this phase; that data will
  feed the Safety Score Engine (Phase 12+) instead.
"""
import logging
import math
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import Medication, MedicationDose, MedicationSchedule, Patient, ReferenceDrug
from app.db.session import get_db
from app.schemas.schedule import (
    MedicationDoseMarkRequest,
    MedicationDoseResponse,
    UpcomingDoseResponse,
)
from app.services.timeline_writer import log_timeline_event

router = APIRouter(tags=["schedule"])
logger = logging.getLogger("app.schedule")

# Defensive cap on total doses generated in a single call -- guards against
# pathological inputs (e.g. times_per_day=24 with a multi-year
# duration_days, or a very small interval_hours over a long duration)
# producing tens of thousands of rows. Not a spec requirement; purely a
# safety guard.
MAX_GENERATED_DOSES = 3650

# Anchor time-of-day for the first generated dose, since Medication only
# stores a date (start_date), not a datetime, but scheduled_time is a
# timestamptz. Documented default, not a silent guess.
DEFAULT_FIRST_DOSE_TIME = time(hour=8, tzinfo=timezone.utc)

# Small epsilon to guard the floor() calculation in the interval-only
# branch against floating point representation error (e.g. duration_days
# * 24 / interval_hours landing at 3.999999999 instead of 4.0).
_FLOOR_EPSILON = 1e-9

# Maps a dose mark status to its timeline event_type, per the canonical
# event_type list documented in spec section 5.
_MARK_EVENT_TYPES = {
    "taken": "dose_taken",
    "missed": "dose_missed",
    "skipped": "dose_skipped",
}

# Maps a dose mark status to a human-readable verb for timeline titles.
_MARK_TITLE_VERBS = {
    "taken": "Took",
    "missed": "Missed",
    "skipped": "Skipped",
}


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


async def _get_owned_dose(
    dose_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> tuple[MedicationDose, uuid.UUID, str | None]:
    """
    Fetch a dose by id, scoped to the current user via its medication's
    parent patient, or raise 404.

    Returns (dose, patient_id, drug_name) -- patient_id and drug_name are
    fetched alongside the dose (rather than via separate queries) since
    both are needed by mark_dose regardless: patient_id to run the
    missed-dose sweep and log timeline events, drug_name for the timeline
    event title.
    """
    result = await db.execute(
        select(MedicationDose, Medication.patient_id, ReferenceDrug.name)
        .join(Medication, Medication.id == MedicationDose.medication_id)
        .join(Patient, Patient.id == Medication.patient_id)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(MedicationDose.id == dose_id, Patient.user_id == current_user.id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dose not found.",
        )
    dose, patient_id, drug_name = row
    return dose, patient_id, drug_name


def _compute_schedule_params(medication: Medication) -> tuple[int, float]:
    """
    Determine (total_doses, interval_hours) for schedule generation.

    Two supported input shapes, per the caller's validated preconditions
    (duration_days set, and at least one of times_per_day/interval_hours
    set):

    1. times_per_day is set (interval_hours optional):
       total_doses = times_per_day * duration_days
       interval_hours = medication.interval_hours or (24 / times_per_day)

    2. times_per_day is None, interval_hours is set:
       interval_hours = medication.interval_hours
       total_doses = floor(duration_days * 24 / interval_hours), min 1
    """
    if medication.times_per_day is not None:
        total_doses = medication.times_per_day * medication.duration_days
        interval_hours = medication.interval_hours or (24 / medication.times_per_day)
        return total_doses, float(interval_hours)

    interval_hours = float(medication.interval_hours)
    total_doses = math.floor(
        medication.duration_days * 24 / interval_hours + _FLOOR_EPSILON
    )
    total_doses = max(total_doses, 1)
    return total_doses, interval_hours


async def _sweep_missed_doses(patient_id: uuid.UUID, db: AsyncSession) -> None:
    """
    Lazy, query-time substitute for a "missed-dose background check"
    (spec section 10, Phase 9) -- there is no job scheduler in the tech
    stack (spec section 4), so this runs synchronously whenever a
    dose-related route for this patient is hit.

    Flips every dose belonging to `patient_id` where `scheduled_time` has
    already passed and `status IS NULL` to `missed`, logging a
    `dose_missed` timeline event per affected dose. Applies regardless of
    the parent medication's status (active/paused/discontinued/etc.) --
    a dose that was due is either taken or missed in reality, independent
    of the medication's current lifecycle state.

    Does NOT commit -- callers commit alongside whatever else their
    request does (a plain read in list_upcoming_doses, or the dose write
    in mark_dose), so the sweep's changes and the caller's own changes
    land in the same transaction.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MedicationDose, ReferenceDrug.name)
        .join(Medication, Medication.id == MedicationDose.medication_id)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(
            Medication.patient_id == patient_id,
            MedicationDose.status.is_(None),
            MedicationDose.scheduled_time < now,
        )
    )
    for dose, drug_name in result.all():
        dose.status = "missed"
        dose.actual_time = None
        dose.updated_at = now

        await log_timeline_event(
            db,
            patient_id=patient_id,
            event_type="dose_missed",
            ref_id=dose.id,
            event_title=f"Missed dose of {drug_name}" if drug_name else "Dose missed",
            payload={
                "medication_id": str(dose.medication_id),
                "scheduled_time": dose.scheduled_time.isoformat(),
                "auto_detected": True,
            },
        )


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

    if medication.duration_days is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "medication.duration_days must be set before a schedule can be "
                "generated. Update the medication first via PUT /medications/{id}."
            ),
        )
    if medication.times_per_day is None and medication.interval_hours is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "At least one of medication.times_per_day or "
                "medication.interval_hours must be set before a schedule can be "
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

    total_doses, interval_hours = _compute_schedule_params(medication)

    if total_doses > MAX_GENERATED_DOSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested schedule would generate {total_doses} doses, exceeding "
                f"the maximum of {MAX_GENERATED_DOSES}. Reduce times_per_day, "
                "interval_hours, or duration_days."
            ),
        )

    anchor = datetime.combine(medication.start_date, DEFAULT_FIRST_DOSE_TIME)

    now = datetime.now(timezone.utc)
    created_doses: list[MedicationDose] = []
    for i in range(total_doses):
        scheduled_time = anchor + timedelta(hours=interval_hours * i)

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
    """
    List upcoming (future, unmarked) doses for a patient's active medications.

    Phase 9: runs the missed-dose sweep for this patient first (see
    `_sweep_missed_doses`) and commits it -- this route now has a small,
    documented write side-effect (flipping overdue unmarked doses to
    "missed") in addition to its read. The sweep itself never changes
    what this query returns (it only touches doses with
    `scheduled_time < now`, and this query only ever returns
    `scheduled_time >= now`), but it keeps stored dose status accurate
    for anything reading `medication_doses` directly (e.g. a future
    adherence-statistics feature).
    """
    await _assert_patient_owned(patient_id, current_user, db)

    await _sweep_missed_doses(patient_id, db)
    await db.commit()

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


@router.post("/doses/{dose_id}/mark", response_model=MedicationDoseResponse)
async def mark_dose(
    dose_id: uuid.UUID,
    payload: MedicationDoseMarkRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationDose:
    """
    Mark a dose as taken, missed, or skipped (Phase 9 -- Adherence).

    Runs the missed-dose sweep for this dose's patient first, so a dose
    that has itself gone overdue and unmarked is flipped to "missed"
    (and thus rejected below as "already marked") rather than silently
    overwritten by an unrelated explicit mark. A dose can only be marked
    once -- a second attempt (whether the first mark was explicit or
    sweep-applied) returns 409, since the spec defines no "correct a
    mark" flow.
    """
    dose, patient_id, drug_name = await _get_owned_dose(dose_id, current_user, db)

    await _sweep_missed_doses(patient_id, db)
    await db.flush()  # ensure `dose.status` reflects any sweep-applied change

    if dose.status is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dose already marked as '{dose.status}'.",
        )

    now = datetime.now(timezone.utc)
    dose.status = payload.status
    dose.actual_time = payload.actual_time or (now if payload.status == "taken" else None)
    dose.updated_at = now

    verb = _MARK_TITLE_VERBS[payload.status]
    await log_timeline_event(
        db,
        patient_id=patient_id,
        event_type=_MARK_EVENT_TYPES[payload.status],
        ref_id=dose.id,
        event_title=f"{verb} dose of {drug_name}" if drug_name else f"Dose {payload.status}",
        payload={
            "medication_id": str(dose.medication_id),
            "scheduled_time": dose.scheduled_time.isoformat(),
            "actual_time": dose.actual_time.isoformat() if dose.actual_time else None,
        },
    )

    await db.commit()
    await db.refresh(dose)

    logger.info(
        "Dose marked",
        extra={
            "dose_id": dose.id,
            "status": payload.status,
            "user_id": current_user.id,
        },
    )
    return dose
