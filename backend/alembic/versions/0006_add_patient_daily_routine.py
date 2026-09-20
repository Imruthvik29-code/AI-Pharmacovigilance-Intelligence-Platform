"""add optional patient daily routine (timezone + meal times)

Revision ID: 0006_add_patient_daily_routine
Revises: 0005_add_patient_relation

Routine context for schedule generation, not clinical data. `timezone`
holds an IANA key (e.g. "Asia/Kolkata"). The meal columns are recurring
local wall-clock times and therefore use TIME WITHOUT TIME ZONE -- a
timestamptz would pin them to a single instant and drift across DST,
which is wrong for "the patient eats breakfast at 08:00".

All four are nullable: existing patients have no routine recorded, and
no value is ever inferred for them.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_patient_daily_routine"
down_revision = "0005_add_patient_relation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("patients", sa.Column("breakfast_time", sa.Time(timezone=False), nullable=True))
    op.add_column("patients", sa.Column("lunch_time", sa.Time(timezone=False), nullable=True))
    op.add_column("patients", sa.Column("dinner_time", sa.Time(timezone=False), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "dinner_time")
    op.drop_column("patients", "lunch_time")
    op.drop_column("patients", "breakfast_time")
    op.drop_column("patients", "timezone")
