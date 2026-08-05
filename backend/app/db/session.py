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

from app.core.config import get_settings

settings = get_settings()

# echo=False in production; flip to True locally if you need to debug SQL.
engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)


@event.listens_for(engine.sync_engine, "connect")
def _trace_connect(dbapi_connection, connection_record) -> None:
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    print(
        "TRACE engine connect "
        f"loop={loop_id} engine={id(engine)} pool={id(engine.pool)} "
        f"dbapi_connection={id(dbapi_connection)} connection_record={id(connection_record)}"
    )


@event.listens_for(engine.sync_engine, "checkout")
def _trace_checkout(dbapi_connection, connection_record, connection_proxy) -> None:
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    print(
        "TRACE engine checkout "
        f"loop={loop_id} engine={id(engine)} pool={id(engine.pool)} "
        f"dbapi_connection={id(dbapi_connection)} connection_record={id(connection_record)} "
        f"connection_proxy={id(connection_proxy)}"
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a DB session and ensures cleanup."""
    async with AsyncSessionLocal() as session:
        loop = asyncio.get_running_loop()
        print(
            f"TRACE get_db loop={id(loop)} engine={id(engine)} pool={id(engine.pool)} "
            f"session={id(session)} session_bind={id(session.sync_session.bind)}"
        )
        try:
            yield session
        finally:
            await session.close()
