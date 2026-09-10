"""add patient identity fields

Revision ID: 0005_add_patient_identity_fields
Revises: 0004_add_reference_drug_search_trigram_indexes
"""
from alembic import op
import sqlalchemy as sa
revision = "0005_add_patient_identity_fields"
down_revision = "0004_add_reference_drug_search_trigram_indexes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("patients", sa.Column("relation", sa.String(), nullable=True))
    op.add_column("patients", sa.Column("photo_url", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("patients", "photo_url")
    op.drop_column("patients", "relation")
