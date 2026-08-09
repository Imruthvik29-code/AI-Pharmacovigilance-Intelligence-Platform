-- Reference Drug Catalog Infrastructure
-- Additive migration only -- adds external-reference columns to
-- reference_drugs so a reproducible RxNorm import
-- (backend/scripts/import_rxnorm.py) can upsert idempotently without
-- altering any existing row's primary key or breaking existing foreign
-- keys.
--
-- medications.drug_id, interaction_rules.drug_a_id/drug_b_id, and
-- adr_rules.drug_id all reference reference_drugs.id -- this migration
-- never touches that column.
--
-- All three columns are nullable with no default, so every existing
-- seeded row (002_seed_data.sql) remains valid immediately after this
-- migration with NULL in all three new fields.

alter table reference_drugs
  add column rxcui text unique,
  add column source text,
  add column source_updated_at timestamptz;

comment on column reference_drugs.rxcui is
  'RxNorm Concept Unique Identifier (RXCUI). Idempotency key for the RxNorm import pipeline (backend/scripts/import_rxnorm.py). NULL for rows not yet matched/imported from RxNorm.';
comment on column reference_drugs.source is
  'Provenance of this row, e.g. "RxNorm" or "FDA Label" (mirrors interaction_rules.source / adr_rules.source). NULL for rows predating this column.';
comment on column reference_drugs.source_updated_at is
  'Timestamp of the last successful import/update from the source identified by `source`. NULL until first imported.';
