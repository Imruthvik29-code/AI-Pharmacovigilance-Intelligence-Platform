"""Add rxnorm_concept_relations — typed RxNorm relationship edges.

Revision ID: 0003_rxnorm_concept_relations
Revises: 0002_add_term_type_is_active
Create Date: 2026-08-19

Why this table exists
---------------------
The RxNav bulk endpoint the importer already uses
(`getAllConceptsByTTY` -> /REST[Prescribe]/allconcepts.json?tty=...) returns
only `rxcui`, `name`, and `tty` per concept (verified against NLM's RxNav
API documentation) — no parent/relationship fields. RxNorm's structural
hierarchy (ingredient -> precise ingredient -> clinical drug -> branded
drug, plus pack/dose-form links) is exposed by the per-concept
`getRelatedByRelationship` endpoint
(`GET /REST/rxcui/<rxcui>/related.json?rela=<type>`), whose response tags
concepts only by TTY group, not by relation type.

This table stores those edges explicitly instead of flattening the
hierarchy, so the platform can answer "which ingredients does this
branded product contain?" without inventing anything:

    source_rxcui <relation_type> target_rxcui

- `relation_type` is the RxNorm relationship name exactly as queried via
  `getRelaTypes` (e.g. `has_ingredient`, `has_precise_ingredient`,
  `has_tradename`, `isa`, `has_form`, `has_dose_form`, `has_part`).
- `target_tty` is the TTY of the target as reported by the API when
  present (defensive: NLM docs state empty fields may be null/omitted).
- Only relationships actually returned by the RxNorm API are stored.
  Nothing is derived or guessed.

Populated by the opt-in `--related` mode of
`backend/scripts/import_rxnorm.py` (per-concept HTTP with disk caching and
resume), never by the default concept import.

Design notes
------------
- Additive only: no existing table, column, enum, index, or constraint is
  touched. `reference_drugs.id` (and therefore every existing foreign key)
  is unaffected.
- No foreign keys to `reference_drugs(rxcui)`, deliberately: relationship
  targets may belong to a TTY not yet imported (imports are TTY-by-TTY and
  order-independent), and the API may reference concepts outside the
  imported set. The rxcui strings are therefore logical references,
  resolvable by join whenever both ends exist in `reference_drugs`.
- `unique (source_rxcui, relation_type, target_rxcui)` makes the importer's
  bulk `ON CONFLICT DO NOTHING` upsert idempotent: re-running any slice
  never creates duplicate edges.
- RLS mirrors the other shared reference tables (readable by all
  authenticated users, not user-owned). The importer connects as the
  owning `postgres` role, which is exempt from RLS.
- Reversible: downgrade drops the policy and the table (no other object
  references it). Data loss on downgrade is limited to the relationship
  rows, which are fully reproducible by re-running `--related`.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_rxnorm_concept_relations"
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
        "Logical reference to reference_drugs.rxcui (no FK: the target/endpoint"
        " may not be imported yet).'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.target_rxcui IS"
        " 'RxCUI of the related concept, as returned by the RxNav API. "
        "Logical reference to reference_drugs.rxcui (no FK: the endpoint may"
        " not be imported yet).'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.relation_type IS"
        " 'RxNorm relationship name per RxNav getRelaTypes, e.g. has_ingredient,"
        " has_precise_ingredient, has_tradename, isa, has_form, has_dose_form, has_part.'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.target_tty IS"
        " 'TTY of the target concept as reported by the API; NULL when the API"
        " omits it (per NLM docs, empty fields may be null or left out).'"
    )
    op.execute(
        "COMMENT ON COLUMN rxnorm_concept_relations.source IS"
        " 'Provenance of this edge, e.g. \"RxNorm\".' "
    )
    # Shared reference data — readable by all authenticated users, not
    # user-owned (same treatment as reference_drugs / interaction_rules /
    # adr_rules in 001_initial_schema.sql).
    op.execute(
        "ALTER TABLE rxnorm_concept_relations ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        'CREATE POLICY "Authenticated users read rxnorm_concept_relations"'
        " ON rxnorm_concept_relations"
        " FOR SELECT USING (auth.role() = 'authenticated')"
    )


def downgrade() -> None:
    # Drop the RLS policy, then the table (index/constraint drop with it).
    op.execute(
        'DROP POLICY "Authenticated users read rxnorm_concept_relations"'
        " ON rxnorm_concept_relations"
    )
    op.execute("DROP TABLE rxnorm_concept_relations")
