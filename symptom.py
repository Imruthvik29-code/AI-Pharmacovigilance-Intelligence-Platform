"""
Pydantic schemas for symptom endpoints (spec section 7).

SymptomCreate deliberately omits `patient_id` -- it is always taken from
the path parameter on /patients/{id}/symptoms and never accepted from the
request body, matching the precedent set in schemas/condition.py and
schemas/medication.py.

`severity` is constrained via Literal to the same three values as the
database's `severity_level` enum (001_initial_schema.sql), so invalid
input is rejected as a 422 at the API boundary rather than surfacing as a
raw Postgres enum error.

Note: per the frozen spec (section 7), symptoms only expose
POST /patients/{id}/symptoms and GET /patients/{id}/symptoms -- there is
no PUT or DELETE route, so SymptomUpdate is intentionally not defined.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SymptomSeverity = Literal["mild", "moderate", "severe"]


class SymptomBase(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    severity: SymptomSeverity = "mild"
    condition_id: uuid.UUID | None = None
    medication_id: uuid.UUID | None = None
    # Optional on input -- if omitted, the endpoint applies date.today(),
    # matching the DB column's `default current_date` (see docstring above
    # for why this is applied in the app layer rather than left to the DB).
    onset_date: date | None = None
    resolved_date: date | None = None


class SymptomCreate(SymptomBase):
    pass


class SymptomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    condition_id: uuid.UUID | None
    medication_id: uuid.UUID | None
    description: str
    severity: SymptomSeverity
    onset_date: date
    resolved_date: date | None
    created_at: datetime
    updated_at: datetime
