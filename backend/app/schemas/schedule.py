"""
Pydantic schemas for dose scheduling and adherence endpoints (spec section 7):

    POST /medications/{id}/schedule
    GET  /patients/{id}/doses/upcoming
    POST /doses/{id}/mark

`MedicationDoseResponse` / `UpcomingDoseResponse` are response-only shapes
for the schedule-generation and upcoming-doses routes -- neither accepts a
client-supplied body (schedule generation derives everything from the
medication's own fields; upcoming-doses is a pure read).

Phase 9 addition: `MedicationDoseMarkRequest` is the request body for
`POST /doses/{id}/mark`. `status` is required (one of the three
`dose_status_enum` values); `actual_time` is optional -- if omitted, the
endpoint applies `now()` when marking "taken", and leaves it null for
"missed"/"skipped" (there's no meaningful "actual" time for a dose that
wasn't taken). See app/api/v1/schedule.py's `mark_dose` for the full
behavior, including the automatic missed-dose sweep.

`status` is constrained via Literal to the same three values as the
database's `dose_status_enum` (001_initial_schema.sql). It is nullable on
`MedicationDoseResponse` (unlike symptom/condition severity/status)
because a freshly generated dose is unmarked until it is explicitly
marked (or auto-marked "missed" by the sweep).
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DoseStatus = Literal["taken", "missed", "skipped"]


class MedicationDoseResponse(BaseModel):
    """A single dose, returned by schedule generation, upcoming-doses, and mark."""

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


class MedicationDoseMarkRequest(BaseModel):
    """Request body for POST /doses/{id}/mark (Phase 9)."""

    status: DoseStatus
    actual_time: datetime | None = None
