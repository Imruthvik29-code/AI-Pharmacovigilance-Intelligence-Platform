"""
Timeline event writer (Phase 7).

A small, reusable helper other API modules call to record a
a`timeline_events` row as a side effect of their own writes (e.g.
medications.py logs `medication_started` when a medication is created).
Deliberately NOT listed in the spec's folder structure (section 6) under
`services/` -- that list wasn't exhaustive at the file-name granularity,
and this is a natural, additive fit alongside `patient_context_builder.py`
/ `llm_service.py`, not an architecture change.

Design: `log_timeline_event` only calls `db.add(...)` -- it never commits.
Callers add the returned event to the same session as the entity write
that triggered it, then commit both together, so the entity and its
timeline event are always persisted atomically (never one without the
other).

`event_type` is intentionally a plain string, not a Python enum -- it
mirrors the DB column (`timeline_events.event_type text`, not a Postgres
enum), matching spec section 5's schema exactly. The values currently in
use (`medication_started`, `medication_discontinued`,
`condition_status_changed`, `symptom_reported`) are drawn directly from
the canonical list documented in that section's `event_type` comment.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TimelineEvent


async def log_timeline_event(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    event_type: str,
    event_title: str,
    ref_id: uuid.UUID | None = None,
    event_description: str | None = None,
    payload: dict | None = None,
) -> TimelineEvent:
    """Add (but do not commit) a new timeline_events row.

    Caller is responsible for `await db.commit()` -- typically alongside
    the commit of whatever entity write this event is describing, so both
    land in the same transaction.
    """
    now = datetime.now(timezone.utc)
    event = TimelineEvent(
        id=uuid.uuid4(),
        patient_id=patient_id,
        event_type=event_type,
        ref_id=ref_id,
        event_title=event_title,
        event_description=event_description,
        event_time=now,
        payload=payload,
        created_at=now,
    )
    db.add(event)
    return event
