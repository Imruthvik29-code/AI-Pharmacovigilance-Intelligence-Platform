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

Phase 5 addition: `created_condition_ids` + its cleanup fixture follow
the same explicit-tracking pattern for conditions. No `existing_*_id`
fixture is needed here since conditions have no external FK dependency
beyond `patient_id`, which tests already create directly via the
patients API.

Phase 6 addition: `created_symptom_ids` + its cleanup fixture follow the
same explicit-tracking pattern for symptoms. No `existing_*_id`
fixture is needed here either -- symptoms' optional condition_id/medication_id
references are created directly via the conditions/medications APIs
within each test that needs them.

E2E lifecycle note: `test_e2e_verification.py` intentionally carries
patient/medication/condition/symptom ids across multiple ordered tests.
Those tests therefore cannot use the normal per-test cleanup lifecycle.
For that module only, created ids are deferred to a session teardown and
cleaned in dependency order after the E2E sequence completes. All other
tests retain the existing per-test cleanup behavior.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import bindparam, text

from app.db.session import AsyncSessionLocal


_E2E_CREATED_IDS: dict[str, set[uuid.UUID]] = {
    "patients": set(),
    "medications": set(),
    "conditions": set(),
    "symptoms": set(),
}


def _is_e2e_module(request: pytest.FixtureRequest) -> bool:
    return request.node.module.__name__ == "test_e2e_verification"


def _defer_e2e_ids(
    request: pytest.FixtureRequest,
    kind: str,
    ids: list[uuid.UUID],
) -> bool:
    """Defer cleanup only for the stateful E2E module."""
    if not _is_e2e_module(request):
        return False
    _E2E_CREATED_IDS[kind].update(ids)
    return True


async def _cleanup_e2e_rows() -> None:
    """Clean E2E rows after the whole ordered verification sequence finishes."""
    cleanup_order = (
        ("symptoms", "symptoms"),
        ("conditions", "conditions"),
        ("medications", "medications"),
        ("patients", "patients"),
    )
    async with AsyncSessionLocal() as session:
        for kind, table in cleanup_order:
            ids = _E2E_CREATED_IDS[kind]
            if not ids:
                continue
            stmt = text(f"DELETE FROM {table} WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            )
            await session.execute(stmt, {"ids": list(ids)})
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_e2e_created_rows():
    yield
    if any(_E2E_CREATED_IDS.values()):
        asyncio.run(_cleanup_e2e_rows())


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


@pytest.fixture
def created_condition_ids() -> list[uuid.UUID]:
    """Same explicit-tracking pattern as created_patient_ids, for conditions."""
    return []


@pytest.fixture
def created_symptom_ids() -> list[uuid.UUID]:
    """Same explicit-tracking pattern as created_patient_ids, for symptoms."""
    return []


@pytest.fixture(autouse=True)
async def _cleanup_created_patients(
    request: pytest.FixtureRequest,
    created_patient_ids: list[uuid.UUID],
):
    yield
    if not created_patient_ids:
        return
    if _defer_e2e_ids(request, "patients", created_patient_ids):
        return
    stmt = text("DELETE FROM patients WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_patient_ids})
        await session.commit()


@pytest.fixture(autouse=True)
async def _cleanup_created_medications(
    request: pytest.FixtureRequest,
    created_medication_ids: list[uuid.UUID],
):
    yield
    if not created_medication_ids:
        return
    if _defer_e2e_ids(request, "medications", created_medication_ids):
        return
    stmt = text("DELETE FROM medications WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_medication_ids})
        await session.commit()


@pytest.fixture(autouse=True)
async def _cleanup_created_conditions(
    request: pytest.FixtureRequest,
    created_condition_ids: list[uuid.UUID],
):
    yield
    if not created_condition_ids:
        return
    if _defer_e2e_ids(request, "conditions", created_condition_ids):
        return
    stmt = text("DELETE FROM conditions WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_condition_ids})
        await session.commit()


@pytest.fixture(autouse=True)
async def _cleanup_created_symptoms(
    request: pytest.FixtureRequest,
    created_symptom_ids: list[uuid.UUID],
):
    yield
    if not created_symptom_ids:
        return
    if _defer_e2e_ids(request, "symptoms", created_symptom_ids):
        return
    stmt = text("DELETE FROM symptoms WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_symptom_ids})
        await session.commit()
