"""Static (DB-free) tests for Alembic migration SQL.

These tests never open a database connection -- they import the migration
modules directly from ``backend/alembic/versions/`` and walk every
``op.execute(...)`` call to extract the literal SQL string(s), then assert
basic syntactic properties (balanced quotes, balanced parentheses, no
obvious concatenation regressions).

Why static tests?
-----------------
The Phase 17 ``0003_add_rxnorm_concept_relations`` migration originally
shipped with a Python string-literal bug in two COMMENT statements that
broke ``alembic upgrade head`` at runtime with a SQL parse error. Static
analysis of the SQL literals catches that class of regression without
requiring a live Postgres (Supabase) instance, which is exactly the kind
of guard we want in CI.

Scope
-----
- Pure static checks only (no DB, no network, no env vars required).
- Covers every Alembic version file present under
  ``backend/alembic/versions/`` at test time.
- Does not run the migrations -- that is a separate integration concern.

Run with:
    pytest backend/tests/test_migrations_sql.py -v
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


ALEMBIC_VERSIONS_DIR = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
)


def _iter_migration_modules() -> list[Path]:
    return sorted(
        p for p in ALEMBIC_VERSIONS_DIR.glob("*.py") if not p.name.startswith("_")
    )


def _extract_op_execute_sql(module_path: Path) -> list[tuple[int, str]]:
    """Return ``(lineno, sql_string)`` for every ``op.execute(<str>)`` in *module_path*.

    Uses ``ast.literal_eval`` on the first argument so Python's implicit
    adjacent-string-literal concatenation is resolved exactly as the
    interpreter would, which is what makes this guard effective against
    the COMMENT-literal regression we are guarding against here.
    """
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    results: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ):
            continue
        if not node.args:
            continue
        try:
            value = ast.literal_eval(node.args[0])
        except (ValueError, SyntaxError):
            # Could be a sa.text(...) / sa.func.gen_random_uuid() style arg
            # -- only statically-checkable string literals are in scope here.
            continue
        if isinstance(value, str):
            results.append((node.lineno, value))

    return results


# ---------------------------------------------------------------------------
# Per-migration structural invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_path", _iter_migration_modules(), ids=lambda p: p.stem)
def test_every_op_execute_sql_is_balanced(module_path: Path):
    """Every ``op.execute("<sql>")`` literal must have balanced quotes/parens.

    This is the direct regression guard for the 0003 COMMENT bug: an
    unbalanced single quote or a stray parenthesis causes a SQL parse
    error the moment Alembic runs the migration.
    """
    for lineno, sql in _extract_op_execute_sql(module_path):
        # Single quotes must pair up. We do NOT try to parse escape/$$
        # constructs -- our migrations use plain ''-quoted strings only.
        assert sql.count("'") % 2 == 0, (
            f"{module_path.name}:{lineno} has unbalanced single quotes: {sql!r}"
        )
        # Parentheses must balance (ignores content inside quotes but our
        # migrations don't embed parens inside string literals, so a raw
        # count is a fine first-order guard).
        assert sql.count("(") == sql.count(")"), (
            f"{module_path.name}:{lineno} has unbalanced parentheses: {sql!r}"
        )


# ---------------------------------------------------------------------------
# 0003-specific invariants (guard the COMMENT-literal repair)
# ---------------------------------------------------------------------------


def _find_migration(name_suffix: str) -> Path:
    matches = [p for p in _iter_migration_modules() if name_suffix in p.name]
    assert len(matches) == 1, f"expected exactly one migration matching {name_suffix}"
    return matches[0]


def _extract_comment_targets(module_path: Path) -> dict[tuple[str, str], str]:
    """Return {(object_kind, object_name): comment_text} from COMMENT ON <obj> statements."""
    pattern = re.compile(
        r"COMMENT\s+ON\s+(TABLE|COLUMN)\s+([\w\.]+)\s+IS\s+'((?:[^']|'')*)'",
        re.IGNORECASE,
    )
    out: dict[tuple[str, str], str] = {}
    for _lineno, sql in _extract_op_execute_sql(module_path):
        for kind, name, text in pattern.findall(sql):
            out[(kind.upper(), name.lower())] = text
    return out


def test_0003_comment_literals_are_single_well_formed_strings():
    """The two COLUMN COMMENT literals that broke must be repaired exactly.

    The bug was that after the first '...', the continuation line was not
    reopened with a quote, producing SQL like:

        COMMENT ON COLUMN ... IS 'first part.' second part. ' (broken!)

    After the fix each COMMENT statement's body is one continuous,
    well-formed string literal; we assert that indirectly via the
    balanced-quote test above, and directly here by verifying the parsed
    COMMENT body matches the intended natural-language text.
    """
    m0003 = _find_migration("0003_rxnorm_concept_relations")
    comments = _extract_comment_targets(m0003)

    table_comment = comments[("TABLE", "rxnorm_concept_relations")]
    assert "Typed RxNorm relationship edges" in table_comment
    assert "import_rxnorm.py --related" in table_comment

    source_col_comment = comments[
        ("COLUMN", "rxnorm_concept_relations.source_rxcui")
    ]
    assert source_col_comment.startswith("RxCUI of the concept the relationship was fetched for.")
    assert "no FK" in source_col_comment
    # The buggy version had a stray closing quote mid-string; the fixed
    # body must be a single coherent sentence without internal unescaped
    # quotes.
    assert "'" not in source_col_comment

    target_col_comment = comments[
        ("COLUMN", "rxnorm_concept_relations.target_rxcui")
    ]
    assert target_col_comment.startswith(
        "RxCUI of the related concept, as returned by the RxNav API."
    )
    assert "no FK" in target_col_comment
    assert "'" not in target_col_comment


def test_0003_upgrade_creates_expected_objects():
    """Static check that the 0003 upgrade creates the expected table/index/policy."""
    m0003 = _find_migration("0003_rxnorm_concept_relations")
    sql_blobs = [sql for _ln, sql in _extract_op_execute_sql(m0003)]
    joined = "\n".join(sql_blobs).lower()

    assert "create table rxnorm_concept_relations" in joined
    assert "create index idx_rxnorm_concept_relations_target" in joined
    assert "enable row level security" in joined
    assert "authenticated users read rxnorm_concept_relations" in joined
    # RLS policy grants SELECT only.
    assert " for select " in joined


def test_0003_downgrade_drops_policy_before_table():
    """Downgrade must drop the policy before dropping the table (order matters)."""
    m0003 = _find_migration("0003_rxnorm_concept_relations")
    source = m0003.read_text(encoding="utf-8")
    downgrade_start = source.index("def downgrade")
    downgrade_body = source[downgrade_start:]
    drop_policy_idx = downgrade_body.upper().index("DROP POLICY")
    drop_table_idx = downgrade_body.upper().index("DROP TABLE")
    assert drop_policy_idx < drop_table_idx, (
        "downgrade() must DROP POLICY before DROP TABLE"
    )


def test_0003_does_not_alter_existing_tables():
    """0003 is additive -- it must not ALTER/DROP any pre-existing table."""
    m0003 = _find_migration("0003_rxnorm_concept_relations")
    # Only inspect the upgrade() body.
    source = m0003.read_text(encoding="utf-8")
    upgrade_start = source.index("def upgrade")
    downgrade_start = source.index("def downgrade")
    upgrade_body = source[upgrade_start:downgrade_start].lower()

    # 0003 creates ONE new table and is allowed to ALTER that same table
    # (it ENABLE ROW LEVEL SECURITY on it). It must NOT touch any
    # pre-existing table.
    preexisting_tables = (
        "patients",
        "conditions",
        "medications",
        "medication_schedule",
        "medication_doses",
        "symptoms",
        "reference_drugs",
        "interaction_rules",
        "adr_rules",
        "timeline_events",
        "analysis_runs",
    )
    for tbl in preexisting_tables:
        assert f"alter table {tbl}" not in upgrade_body, (
            f"0003 must not alter pre-existing table {tbl!r}"
        )
        assert f"drop table {tbl}" not in upgrade_body, (
            f"0003 must not drop pre-existing table {tbl!r}"
        )

    forbidden_phrases = ["drop index", "rename table", "rename column", "drop column"]
    for needle in forbidden_phrases:
        assert needle not in upgrade_body, (
            f"0003 upgrade must be additive but found {needle!r}"
        )
