"""
Timeline Engine (Phase 14).

Per explicit project-owner direction during Phase 14 planning: this
engine's responsibility is limited strictly to *retrieving and
structuring* the patient's timeline context. It deliberately does NOT
perform pattern detection, trend analysis, or any form of scoring --
that would be speculative functionality beyond what
`pharmacovigilance-spec-v1.md` defines for this node, and would blur the
line CLAUDE.md draws between deterministic *analysis* and mere
*retrieval*.

Placement: `app/analysis/`, per spec section 6's folder structure
(`analysis/timeline_engine.py` is explicitly named there), alongside
`drug_interaction_engine.py` / `adr_engine.py` / `adherence_engine.py` /
`safety_score_engine.py`.

Graph position (confirmed during Phase 14 planning): this node runs
*after* the Evidence Retrieval node, not in parallel with the other
deterministic engines. Evidence Retrieval (Phase 13) already supplies
finding-scoped personal evidence (timeline events tied to a *specific*
drug-interaction/ADR/adherence finding). This engine instead builds the
patient's full, unscoped timeline as broader explanatory/narrative
context for the eventual LLM Explanation Node (Phase 15) -- the two are
complementary, not redundant: one is "what happened relevant to this
specific finding," the other is "what happened for this patient,
period."

Not exposed via any HTTP route -- same as Phases 10-13's engines/services.
Wired only as a node inside `app/services/langgraph_workflow.py`.

No artificial cap on the number of events returned, consistent with
`GET /patients/{id}/timeline` (Phase 7), which also returns the full
timeline with no pagination -- if this becomes a real problem for very
long-running patients, that is a future, explicitly-requested change,
not something to guess at here.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TimelineEvent


@dataclass(frozen=True)
class TimelineEntry:
    """One timeline event, structured for downstream (eventual LLM) consumption."""

    id: uuid.UUID
    event_type: str
    ref_id: uuid.UUID | None
    event_title: str
    event_description: str | None
    event_time: datetime
    payload: dict | None


@dataclass(frozen=True)
class TimelineContext:
    """The patient's full timeline, structured chronologically (oldest first)."""

    patient_id: uuid.UUID
    entries: list[TimelineEntry]


async def build_timeline_context(patient_id: uuid.UUID, db: AsyncSession) -> TimelineContext:
    """
    Retrieve and structure a patient's full timeline as narrative context.

    Ordered chronologically ascending (oldest -> newest) -- the opposite
    of `GET /patients/{id}/timeline`'s most-recent-first ordering (Phase
    7), which is tuned for a UI feed. This engine's output is meant to
    read as a story in the order events actually happened, which is the
    more natural order for an eventual LLM explanation to consume.

    Performs no writes, no filtering beyond scoping to this patient, and
    no interpretation of any kind -- purely a structured read of
    `timeline_events`, which remains the single source of truth (nothing
    here is persisted separately).
    """
    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.patient_id == patient_id)
        .order_by(TimelineEvent.event_time.asc())
    )

    entries = [
        TimelineEntry(
            id=event.id,
            event_type=event.event_type,
            ref_id=event.ref_id,
            event_title=event.event_title,
            event_description=event.event_description,
            event_time=event.event_time,
            payload=event.payload,
        )
        for event in result.scalars().all()
    ]

    return TimelineContext(patient_id=patient_id, entries=entries)
