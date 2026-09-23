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

drug_id validation: must reference an existing reference_drugs row,
otherwise 404 -- the reference catalog is selected from verified data, not
free-typed.

Phase 7 addition: medication creation logs a `medication_started` timeline
event, and updating a medication's status to `discontinued` (from any
other status) logs a `medication_discontinued` event -- both via
app/services/timeline_writer.py, added to the same DB session/transaction
as the medication write itself so the two are always persisted together.
Hard `DELETE` does not log an event -- the spec's event_type list (section
5) has no "medication deleted" value, only "medication_discontinued"
(a status transition), so deletion is intentionally left unlogged rather
than inventing a new event type.

Catalog identity: medication responses include the selected reference
catalog name, generic name, term type, and source. This is deliberately
additive: clients no longer need a browser-local name cache to render a
medication, while the existing `drug_id` remains the stable internal
reference used by the safety engine.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import (
    Condition,
    Medication,
    MedicationDoseRule,
    Patient,
    ReferenceDrug,
)
from app.db.session import get_db
from app.schemas.dose_rule import DoseRuleCreate, DoseRuleResponse
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


async def _get_drug(drug_id: uuid.UUID, db: AsyncSession) -> ReferenceDrug:
    result = await db.execute(select(ReferenceDrug).where(ReferenceDrug.id == drug_id))
    drug = result.scalar_one_or_none()
    if drug is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference drug not found.",
        )
    return drug


async def _assert_drug_exists(drug_id: uuid.UUID, db: AsyncSession) -> None:
    await _get_drug(drug_id, db)


async def _get_drug_name(drug_id: uuid.UUID, db: AsyncSession) -> str | None:
    """Best-effort drug name lookup for timeline titles."""
    result = await db.execute(select(ReferenceDrug.name).where(ReferenceDrug.id == drug_id))
    return result.scalar_one_or_none()


def _serialize_medication(
    medication: Medication,
    drug: ReferenceDrug,
    rules: list[MedicationDoseRule] | None = None,
) -> MedicationResponse:
    """Build the API response without triggering async relationship loading.

    `rules` is passed in explicitly for the same reason the drug columns
    are: lazy-loading a relationship here would emit IO on attribute
    access, which an async session cannot do.
    """
    return MedicationResponse.model_validate(medication).model_copy(
        update={
            "drug_name": drug.name,
            "drug_generic_name": drug.generic_name,
            "drug_term_type": drug.term_type,
            "drug_source": drug.source,
            "dose_rules": [DoseRuleResponse.model_validate(r) for r in (rules or [])],
        }
    )


async def _load_rules(
    medication_ids: list[uuid.UUID], db: AsyncSession
) -> dict[uuid.UUID, list[MedicationDoseRule]]:
    """Fetch dose rules for several medications in one query, ordered."""
    if not medication_ids:
        return {}
    result = await db.execute(
        select(MedicationDoseRule)
        .where(MedicationDoseRule.medication_id.in_(medication_ids))
        .order_by(MedicationDoseRule.medication_id, MedicationDoseRule.sequence)
    )
    grouped: dict[uuid.UUID, list[MedicationDoseRule]] = {}
    for rule in result.scalars().all():
        grouped.setdefault(rule.medication_id, []).append(rule)
    return grouped


def _build_rules(
    medication_id: uuid.UUID, rules: list[DoseRuleCreate], now: datetime
) -> list[MedicationDoseRule]:
    return [
        MedicationDoseRule(
            id=uuid.uuid4(),
            medication_id=medication_id,
            sequence=r.sequence,
            anchor_type=r.anchor_type,
            anchor_relation=r.anchor_relation,
            offset_minutes=r.offset_minutes,
            clock_time=r.clock_time,
            dose=r.dose,
            created_at=now,
            updated_at=now,
        )
        for r in sorted(rules, key=lambda r: r.sequence)
    ]


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
) -> list[MedicationResponse]:
    """List all medications with their verified catalog identity."""
    await _assert_patient_owned(patient_id, current_user, db)

    result = await db.execute(
        select(Medication, ReferenceDrug)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(Medication.patient_id == patient_id)
        .order_by(Medication.created_at)
    )
    rows = result.all()
    rules = await _load_rules([medication.id for medication, _ in rows], db)
    return [
        _serialize_medication(medication, drug, rules.get(medication.id, []))
        for medication, drug in rows
    ]


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
) -> MedicationResponse:
    """Create a new medication course for a patient owned by the caller."""
    await _assert_patient_owned(patient_id, current_user, db)
    drug = await _get_drug(payload.drug_id, db)
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

    rules = _build_rules(medication.id, payload.dose_rules, now)
    for rule in rules:
        db.add(rule)

    await log_timeline_event(
        db,
        patient_id=patient_id,
        event_type="medication_started",
        ref_id=medication.id,
        event_title=f"Started {drug.name}",
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
    return _serialize_medication(medication, drug, rules)


@router.put("/medications/{medication_id}", response_model=MedicationResponse)
async def update_medication(
    medication_id: uuid.UUID,
    payload: MedicationUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MedicationResponse:
    """Update a medication with partial PUT semantics."""
    medication = await _get_owned_medication(medication_id, current_user, db)
    previous_status = medication.status

    updates = payload.model_dump(exclude_unset=True)

    # dose_rules is a collection, not a column, so it must come out before
    # the generic setattr loop below. `exclude_unset` gives the three-way
    # distinction the contract needs: key absent -> leave rules alone;
    # [] -> clear them; a list -> replace the whole set.
    replace_rules = "dose_rules" in updates
    submitted_rules = payload.dose_rules if replace_rules else None
    updates.pop("dose_rules", None)

    drug = await _get_drug(updates["drug_id"], db) if updates.get("drug_id") else await _get_drug(medication.drug_id, db)

    if updates.get("condition_id") is not None:
        await _assert_condition_belongs_to_patient(
            updates["condition_id"], medication.patient_id, db
        )

    for field, value in updates.items():
        setattr(medication, field, value)
    now = datetime.now(timezone.utc)
    medication.updated_at = now

    if replace_rules:
        # Whole-collection replacement in the same transaction as the
        # medication update, so the two can never disagree. Rule ids are
        # not preserved -- nothing references them, because a generated
        # dose snapshots the resolved amount rather than pointing at a rule.
        await db.execute(
            delete(MedicationDoseRule).where(
                MedicationDoseRule.medication_id == medication_id
            )
        )
        await db.flush()
        for rule in _build_rules(medication_id, submitted_rules or [], now):
            db.add(rule)

    if updates.get("status") == "discontinued" and previous_status != "discontinued":
        await log_timeline_event(
            db,
            patient_id=medication.patient_id,
            event_type="medication_discontinued",
            ref_id=medication.id,
            event_title=f"Discontinued {drug.name}",
            payload={"previous_status": previous_status, "new_status": "discontinued"},
        )

    await db.commit()
    await db.refresh(medication)

    logger.info(
        "Medication updated",
        extra={"medication_id": medication_id, "user_id": current_user.id},
    )
    rules = (await _load_rules([medication_id], db)).get(medication_id, [])
    return _serialize_medication(medication, drug, rules)


@router.delete("/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_medication(
    medication_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a medication course using the existing cascade constraints."""
    medication = await _get_owned_medication(medication_id, current_user, db)
    await db.delete(medication)
    await db.commit()

    logger.info(
        "Medication deleted",
        extra={"medication_id": medication_id, "user_id": current_user.id},
    )


# ── Dose rules are managed as a set, not individually ────────────────────
#
# Rules form an ordered collection whose size must match
# `medications.times_per_day` for the course to be schedulable, so they are
# replaced wholesale through PUT /medications/{id} rather than edited one at
# a time -- per-rule writes could leave a set that satisfies no invariant.
# These guards exist so the prohibition is explicit at the route rather than
# implied by a 404, following the same convention as the symptom item routes.
#
# GET is guarded too, and not only for symmetry: with no GET route
# registered, Starlette answers a GET with its own 405 whose Allow header
# names the first matching route's method -- advertising POST, the very
# method these guards refuse. An explicit GET route keeps the Allow header
# honest. It is empty on every guard because this path supports no methods
# at all, which RFC 9110 states as an empty Allow field value.

_DOSE_RULE_GUARD_DETAIL = (
    "Dose rules are managed as a set. Send the full collection as "
    "`dose_rules` on PUT /api/v1/medications/{medication_id}; an empty "
    "list clears them."
)


@router.get("/dose-rules/{dose_rule_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def read_dose_rule_not_allowed(dose_rule_id: uuid.UUID):
    """Dose rules are not addressable individually; read them on the medication."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=_DOSE_RULE_GUARD_DETAIL,
        headers={"Allow": ""},
    )


@router.post("/dose-rules/{dose_rule_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def create_dose_rule_not_allowed(dose_rule_id: uuid.UUID):
    """Dose rules cannot be created individually."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=_DOSE_RULE_GUARD_DETAIL,
        headers={"Allow": ""},
    )


@router.put("/dose-rules/{dose_rule_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def update_dose_rule_not_allowed(dose_rule_id: uuid.UUID):
    """Dose rules cannot be updated individually."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=_DOSE_RULE_GUARD_DETAIL,
        headers={"Allow": ""},
    )


@router.delete("/dose-rules/{dose_rule_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def delete_dose_rule_not_allowed(dose_rule_id: uuid.UUID):
    """Dose rules cannot be deleted individually."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=_DOSE_RULE_GUARD_DETAIL,
        headers={"Allow": ""},
    )
