"""
Database session management.

Provides a single async engine/sessionmaker for the app, plus a FastAPI
dependency (`get_db`) that yields a session per-request and guarantees
it's closed afterward.
"""
import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session as SyncSession

from app.core.config import get_settings

settings = get_settings()

# echo=False in production; flip to True locally if you need to debug SQL.
engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
print(f"[DB INSTR] AsyncEngine created id={id(engine)}")

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@event.listens_for(engine.sync_engine, "checkout")
def _log_connection_checkout(dbapi_connection, connection_record, connection_proxy):
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    print(
        f"[DB INSTR] connection checkout raw_conn_id={id(dbapi_connection)} "
        f"record_id={id(connection_record)} loop_id={loop_id}"
    )


@event.listens_for(engine.sync_engine, "checkin")
def _log_connection_checkin(dbapi_connection, connection_record):
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    print(
        f"[DB INSTR] connection checkin raw_conn_id={id(dbapi_connection)} "
        f"record_id={id(connection_record)} loop_id={loop_id}"
    )


@event.listens_for(SyncSession, "before_commit")
def _log_before_commit(session):
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    try:
        bind = session.get_bind()
        bind_id = id(bind)
    except Exception as exc:
        bind_id = f"error:{exc!r}"
    print(
        f"[DB INSTR] before_commit session_id={id(session)} bind_id={bind_id} loop_id={loop_id}"
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a DB session and ensures cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            try:
                loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                loop_id = None
            try:
                bind_id = id(session.get_bind())
            except Exception as exc:
                bind_id = f"error:{exc!r}"
            print(
                f"[DB INSTR] get_db enter session_id={id(session)} "
                f"engine_id={id(engine)} bind_id={bind_id} loop_id={loop_id}"
            )
            yield session
        finally:
            try:
                loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                loop_id = None
            print(
                f"[DB INSTR] get_db exit session_id={id(session)} loop_id={loop_id}"
            )
            await session.close()
