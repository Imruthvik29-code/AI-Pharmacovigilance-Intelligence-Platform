"""Add rxnorm_concept_relations — typed RxNorm relationship edges.

Revision ID: 0003_add_rxnorm_concept_relations
Revises: 0002_add_term_type_is_active
Create Date: 2026-08-19

Stores RxNorm relationship edges as source_rxcui <relation_type> target_rxcui.
Only relationships actually returned by RxNav are stored; no hierarchy is
invented or inferred.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_rxnorm_concept_relations"
down_revision: Union[str, None] = "0002_add_term_type_is_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE rxnorm_concept_relations ("
        "  id uuid primary key default gen_random_uuid(),"
        "  source_rxcui text not null,"
        "  target_rxcui text not null,"
        "  relation_type text not null,"
        "  target_tty text,"
        "  source text not null default 'RxNorm',"
        "  created_at timestamptz not null default now(),"
        "  constraint uq_rxnorm_concept_relations_source_type_target"
        "    unique (source_rxcui, relation_type, target_rxcui)"
        ")"
    )
    op.execute(
        "CREATE INDEX idx_rxnorm_concept_relations_target"
        " ON rxnorm_concept_relations (target_rxcui)"
    )
    op.execute(
        "COMMENT ON TABLE rxnorm_concept_relations IS"
        " 'Typed RxNorm relationship edges (source_rxcui <relation_type> target_rxcui),"
        " populated from RxNav getRelatedByRelationship by backend/scripts/import_rxnorm.py --related."
        " Only relationships reported by the RxNorm source are stored.'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.source_rxcui IS"
        " 'RxCUI of the concept the relationship was fetched for. "
        "Logical reference to reference_drugs.rxcui (no FK: the target/endpoint "
        "may not be imported yet).'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.target_rxcui IS"
        " 'RxCUI of the related concept, as returned by the RxNav API. "
        "Logical reference to reference_drugs.rxcui (no FK: the endpoint may "
        "not be imported yet).'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.relation_type IS"
        " 'RxNorm relationship name per RxNav getRelaTypes, e.g. has_ingredient, "
        "has_precise_ingredient, has_tradename, isa, has_form, has_dose_form, has_part.'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.target_tty IS"
        " 'TTY of the target concept as reported by the API; NULL when the API "
        "omits it (per NLM docs, empty fields may be null or left out).'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.source IS"
        " 'Provenance of this edge, e.g. \"RxNorm\".'"
    )
    op.execute("ALTER TABLE rxnorm_concept_relations ENABLE ROW LEVEL SECURITY")
    op.execute(
        'CREATE POLICY "Authenticated users read rxnorm_concept_relations"'
        " ON rxnorm_concept_relations"
        " FOR SELECT USING (auth.role() = 'authenticated')"
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY "Authenticated users read rxnorm_concept_relations"'
        " ON rxnorm_concept_relations"
    )
    op.execute("DROP TABLE rxnorm_concept_relations")
