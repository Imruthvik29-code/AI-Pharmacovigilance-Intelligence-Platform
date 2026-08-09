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
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug
from app.db.session import get_db
from app.schemas.reference_drug import ReferenceDrugSearchResult

router = APIRouter(tags=["reference-drugs"])

MIN_QUERY_LENGTH = 2
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@router.get("/reference-drugs/search", response_model=list[ReferenceDrugSearchResult])
async def search_reference_drugs(
    q: str = Query(
        ...,
        min_length=MIN_QUERY_LENGTH,
        description="Partial, case-insensitive drug name to search for (min 2 chars).",
    ),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
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

    Leading/trailing whitespace in `q` is stripped before matching.
    """
    normalized = q.strip()

    rank = case(
        (func.lower(ReferenceDrug.name) == normalized.lower(), 0),
        (ReferenceDrug.name.ilike(f"{normalized}%"), 1),
        else_=2,
    )

    stmt = (
        select(ReferenceDrug)
        .where(ReferenceDrug.name.ilike(f"%{normalized}%"))
        .order_by(rank, ReferenceDrug.name)
        .limit(limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())
