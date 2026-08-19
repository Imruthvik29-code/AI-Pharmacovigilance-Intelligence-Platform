# Alembic Migration Framework — AI Pharmacovigilance Platform

This directory is the **versioned migration workflow** that replaces the previous
manual `psql`/SQL Editor application of `001_initial_schema.sql`,
`002_seed_data.sql`, `003_reference_drugs_external_reference.sql` (flat files
at repository root, per `ARCHITECTURE_DECISIONS.md` §6.1).

## Status

- **Phase B Data Quality & Migration Foundation** — Alembic is **Independent** and **Before** any schema extension (term_type/is_active, ingredient_mapping, search indexes) — per Section 24.4
- **Current baseline:** Existing databases already have 001–003 applied manually
- **New databases:** Continue using 001–003 until a full baseline migration is generated, or use a proper baseline revision that builds schema from scratch (see Workflow below)

## Configuration

- `alembic.ini` at repository root — `script_location = backend/alembic`
- `backend/alembic/env.py` — async implementation using existing `asyncpg` driver (no extra `psycopg2-binary` needed)
  - Reads `DATABASE_URL` from `app.core.config.get_settings()` (loads `backend/.env` locally, real env vars in deployment)
  - `target_metadata = Base.metadata` from `app.db.models` (typed ORM mirrors 001_initial_schema.sql, `create_type=False` on all ENUMs)
  - Offline: `literal_binds=True`
  - Online: `async_engine_from_config` + `await connection.run_sync(do_run_migrations)` + `asyncio.run()`
  - Fail-closed: if `DATABASE_URL` empty, placeholder remains and Alembic fails with clear connection error — same convention as `auth.py:_supabase_headers()` and `security.py:_get_jwks_client()`

## Workflow

### For existing databases (already have 001–003 applied manually)

Mark the schema as already at the baseline without re-executing DDL:

```bash
cd /path/to/repo
# Ensure backend/.env has DATABASE_URL
cd backend
alembic stamp <baseline_revision>
# e.g.
alembic stamp 0001_baseline
```

This creates/updates the `alembic_version` table only — no DDL executed.

Then future migrations can be applied normally:

```bash
alembic upgrade head
```

### For new databases (from scratch)

**Option 1 — Continue using 001–003 until full baseline migration exists (recommended during transition):**

```bash
psql "$DATABASE_URL" -f ../001_initial_schema.sql
psql "$DATABASE_URL" -f ../002_seed_data.sql
psql "$DATABASE_URL" -f ../003_reference_drugs_external_reference.sql
alembic stamp <baseline_revision>
```

**Option 2 — Generate a proper baseline revision that builds schema from scratch (future):**

```bash
# Once Base.metadata fully reflects desired schema, generate baseline:
alembic revision --autogenerate -m "baseline schema from scratch"
# Review the generated DDL carefully — especially ENUM creation (create_type=False in models means Alembic will NOT auto-create ENUMs unless configured)
# Then:
alembic upgrade head
```

### Creating a new migration

```bash
cd backend
alembic revision --autogenerate -m "add term_type enum and is_active to reference_drugs"
# Edit the generated file in backend/alembic/versions/ — review DDL, especially for ENUMs
# Then:
alembic upgrade head
# Verify:
alembic current
alembic history
```

### Downgrade / Rollback

```bash
alembic downgrade -1
alembic downgrade base
alembic upgrade head
```

All upgrades/downgrades should be reproducible — per Section 24.4 Success Criteria.

## Why Alembic Now?

Per `ARCHITECTURE_DECISIONS.md` §6.4 final decision: migration tooling adoption should occur while migration-file count remains low (early), not deferred to late phase. Cost of adopting tracked migrations is proportional to untracked history at adoption time — every additional manually-applied file between now and eventual adoption increases retroactive-reconciliation burden. Repository currently has 3 sequential SQL files manual — low count — ideal time to adopt.

## Relationship to Architecture Documentation

- Section 19.4 — Migration tooling early adoption while count low — was DEFERRED, now IMPLEMENTED after this sprint
- Section 21.14 — Current limitations list included "no evidence of Alembic" — after this sprint, reclassify to implemented for Alembic specifically
- Section 23.2 — Current limitations included "no evidence of Alembic" — same reclassification
- Section 24.4 Phase B — Alembic objective with Objective/Reason/Dependencies/Success Criteria — this sprint satisfies it
- No new architectural decisions introduced — only versioned workflow for already-approved schema changes (term_type/is_active shipped in `0002`, rxnorm_concept_relations shipped in `0003`; remaining candidates: ingredient_mapping, idx_reference_drugs_name_lower)

## Verification

Without live DB (arena container, no Supabase):

```bash
python -m py_compile backend/alembic/env.py
alembic --help
alembic history  # should show empty or baseline once created
```

With live DB (requires DATABASE_URL):

```bash
alembic current
alembic upgrade head --sql  # offline SQL preview
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

## References

- https://alembic.sqlalchemy.org/en/latest/tutorial.html
- https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- Existing manual migrations: `001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql` at repo root
- Models: `backend/app/db/models.py` — `Base.metadata` — `create_type=False` on ENUMs
- Config: `backend/app/core/config.py` — `get_settings().database_url`
