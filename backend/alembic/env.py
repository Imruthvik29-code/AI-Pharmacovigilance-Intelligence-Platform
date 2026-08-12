"""
Alembic environment — async implementation for AI Pharmacovigilance Platform.

This file is the single source of truth for how Alembic connects to the
database and what metadata it compares against.

- Uses `backend/app/db/models.py:Base.metadata` as `target_metadata` — the
  ORM models are typed mirrors of `001_initial_schema.sql` (source of truth
  per models.py docstring), with `create_type=False` on all ENUMs because
  the enums are created by migrations, not by SQLAlchemy itself.

- Reads `DATABASE_URL` from `app.core.config.get_settings()` (which loads
  `backend/.env` locally, real env vars in deployment). This matches the
  existing `session.py:create_async_engine(settings.database_url)` pattern.

- Async engine path uses existing `asyncpg` driver (no extra
  `psycopg2-binary` needed) via `sqlalchemy.ext.asyncio.async_engine_from_config`
  + `await connection.run_sync(do_run_migrations)` — per Alembic async docs.

- Offline migrations use the same URL with `literal_binds=True`.

- Fail-closed: if `DATABASE_URL` is empty, the placeholder from `alembic.ini`
  remains and Alembic will fail with a clear connection error — same
  fail-at-call-time convention as `auth.py:_supabase_headers()` and
  `security.py:_get_jwks_client()` and `llm_providers.py:complete()`.

Existing databases (already have 001–003 applied manually):
  `alembic stamp <baseline_revision>` — marks schema as already at baseline
  without executing DDL.

New databases:
  Either continue using 001–003 SQL files until a full baseline migration is
  generated, or generate a proper baseline revision that builds schema from
  scratch (see README.md).
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---------------------------------------------------------------------
# Alembic Config object — provides access to .ini values
# ---------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging — unless we are told not to
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------
# Make `backend/` importable and load target_metadata
# ---------------------------------------------------------------------
# When alembic.ini lives at repo root with `prepend_sys_path = .` and
# `script_location = backend/alembic`, the repo root is on sys.path,
# so `backend.app...` is importable. We also add backend/ explicitly
# to support `cd backend && alembic` invocations.
BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
ROOT_DIR = BASE_DIR.parent  # repo root
for p in (str(ROOT_DIR), str(BASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.core.config import get_settings
    from app.db.models import Base

    settings = get_settings()
    target_metadata = Base.metadata
except Exception as exc:
    # If import fails (e.g. dependencies not installed in this env),
    # keep target_metadata None so `alembic history` still works and
    # the error surfaces only when a DB connection is actually attempted.
    print(f"Warning: could not import app settings/models for Alembic env: {exc}", file=sys.stderr)
    settings = None  # type: ignore
    target_metadata = None


def get_url() -> str:
    """Resolve database URL from settings or fall back to alembic.ini."""
    if settings is not None:
        try:
            db_url = settings.database_url
            if db_url:
                return db_url
        except Exception:
            pass
    # Fallback to ini placeholder — allows `alembic history` without env
    return config.get_main_option("sqlalchemy.url") or ""


# ---------------------------------------------------------------------
# Offline migrations — generate SQL script without DB connection
# ---------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------
# Online migrations — async path
# ---------------------------------------------------------------------
def do_run_migrations(connection):
    """Shared sync callable executed inside async connection.run_sync()."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Create async engine and run migrations via run_sync."""
    # Override sqlalchemy.url with live DATABASE_URL from settings
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode via asyncio."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------
# Entrypoint — dispatch to offline vs online
# ---------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
