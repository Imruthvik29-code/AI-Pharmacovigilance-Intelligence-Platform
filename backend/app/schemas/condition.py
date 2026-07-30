"""
Pydantic schemas for condition endpoints (spec section 7).

ConditionCreate/ConditionUpdate deliberately omit `patient_id` -- it is
always taken from the path parameter on /patients/{id}/conditions and
never accepted from the request body, matching the precedent set in
schemas/medication.py and schemas/patient.py.

`status` and `reason` are constrained via Literal to the same values as
the database's `condition_status_enum` / `condition_reason_enum`
(001_initial_schema.sql), so invalid input is rejected as a 422 at the
API boundary rather than surfacing as a raw Postgres enum error.

Note: per the frozen spec (section 7), conditions only expose
POST /patients/{id}/conditions and PUT /conditions/{id} -- there is no
GET endpoint, so ConditionResponse is only ever returned from those two
routes.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConditionStatus = Literal["active", "improving", "resolved", "persistent", "recurred"]
ConditionReason = Literal["doctor_diagnosis", "user_suspected", "unknown"]


class ConditionBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: ConditionStatus = "active"
    reason: ConditionReason = "unknown"
    diagnosed_date: date | None = None
    resolved_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ConditionCreate(ConditionBase):
    pass


class ConditionUpdate(BaseModel):
    """All fields optional -- only provided fields are applied (partial update).

    Same PUT semantics precedent as PatientUpdate / MedicationUpdate.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: ConditionStatus | None = None
    reason: ConditionReason | None = None
    diagnosed_date: date | None = None
    resolved_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ConditionResponse(ConditionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
