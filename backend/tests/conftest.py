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

Test isolation note (Phase 3 review): these are integration tests against
a live database, run via the synchronous `TestClient`, which executes the
ASGI app on its own thread/event loop. A per-test SAVEPOINT-rollback
pattern would require binding the async session to that same loop, which
`TestClient` doesn't expose -- forcing it risks cross-event-loop asyncpg
errors. Instead, tests explicitly track the ids of any patients they
create (via the `created_patient_ids` fixture below) and an autouse
fixture deletes exactly those rows afterward, so repeated runs don't
accumulate data.

Phase 4 addition: `existing_drug_id` mirrors `existing_auth_user_id` --
medications.drug_id has a real FK to reference_drugs (seeded in Phase 1's
002_seed_data.sql), so tests pull a real seeded id rather than fabricating
one. `created_medication_ids` + its cleanup fixture follow the exact same
explicit-tracking pattern as `created_patient_ids`, for the same reason
(no transactional rollback available under TestClient).
"""
import uuid

import pytest
from sqlalchemy import bindparam, text

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


@pytest.fixture
async def existing_drug_id():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id FROM reference_drugs LIMIT 1"))
        row = result.first()
    if row is None:
        pytest.skip(
            "No rows in reference_drugs -- run 002_seed_data.sql before "
            "running medication tests."
        )
    return row[0]


@pytest.fixture
def created_patient_ids() -> list[uuid.UUID]:
    """
    Tests append the id of any patient they create to this list. The
    autouse cleanup fixture below deletes exactly those rows after the
    test finishes, regardless of pass/fail.
    """
    return []


@pytest.fixture
def created_medication_ids() -> list[uuid.UUID]:
    """Same explicit-tracking pattern as created_patient_ids, for medications."""
    return []


@pytest.fixture(autouse=True)
async def _cleanup_created_patients(created_patient_ids: list[uuid.UUID]):
    yield
    if not created_patient_ids:
        return
    stmt = text("DELETE FROM patients WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_patient_ids})
        await session.commit()


@pytest.fixture(autouse=True)
async def _cleanup_created_medications(created_medication_ids: list[uuid.UUID]):
    yield
    if not created_medication_ids:
        return
    stmt = text("DELETE FROM medications WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_medication_ids})
        await session.commit()
