-- Alembic version-table bootstrap — INFRASTRUCTURE, NOT A SCHEMA MIGRATION.
--
-- This file creates no application schema. It defines nothing about
-- patients, medications, or any other domain table. The schema foundation
-- remains 001_initial_schema.sql / 002_seed_data.sql /
-- 003_reference_drugs_external_reference.sql, and every schema change
-- after that baseline remains an Alembic revision under
-- backend/alembic/versions/. No new baseline is introduced here.
--
-- WHY THIS EXISTS
--
-- Alembic 1.13.2 creates its bookkeeping table with a fixed-width column:
--
--     Column("version_num", String(32), nullable=False)
--         -- alembic/runtime/migration.py
--
-- This repository uses descriptive revision identifiers, and two of them
-- are longer than 32 characters:
--
--     0003_add_rxnorm_concept_relations                33 characters
--     0004_add_reference_drug_search_trigram_indexes    46 characters
--
-- On a stock version table, `alembic upgrade head` therefore aborts when
-- it records the 0002 -> 0003 transition, because the new value does not
-- fit the column. The failure happens inside a single transaction, so the
-- whole upgrade rolls back and the database is left at 0001_baseline.
--
-- Alembic adopts an existing version table rather than recreating it:
-- `_ensure_version_table()` calls `self._version.create(..., checkfirst=True)`,
-- so when this table is already present Alembic issues no DDL against it
-- and never inspects or alters its column type. Creating it up front with
-- a wider column is therefore sufficient, and requires no change to
-- Alembic's configuration, to env.py, or to any existing revision.
--
-- VARCHAR(64) matches the width already present on the project's existing
-- database and leaves 18 characters of headroom beyond the current longest
-- identifier (46). The NOT NULL constraint and the single-column primary
-- key named `alembic_version_pkc` reproduce exactly what Alembic itself
-- would have created, so a bootstrapped database is indistinguishable from
-- one Alembic set up on its own.
--
-- WHEN TO RUN IT
--
-- On a NEW database only, and FIRST — before the legacy schema files and
-- before any Alembic command:
--
--     bootstrap_alembic_version.sql          <-- this file, first
--     001_initial_schema.sql
--     002_seed_data.sql
--     003_reference_drugs_external_reference.sql
--     alembic stamp 0001_baseline
--     alembic upgrade head
--
-- It runs first so the preflight guard below is meaningful: `patients` is
-- created by 001_initial_schema.sql, so the guard can only distinguish an
-- untouched database from an established one while it runs ahead of that
-- file. The version table has no dependency on any object in 001-003, so
-- creating it first is safe.
--
-- The Alembic steps must be run ONLINE (connected directly to the
-- database). Offline `--sql` generation emits its own unconditional
-- CREATE TABLE for the version table using the default VARCHAR(32), so a
-- generated offline script is not a substitute for this sequence.
--
-- Re-running this file during a fresh bootstrap is safe only before
-- 001_initial_schema.sql has been applied; afterwards the guard will
-- refuse, which is the intended protection rather than a failure.

-- Preflight: refuse to run against an established database. `patients` is
-- created by 001_initial_schema.sql and exists in every database that has
-- been set up, which makes its absence a reliable marker for a genuinely
-- new one. `to_regclass` returns NULL rather than raising when the table
-- is absent, so this is a plain existence test with no dependency on any
-- extension, role, or environment-specific value.
DO $$
BEGIN
    IF to_regclass('public.patients') IS NOT NULL THEN
        RAISE EXCEPTION
          'Refusing to bootstrap: table "patients" already exists. '
          'This sequence is for NEW databases only.';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(64) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
