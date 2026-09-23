"""
Pydantic schemas for medication endpoints (spec section 7).

MedicationCreate/MedicationUpdate deliberately omit `patient_id` -- it is
always taken from the path parameter on /patients/{id}/medications and
never accepted from the request body, so a caller can never attach a
medication to a patient they don't own (see api/v1/medications.py's
ownership check).

`status` is constrained to the same five values as the database's
`medication_status_enum` (001_initial_schema.sql) via Literal, so invalid
input is rejected as a 422 at the API boundary rather than surfacing as a
raw Postgres enum error.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.dose_rule import (
    DoseRuleCreate,
    DoseRuleResponse,
    validate_rule_collection,
)

MedicationStatus = Literal["active", "completed", "completed_early", "paused", "discontinued"]


class MedicationBase(BaseModel):
    condition_id: uuid.UUID | None = None
    purpose_text: str | None = Field(default=None, max_length=1000)
    drug_id: uuid.UUID
    dose: str | None = Field(default=None, max_length=200)
    times_per_day: int | None = Field(default=None, ge=1, le=24)
    interval_hours: float | None = Field(default=None, gt=0)
    duration_days: int | None = Field(default=None, ge=1)
    status: MedicationStatus = "active"
    start_date: date
    end_date: date | None = None


class MedicationCreate(MedicationBase):
    #: Optional at create time. An incomplete set is accepted and simply
    #: leaves the medication not yet schedulable -- completeness is checked
    #: at generation, not here.
    dose_rules: list[DoseRuleCreate] = Field(default_factory=list)

    @field_validator("dose_rules")
    @classmethod
    def _check_rules(cls, v: list[DoseRuleCreate]) -> list[DoseRuleCreate]:
        return validate_rule_collection(v)


class MedicationUpdate(BaseModel):
    """All fields optional -- only provided fields are applied (partial update).

    Same PUT semantics precedent as PatientUpdate in schemas/patient.py.
    """

    condition_id: uuid.UUID | None = None
    purpose_text: str | None = Field(default=None, max_length=1000)
    drug_id: uuid.UUID | None = None
    dose: str | None = Field(default=None, max_length=200)
    times_per_day: int | None = Field(default=None, ge=1, le=24)
    interval_hours: float | None = Field(default=None, gt=0)
    duration_days: int | None = Field(default=None, ge=1)
    status: MedicationStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    #: Whole-collection replacement. Absent leaves existing rules alone
    #: (standard exclude_unset semantics); [] clears them; a list replaces
    #: the set outright. Rule ids are not preserved across a replacement.
    #:
    #: An explicit null is rejected rather than treated as either of those:
    #: it reads naturally as "no change" but would have to be implemented as
    #: "clear", and guessing wrong silently destroys a prescription's timing.
    #: The annotation allows None only so the absent case has a default;
    #: field validators do not run on defaults, so the check below sees None
    #: only when a client actually sent one.
    dose_rules: list[DoseRuleCreate] | None = None

    @field_validator("dose_rules")
    @classmethod
    def _check_rules(cls, v: list[DoseRuleCreate] | None) -> list[DoseRuleCreate] | None:
        if v is None:
            raise ValueError(
                "dose_rules may not be null. Omit the field to leave the "
                "existing rules unchanged, or send [] to clear them."
            )
        return validate_rule_collection(v)


class MedicationResponse(MedicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Human-facing catalog identity is returned with the medication so the
    # frontend never depends on a browser-local cache to render a medicine.
    drug_name: str | None = None
    drug_generic_name: str | None = None
    drug_term_type: str | None = None
    drug_source: str | None = None
    #: Ordered by `sequence`. Empty when the course has no timing rules.
    dose_rules: list[DoseRuleResponse] = Field(default_factory=list)
