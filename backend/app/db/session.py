"""
Database session management.

Provides a single async engine/sessionmaker for the app, plus a FastAPI
dependency (`get_db`) that yields a session per-request and guarantees
it's closed afterward.

The test suite uses a NullPool so asyncpg connections are never reused
across pytest event loops. Production keeps SQLAlchemy's normal pool.
"""
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

# pytest runs synchronous TestClient requests on their own event loops while
# async fixtures run on pytest-managed loops. asyncpg connections from a
# normal QueuePool cannot safely migrate between those loops. Keep pooling
# enabled in production, but disable it for the integration-test process.
_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if os.getenv("PV_TESTING") == "1":
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a DB session and ensures cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
