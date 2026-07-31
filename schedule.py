"""
Pydantic schemas for dose scheduling endpoints (spec section 7):

    POST /medications/{id}/schedule
    GET  /patients/{id}/doses/upcoming

Both routes are read/generate-only from the client's perspective -- there
is no client-supplied request body for schedule generation (all inputs
come from the medication's own fields: times_per_day, interval_hours,
duration_days, start_date), so only response schemas are defined here,
matching the pattern used for schemas/timeline.py in Phase 7.

`status` is constrained via Literal to the same three values as the
database's `dose_status_enum` (001_initial_schema.sql). It is nullable
here (unlike symptom/condition severity/status) because a freshly
generated dose is unmarked until Phase 9's mark endpoint sets it.
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DoseStatus = Literal["taken", "missed", "skipped"]


class MedicationDoseResponse(BaseModel):
    """A single generated dose, returned by POST /medications/{id}/schedule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    medication_id: uuid.UUID
    schedule_id: uuid.UUID | None
    scheduled_time: datetime
    status: DoseStatus | None
    actual_time: datetime | None
    created_at: datetime
    updated_at: datetime


class UpcomingDoseResponse(BaseModel):
    """
    An upcoming dose enriched with drug context, returned by
    GET /patients/{id}/doses/upcoming.

    Not `from_attributes`-mapped directly from an ORM row -- the endpoint
    joins across medications/reference_drugs and constructs this schema
    explicitly, so `drug_name`/`dose` are always populated for display.
    """

    id: uuid.UUID
    medication_id: uuid.UUID
    scheduled_time: datetime
    drug_name: str
    dose: str | None
