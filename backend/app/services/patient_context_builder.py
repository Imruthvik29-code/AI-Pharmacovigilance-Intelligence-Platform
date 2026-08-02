"""
Patient Context Builder (Phase 14).

Implements spec section 8's "Patient Context Builder Node" -- the first
node in the LangGraph workflow. Per the design note already recorded in
001_initial_schema.sql / pharmacovigilance-spec-v1.md section 5 ("no
patient_context table by design"), this builds a fresh context object on
every analysis run by querying `patients`/`conditions`/`medications`/
`symptoms` directly -- there is no stored cache table, so the context can
never go stale.

Placement: `app/services/`, alongside `llm_service.py` and
`langgraph_workflow.py` (spec section 6's `services/` folder), since this
is an application-level orchestration helper, not a deterministic
analysis engine (mirrors the same `services/` vs `analysis/` distinction
already established by Phase 13's `evidence_retrieval.py`).

## Scope decisions (confirmed defaults, documented per this codebase's
## convention of naming judgment calls explicitly rather than embedding
## them silently in query logic)

- **Active medications**: `status == "active"` -- identical filter to
  every other engine in `app/analysis/` (Phases 10-12) and to
  `GET /patients/{id}/doses/upcoming` (Phase 8), for a single consistent
  notion of "currently being taken."
- **Active conditions**: `status != "resolved"` -- the condition lifecycle
  (`active`, `improving`, `resolved`, `persistent`, `recurred`) has only
  one clearly terminal state (`resolved`); the other four all describe a
  condition still clinically relevant to the patient's current picture.
  This is an implementation default, not a spec-defined rule (the frozen
  spec does not define a condition lifecycle state machine -- see Phase
  5's own documented scope note) -- if a narrower definition of "active"
  is wanted later, that's a deliberate change to request explicitly.
- **Active symptoms**: `resolved_date IS NULL` -- an unresolved/ongoing
  symptom, mirroring the same "not yet resolved" concept applied to
  conditions above, using the field that already exists on `symptoms`
  (which has no separate `status` enum of its own).

This module performs no writes and computes nothing beyond straight
retrieval + structuring -- no severity, no scoring, no interpretation.
"""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Condition, Medication, Patient, ReferenceDrug, Symptom


@dataclass(frozen=True)
class ConditionSummary:
    """One of the patient's currently active conditions (see module docstring)."""

    id: uuid.UUID
    name: str
    status: str
    reason: str
    diagnosed_date: date | None
    resolved_date: date | None
    notes: str | None


@dataclass(frozen=True)
class MedicationSummary:
    """One of the patient's currently active medications, denormalized with the drug name."""

    id: uuid.UUID
    drug_id: uuid.UUID
    drug_name: str
    condition_id: uuid.UUID | None
    purpose_text: str | None
    dose: str | None
    times_per_day: int | None
    interval_hours: float | None
    duration_days: int | None
    status: str
    start_date: date
    end_date: date | None


@dataclass(frozen=True)
class SymptomSummary:
    """One of the patient's currently unresolved symptoms."""

    id: uuid.UUID
    description: str
    severity: str
    condition_id: uuid.UUID | None
    medication_id: uuid.UUID | None
    onset_date: date
    resolved_date: date | None


@dataclass(frozen=True)
class PatientContext:
    """
    Full, freshly-built context for one analysis run -- demographics plus
    active conditions/medications/symptoms. Built new on every call;
    never cached (see module docstring).
    """

    patient_id: uuid.UUID
    name: str
    age: int | None
    sex: str | None
    weight_kg: float | None
    renal_flag: bool
    hepatic_flag: bool
    active_conditions: list[ConditionSummary]
    active_medications: list[MedicationSummary]
    active_symptoms: list[SymptomSummary]


async def _get_patient(patient_id: uuid.UUID, db: AsyncSession) -> Patient:
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    return result.scalar_one()


async def _get_active_conditions(patient_id: uuid.UUID, db: AsyncSession) -> list[ConditionSummary]:
    result = await db.execute(
        select(Condition)
        .where(Condition.patient_id == patient_id, Condition.status != "resolved")
        .order_by(Condition.created_at)
    )
    return [
        ConditionSummary(
            id=c.id,
            name=c.name,
            status=c.status,
            reason=c.reason,
            diagnosed_date=c.diagnosed_date,
            resolved_date=c.resolved_date,
            notes=c.notes,
        )
        for c in result.scalars().all()
    ]


async def _get_active_medications(patient_id: uuid.UUID, db: AsyncSession) -> list[MedicationSummary]:
    result = await db.execute(
        select(Medication, ReferenceDrug.name)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(Medication.patient_id == patient_id, Medication.status == "active")
        .order_by(Medication.created_at)
    )
    return [
        MedicationSummary(
            id=m.id,
            drug_id=m.drug_id,
            drug_name=drug_name,
            condition_id=m.condition_id,
            purpose_text=m.purpose_text,
            dose=m.dose,
            times_per_day=m.times_per_day,
            interval_hours=float(m.interval_hours) if m.interval_hours is not None else None,
            duration_days=m.duration_days,
            status=m.status,
            start_date=m.start_date,
            end_date=m.end_date,
        )
        for m, drug_name in result.all()
    ]


async def _get_active_symptoms(patient_id: uuid.UUID, db: AsyncSession) -> list[SymptomSummary]:
    result = await db.execute(
        select(Symptom)
        .where(Symptom.patient_id == patient_id, Symptom.resolved_date.is_(None))
        .order_by(Symptom.onset_date, Symptom.created_at)
    )
    return [
        SymptomSummary(
            id=s.id,
            description=s.description,
            severity=s.severity,
            condition_id=s.condition_id,
            medication_id=s.medication_id,
            onset_date=s.onset_date,
            resolved_date=s.resolved_date,
        )
        for s in result.scalars().all()
    ]


async def build_patient_context(patient_id: uuid.UUID, db: AsyncSession) -> PatientContext:
    """
    Build a fresh PatientContext for one analysis run.

    Deterministic retrieval only -- no interpretation, scoring, or
    filtering beyond the documented "active" definitions above. Assumes
    the caller has already verified the patient exists and is owned by
    the requesting user (this function performs no ownership check
    itself, matching the precedent set by `app/analysis/*` and
    `evidence_retrieval.py`, which all assume patient_id has already been
    authorized by the API layer).
    """
    patient = await _get_patient(patient_id, db)
    active_conditions = await _get_active_conditions(patient_id, db)
    active_medications = await _get_active_medications(patient_id, db)
    active_symptoms = await _get_active_symptoms(patient_id, db)

    return PatientContext(
        patient_id=patient_id,
        name=patient.name,
        age=patient.age,
        sex=patient.sex,
        weight_kg=float(patient.weight_kg) if patient.weight_kg is not None else None,
        renal_flag=patient.renal_flag,
        hepatic_flag=patient.hepatic_flag,
        active_conditions=active_conditions,
        active_medications=active_medications,
        active_symptoms=active_symptoms,
    )
