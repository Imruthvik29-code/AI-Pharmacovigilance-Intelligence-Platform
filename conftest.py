"""
Shared test fixtures.

`patients.user_id` has a real FK to Supabase's `auth.users` table (see
001_initial_schema.sql), so any patient inserted in a test must reference
an id that actually exists there. Rather than fabricate a UUID (which
would fail the FK, as already noted in Phase 1's test caveats), this
fixture pulls an existing user id from the live database and skips
dependent tests if none exists yet.

To populate one for local testing: sign up a user via POST /auth/signup
(Phase 2) against your Supabase project, then re-run these tests.
"""
import pytest
from sqlalchemy import text

from app.db.session import AsyncSessionLocal


@pytest.fixture
async def existing_auth_user_id():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id FROM auth.users LIMIT 1"))
        row = result.first()
    if row is None:
        pytest.skip(
            "No rows in auth.users -- sign up at least one test user via "
            "POST /auth/signup before running patient tests."
        )
    return row[0]
