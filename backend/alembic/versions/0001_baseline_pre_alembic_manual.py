"""Baseline — pre-Alembic manual migrations 001-003 already applied.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-12

This revision marks the point where Alembic takes over versioned migration
management from the previous manual workflow of applying flat SQL files at
repository root:

- 001_initial_schema.sql (enums, tables, indexes, RLS — 11 tables, 7 ENUMs, 11 indexes)
- 002_seed_data.sql (12 seed reference_drugs + 7 interaction_rules + 13 adr_rules, source='FDA Label')
- 003_reference_drugs_external_reference.sql (adds rxcui unique, source, source_updated_at)

For existing databases that already have 001–003 applied manually via psql
or Supabase SQL editor:

    alembic stamp 0001_baseline

This creates/updates the `alembic_version` table only — no DDL executed —
and marks the schema as already at this baseline. Future migrations (e.g.
term_type/is_active, ingredient_mapping, idx_reference_drugs_name_lower)
can then be applied with:

    alembic upgrade head

For new databases (from scratch), two options during transition period:

Option 1 — Continue using 001–003 until a full baseline migration is
generated (recommended during transition):

    psql "$DATABASE_URL" -f 001_initial_schema.sql
    psql "$DATABASE_URL" -f 002_seed_data.sql
    psql "$DATABASE_URL" -f 003_reference_drugs_external_reference.sql
    alembic stamp 0001_baseline

Option 2 — Generate a proper baseline revision that builds schema from
scratch via `Base.metadata`:

    alembic revision --autogenerate -m "baseline schema from scratch"
    # Review DDL carefully — especially ENUM creation (models.py uses
    # create_type=False, so Alembic will NOT auto-create ENUMs unless
    # configured to do so)
    alembic upgrade head

This baseline revision intentionally does nothing (pass) because 001–003
remain the source of truth for existing databases. It exists solely to
provide a starting point for versioned history and to enable stamped
upgrade/downgrade reproducibility per Section 24.4 Success Criteria.

No new architectural decisions are introduced here — only versioned workflow
for already-approved future schema changes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline — pre-Alembic manual migrations 001–003 already applied
    # This revision does nothing but provides a starting point for
    # versioned history. Existing DBs should be stamped, not upgraded.
    pass


def downgrade() -> None:
    # Baseline downgrade does nothing — 001–003 remain manual baseline
    pass
