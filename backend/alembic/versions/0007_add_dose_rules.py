"""Add medication dose rules + generated-dose amount snapshot.

Revision ID: 0007_add_dose_rules
Revises: 0006_add_patient_daily_routine

Phase 2 (dose-rule data model). Two additions, both additive:

1. `medication_dose_rules` -- one row per daily dose, saying WHEN that dose
   is taken relative to the patient's recorded routine. Frequency stays on
   `medications.times_per_day`; these rows say when, not how many. The two
   are reconciled at schedule generation, not at write, so a partially
   specified prescription remains saveable and simply reports as not yet
   schedulable.

2. `medication_doses.dose` -- the resolved dose amount, snapshotted when a
   schedule is generated. Nullable: every row that already exists predates
   this column and keeps reading through to `medications.dose`.

Why a snapshot rather than a link to the rule: a generated dose is a
historical scheduling fact. Editing or deleting a rule afterwards must not
rewrite what an already-generated dose represented, so the value is frozen
at generation and the dose row holds no reference to the rule that produced
it. This mirrors `scheduled_time`, which is likewise stored rather than
recomputed from the prescription on read.

Anchor semantics enforced by `ck_dose_rule_anchor_coherence`:

    before      offset required, 1..60      anchor - offset
    with        offset prohibited (NULL)    anchor exactly
    after       offset required, 1..60      anchor + offset
    clock_time  no relation, no offset      clock_time exactly

`offset_minutes` is a non-negative magnitude; direction comes from the
relation, so "30 minutes before" cannot be expressed two ways. The offset
is required for before/after rather than defaulting to zero -- an
unquantified "before breakfast" is not a schedule, and silently treating it
as zero would make it indistinguishable from "with breakfast", which is a
different instruction. This follows the existing rule in api/v1/schedule.py
that clinically meaningful quantities are never given invented defaults.

`offset_minutes` is capped at 60. before/with/after express medication
timing around a recorded meal, not an arbitrary displacement from it, so an
hour is the widest offset that still means "around this meal". The cap also
means an ordinary meal time cannot push a dose across local midnight,
though a meal recorded within an hour of midnight still can -- schedule
generation checks the resulting date against the course window rather than
relying on the cap for that.

create_type=False on the ORM enums, per models.py's convention: this
migration owns CREATE/DROP TYPE explicitly, as 0002 does.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_add_dose_rules"
down_revision: Union[str, None] = "0006_add_patient_daily_routine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ANCHOR_ENUM_SQL = (
    "CREATE TYPE dose_anchor_enum AS ENUM "
    "('breakfast', 'lunch', 'dinner', 'clock_time')"
)
_RELATION_ENUM_SQL = (
    "CREATE TYPE dose_relation_enum AS ENUM ('before', 'with', 'after')"
)

dose_anchor_enum = postgresql.ENUM(
    "breakfast", "lunch", "dinner", "clock_time",
    name="dose_anchor_enum", create_type=False,
)
dose_relation_enum = postgresql.ENUM(
    "before", "with", "after",
    name="dose_relation_enum", create_type=False,
)

# A clock_time rule carries its own time and no meal relation; a meal rule
# carries a relation and no clock_time, with the offset required exactly
# when the relation is directional.
_ANCHOR_COHERENCE = """
(
    anchor_type = 'clock_time'
    AND clock_time IS NOT NULL
    AND anchor_relation IS NULL
    AND offset_minutes IS NULL
)
OR (
    anchor_type <> 'clock_time'
    AND clock_time IS NULL
    AND anchor_relation IS NOT NULL
    AND (
        (anchor_relation = 'with' AND offset_minutes IS NULL)
        OR (
            anchor_relation <> 'with'
            AND offset_minutes IS NOT NULL
            AND offset_minutes > 0
            AND offset_minutes <= 60
        )
    )
)
"""


def upgrade() -> None:
    op.execute(_ANCHOR_ENUM_SQL)
    op.execute(_RELATION_ENUM_SQL)

    op.create_table(
        "medication_dose_rules",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "medication_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medications.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("anchor_type", dose_anchor_enum, nullable=False),
        sa.Column("anchor_relation", dose_relation_enum, nullable=True),
        sa.Column("offset_minutes", sa.Integer(), nullable=True),
        sa.Column("clock_time", sa.Time(timezone=False), nullable=True),
        # NULL means "inherit medications.dose" -- only set when this
        # particular dose differs from the course default.
        sa.Column("dose", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "medication_id", "sequence", name="uq_dose_rule_sequence"
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_dose_rule_sequence_positive"),
        sa.CheckConstraint(_ANCHOR_COHERENCE, name="ck_dose_rule_anchor_coherence"),
    )
    op.create_index(
        "idx_dose_rules_medication", "medication_dose_rules", ["medication_id"]
    )

    # Resolved amount, frozen at generation. Nullable so existing rows keep
    # falling back to medications.dose; deliberately not backfilled, because
    # no amount was recorded for them at the time.
    op.add_column("medication_doses", sa.Column("dose", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("medication_doses", "dose")
    op.drop_index("idx_dose_rules_medication", table_name="medication_dose_rules")
    op.drop_table("medication_dose_rules")
    op.execute("DROP TYPE dose_relation_enum")
    op.execute("DROP TYPE dose_anchor_enum")
