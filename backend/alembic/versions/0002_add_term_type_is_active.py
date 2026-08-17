"""Add rxnorm_term_type_enum + term_type + is_active to reference_drugs.

Revision ID: 0002_add_term_type_is_active
Revises: 0001_baseline
Create Date: 2026-08-17

Implements ARCHITECTURE_DECISIONS.md §6.2 / §7.3 (Phase 1 additions):

1. CREATE TYPE rxnorm_term_type_enum with the full 23-value RxNorm TTY
   vocabulary from NLM's RxNorm Appendix 5:
   IN, PIN, MIN, BN, SCD, SBD, SCDC, SCDF, SCDFP, SCDG, SCDGP, SBDC,
   SBDF, SBDFP, SBDG, GPCK, BPCK, DF, DFG, ET, PSN, SY, TMSY
2. ALTER TABLE reference_drugs ADD COLUMN term_type rxnorm_term_type_enum
   (nullable -- NULL is a distinct, meaningful state for legacy/hand-curated
   rows with no known TTY).
3. ALTER TABLE reference_drugs ADD COLUMN is_active boolean NOT NULL
   DEFAULT true (every row, including legacy rows, is active by definition
   until a future mechanism proves otherwise).

Additive only: never touches reference_drugs.id, so medications.drug_id,
interaction_rules.drug_a_id/drug_b_id and adr_rules.drug_id foreign keys
remain valid; existing rows are preserved (is_active backfilled to true via
the server default).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_term_type_is_active"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Full RxNorm TTY vocabulary per NLM RxNorm Appendix 5 (§6.2).
# create_type=False: this migration owns CREATE/DROP TYPE explicitly below,
# mirroring models.py's convention (the migration owns the type).
rxnorm_term_type_enum = postgresql.ENUM(
    "IN", "PIN", "MIN", "BN", "SCD", "SBD", "SCDC", "SCDF", "SCDFP",
    "SCDG", "SCDGP", "SBDC", "SBDF", "SBDFP", "SBDG", "GPCK", "BPCK",
    "DF", "DFG", "ET", "PSN", "SY", "TMSY",
    name="rxnorm_term_type_enum",
    create_type=False,
)

# 23 values, in the exact order approved in ARCHITECTURE_DECISIONS.md §6.2.
_RXNORM_TERM_TYPE_ENUM_SQL = (
    "CREATE TYPE rxnorm_term_type_enum AS ENUM "
    "('IN', 'PIN', 'MIN', 'BN', 'SCD', 'SBD', 'SCDC', 'SCDF', 'SCDFP', "
    "'SCDG', 'SCDGP', 'SBDC', 'SBDF', 'SBDFP', 'SBDG', 'GPCK', 'BPCK', "
    "'DF', 'DFG', 'ET', 'PSN', 'SY', 'TMSY')"
)


def upgrade() -> None:
    # 1. Create the enum type.
    op.execute(_RXNORM_TERM_TYPE_ENUM_SQL)

    # 2. Add nullable term_type (NULL is meaningful for legacy rows).
    op.add_column(
        "reference_drugs",
        sa.Column("term_type", rxnorm_term_type_enum, nullable=True),
    )

    # 3. Add non-null is_active with server default true (existing rows
    #    become active without changing their id).
    op.add_column(
        "reference_drugs",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    # 1. Drop is_active.
    op.drop_column("reference_drugs", "is_active")
    # 2. Drop term_type.
    op.drop_column("reference_drugs", "term_type")
    # 3. Drop the enum type.
    op.execute("DROP TYPE rxnorm_term_type_enum")
