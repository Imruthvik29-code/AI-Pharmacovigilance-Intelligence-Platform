"""
Pydantic schemas for medication dose rules (Phase 2).

A dose rule says WHEN one of a medication's daily doses is taken, relative
to the patient's recorded routine. Frequency stays on
`medications.times_per_day`; rules never carry a count of their own.

Anchor semantics, enforced here and mirrored by
`ck_dose_rule_anchor_coherence` in migration 0007:

    before      offset required, 1..60      anchor - offset
    with        offset prohibited           anchor exactly
    after       offset required, 1..60      anchor + offset
    clock_time  no relation, no offset      clock_time exactly

`offset_minutes` is a non-negative magnitude and the relation carries the
direction, so "30 minutes before" has exactly one representation. The
offset is required for before/after rather than defaulting to zero: an
unquantified "before breakfast" is not a schedule, and treating it as zero
would silently make it mean "with breakfast", a different instruction. This
follows api/v1/schedule.py's existing rule that clinically meaningful
quantities never get invented defaults.

Validation is duplicated between this layer and the database on purpose --
Pydantic so a malformed request gets a readable 422 at the boundary, the
CHECK constraint so the invariant holds regardless of who writes the row.
"""
import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DoseAnchor = Literal["breakfast", "lunch", "dinner", "clock_time"]
DoseRelation = Literal["before", "with", "after"]

#: before/with/after express medication timing *around* a recorded meal,
#: not an arbitrary displacement from it, so an hour is the widest offset
#: that still means "around this meal". This bounds the offset magnitude
#: only; it does not by itself guarantee a dose stays on the same calendar
#: day (a meal recorded near midnight can still cross it), which schedule
#: generation checks separately against the course window.
MAX_OFFSET_MINUTES = 60


class DoseRuleBase(BaseModel):
    """One dose slot. `sequence` is 1-based and orders slots within a day."""

    sequence: int = Field(ge=1, le=24)
    anchor_type: DoseAnchor
    anchor_relation: DoseRelation | None = None
    offset_minutes: int | None = Field(default=None, ge=1, le=MAX_OFFSET_MINUTES)
    clock_time: time | None = None
    #: NULL inherits the course default from `medications.dose`.
    dose: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_anchor_coherence(self) -> "DoseRuleBase":
        if self.anchor_type == "clock_time":
            if self.clock_time is None:
                raise ValueError("clock_time is required when anchor_type is 'clock_time'.")
            if self.anchor_relation is not None:
                raise ValueError("anchor_relation must be omitted for a clock_time rule.")
            if self.offset_minutes is not None:
                raise ValueError("offset_minutes must be omitted for a clock_time rule.")
            return self

        if self.clock_time is not None:
            raise ValueError("clock_time is only valid when anchor_type is 'clock_time'.")
        if self.anchor_relation is None:
            raise ValueError(
                "anchor_relation ('before', 'with' or 'after') is required for a meal rule."
            )
        if self.anchor_relation == "with":
            if self.offset_minutes is not None:
                raise ValueError("offset_minutes must be omitted when anchor_relation is 'with'.")
        elif self.offset_minutes is None:
            raise ValueError(
                f"offset_minutes is required when anchor_relation is "
                f"'{self.anchor_relation}'. It is not defaulted, because an "
                f"unquantified offset would silently mean 'with'."
            )
        return self


class DoseRuleCreate(DoseRuleBase):
    pass


class DoseRuleResponse(DoseRuleBase):
    model_config = ConfigDict(from_attributes=True)

    #: Rules are replaced as a whole set, so this id is stable only within
    #: one response -- nothing downstream references it (a generated dose
    #: snapshots the resolved amount rather than pointing at a rule).
    id: uuid.UUID
    medication_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


def validate_rule_collection(rules: list[DoseRuleCreate]) -> list[DoseRuleCreate]:
    """Reject duplicate or non-contiguous sequences.

    Sequences must be exactly 1..N. Gaps are refused rather than
    renumbered: `sequence` is user-facing ordering ("Dose 2"), so silently
    renumbering would guess which slot the client meant.
    """
    seqs = [r.sequence for r in rules]
    if len(set(seqs)) != len(seqs):
        raise ValueError("dose_rules contains duplicate sequence values.")
    if sorted(seqs) != list(range(1, len(seqs) + 1)):
        raise ValueError(
            f"dose_rules sequences must be contiguous starting at 1; got {sorted(seqs)}."
        )
    return rules
