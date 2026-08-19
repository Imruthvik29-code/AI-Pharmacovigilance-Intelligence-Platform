"""
Reference-drug search endpoint:

    GET /api/v1/reference-drugs/search

Read-only lookup over the shared `reference_drugs` catalog, added to
support the frontend medication-picker autocomplete once the RxNorm
import (backend/scripts/import_rxnorm.py) has expanded the catalog
beyond the hand-curated Phase 1 seed drugs. Frontend autocomplete itself
is NOT implemented here.

Ownership: none -- reference_drugs is shared reference data across all
authenticated users (001_initial_schema.sql's existing RLS policy:
"Authenticated users read reference_drugs"), not scoped to a patient or
the calling user -- same treatment medications.py already gives drug
lookups via `_assert_drug_exists`.

This route is its own file rather than living in medications.py -- it is
a lookup over the shared catalog itself, not a patient-scoped medication
record, mirroring how conditions.py/symptoms.py/timeline.py/schedule.py
are each their own router file per resource area.

Authentication: requires a verified caller (`get_current_user`), same as
every other route in this API -- not a public/anonymous endpoint, even
though the underlying data isn't user-owned.

Ranking: results are ordered
  1. exact (case-insensitive) name match
  2. prefix match (name starts with the query, case-insensitive)
  3. alphabetically
via a single SQLAlchemy `case()` ranking expression as the primary
ORDER BY key, with `ReferenceDrug.name` as the secondary/tiebreaker key
-- no raw SQL, matching this codebase's existing convention throughout
app/api/v1/*.py.

No new index is added for this search -- a plain `ilike('%...%')` scan is
adequate at the catalog sizes in scope here; if this becomes a real
bottleneck at much larger scale, that is a deliberate, separately
requested change, not something to guess at here.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug, rxnorm_term_type_enum
from app.db.session import get_db
from app.schemas.reference_drug import ReferenceDrugSearchResult

router = APIRouter(tags=["reference-drugs"])

MIN_QUERY_LENGTH = 2
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# RxNorm TTY vocabulary, from the DB enum (single source of truth).
_VALID_TERM_TYPES = set(rxnorm_term_type_enum.enums)


def _parse_term_type_filter(raw: str | None) -> list[str]:
    """Parse and validate the optional comma-separated TTY filter.

    Raises HTTPException(422) for unknown TTYs (same rejection style as the
    Query ge/le constraints on `limit`).
    """
    if not raw:
        return []
    requested = [t.strip().upper() for t in raw.split(",") if t.strip()]
    invalid = [t for t in requested if t not in _VALID_TERM_TYPES]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown term type(s): {', '.join(invalid)}. "
                f"Valid values: {', '.join(sorted(_VALID_TERM_TYPES))}"
            ),
        )
    return requested


@router.get("/reference-drugs/search", response_model=list[ReferenceDrugSearchResult])
async def search_reference_drugs(
    q: str = Query(
        ...,
        min_length=MIN_QUERY_LENGTH,
        description="Partial, case-insensitive drug name to search for (min 2 chars).",
    ),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    term_type: str | None = Query(
        default=None,
        description=(
            "Optional comma-separated RxNorm Term Type filter, e.g. 'IN,SCD' "
            "(ingredient, clinical drug, ...). Restricts results to concepts "
            "of the given TTY(s). Defaults to all TTYs."
        ),
    ),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReferenceDrug]:
    """
    Search the reference drug catalog by partial, case-insensitive name.

    `q` shorter than MIN_QUERY_LENGTH is rejected as a 422 via FastAPI's
    `min_length` query validation. `limit` is capped at MAX_LIMIT -- an
    out-of-range value is rejected as a 422 rather than silently clamped,
    matching the same `ge`/`le` Query pattern already used elsewhere in
    this codebase (e.g. schemas/medication.py's `times_per_day`).

    `term_type` is an optional, additive TTY filter (e.g. `IN` for
    ingredients, `SCD`/`SBD` for clinical/branded drugs, `GPCK`/`BPCK` for
    packs, `DF` for dose forms). Unknown values are rejected with a 422.
    Omitting it preserves the original behavior of searching every TTY.

    Leading/trailing whitespace in `q` is stripped before matching.
    """
    normalized = q.strip()
    ttys = _parse_term_type_filter(term_type)

    rank = case(
        (func.lower(ReferenceDrug.name) == normalized.lower(), 0),
        (ReferenceDrug.name.ilike(f"{normalized}%"), 1),
        else_=2,
    )

    stmt = select(ReferenceDrug).where(ReferenceDrug.name.ilike(f"%{normalized}%"))
    if ttys:
        stmt = stmt.where(ReferenceDrug.term_type.in_(ttys))
    stmt = stmt.order_by(rank, ReferenceDrug.name).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
