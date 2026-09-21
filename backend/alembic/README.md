# Alembic Migration Framework — AI Pharmacovigilance Platform

This directory is the **versioned migration workflow** that replaces the previous
manual `psql`/SQL Editor application of `001_initial_schema.sql`,
`002_seed_data.sql`, `003_reference_drugs_external_reference.sql` (flat files
at repository root, per `ARCHITECTURE_DECISIONS.md` §6.1).

## Status

- **Phase B Data Quality & Migration Foundation** — Alembic is **Independent** and **Before** schema extensions.
- **Current tracked history:** `0001_baseline -> 0002_add_term_type_is_active -> 0003_add_rxnorm_concept_relations -> 0004_add_reference_drug_search_trigram_indexes -> 0005_add_patient_relation -> 0006_add_patient_daily_routine`.
- Existing production databases originally received 001–003 manually and were reconciled to the Alembic history; subsequent schema changes are tracked as migrations.
- `0004` adds the `pg_trgm` extension and GIN trigram indexes used by the existing `reference_drugs` name/generic-name search. It changes no API or medication-identity semantics.
- `0005` adds the optional `patients.relation` column; `0006` adds the optional patient daily-routine columns (`timezone`, `breakfast_time`, `lunch_time`, `dinner_time`).

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

Run these six steps in order, from the repository root, against an empty database:

```bash
psql "$DATABASE_URL" -f bootstrap_alembic_version.sql          # 1. version table (infrastructure)
psql "$DATABASE_URL" -f 001_initial_schema.sql                 # 2. schema
psql "$DATABASE_URL" -f 002_seed_data.sql                      # 3. seed
psql "$DATABASE_URL" -f 003_reference_drugs_external_reference.sql
python -m alembic -c alembic.ini stamp 0001_baseline           # 5. adopt baseline
python -m alembic -c alembic.ini upgrade head                  # 6. apply 0002 -> 0006
```

**Steps 5 and 6 must be run ONLINE** — connected directly to the database.
See the `--sql` caveat under *Verification* below; generated offline SQL is
**not** a valid substitute for this sequence.

`bootstrap_alembic_version.sql` runs **first**, before any schema exists. It
creates `alembic_version` with `version_num VARCHAR(64)`. Alembic 1.13.2
would otherwise create that column as `VARCHAR(32)`
(`Column("version_num", String(32))` in `alembic/runtime/migration.py`),
which is too narrow for this project's longest revision identifier,
`0004_add_reference_drug_search_trigram_indexes` (46 characters). On a stock
version table `upgrade head` aborts while recording the `0002 -> 0003`
transition, and because the run is wrapped in a single transaction the whole
upgrade rolls back to `0001_baseline`.

Alembic adopts the pre-created table rather than replacing it:
`_ensure_version_table()` calls `self._version.create(..., checkfirst=True)`,
so it issues no DDL against an existing version table and never inspects or
alters the column type. No change to `env.py`, `alembic.ini`, or any existing
revision is involved.

The bootstrap file refuses to run if `patients` already exists, which is why
it must precede `001_initial_schema.sql` — that file creates `patients`, and
the guard can only tell a new database from an established one while it runs
ahead of it.

This remains the transitional procedure: the legacy 001–003 files are still
the schema foundation, and no full baseline revision is introduced.

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
alembic upgrade head --sql   # inspection only — see caveat below
alembic upgrade head
```

#### `--sql` (offline) caveat

`--sql` is useful for reviewing what a migration *would* emit, but it must
never be used to bootstrap or migrate a database in place of the online
commands.

In offline mode Alembic cannot query the database, so when it starts from no
known version it emits its **own unconditional** version-table DDL:

```python
if self.as_sql and not head_maintainer.heads:
    # for offline mode, include a CREATE TABLE from the base
    self._version.create(self.connection)   # note: no checkfirst
```

That statement creates `version_num` at the default `VARCHAR(32)`. Applying
such a script therefore either collides with an existing `alembic_version`
table or reintroduces the too-narrow column that
`bootstrap_alembic_version.sql` exists to prevent.

Online commands take a different path — `_ensure_version_table()` with
`checkfirst=True` — which adopts the pre-created table untouched. Use the
online sequence documented under *For new databases* for any real database.

## References

- https://alembic.sqlalchemy.org/en/latest/tutorial.html
- https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- Existing manual migrations: `001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql` at repo root
- Models: `backend/app/db/models.py` — `Base.metadata` — `create_type=False` on ENUMs
- Config: `backend/app/core/config.py` — `get_settings().database_url`
