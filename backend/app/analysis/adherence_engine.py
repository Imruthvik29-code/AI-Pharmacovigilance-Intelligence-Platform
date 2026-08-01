"""
Adherence Engine (Phase 12).

Pure deterministic *measurement* service -- unlike
`drug_interaction_engine.py` (Phase 10) and `adr_engine.py` (Phase 11),
which surface an already-authoritative severity from a curated rules
table (`interaction_rules` / `adr_rules`), there is no equivalent
authoritative "adherence severity" table in the schema. Classifying a
given adherence rate as mild/moderate/severe is therefore a scoring
*policy* decision, not a lookup -- and per the confirmed Phase 12 design
(see PROJECT_PHASES.md's Phase 12 notes), that policy belongs entirely in
`safety_score_engine.py`, the one module whose job is to apply
thresholds/weights and produce a judgment. This module never classifies,
scores, or interprets -- it only counts.

This mirrors CLAUDE.md's "keep deterministic analysis separate from LLM
reasoning" principle applied one layer deeper: measurement is kept
separate from interpretation even within the deterministic layer itself.

Not exposed via any HTTP route yet -- same as Phase 10/11's engines.
`api/v1/analysis.py` and the `POST /patients/{id}/analyze` /
`GET /patients/{id}/analysis` routes are wired in Phase 14 (LangGraph).

Scope decision (confirmed during Phase 12 planning, consistent with
Phase 10/11's precedent): only medications with `status == "active"` are
evaluated -- a paused/completed/discontinued medication's historical
adherence is not part of the patient's *current* safety picture, which
is what feeds the Safety Score Engine. This mirrors the same
`status == "active"` filter already used by
`detect_drug_interactions` (Phase 10) and `detect_adrs` (Phase 11).

"Due" dose definition (a deliberate design choice, not incidental):
`GET /patients/{id}/doses/upcoming` and `POST /doses/{id}/mark` (Phase 9)
implement the missed-dose background check as a *lazy, query-time sweep*
-- an overdue dose only flips from `status IS NULL` to `status = 'missed'`
in the database once one of those two routes runs for the owning
patient. If `analyze_adherence()` only counted doses that already carry
an explicit status, adherence measurements would silently depend on
whether/when that sweep last ran for a given patient, rather than on the
patient's actual medication-taking behavior -- an unreliable and
surprising basis for a safety-relevant computation, and a wrong
architectural coupling for `analysis/` (a pure-read layer) to have on
`api/v1/schedule.py`'s lazy write side-effect.

To avoid that coupling, `analyze_adherence()` computes "due" and
"missed" independently, without relying on the sweep having run:

  - `due`      = doses with `scheduled_time <= now()`, any status.
  - `taken`    = due doses with `status == 'taken'`.
  - `skipped`  = due doses with `status == 'skipped'`.
  - `missed`   = due doses with `status == 'missed'`
                 PLUS due doses with `status IS NULL` (i.e. overdue and
                 not yet explicitly marked by the patient or swept) --
                 for measurement purposes, an overdue unmarked dose is
                 functionally a missed dose regardless of whether the
                 `medication_doses` row has been updated to say so yet.

This function performs no writes -- it does NOT invoke or duplicate the
Phase 9 sweep, and does not mutate `medication_doses.status`. It is a
read-only reinterpretation of "missed" for measurement purposes only; the
persisted sweep behavior in `api/v1/schedule.py` is unchanged and remains
the source of truth for what the API layer reports as `status`.

Future (not-yet-due) doses are excluded entirely from `due` -- a
medication with doses scheduled but none due yet contributes no finding.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Medication, MedicationDose, ReferenceDrug


@dataclass(frozen=True)
class AdherenceFinding:
    """
    Pure dose-count measurement for one of the patient's active
    medications. Carries no severity/classification -- see module
    docstring for why that responsibility lives in
    `safety_score_engine.py` instead.

    `adherence_rate` is `taken / due`, or `None` if `due == 0` (no doses
    are due yet for this medication -- there is nothing to measure).
    """

    medication_id: uuid.UUID
    drug_name: str
    taken: int
    missed: int
    skipped: int
    due: int
    adherence_rate: float | None


async def analyze_adherence(patient_id: uuid.UUID, db: AsyncSession) -> list[AdherenceFinding]:
    """
    Measure dose adherence for each of a patient's active medications.

    Deterministic only -- every count comes directly from
    `medication_doses` rows already persisted by Phase 8/9's scheduling
    and marking endpoints; nothing here is inferred, ranked, or
    generated. See module docstring for the "due"/"missed" definitions
    and why they don't depend on the Phase 9 lazy sweep having run.

    Returns one `AdherenceFinding` per active medication that has at
    least one due dose (`due > 0`). Active medications with no due doses
    yet are omitted entirely -- there's nothing to measure.
    """
    now = datetime.now(timezone.utc)

    # `status IS NULL` doses count toward `missed` per the module
    # docstring's rationale -- an overdue, unmarked dose is functionally
    # missed for measurement purposes, independent of whether the lazy
    # sweep has run yet.
    taken_count = func.count(case((MedicationDose.status == "taken", 1)))
    skipped_count = func.count(case((MedicationDose.status == "skipped", 1)))
    missed_count = func.count(
        case((MedicationDose.status == "missed", 1), (MedicationDose.status.is_(None), 1))
    )
    due_count = func.count(MedicationDose.id)

    result = await db.execute(
        select(
            Medication.id,
            ReferenceDrug.name,
            taken_count,
            missed_count,
            skipped_count,
            due_count,
        )
        .join(MedicationDose, MedicationDose.medication_id == Medication.id)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(
            Medication.patient_id == patient_id,
            Medication.status == "active",
            MedicationDose.scheduled_time <= now,
        )
        .group_by(Medication.id, ReferenceDrug.name)
    )

    findings: list[AdherenceFinding] = []
    for medication_id, drug_name, taken, missed, skipped, due in result.all():
        if due == 0:
            continue
        findings.append(
            AdherenceFinding(
                medication_id=medication_id,
                drug_name=drug_name,
                taken=taken,
                missed=missed,
                skipped=skipped,
                due=due,
                adherence_rate=(taken / due) if due > 0 else None,
            )
        )

    return findings
