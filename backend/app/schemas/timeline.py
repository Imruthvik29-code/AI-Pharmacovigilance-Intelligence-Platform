"""
Pydantic schemas for the timeline endpoint (spec section 7).

Read-only: timeline events are never created directly by a client, only
as a side effect of other writes (see app/services/timeline_writer.py),
so only a response schema is defined here -- no Create/Update schema,
matching the same pattern as symptoms (no client-facing write shape for
data the client doesn't directly author).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TimelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    event_type: str
    ref_id: uuid.UUID | None
    event_title: str
    event_description: str | None
    event_time: datetime
    payload: dict | None
    created_at: datetime
