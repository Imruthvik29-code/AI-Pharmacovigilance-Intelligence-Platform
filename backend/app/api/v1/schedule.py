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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import (
    Medication,
    MedicationDose,
    MedicationDoseRule,
    MedicationSchedule,
    Patient,
    ReferenceDrug,
)
from app.db.session import get_db
from app.schemas.schedule import (
    MedicationDoseMarkRequest,
    MedicationDoseResponse,
    UpcomingDoseResponse,
)
from app.services.timeline_writer import log_timeline_event

router = APIRouter(tags=["schedule"])
logger = logging.getLogger("app.schedule")

MAX_GENERATED_DOSES = 3650
DEFAULT_FIRST_DOSE_TIME = time(hour=8, tzinfo=timezone.utc)
_FLOOR_EPSILON = 1e-9

_MARK_EVENT_TYPES = {
    "taken": "dose_taken",
    "missed": "dose_missed",
    "skipped": "dose_skipped",
}

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
    """Fetch a dose by id, scoped to the current user via its medication's
    parent patient, or raise 404."""
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


_MEAL_FIELDS = {
    "breakfast": "breakfast_time",
    "lunch": "lunch_time",
    "dinner": "dinner_time",
}


def _resolve_zone(patient: Patient) -> ZoneInfo:
    """The patient's IANA zone, or 400 when it is absent/unresolvable."""
    if not patient.timezone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "patient.timezone must be set before a rule-based schedule can "
                "be generated. Record the patient's daily routine first."
            ),
        )
    try:
        return ZoneInfo(patient.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"patient.timezone {patient.timezone!r} is not a resolvable IANA timezone.",
        ) from exc


def _anchor_local_time(rule: MedicationDoseRule, patient: Patient) -> time:
    """The rule's anchor as a local wall-clock time, or 400 if unrecorded."""
    if rule.anchor_type == "clock_time":
        return rule.clock_time

    field = _MEAL_FIELDS[rule.anchor_type]
    value = getattr(patient, field)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dose {rule.sequence} is anchored to {rule.anchor_type}, but "
                f"patient.{field} is not recorded. Record the patient's daily "
                f"routine first."
            ),
        )
    return value


def _apply_offset(anchor: datetime, rule: MedicationDoseRule) -> datetime:
    """Shift by the rule's offset. Magnitude is non-negative; the relation
    supplies the direction, so 'before' subtracts and 'after' adds."""
    if rule.anchor_type == "clock_time" or rule.anchor_relation == "with":
        return anchor
    delta = timedelta(minutes=rule.offset_minutes or 0)
    return anchor - delta if rule.anchor_relation == "before" else anchor + delta


def _localize(naive: datetime, zone: ZoneInfo, rule_sequence: int) -> datetime:
    """Convert a local wall-clock datetime to a UTC instant.

    Two daylight-saving edge cases are handled explicitly rather than left
    to whatever the library happens to do:

    * Nonexistent (spring forward): the wall-clock time never occurs, so
      the request is refused with a 400 naming the date. Emitting a dose at
      a silently shifted time would misrepresent the prescription.
    * Ambiguous (autumn back): the time occurs twice. `fold=0` selects the
      first occurrence -- a documented convention, deterministic across
      runs, not a guess about clinical intent.
    """
    local = naive.replace(tzinfo=zone, fold=0)
    # PEP 495 round-trip test: a nonexistent local time does not survive a
    # conversion to UTC and back.
    if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dose {rule_sequence} would fall at {naive.isoformat()} local "
                f"time, which does not exist in {zone.key} because of a "
                f"daylight-saving transition. Adjust the routine or the rule's "
                f"offset."
            ),
        )
    return local.astimezone(timezone.utc)


def _rule_dose(rule: MedicationDoseRule, medication: Medication) -> str | None:
    """Resolved amount for this slot: the rule's override, else the course
    default. Snapshotted at generation so later edits cannot rewrite it."""
    return rule.dose if rule.dose is not None else medication.dose


def _assert_within_course(
    wall: datetime, medication: Medication, rule: MedicationDoseRule
) -> None:
    """Every dose must land on a local calendar date inside the course.

    The window is the medication's own day range, and it is checked against
    the dose's *resulting* local date so an offset cannot quietly place a
    dose outside the prescribed course. The check is deliberately in local
    time: a dose at 03:00 in Asia/Kolkata on the start date is 21:30 UTC the
    previous day, and is correctly inside the course.

    Offsets are capped at an hour, so an ordinary meal time cannot reach
    across midnight; a meal recorded within an hour of one still can, which
    is exactly what this rejects. Nothing is clamped or dropped -- the
    prescription is refused so it can be corrected.
    """
    first = medication.start_date
    last = first + timedelta(days=medication.duration_days - 1)
    if first <= wall.date() <= last:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Dose {rule.sequence} would fall at {wall.isoformat()} local time, "
            f"outside the course window {first.isoformat()}..{last.isoformat()}. "
            f"Adjust the rule's offset, the recorded meal time, or the duration."
        ),
    )


def _assert_no_duplicate_instants(
    planned: list[tuple[datetime, str | None, int]]
) -> None:
    """Two rules must not resolve to the same instant.

    Merging them would silently halve the prescribed frequency and shifting
    one would invent a time nobody prescribed, so the schedule is refused
    and the colliding rules are named.
    """
    seen: dict[datetime, int] = {}
    for instant, _dose, sequence in planned:
        first = seen.get(instant)
        if first is not None and first != sequence:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Dose rules {first} and {sequence} both resolve to "
                    f"{instant.isoformat()}. Two doses cannot share an instant; "
                    f"adjust one rule's anchor or offset."
                ),
            )
        seen.setdefault(instant, sequence)


def _compute_rule_schedule(
    medication: Medication,
    rules: list[MedicationDoseRule],
    patient: Patient,
) -> list[tuple[datetime, str | None]]:
    """(instant, resolved_dose) for every dose across the whole course."""
    zone = _resolve_zone(patient)
    out: list[tuple[datetime, str | None, int]] = []
    for day in range(medication.duration_days):
        local_date = medication.start_date + timedelta(days=day)
        for rule in rules:
            anchor = datetime.combine(local_date, _anchor_local_time(rule, patient))
            wall = _apply_offset(anchor, rule)
            _assert_within_course(wall, medication, rule)
            out.append(
                (_localize(wall, zone, rule.sequence), _rule_dose(rule, medication), rule.sequence)
            )
    out.sort(key=lambda row: row[0])
    _assert_no_duplicate_instants(out)
    return [(instant, dose) for instant, dose, _sequence in out]


def _compute_schedule_params(medication: Medication) -> tuple[int, float]:
    """Determine (total_doses, interval_hours) for schedule generation."""
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
    """Lazily mark all overdue, unmarked doses for a patient as missed."""
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

    rules = list(
        (
            await db.execute(
                select(MedicationDoseRule)
                .where(MedicationDoseRule.medication_id == medication_id)
                .order_by(MedicationDoseRule.sequence)
            )
        )
        .scalars()
        .all()
    )

    if medication.duration_days is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "medication.duration_days must be set before a schedule can be "
                "generated. Update the medication first via PUT /medications/{id}."
            ),
        )

    # Rules and interval_hours express contradictory intent. Refuse rather
    # than silently preferring one -- picking a winner would be a guess.
    if rules and medication.interval_hours is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "medication has both dose rules and interval_hours set. These "
                "describe different schedules; clear one before generating."
            ),
        )

    if rules and medication.times_per_day is None and medication.interval_hours is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "medication.times_per_day must be set alongside dose rules so "
                "the prescribed frequency and the number of rules can be "
                "reconciled."
            ),
        )

    if rules and len(rules) != medication.times_per_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"medication.times_per_day is {medication.times_per_day} but "
                f"{len(rules)} dose rule(s) are defined. They must match before "
                f"a schedule can be generated."
            ),
        )

    if not rules and medication.times_per_day is None and medication.interval_hours is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "At least one of medication.times_per_day or "
                "medication.interval_hours must be set before a schedule can be "
                "generated. Update the medication first via PUT /medications/{id}."
            ),
        )

    # A generated schedule is one medication_schedule row per dose, so any
    # schedule with more than one dose returns several rows here. Only
    # existence matters: limit(1) keeps scalar_one_or_none() from raising
    # MultipleResultsFound (a 500) where this should answer 409.
    existing = await db.execute(
        select(MedicationSchedule.id)
        .where(MedicationSchedule.medication_id == medication_id)
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A schedule already exists for this medication.",
        )

    # The dose count is derived arithmetically and checked against the cap
    # BEFORE any dose is materialised. Building the list first would let a
    # single request with a tiny interval_hours or a huge duration_days
    # allocate hundreds of millions of entries -- minutes of work and
    # gigabytes of memory -- before being refused, and would surface a date
    # overflow as a 500 rather than this 400.
    if rules:
        total_doses = len(rules) * medication.duration_days
    else:
        total_doses, interval_hours = _compute_schedule_params(medication)

    if total_doses > MAX_GENERATED_DOSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested schedule would generate {total_doses} doses, exceeding "
                f"the maximum of {MAX_GENERATED_DOSES}. Reduce times_per_day, "
                "interval_hours, dose rules, or duration_days."
            ),
        )

    if rules:
        # Rule-based: anchors come from the patient's recorded routine, so
        # the patient row is needed to resolve them.
        patient = (
            await db.execute(select(Patient).where(Patient.id == medication.patient_id))
        ).scalar_one()
        planned = _compute_rule_schedule(medication, rules, patient)
    else:
        # Interval/even-spread: unchanged from the original implementation,
        # including the documented 08:00 UTC first-dose anchor.
        anchor = datetime.combine(medication.start_date, DEFAULT_FIRST_DOSE_TIME)
        planned = [
            (anchor + timedelta(hours=interval_hours * i), medication.dose)
            for i in range(total_doses)
        ]

    now = datetime.now(timezone.utc)

    schedule_rows: list[tuple[MedicationSchedule, str | None]] = []
    for scheduled_time, resolved_dose in planned:
        schedule_row = MedicationSchedule(
            id=uuid.uuid4(),
            medication_id=medication_id,
            scheduled_time=scheduled_time,
            created_at=now,
        )
        db.add(schedule_row)
        schedule_rows.append((schedule_row, resolved_dose))

    await db.flush()

    created_doses: list[MedicationDose] = []
    for schedule_row, resolved_dose in schedule_rows:
        dose_row = MedicationDose(
            id=uuid.uuid4(),
            medication_id=medication_id,
            schedule_id=schedule_row.id,
            scheduled_time=schedule_row.scheduled_time,
            status=None,
            actual_time=None,
            # Frozen here: a later edit to the medication or its rules
            # must not rewrite what this dose represented.
            dose=resolved_dose,
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
    """List upcoming future, unmarked doses for active medications."""
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
            # Prefer the amount frozen at generation. Rows created before
            # that column existed hold NULL and fall back to the course
            # default, preserving their previous behaviour.
            func.coalesce(MedicationDose.dose, Medication.dose),
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
    """Mark a dose once; overdue doses are first swept to missed."""
    dose, patient_id, drug_name = await _get_owned_dose(dose_id, current_user, db)

    await _sweep_missed_doses(patient_id, db)
    await db.flush()

    if dose.status is not None:
        # The sweep is a real state-changing operation. If this request is
        # rejected because the target dose is now missed (or was already
        # explicitly marked), persist the sweep before returning 409 rather
        # than rolling the state change back with the failed request.
        await db.commit()
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
