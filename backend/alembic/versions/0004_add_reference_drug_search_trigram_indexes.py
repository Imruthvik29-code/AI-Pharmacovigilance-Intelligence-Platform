"""Add trigram indexes for reference-drug catalog search.

Revision ID: 0004_add_reference_drug_search_trigram_indexes
Revises: 0003_add_rxnorm_concept_relations
Create Date: 2026-09-08

The medication search endpoint performs case-insensitive prefix/substring
matching against reference_drugs.name and reference_drugs.generic_name.
With the catalog now containing roughly 100k rows, unindexed ILIKE scans
were measured at roughly 300 ms for a common query. PostgreSQL's pg_trgm
GIN indexes allow the existing search contract to use bitmap index scans
without changing matching, ranking, limits, or API behavior.

This migration is intentionally limited to the two columns used by the
existing search endpoint. No schema or identity semantics are changed.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_reference_drug_search_trigram_indexes"
down_revision: Union[str, None] = "0003_add_rxnorm_concept_relations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX idx_reference_drugs_name_trgm "
        "ON reference_drugs USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_reference_drugs_generic_name_trgm "
        "ON reference_drugs USING gin (generic_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_reference_drugs_generic_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_reference_drugs_name_trgm")
