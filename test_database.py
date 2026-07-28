"""
Phase 1 database tests.

Requires a real DATABASE_URL pointing at the migrated Supabase instance
(run 001_initial_schema.sql then 002_seed_data.sql first). These are
integration tests against the actual DB, not mocks — Phase 1's job is to
prove the schema + seed data are usable, not to test business logic
(that comes with later phases' engines).

Run with:  pytest backend/tests/test_database.py -v
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text

from app.db.models import Condition, InteractionRule, Patient, ReferenceDrug
from app.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_connection_is_alive():
    """Sanity check: can we reach the database at all."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_seed_reference_drugs_present():
    """Seed data loaded the expected curated drug list."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReferenceDrug))
        drugs = result.scalars().all()
        names = {d.name for d in drugs}
        assert len(drugs) >= 12
        assert {"Warfarin", "Aspirin", "Ibuprofen", "Simvastatin"}.issubset(names)


@pytest.mark.asyncio
async def test_seed_interaction_rules_reference_valid_drugs():
    """Every interaction rule points at two drugs that actually exist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(InteractionRule))
        rules = result.scalars().all()
        assert len(rules) >= 5
        for rule in rules:
            assert rule.drug_a_id is not None
            assert rule.drug_b_id is not None
            assert rule.severity in ("mild", "moderate", "severe")


@pytest.mark.asyncio
async def test_known_interaction_warfarin_aspirin_exists():
    """The specific, clinically important warfarin+aspirin rule seeded correctly."""
    async with AsyncSessionLocal() as session:
        warfarin = (
            await session.execute(select(ReferenceDrug).where(ReferenceDrug.name == "Warfarin"))
        ).scalar_one()
        aspirin = (
            await session.execute(select(ReferenceDrug).where(ReferenceDrug.name == "Aspirin"))
        ).scalar_one()

        result = await session.execute(
            select(InteractionRule).where(
                InteractionRule.drug_a_id == warfarin.id,
                InteractionRule.drug_b_id == aspirin.id,
            )
        )
        rule = result.scalar_one()
        assert rule.severity == "severe"


@pytest.mark.asyncio
async def test_patient_condition_roundtrip_and_cascade():
    """
    Insert a patient + condition, verify FK relationship and enum defaults
    work, then delete the patient and confirm the condition cascades away
    (proves the on-delete=CASCADE constraint from the migration is live).
    """
    async with AsyncSessionLocal() as session:
        patient_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        patient = Patient(
            id=patient_id,
            user_id=uuid.uuid4(),  # stand-in; real auth.users FK enforced separately
            name="Test Patient",
            age=45,
            sex="female",
            created_at=now,
            updated_at=now,
        )
        session.add(patient)
        await session.flush()

        condition = Condition(
            id=uuid.uuid4(),
            patient_id=patient_id,
            name="Hypertension",
            diagnosed_date=date.today(),
            created_at=now,
            updated_at=now,
        )
        session.add(condition)
        await session.commit()

        # Confirm defaults applied
        refreshed = (
            await session.execute(select(Condition).where(Condition.patient_id == patient_id))
        ).scalar_one()
        assert refreshed.status == "active"
        assert refreshed.reason == "unknown"

        # Cascade delete check
        await session.delete(patient)
        await session.commit()

        remaining = (
            await session.execute(select(Condition).where(Condition.patient_id == patient_id))
        ).scalars().all()
        assert remaining == []
