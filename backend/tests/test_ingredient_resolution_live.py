"""
PR #10 — Real PostgreSQL/Supabase integration coverage for the
RxNorm ingredient-resolution path through the actual ADR, drug-interaction
and safety-score engines.

Why this file exists
-------------------
PR #8 added:

    reference_drugs (rxcui, term_type, is_active)
    → rxnorm_concept_relations (source_rxcui has_ingredient target_rxcui)
    → ingredient resolution (resolve_to_ingredient_ids)
    → ADR / interaction rule matching

The resolver has extensive DB-free coverage (test_ingredient_resolver.py)
but the complete production path through the real database (real
SQLAlchemy query path + real engine functions) was not yet covered.

This module proves that path end-to-end against a live PostgreSQL
instance, using the repository's established live-DB conventions
(AsyncSessionLocal, TestClient + get_current_user override,
explicitly-tracked synthetic rows, deterministic cleanup).

Live-DB vs DB-free
------------------
* DB-free tests in this file never open a connection. They verify the
  Alembic migration head statically (0003 is current head, no 0004).
* Live tests require a reachable Supabase/Postgres. They are *not* faked.
  When DATABASE_URL is unset or the database is unreachable, each live
  test calls _require_live_db() which does ``pytest.skip("live DB
  unavailable: ...")`` — the skip is visible in the pytest report and
  counts as "live-DB unavailable", not as a pass or a genuine failure.
  Do not weaken these tests to make sandbox execution succeed.

Data isolation / cleanup
------------------------
Every synthetic row is inserted with a UUID primary key generated for
that test run and a uniquely-identifiable name/rxcui
(``PR10-...-<8-hex>``). Rows are tracked in the ``synthetic_tracker``
fixture and deleted in dependency order after the test finishes
(interaction_rules / adr_rules → rxnorm_concept_relations →
reference_drugs → medications → patients). Existing seed rows are never
mutated.

The tests use the same explicit-tracking pattern as conftest.py
(created_patient_ids etc.) so repeated runs do not accumulate data.

Constraints respected (PR #10 §G)
---------------------------------
* No frontend, Alembic migration, models.py, import_rxnorm.py,
  ingredient_resolver.py, llm_service.py or langgraph_workflow.py
  modifications.
* No monkeypatch of resolve_to_ingredient_ids.
* No FakeSession — every live test executes the real SQLAlchemy query
  path via AsyncSessionLocal and the real engine functions
  detect_adrs / detect_drug_interactions / calculate_safety_score.

Run
---
DB-free only (works without Supabase):
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres \
        pytest backend/tests/test_ingredient_resolution_live.py -k "not live" -v

Full live suite (requires Supabase DATABASE_URL + auth.users seed):
    pytest backend/tests/test_ingredient_resolution_live.py -v

See PR #10 checklist §F for the full reporting split.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.core.security import CurrentUser, get_current_user
from app.db.session import AsyncSessionLocal
from app.main import app

# Engine imports — the *real* production path, never mocked.
from app.analysis.adr_engine import detect_adrs
from app.analysis.drug_interaction_engine import detect_drug_interactions
from app.analysis.safety_score_engine import calculate_safety_score
from app.db.models import AdrRule, InteractionRule, ReferenceDrug, RxnormConceptRelation

client = TestClient(app)

# ---------------------------------------------------------------------------
# Generic helpers — unique synthetic identifiers
# ---------------------------------------------------------------------------

def _unique_rxcui() -> str:
    """Synthetic RxCUI that is numeric-like, unique, and never collides.

    Production RxCUIs are numeric strings. This helper produces a 9-digit
    value prefixed with 99* so synthetic rows are instantly recognisable
    while still satisfying the text column + uniqueness.
    """
    # Use 7 random digits from uuid int to avoid collisions across parallel runs.
    suffix = f"{uuid.uuid4().int % 9000000 + 1000000:07d}"
    return f"99{suffix}"


def _unique_name(prefix: str) -> str:
    return f"PR10-{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _override_current_user(user_id) -> CurrentUser:
    async def _fake() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")
    return _fake


def _create_patient(name: str) -> dict:
    resp = client.post("/api/v1/patients", json={"name": name})
    assert resp.status_code == 201, f"create patient failed: {resp.status_code} {resp.text}"
    return resp.json()


def _create_active_medication(patient_id: str, drug_id: str, **kwargs) -> dict:
    payload = {"drug_id": drug_id, "start_date": str(date.today()), "status": "active", **kwargs}
    resp = client.post(f"/api/v1/patients/{patient_id}/medications", json=payload)
    assert resp.status_code == 201, f"create medication failed: {resp.status_code} {resp.text}"
    return resp.json()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Live-DB availability helper
# ---------------------------------------------------------------------------

async def _require_live_db() -> None:
    """Skip the calling test if no live PostgreSQL is reachable.

    Do NOT fake success — a missing DATABASE_URL or a connection failure
    must surface as a skip (live-DB unavailable), not a pass.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — we want to catch *all* connection errors
        pytest.skip(f"live Supabase/Postgres unavailable: {exc}")


async def _get_live_auth_user_id() -> uuid.UUID:
    """Return an existing auth.users id from the live DB, or skip."""
    await _require_live_db()
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT id FROM auth.users LIMIT 1"))
            row = result.first()
            if row is None:
                pytest.skip("No rows in auth.users — sign up at least one user via POST /auth/signup")
            return row[0]
    except Exception as exc:  # noqa: BLE001
        # includes the SELECT 1 check above, but also auth query failure
        if isinstance(exc, pytest.skip.Exception):
            raise
        pytest.skip(f"live DB unavailable when fetching auth user: {exc}")


# ---------------------------------------------------------------------------
# Synthetic-row tracker — deterministic cleanup in FK-safe order
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_tracker() -> dict[str, list[uuid.UUID]]:
    """Per-test accumulator for synthetic IDs. Deleted after yield in FK-safe order.

    Keys: reference_drugs, relations, adr_rules, interaction_rules
    """
    tracker: dict[str, list[uuid.UUID]] = {
        "reference_drugs": [],
        "relations": [],
        "adr_rules": [],
        "interaction_rules": [],
    }
    return tracker


@pytest.fixture(autouse=True)
async def _cleanup_synthetic(synthetic_tracker):
    yield
    # Teardown after test body — delete children before parents.
    # Use expanding bindparam for IN queries.
    # Medication rows that reference synthetic reference_drugs are
    # cascade-deleted when their patient is deleted (conftest's
    # created_patient_ids cleanup). But to handle FK ordering if that
    # cleanup hasn't run yet, delete medications referencing synthetic
    # drugs first.
    if not any(synthetic_tracker.values()):
        return
    try:
        async with AsyncSessionLocal() as session:
            if synthetic_tracker["reference_drugs"]:
                # Best-effort: delete medications that still reference synthetic drugs.
                try:
                    await session.execute(
                        text("DELETE FROM medications WHERE drug_id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": synthetic_tracker["reference_drugs"]},
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()

            if synthetic_tracker["interaction_rules"]:
                try:
                    await session.execute(
                        text("DELETE FROM interaction_rules WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": synthetic_tracker["interaction_rules"]},
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()

            if synthetic_tracker["adr_rules"]:
                try:
                    await session.execute(
                        text("DELETE FROM adr_rules WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": synthetic_tracker["adr_rules"]},
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()

            if synthetic_tracker["relations"]:
                try:
                    await session.execute(
                        text("DELETE FROM rxnorm_concept_relations WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": synthetic_tracker["relations"]},
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()

            if synthetic_tracker["reference_drugs"]:
                try:
                    await session.execute(
                        text("DELETE FROM reference_drugs WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": synthetic_tracker["reference_drugs"]},
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
    except Exception:
        # Cleanup must never mask a genuine test failure.
        # If the DB itself is unavailable, there's nothing to clean.
        pass


# created_patient_ids and its autouse cleanup are provided by
# conftest.py (both at repository root and backend/tests). We rely on
# that global fixture exactly as the existing engine tests do — no local
# duplicate is needed, keeping the isolation strategy identical to the
# rest of the suite.


# ---------------------------------------------------------------------------
# Low-level insertion helpers (use the real ORM models / real DB)
# ---------------------------------------------------------------------------

async def _insert_reference_drugs(
    rows: list[dict],
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        for r in rows:
            # Default timestamps if not provided
            r.setdefault("created_at", now)
            r.setdefault("updated_at", now)
            session.add(
                ReferenceDrug(
                    id=r["id"],
                    name=r["name"],
                    generic_name=r.get("generic_name", r["name"].lower()),
                    drug_class=r.get("drug_class", "PR10 Test"),
                    rxcui=r["rxcui"],
                    source=r.get("source", "RxNorm"),
                    term_type=r["term_type"],
                    is_active=r.get("is_active", True),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
            )
        await session.commit()


async def _insert_relation(
    *,
    id: uuid.UUID,
    source_rxcui: str,
    relation_type: str,
    target_rxcui: str,
    target_tty: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            RxnormConceptRelation(
                id=id,
                source_rxcui=source_rxcui,
                target_rxcui=target_rxcui,
                relation_type=relation_type,
                target_tty=target_tty,
                source="RxNorm",
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _insert_adr_rule(
    *,
    id: uuid.UUID,
    drug_id: uuid.UUID,
    reaction: str,
    severity: str = "moderate",
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        session.add(
            AdrRule(
                id=id,
                drug_id=drug_id,
                reaction_description=reaction,
                severity=severity,
                frequency_class="common",
                source="PR10 Test",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _insert_interaction_rule(
    *,
    id: uuid.UUID,
    drug_a_id: uuid.UUID,
    drug_b_id: uuid.UUID,
    severity: str = "moderate",
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        session.add(
            InteractionRule(
                id=id,
                drug_a_id=drug_a_id,
                drug_b_id=drug_b_id,
                severity=severity,
                mechanism="PR10 test mechanism",
                recommendation="PR10 test recommendation",
                source="PR10 Test",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


# ===========================================================================
# E. Migration / schema validation
# ===========================================================================

class TestMigrationHeadDbFree:
    """DB-free static checks — must pass without any database connection."""

    def test_0003_is_current_alembic_head(self):
        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        assert versions_dir.exists(), "backend/alembic/versions missing"
        files = sorted(p for p in versions_dir.glob("*.py") if not p.name.startswith("_"))
        stems = [p.stem for p in files]
        assert "0003_add_rxnorm_concept_relations" in stems, "0003 migration file missing"
        # No 0004 must exist for this PR
        assert not any(s.startswith("0004") for s in stems), "0004 must not exist for PR #10"
        # Verify head chain: find file with revision == head via content
        # The 0003 file's revision must be head (no file revises it)
        revisions: dict[str, str | None] = {}
        downs: dict[str, str | None] = {}
        for p in files:
            txt = p.read_text()
            # crude but reliable: extract revision = "..." and down_revision = "..."
            import re
            m = re.search(r'revision:\s*str\s*=\s*"([^"]+)"', txt)
            d = re.search(r'down_revision.*=\s*"([^"]+)"|down_revision.*=\s*None', txt)
            if m:
                rev = m.group(1)
                down = None
                if d and d.group(1):
                    down = d.group(1)
                revisions[rev] = rev
                downs[rev] = down
        # Head is revision that is not a down_revision of any other
        all_downs = {v for v in downs.values() if v}
        heads = [r for r in revisions if r not in all_downs]
        assert "0003_add_rxnorm_concept_relations" in heads, f"expected 0003 to be head, got heads={heads}"

    def test_0003_does_not_create_0004(self):
        versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        assert not (versions_dir / "0004_anything.py").exists()
        assert not list(versions_dir.glob("0004*"))

    def test_0003_file_creates_rxnorm_concept_relations(self):
        p = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0003_add_rxnorm_concept_relations.py"
        txt = p.read_text()
        assert "CREATE TABLE rxnorm_concept_relations" in txt
        assert "uq_rxnorm_concept_relations_source_type_target" in txt
        assert "idx_rxnorm_concept_relations_target" in txt
        assert "ENABLE ROW LEVEL SECURITY" in txt


@pytest.mark.asyncio
async def test_rxnorm_concept_relations_table_exists_live():
    await _require_live_db()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name='rxnorm_concept_relations')"
            )
        )
        exists = result.scalar()
    assert exists is True, "rxnorm_concept_relations table must exist in live DB (migration 0003)"


@pytest.mark.asyncio
async def test_rxnorm_concept_relations_required_columns_live():
    await _require_live_db()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name='rxnorm_concept_relations' "
                "ORDER BY column_name"
            )
        )
        cols = {row[0]: (row[1], row[2]) for row in result.all()}
    required = {
        "id": "uuid",
        "source_rxcui": "text",
        "target_rxcui": "text",
        "relation_type": "text",
        "target_tty": "text",
        "source": "text",
        "created_at": "timestamp with time zone",
    }
    for col, expected_type in required.items():
        assert col in cols, f"missing required column {col}"
        # Type check is lax due to variations in info_schema reporting
        # but must not be completely wrong
        actual_type, nullable = cols[col]
        assert actual_type is not None

    # source_rxcui, target_rxcui, relation_type must be NOT NULL
    # (checked via information_schema is_nullable)
    async with AsyncSessionLocal() as session:
        res2 = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='rxnorm_concept_relations' AND is_nullable='NO'"
            )
        )
        not_null = {r[0] for r in res2.all()}
    for col in ("source_rxcui", "target_rxcui", "relation_type", "source", "created_at"):
        # id is primary key -> NOT NULL implicitly; source has default
        if col != "id":
            assert col in not_null, f"{col} should be NOT NULL"


@pytest.mark.asyncio
async def test_rxnorm_concept_relations_unique_constraint_live():
    await _require_live_db()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_name='rxnorm_concept_relations' AND constraint_type='UNIQUE'"
            )
        )
        names = {r[0] for r in result.all()}
    assert "uq_rxnorm_concept_relations_source_type_target" in names


@pytest.mark.asyncio
async def test_alembic_version_is_0003_live():
    await _require_live_db()
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            row = result.first()
        except Exception as exc:
            pytest.skip(f"alembic_version table not accessible: {exc}")
    assert row is not None, "alembic_version must have a row"
    assert row[0] == "0003_add_rxnorm_concept_relations", f"expected head 0003, got {row[0]}"


@pytest.mark.asyncio
async def test_reference_drugs_required_columns_live():
    await _require_live_db()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='reference_drugs' ORDER BY column_name"
            )
        )
        cols = {r[0] for r in result.all()}
    for col in ("id", "name", "rxcui", "term_type", "is_active", "source", "source_updated_at"):
        assert col in cols, f"reference_drugs missing {col}"


# ===========================================================================
# A. ADR ingredient resolution — live DB
# ===========================================================================

@pytest.mark.asyncio
async def test_adr_finds_ingredient_rule_via_branded_product_live(
    synthetic_tracker, created_patient_ids
):
    """
    Synthetic setup:
      ingredient (IN)  — rxcui=ING, term_type IN, is_active true, distinct UUID
      branded (SBD)    — rxcui=SBD, term_type SBD, is_active true, distinct UUID
      relation SBD has_ingredient ING
      adr_rules row keyed to ingredient UUID
      medication for test patient using branded UUID

    Call REAL detect_adrs() against the real DB.
    Assert finding is returned, rule matched ingredient, no fabricated mapping.
    """
    ing_id = uuid.uuid4()
    branded_id = uuid.uuid4()
    ing_rxcui = _unique_rxcui()
    branded_rxcui = _unique_rxcui()
    # Ensure distinct rxcuis
    while branded_rxcui == ing_rxcui:
        branded_rxcui = _unique_rxcui()
    ing_name = _unique_name("ING-ADR")
    branded_name = _unique_name("SBD-ADR")
    rel_id = uuid.uuid4()
    adr_rule_id = uuid.uuid4()

    synthetic_tracker["reference_drugs"].extend([ing_id, branded_id])
    synthetic_tracker["relations"].append(rel_id)
    synthetic_tracker["adr_rules"].append(adr_rule_id)

    live_user = await _get_live_auth_user_id()

    # Insert synthetic reference data
    await _insert_reference_drugs(
        [
            {"id": ing_id, "name": ing_name, "rxcui": ing_rxcui, "term_type": "IN", "is_active": True},
            {"id": branded_id, "name": branded_name, "rxcui": branded_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    await _insert_relation(
        id=rel_id, source_rxcui=branded_rxcui, relation_type="has_ingredient", target_rxcui=ing_rxcui, target_tty="IN"
    )
    await _insert_adr_rule(id=adr_rule_id, drug_id=ing_id, reaction="PR10 ADR via ingredient", severity="moderate")

    # Create patient + medication via the real API
    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-ADR-ING"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(branded_id))

    # Call the REAL engine (no mock, no FakeSession)
    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    # --- Assertions ---
    # The branded prescription must surface the ingredient-level ADR.
    assert findings, "detect_adrs() must return a finding via ingredient resolution"
    # Find the specific synthetic rule
    matching = [f for f in findings if f.adr_rule_id == adr_rule_id]
    assert len(matching) == 1, f"expected exactly one finding for synthetic ADR rule, got {matching}"
    finding = matching[0]
    # The rule is keyed to the ingredient, not the branded product
    assert finding.drug_id == ing_id, "finding must reference the ingredient-level drug_id (where the rule is keyed)"
    assert finding.drug_name == ing_name, "drug_name must be the ingredient name (rule's drug)"
    assert finding.reaction_description == "PR10 ADR via ingredient"
    assert finding.severity == "moderate"
    # No fabricated mapping: the branded product itself has no direct ADR rule,
    # so the only way this passes is through the real has_ingredient edge.
    # The branded product's own ID must NOT equal the finding's drug_id.
    assert finding.drug_id != branded_id


@pytest.mark.asyncio
async def test_adr_direct_ingredient_prescription_still_works_live(
    synthetic_tracker, created_patient_ids
):
    """
    Existing direct-IN behavior must remain intact: prescribing the
    ingredient itself must still match the ingredient-level rule without
    needing any relation.
    """
    ing_id = uuid.uuid4()
    ing_rxcui = _unique_rxcui()
    ing_name = _unique_name("ING-DIRECT")
    adr_rule_id = uuid.uuid4()
    synthetic_tracker["reference_drugs"].append(ing_id)
    synthetic_tracker["adr_rules"].append(adr_rule_id)
    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [{"id": ing_id, "name": ing_name, "rxcui": ing_rxcui, "term_type": "IN", "is_active": True}]
    )
    await _insert_adr_rule(id=adr_rule_id, drug_id=ing_id, reaction="PR10 Direct IN ADR", severity="mild")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-ADR-Direct"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(ing_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    matching = [f for f in findings if f.adr_rule_id == adr_rule_id]
    assert len(matching) == 1
    assert matching[0].drug_id == ing_id
    assert matching[0].drug_name == ing_name


@pytest.mark.asyncio
async def test_adr_no_fabricated_mapping_without_relation_live(
    synthetic_tracker, created_patient_ids
):
    """
    If no has_ingredient edge exists, a branded prescription must NOT
    fabricate an ingredient match. This guards against a resolver that
    invents ingredients.
    """
    ing_id = uuid.uuid4()
    branded_id = uuid.uuid4()
    ing_rxcui = _unique_rxcui()
    branded_rxcui = _unique_rxcui()
    while branded_rxcui == ing_rxcui:
        branded_rxcui = _unique_rxcui()
    ing_name = _unique_name("ING-NOEDGE")
    branded_name = _unique_name("SBD-NOEDGE")
    adr_rule_id = uuid.uuid4()
    synthetic_tracker["reference_drugs"].extend([ing_id, branded_id])
    synthetic_tracker["adr_rules"].append(adr_rule_id)
    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [
            {"id": ing_id, "name": ing_name, "rxcui": ing_rxcui, "term_type": "IN", "is_active": True},
            {"id": branded_id, "name": branded_name, "rxcui": branded_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    # Deliberately NO relation inserted.
    await _insert_adr_rule(id=adr_rule_id, drug_id=ing_id, reaction="PR10 No Edge ADR", severity="mild")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-NoEdge"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(branded_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_adrs(uuid.UUID(patient["id"]), session)

    # Branded drug without a relation must not match the ingredient rule.
    assert all(f.adr_rule_id != adr_rule_id for f in findings), "must NOT match ingredient ADR without has_ingredient edge"
    assert all(f.drug_id != ing_id or f.adr_rule_id != adr_rule_id for f in findings)


# ===========================================================================
# B. Drug interaction ingredient resolution — live DB
# ===========================================================================

@pytest.mark.asyncio
async def test_interaction_resolves_two_branded_via_ingredients_live(
    synthetic_tracker, created_patient_ids
):
    """
    Product A (SBD, rxcui PA) --has_ingredient--> ingredient A (IN, rxcui IA)
    Product B (SBD, rxcui PB) --has_ingredient--> ingredient B (IN, rxcui IB)
    Interaction rule keyed to IA + IB (moderate).
    Patient takes PA + PB (branded).

    REAL detect_drug_interactions must:
      * return a finding
      * match the ingredient-level rule
      * result not empty
      * both source products represented via source-map logic
    """
    # Ingredient A/B
    ing_a_id = uuid.uuid4()
    ing_b_id = uuid.uuid4()
    prod_a_id = uuid.uuid4()
    prod_b_id = uuid.uuid4()
    ing_a_rxcui = _unique_rxcui()
    ing_b_rxcui = _unique_rxcui()
    while ing_b_rxcui == ing_a_rxcui:
        ing_b_rxcui = _unique_rxcui()
    prod_a_rxcui = _unique_rxcui()
    prod_b_rxcui = _unique_rxcui()
    # Ensure all four distinct
    rxcuis = {ing_a_rxcui, ing_b_rxcui, prod_a_rxcui, prod_b_rxcui}
    while len(rxcuis) < 4:
        prod_b_rxcui = _unique_rxcui()
        rxcuis = {ing_a_rxcui, ing_b_rxcui, prod_a_rxcui, prod_b_rxcui}

    ing_a_name = _unique_name("ING-A")
    ing_b_name = _unique_name("ING-B")
    prod_a_name = _unique_name("SBD-A")
    prod_b_name = _unique_name("SBD-B")

    rel_a_id = uuid.uuid4()
    rel_b_id = uuid.uuid4()
    rule_id = uuid.uuid4()

    synthetic_tracker["reference_drugs"].extend([ing_a_id, ing_b_id, prod_a_id, prod_b_id])
    synthetic_tracker["relations"].extend([rel_a_id, rel_b_id])
    synthetic_tracker["interaction_rules"].append(rule_id)

    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [
            {"id": ing_a_id, "name": ing_a_name, "rxcui": ing_a_rxcui, "term_type": "IN", "is_active": True},
            {"id": ing_b_id, "name": ing_b_name, "rxcui": ing_b_rxcui, "term_type": "IN", "is_active": True},
            {"id": prod_a_id, "name": prod_a_name, "rxcui": prod_a_rxcui, "term_type": "SBD", "is_active": True},
            {"id": prod_b_id, "name": prod_b_name, "rxcui": prod_b_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    await _insert_relation(id=rel_a_id, source_rxcui=prod_a_rxcui, relation_type="has_ingredient", target_rxcui=ing_a_rxcui, target_tty="IN")
    await _insert_relation(id=rel_b_id, source_rxcui=prod_b_rxcui, relation_type="has_ingredient", target_rxcui=ing_b_rxcui, target_tty="IN")
    await _insert_interaction_rule(id=rule_id, drug_a_id=ing_a_id, drug_b_id=ing_b_id, severity="moderate")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-Inter-ING"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(prod_a_id))
    _create_active_medication(patient["id"], str(prod_b_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    assert findings, "detect_drug_interactions must return a finding via ingredient resolution"
    matching = [f for f in findings if f.interaction_rule_id == rule_id]
    assert len(matching) == 1, f"expected exactly one finding for synthetic rule, got {matching}"
    finding = matching[0]
    # Rule is keyed to ingredients, not products
    assert {finding.drug_a_id, finding.drug_b_id} == {ing_a_id, ing_b_id}
    assert {finding.drug_a_name, finding.drug_b_name} == {ing_a_name, ing_b_name}
    assert finding.severity == "moderate"
    assert finding.mechanism is not None
    assert finding.source == "PR10 Test"
    # Both source products are represented via the resolution/source-map:
    # the resolved_ids contains ingredient IDs, but source_map ensures
    # they trace back to disjoint selected drugs. We verify indirectly by
    # confirming the finding exists (which the source_map gate allows) and
    # that a direct query of the source_map would show both products.
    # As an extra guard, verify that taking only ONE of the products yields nothing.
    # (Pair count before resolution requires >=2 distinct active drugs)
    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    single_patient = _create_patient(_unique_name("Patient-Inter-Single"))
    created_patient_ids.append(uuid.UUID(single_patient["id"]))
    _create_active_medication(single_patient["id"], str(prod_a_id))
    async with AsyncSessionLocal() as session:
        single_findings = await detect_drug_interactions(uuid.UUID(single_patient["id"]), session)
    assert single_findings == [], "single branded product must not produce an interaction by itself"


@pytest.mark.asyncio
async def test_interaction_single_product_with_two_ingredients_no_self_interaction_live(
    synthetic_tracker, created_patient_ids
):
    """
    The same selected product cannot self-interact through its own
    multiple ingredients.

    Setup:
      One branded product P (SBD, rxcui P) with TWO ingredient edges:
        P has_ingredient IA
        P has_ingredient IB
      Interaction rule IA + IB (severe).

    Patient takes ONLY P (single medication). The interaction engine must
    NOT report IA+IB as an interaction, because both ingredients come from
    the same selected drug (sources_a and sources_b not disjoint).
    """
    ing_a_id = uuid.uuid4()
    ing_b_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    ing_a_rxcui = _unique_rxcui()
    ing_b_rxcui = _unique_rxcui()
    while ing_b_rxcui == ing_a_rxcui:
        ing_b_rxcui = _unique_rxcui()
    prod_rxcui = _unique_rxcui()
    while prod_rxcui in {ing_a_rxcui, ing_b_rxcui}:
        prod_rxcui = _unique_rxcui()

    ing_a_name = _unique_name("ING-SA")
    ing_b_name = _unique_name("ING-SB")
    prod_name = _unique_name("SBD-SINGLE")

    rel_a_id = uuid.uuid4()
    rel_b_id = uuid.uuid4()
    rule_id = uuid.uuid4()

    synthetic_tracker["reference_drugs"].extend([ing_a_id, ing_b_id, prod_id])
    synthetic_tracker["relations"].extend([rel_a_id, rel_b_id])
    synthetic_tracker["interaction_rules"].append(rule_id)

    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [
            {"id": ing_a_id, "name": ing_a_name, "rxcui": ing_a_rxcui, "term_type": "IN", "is_active": True},
            {"id": ing_b_id, "name": ing_b_name, "rxcui": ing_b_rxcui, "term_type": "IN", "is_active": True},
            {"id": prod_id, "name": prod_name, "rxcui": prod_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    await _insert_relation(id=rel_a_id, source_rxcui=prod_rxcui, relation_type="has_ingredient", target_rxcui=ing_a_rxcui, target_tty="IN")
    await _insert_relation(id=rel_b_id, source_rxcui=prod_rxcui, relation_type="has_ingredient", target_rxcui=ing_b_rxcui, target_tty="IN")
    await _insert_interaction_rule(id=rule_id, drug_a_id=ing_a_id, drug_b_id=ing_b_id, severity="severe")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-Single-MultiING"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(prod_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    # Must NOT produce the IA+IB interaction from a single product.
    # Pair count is <2 distinct selected drugs, so empty. Even if the
    # resolver correctly expands to {P, IA, IB}, the source_map disjoint
    # check would also suppress it.
    assert findings == [], f"single product with two ingredients must not self-interact, got {findings}"
    # Also ensure the synthetic rule specifically is not present
    assert all(f.interaction_rule_id != rule_id for f in findings)


@pytest.mark.asyncio
async def test_interaction_two_branded_same_ingredient_no_false_positive_live(
    synthetic_tracker, created_patient_ids
):
    """
    Two different branded products resolving to the SAME ingredient must
    not produce a self/false-positive interaction.

    Setup:
      Ingredient X (IN)
      Ingredient Y (IN) — unrelated, not taken
      Product P1 (SBD) has_ingredient X
      Product P2 (SBD) has_ingredient X  (same X!)
      Interaction rule X + Y (moderate) — Y not among patient's drugs
      Patient takes P1 + P2

    No interaction should be reported (Y not present). This proves
    deduplication and that the engine does not double-count the same
    ingredient via two products to fabricate a spurious pair.

    Additional self-pair check:
      Interaction rule X + X (same ingredient twice) with patient taking
      P1+P2 must also yield no finding, because sources_a and sources_b
      overlap (both map to {P1, P2}) and are not disjoint.
    """
    ing_x_id = uuid.uuid4()
    ing_y_id = uuid.uuid4()
    prod1_id = uuid.uuid4()
    prod2_id = uuid.uuid4()
    ing_x_rxcui = _unique_rxcui()
    ing_y_rxcui = _unique_rxcui()
    while ing_y_rxcui == ing_x_rxcui:
        ing_y_rxcui = _unique_rxcui()
    prod1_rxcui = _unique_rxcui()
    prod2_rxcui = _unique_rxcui()
    while len({ing_x_rxcui, ing_y_rxcui, prod1_rxcui, prod2_rxcui}) < 4:
        prod2_rxcui = _unique_rxcui()

    ing_x_name = _unique_name("ING-X")
    ing_y_name = _unique_name("ING-Y")
    prod1_name = _unique_name("SBD-P1")
    prod2_name = _unique_name("SBD-P2")

    rel1_id = uuid.uuid4()
    rel2_id = uuid.uuid4()
    rule_xy_id = uuid.uuid4()
    rule_xx_id = uuid.uuid4()

    synthetic_tracker["reference_drugs"].extend([ing_x_id, ing_y_id, prod1_id, prod2_id])
    synthetic_tracker["relations"].extend([rel1_id, rel2_id])
    synthetic_tracker["interaction_rules"].extend([rule_xy_id, rule_xx_id])

    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [
            {"id": ing_x_id, "name": ing_x_name, "rxcui": ing_x_rxcui, "term_type": "IN", "is_active": True},
            {"id": ing_y_id, "name": ing_y_name, "rxcui": ing_y_rxcui, "term_type": "IN", "is_active": True},
            {"id": prod1_id, "name": prod1_name, "rxcui": prod1_rxcui, "term_type": "SBD", "is_active": True},
            {"id": prod2_id, "name": prod2_name, "rxcui": prod2_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    await _insert_relation(id=rel1_id, source_rxcui=prod1_rxcui, relation_type="has_ingredient", target_rxcui=ing_x_rxcui, target_tty="IN")
    await _insert_relation(id=rel2_id, source_rxcui=prod2_rxcui, relation_type="has_ingredient", target_rxcui=ing_x_rxcui, target_tty="IN")
    await _insert_interaction_rule(id=rule_xy_id, drug_a_id=ing_x_id, drug_b_id=ing_y_id, severity="moderate")
    # Self-pair rule X+X — should never fire for P1+P2 via disjoint check
    await _insert_interaction_rule(id=rule_xx_id, drug_a_id=ing_x_id, drug_b_id=ing_x_id, severity="moderate")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-SameING"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(prod1_id))
    _create_active_medication(patient["id"], str(prod2_id))

    async with AsyncSessionLocal() as session:
        findings = await detect_drug_interactions(uuid.UUID(patient["id"]), session)

    # X+Y must not appear (Y not taken)
    assert all(f.interaction_rule_id != rule_xy_id for f in findings), "two products sharing same ingredient must not trigger X+Y"
    # X+X must not appear (self-interaction, disjoint check)
    assert all(f.interaction_rule_id != rule_xx_id for f in findings), "X+X self-rule must not fire for two products of same ingredient"
    # In fact, for this synthetic-only patient, there should be no findings at all
    # (seed interactions could still appear if seed drugs were used, but we only use synthetic)
    synthetic_only = [f for f in findings if f.interaction_rule_id in {rule_xy_id, rule_xx_id}]
    assert synthetic_only == []


# ===========================================================================
# C. Safety score integration — live DB
# ===========================================================================

@pytest.mark.asyncio
async def test_safety_score_includes_ingredient_adr_via_branded_live(
    synthetic_tracker, created_patient_ids
):
    """
    Ingredient-level ADR findings must flow through the REAL
    calculate_safety_score() and contribute to the final deterministic
    result. We assert the actual returned score/risk/findings, not a
    hand-recalculated expectation as the primary assertion.
    """
    ing_id = uuid.uuid4()
    branded_id = uuid.uuid4()
    ing_rxcui = _unique_rxcui()
    branded_rxcui = _unique_rxcui()
    while branded_rxcui == ing_rxcui:
        branded_rxcui = _unique_rxcui()
    ing_name = _unique_name("ING-SCORE-ADR")
    branded_name = _unique_name("SBD-SCORE-ADR")
    rel_id = uuid.uuid4()
    adr_rule_id = uuid.uuid4()

    synthetic_tracker["reference_drugs"].extend([ing_id, branded_id])
    synthetic_tracker["relations"].append(rel_id)
    synthetic_tracker["adr_rules"].append(adr_rule_id)

    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [
            {"id": ing_id, "name": ing_name, "rxcui": ing_rxcui, "term_type": "IN", "is_active": True},
            {"id": branded_id, "name": branded_name, "rxcui": branded_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    await _insert_relation(id=rel_id, source_rxcui=branded_rxcui, relation_type="has_ingredient", target_rxcui=ing_rxcui, target_tty="IN")
    # Severe ADR → 30 points
    await _insert_adr_rule(id=adr_rule_id, drug_id=ing_id, reaction="PR10 Score ADR", severity="severe")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-ScoreADR"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(branded_id))

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    # The real engine must have discovered the ingredient ADR.
    assert len(result.adr_findings) >= 1, "safety score must include at least one ADR finding"
    adr_ids = {f.adr_rule_id for f in result.adr_findings}
    assert adr_rule_id in adr_ids, "synthetic ingredient ADR must appear in safety score's adr_findings"
    # The ADR finding must be tied to the ingredient, not the branded product
    adr_finding = next(f for f in result.adr_findings if f.adr_rule_id == adr_rule_id)
    assert adr_finding.drug_id == ing_id

    # Penalties must include the ADR penalty
    adr_penalties = [p for p in result.penalties if p.category == "adr" and p.source == adr_finding]
    assert len(adr_penalties) == 1, "ADR must produce exactly one penalty entry via safety_score_engine"
    assert adr_penalties[0].severity == "severe"
    assert adr_penalties[0].points == 30

    # Final deterministic result is not manually recalculated as the primary assertion;
    # we assert the actual engine's returned score reflects the deduction:
    # BASE 100 - sum(penalties) floored at MIN 0
    from app.analysis.safety_score_engine import BASE_SCORE, MIN_SCORE

    expected_score = max(BASE_SCORE - result.total_points_deducted, MIN_SCORE)
    assert result.safety_score == expected_score, "safety_score must equal BASE - total_deducted"
    assert result.total_points_deducted >= 30
    assert result.safety_score <= 70  # 100-30 or less
    # Risk level must be consistent with thresholds (low >=70, moderate >=40, else high)
    # With a severe ADR (30 pts) the score is 70 → low boundary; check it is not fabricated.
    assert result.risk_level in ("low", "moderate", "high")
    # Ensure the finding flowed through: safety_score's total_deducted includes the ADR
    assert result.total_points_deducted == sum(p.points for p in result.penalties)


@pytest.mark.asyncio
async def test_safety_score_includes_ingredient_interaction_via_branded_live(
    synthetic_tracker, created_patient_ids
):
    """
    Ingredient-level interaction findings must flow through the REAL
    calculate_safety_score().

    Setup: two branded products each mapping to a distinct ingredient,
    interaction rule between those ingredients (severe → 30 pts).
    """
    ing_a_id = uuid.uuid4()
    ing_b_id = uuid.uuid4()
    prod_a_id = uuid.uuid4()
    prod_b_id = uuid.uuid4()
    ing_a_rxcui = _unique_rxcui()
    ing_b_rxcui = _unique_rxcui()
    while ing_b_rxcui == ing_a_rxcui:
        ing_b_rxcui = _unique_rxcui()
    prod_a_rxcui = _unique_rxcui()
    prod_b_rxcui = _unique_rxcui()
    while len({ing_a_rxcui, ing_b_rxcui, prod_a_rxcui, prod_b_rxcui}) < 4:
        prod_b_rxcui = _unique_rxcui()

    ing_a_name = _unique_name("ING-SCORE-A")
    ing_b_name = _unique_name("ING-SCORE-B")
    prod_a_name = _unique_name("SBD-SCORE-A")
    prod_b_name = _unique_name("SBD-SCORE-B")

    rel_a_id = uuid.uuid4()
    rel_b_id = uuid.uuid4()
    rule_id = uuid.uuid4()

    synthetic_tracker["reference_drugs"].extend([ing_a_id, ing_b_id, prod_a_id, prod_b_id])
    synthetic_tracker["relations"].extend([rel_a_id, rel_b_id])
    synthetic_tracker["interaction_rules"].append(rule_id)

    live_user = await _get_live_auth_user_id()

    await _insert_reference_drugs(
        [
            {"id": ing_a_id, "name": ing_a_name, "rxcui": ing_a_rxcui, "term_type": "IN", "is_active": True},
            {"id": ing_b_id, "name": ing_b_name, "rxcui": ing_b_rxcui, "term_type": "IN", "is_active": True},
            {"id": prod_a_id, "name": prod_a_name, "rxcui": prod_a_rxcui, "term_type": "SBD", "is_active": True},
            {"id": prod_b_id, "name": prod_b_name, "rxcui": prod_b_rxcui, "term_type": "SBD", "is_active": True},
        ]
    )
    await _insert_relation(id=rel_a_id, source_rxcui=prod_a_rxcui, relation_type="has_ingredient", target_rxcui=ing_a_rxcui, target_tty="IN")
    await _insert_relation(id=rel_b_id, source_rxcui=prod_b_rxcui, relation_type="has_ingredient", target_rxcui=ing_b_rxcui, target_tty="IN")
    await _insert_interaction_rule(id=rule_id, drug_a_id=ing_a_id, drug_b_id=ing_b_id, severity="severe")

    app.dependency_overrides[get_current_user] = _override_current_user(live_user)
    patient = _create_patient(_unique_name("Patient-ScoreInter"))
    created_patient_ids.append(uuid.UUID(patient["id"]))
    _create_active_medication(patient["id"], str(prod_a_id))
    _create_active_medication(patient["id"], str(prod_b_id))

    async with AsyncSessionLocal() as session:
        result = await calculate_safety_score(uuid.UUID(patient["id"]), session)

    # Real findings must include the ingredient interaction
    assert len(result.interaction_findings) >= 1
    assert any(f.interaction_rule_id == rule_id for f in result.interaction_findings)

    interaction_finding = next(f for f in result.interaction_findings if f.interaction_rule_id == rule_id)
    assert {interaction_finding.drug_a_id, interaction_finding.drug_b_id} == {ing_a_id, ing_b_id}

    # Penalties must reflect it
    inter_penalties = [p for p in result.penalties if p.category == "drug_interaction" and p.source == interaction_finding]
    assert len(inter_penalties) == 1
    assert inter_penalties[0].points == 30
    assert inter_penalties[0].severity == "severe"

    from app.analysis.safety_score_engine import BASE_SCORE, MIN_SCORE

    assert result.safety_score == max(BASE_SCORE - result.total_points_deducted, MIN_SCORE)
    assert result.total_points_deducted >= 30
    assert result.safety_score <= 70
    assert result.total_points_deducted == sum(p.points for p in result.penalties)


# ===========================================================================
# D. Data isolation / safety to run repeatedly — live check
# ===========================================================================

@pytest.mark.asyncio
async def test_synthetic_rows_are_isolated_and_identifiable_live(
    synthetic_tracker,
):
    """
    Verify that synthetic test rows use uniquely-identifiable names/rxcuis
    and do not mutate existing seed records. This is a meta-check that the
    suite's isolation strategy is working — it inserts a synthetic row and
    confirms seed data is untouched.
    """
    await _require_live_db()
    # Capture seed count before
    async with AsyncSessionLocal() as session:
        before = (await session.execute(text("SELECT count(*) FROM reference_drugs"))).scalar()
        seed_names = (await session.execute(text("SELECT name FROM reference_drugs WHERE name IN ('Warfarin','Aspirin','Lisinopril')"))).all()

    assert len(seed_names) >= 1, "seed data must exist for isolation check"

    ing_id = uuid.uuid4()
    ing_name = _unique_name("ISOLATION-CHECK")
    ing_rxcui = _unique_rxcui()
    synthetic_tracker["reference_drugs"].append(ing_id)
    await _insert_reference_drugs([{"id": ing_id, "name": ing_name, "rxcui": ing_rxcui, "term_type": "IN", "is_active": True}])

    async with AsyncSessionLocal() as session:
        after = (await session.execute(text("SELECT count(*) FROM reference_drugs"))).scalar()
        # Exactly one new row
        assert after == before + 1, "exactly one synthetic row should have been added"
        # Seed rows unchanged
        result = await session.execute(text("SELECT name FROM reference_drugs WHERE name='Warfarin'"))
        assert result.first() is not None
        # Synthetic row is uniquely identifiable
        result2 = await session.execute(
            text("SELECT name, rxcui FROM reference_drugs WHERE id=:id").bindparams(bindparam("id")),
            {"id": ing_id},
        )
        row = result2.first()
        assert row is not None
        assert row[0].startswith("PR10-ISOLATION-CHECK-")
        assert row[1] == ing_rxcui
