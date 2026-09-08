# Alembic Migration Framework — AI Pharmacovigilance Platform

This directory is the **versioned migration workflow** that replaces the previous
manual `psql`/SQL Editor application of `001_initial_schema.sql`,
`002_seed_data.sql`, `003_reference_drugs_external_reference.sql` (flat files
at repository root, per `ARCHITECTURE_DECISIONS.md` §6.1).

## Status

- **Phase B Data Quality & Migration Foundation** — Alembic is **Independent** and **Before** schema extensions.
- **Current tracked history:** `0001_baseline -> 0002_add_term_type_is_active -> 0003_add_rxnorm_concept_relations -> 0004_add_reference_drug_search_trigram_indexes`.
- Existing production databases originally received 001–003 manually and were reconciled to the Alembic history; subsequent schema changes are tracked as migrations.
- `0004` adds the `pg_trgm` extension and GIN trigram indexes used by the existing `reference_drugs` name/generic-name search. It changes no API or medication-identity semantics.

## Configuration

- `alembic.ini` at repository root — `script_location = backend/alembic`
- `backend/alembic/env.py` — async implementation using existing `asyncpg` driver (no extra `psycopg2-binary` needed)
  - Reads `DATABASE_URL` from `app.core.config.get_settings()` (loads `backend/.env` locally, real env vars in deployment)
  - `target_metadata = Base.metadata` from `app.db.models` (typed ORM mirrors 001_initial_schema.sql, `create_type=False` on all ENUMs)
  - Offline: `literal_binds=True`
  - Online: `async_engine_from_config` + `await connection.run_sync(do_run_migrations)` + `asyncio.run()`
  - Fail-closed: if `DATABASE_URL` empty, placeholder remains and Alembic fails with clear connection error — same convention as `auth.py:_supabase_headers()` and `security.py:_get_jwks_client()`

## Workflow

### For existing databases

Existing databases that already contain the legacy 001–003 schema should have their Alembic version stamped/reconciled once without re-executing the legacy DDL. After reconciliation, future migrations are applied normally:

```bash
cd /path/to/repo/backend
alembic upgrade head
```

### For new databases (from scratch)

During the transition, continue using the legacy 001–003 SQL files to create the initial schema, then stamp the appropriate baseline before applying subsequent Alembic revisions. A future full baseline revision can replace this transitional procedure.

### Creating a new migration

```bash
cd backend
alembic revision --autogenerate -m "describe the schema change"
# Review the generated file carefully, especially ENUM creation and indexes.
alembic upgrade head
alembic current
alembic history
```

### Downgrade / Rollback

```bash
alembic downgrade -1
alembic downgrade base
alembic upgrade head
```

All upgrades/downgrades should be reproducible.

## Why Alembic Now?

Per `ARCHITECTURE_DECISIONS.md` §6.4 final decision: migration tooling adoption should occur while migration-file count remains low (early), not deferred to late phase. Cost of adopting tracked migrations is proportional to untracked history at adoption time.

## Relationship to Architecture Documentation

- Migration tooling is implemented and tracked early.
- `0002` owns the RxNorm TTY enum and `reference_drugs.term_type`/`is_active` additions.
- `0003` owns the RxNorm relationship-edge table.
- `0004` owns the reference-drug search trigram indexes required by the current ~100k-row catalog search workload.
- No medication identity, safety-engine, or API architecture is introduced by `0004`.

## Verification

Without live DB:

```bash
python -m py_compile backend/alembic/env.py
alembic --help
alembic history
```

With live DB:

```bash
alembic current
alembic upgrade head --sql
alembic upgrade head
```

## References

- https://alembic.sqlalchemy.org/en/latest/tutorial.html
- https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- Existing manual migrations: `001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql` at repo root
- Models: `backend/app/db/models.py` — `Base.metadata` — `create_type=False` on ENUMs
- Config: `backend/app/core/config.py` — `get_settings().database_url`
