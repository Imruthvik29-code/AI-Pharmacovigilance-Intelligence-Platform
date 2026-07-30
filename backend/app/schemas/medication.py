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

from pydantic import BaseModel, ConfigDict, Field

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
    pass


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


class MedicationResponse(MedicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
