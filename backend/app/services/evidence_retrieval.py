"""
Evidence Retrieval (Phase 13).

Application service, not a deterministic analysis engine -- per the
confirmed Phase 13 design, this lives in `app/services/` (alongside
`patient_context_builder.py` / `llm_service.py` / `langgraph_workflow.py`
from spec section 6) rather than `app/analysis/`, since its job is to
*retrieve and structure supporting evidence* for the Phase 15 LLM
explanation layer, not to detect new findings or compute a score. It is
the direct SQL implementation of spec section 8's "Evidence Retrieval
Node" and section 4's "Retrieval (MVP): Plain SQL (personal history +
interaction rules) -- pgvector added later without node changes."

## Medical evidence -- no duplicate retrieval

`DrugInteractionFinding` (Phase 10) and `ADRFinding` (Phase 11) already
carry everything a "medical knowledge base" lookup would provide --
`mechanism`/`recommendation`/`source` for interactions,
`reaction_description`/`frequency_class`/`source` for ADRs -- because
`detect_drug_interactions()`/`detect_adrs()` already joined against
`interaction_rules`/`adr_rules` to produce them. Per the confirmed Phase
13 design, this module does NOT re-query those tables; it only
*structures* the finding's existing fields into `EvidenceItem`s. Adherence
findings get no medical evidence at all -- there is no rules table
backing an adherence "fact" (see `adherence_engine.py`'s and
`safety_score_engine.py`'s docstrings for the same reasoning applied to
severity classification).

## Personal evidence -- scoped, not the full timeline

Per the confirmed Phase 13 design, personal evidence for a finding is
limited to `timeline_events` rows tied to the specific medication(s) (and
any condition that medication is linked to) involved in THAT finding --
never the patient's entire timeline. Concretely, for a set of medication
ids:

  - `medication_started` / `medication_discontinued` -- matched via
    `ref_id` (these events reference the medication directly).
  - `dose_taken` / `dose_missed` / `dose_skipped` -- matched via
    `payload.medication_id` (these events reference the *dose* as
    `ref_id`; the medication link lives in the payload, per
    `timeline_writer.py`'s calls in `app/api/v1/schedule.py`).
  - `symptom_reported` -- matched via `payload.medication_id`.
  - `condition_status_changed` -- matched via `ref_id` against the
    *condition* linked to the medication (`medications.condition_id`),
    if any. Findings themselves are drug-based, not condition-based, but
    a medication's linked condition is relevant context a clinician
    would want alongside it.

This is a single combined, patient-scoped query per finding, not a broad
timeline fetch filtered down in Python.

## Traceability

Every `FindingEvidence` carries the original finding object (not just an
id or description), mirroring Phase 12's `PenaltyEntry.source` pattern,
so the Phase 15 LLM explanation node (or any future report view) can
explain one finding at a time together with its supporting evidence
without re-querying or recomputing anything.

Not exposed via any HTTP route yet -- same as Phases 10-12.
`api/v1/analysis.py` and the `/patients/{id}/analyze` endpoint are wired
in Phase 14 (LangGraph), which will call `retrieve_evidence()` as the
Evidence Retrieval Node, immediately after the Safety Score Engine merge.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.adherence_engine import AdherenceFinding
from app.analysis.adr_engine import ADRFinding
from app.analysis.drug_interaction_engine import DrugInteractionFinding
from app.analysis.safety_score_engine import SafetyScoreResult
from app.db.models import Medication, TimelineEvent

EvidenceKind = Literal["medical", "personal"]
FindingCategory = Literal["drug_interaction", "adr", "adherence"]

# Timeline event_types (spec section 5) considered relevant "personal
# evidence" for a medication -- deliberately excludes event types with no
# medication/condition linkage relevant to a specific finding.
_MEDICATION_ID_ON_REF_ID = ("medication_started", "medication_discontinued")
_MEDICATION_ID_ON_PAYLOAD = ("dose_taken", "dose_missed", "dose_skipped", "symptom_reported")


@dataclass(frozen=True)
class EvidenceItem:
    """
    One discrete piece of supporting evidence.

    `occurred_at` is populated (from `timeline_events.event_time`) for
    personal evidence, and left `None` for medical evidence -- a rules-
    table fact (e.g. an interaction mechanism) has no "when it happened,"
    unlike a patient's own history.
    """

    kind: EvidenceKind
    statement: str
    source: str | None
    occurred_at: datetime | None


@dataclass(frozen=True)
class FindingEvidence:
    """
    All evidence gathered for exactly one finding, with a direct
    reference back to that finding for traceability (mirrors Phase 12's
    `PenaltyEntry.source`) -- lets a caller explain this one finding in
    isolation without recomputing or re-querying anything.
    """

    category: FindingCategory
    finding: DrugInteractionFinding | ADRFinding | AdherenceFinding
    medical_evidence: list[EvidenceItem]
    personal_evidence: list[EvidenceItem]


@dataclass(frozen=True)
class EvidenceBundle:
    """Evidence for every finding in a SafetyScoreResult, grouped by category."""

    interaction_evidence: list[FindingEvidence]
    adr_evidence: list[FindingEvidence]
    adherence_evidence: list[FindingEvidence]


# ---------------------------------------------------------------------
# Medical evidence -- structured from already-fetched finding fields,
# no additional query.
# ---------------------------------------------------------------------


def _interaction_medical_evidence(finding: DrugInteractionFinding) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    if finding.mechanism:
        items.append(
            EvidenceItem(
                kind="medical", statement=finding.mechanism, source=finding.source, occurred_at=None
            )
        )
    if finding.recommendation:
        items.append(
            EvidenceItem(
                kind="medical",
                statement=finding.recommendation,
                source=finding.source,
                occurred_at=None,
            )
        )
    return items


def _adr_medical_evidence(finding: ADRFinding) -> list[EvidenceItem]:
    statement = finding.reaction_description
    if finding.frequency_class:
        statement = f"{statement} (frequency: {finding.frequency_class})"
    return [
        EvidenceItem(kind="medical", statement=statement, source=finding.source, occurred_at=None)
    ]


# ---------------------------------------------------------------------
# Personal evidence -- scoped timeline retrieval.
# ---------------------------------------------------------------------


async def _active_medication_ids_for_drugs(
    patient_id: uuid.UUID, drug_ids: set[uuid.UUID], db: AsyncSession
) -> list[uuid.UUID]:
    """
    Map reference_drug ids to the patient's currently active medication
    id(s) for those drugs -- interaction/ADR findings are drug-based, but
    personal timeline events are medication-instance-based, so this
    bridges the two. Scoped to `status == "active"`, consistent with how
    `detect_drug_interactions()`/`detect_adrs()` selected these drugs as
    "the patient's drugs" in the first place.
    """
    if not drug_ids:
        return []
    result = await db.execute(
        select(Medication.id).where(
            Medication.patient_id == patient_id,
            Medication.status == "active",
            Medication.drug_id.in_(drug_ids),
        )
    )
    return [row[0] for row in result.all()]


async def _personal_evidence_for_medications(
    patient_id: uuid.UUID, medication_ids: list[uuid.UUID], db: AsyncSession
) -> list[EvidenceItem]:
    """
    Retrieve timeline events scoped to exactly these medication(s) (and
    any condition they're linked to) -- see module docstring for the
    full event-type matching rules. Returns an empty list if there are
    no medication ids to look up (nothing to scope to).
    """
    if not medication_ids:
        return []

    condition_result = await db.execute(
        select(Medication.condition_id).where(
            Medication.id.in_(medication_ids), Medication.condition_id.isnot(None)
        )
    )
    condition_ids = {row[0] for row in condition_result.all()}

    medication_id_strs = [str(mid) for mid in medication_ids]

    match_clauses = [
        and_(
            TimelineEvent.event_type.in_(_MEDICATION_ID_ON_REF_ID),
            TimelineEvent.ref_id.in_(medication_ids),
        ),
        and_(
            TimelineEvent.event_type.in_(_MEDICATION_ID_ON_PAYLOAD),
            TimelineEvent.payload["medication_id"].astext.in_(medication_id_strs),
        ),
    ]
    if condition_ids:
        match_clauses.append(
            and_(
                TimelineEvent.event_type == "condition_status_changed",
                TimelineEvent.ref_id.in_(condition_ids),
            )
        )

    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.patient_id == patient_id, or_(*match_clauses))
        .order_by(TimelineEvent.event_time.desc())
    )

    return [
        EvidenceItem(
            kind="personal",
            statement=(
                f"{event.event_title} \u2014 {event.event_description}"
                if event.event_description
                else event.event_title
            ),
            source=None,
            occurred_at=event.event_time,
        )
        for event in result.scalars().all()
    ]


# ---------------------------------------------------------------------
# Per-finding assembly.
# ---------------------------------------------------------------------


async def _build_interaction_evidence(
    patient_id: uuid.UUID, finding: DrugInteractionFinding, db: AsyncSession
) -> FindingEvidence:
    medication_ids = await _active_medication_ids_for_drugs(
        patient_id, {finding.drug_a_id, finding.drug_b_id}, db
    )
    return FindingEvidence(
        category="drug_interaction",
        finding=finding,
        medical_evidence=_interaction_medical_evidence(finding),
        personal_evidence=await _personal_evidence_for_medications(patient_id, medication_ids, db),
    )


async def _build_adr_evidence(
    patient_id: uuid.UUID, finding: ADRFinding, db: AsyncSession
) -> FindingEvidence:
    medication_ids = await _active_medication_ids_for_drugs(patient_id, {finding.drug_id}, db)
    return FindingEvidence(
        category="adr",
        finding=finding,
        medical_evidence=_adr_medical_evidence(finding),
        personal_evidence=await _personal_evidence_for_medications(patient_id, medication_ids, db),
    )


async def _build_adherence_evidence(
    patient_id: uuid.UUID, finding: AdherenceFinding, db: AsyncSession
) -> FindingEvidence:
    return FindingEvidence(
        category="adherence",
        finding=finding,
        medical_evidence=[],  # no rules-table-backed medical source exists for adherence
        personal_evidence=await _personal_evidence_for_medications(
            patient_id, [finding.medication_id], db
        ),
    )


async def retrieve_evidence(
    patient_id: uuid.UUID, db: AsyncSession, safety_score_result: SafetyScoreResult
) -> EvidenceBundle:
    """
    Build the full evidence bundle for a patient's already-computed
    `SafetyScoreResult` (Phase 12) -- one `FindingEvidence` per finding,
    grouped by category, each combining structured medical evidence
    (Phase 10/11 finding fields, no re-query) with scoped personal
    evidence (a targeted `timeline_events` lookup per finding).

    Deterministic only -- performs no writes, invents nothing, and never
    reaches beyond the medication(s)/condition directly involved in each
    individual finding.
    """
    interaction_evidence = [
        await _build_interaction_evidence(patient_id, finding, db)
        for finding in safety_score_result.interaction_findings
    ]
    adr_evidence = [
        await _build_adr_evidence(patient_id, finding, db)
        for finding in safety_score_result.adr_findings
    ]
    adherence_evidence = [
        await _build_adherence_evidence(patient_id, finding, db)
        for finding in safety_score_result.adherence_findings
    ]

    return EvidenceBundle(
        interaction_evidence=interaction_evidence,
        adr_evidence=adr_evidence,
        adherence_evidence=adherence_evidence,
    )
