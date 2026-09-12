"""Authenticated read-only search over the shared reference-drug catalog."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser, get_current_user
from app.db.models import ReferenceDrug, rxnorm_term_type_enum
from app.db.session import get_db
from app.schemas.reference_drug import ReferenceDrugSearchResult

router = APIRouter(tags=["reference-drugs"])

MIN_QUERY_LENGTH = 2
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_VALID_TERM_TYPES = set(rxnorm_term_type_enum.enums)


def _parse_term_type_filter(raw: str | None) -> list[str]:
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
    q: str = Query(..., min_length=MIN_QUERY_LENGTH, description="Partial, case-insensitive medication or generic name (min 2 chars)."),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    term_type: str | None = Query(default=None, description="Optional comma-separated RxNorm Term Type filter."),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReferenceDrug]:
    """Search by the name patients see or the normalized generic name.

    Brand/product names remain the primary result identity. Matching
    `generic_name` makes ingredient-based discovery possible for catalog
    rows where a generic label is available. No fallback invents or
    resolves an unverified medication.
    """
    normalized = q.strip()
    ttys = _parse_term_type_filter(term_type)
    lowered = normalized.lower()

    exact_name = func.lower(ReferenceDrug.name) == lowered
    prefix_name = ReferenceDrug.name.ilike(f"{normalized}%")
    exact_generic = func.lower(ReferenceDrug.generic_name) == lowered
    prefix_generic = ReferenceDrug.generic_name.ilike(f"{normalized}%")
    contains_name = ReferenceDrug.name.ilike(f"%{normalized}%")
    contains_generic = ReferenceDrug.generic_name.ilike(f"%{normalized}%")

    rank = case(
        (exact_name, 0),
        (prefix_name, 1),
        (exact_generic, 2),
        (prefix_generic, 3),
        else_=4,
    )

    stmt = select(ReferenceDrug).where(or_(contains_name, contains_generic))
    if ttys:
        stmt = stmt.where(ReferenceDrug.term_type.in_(ttys))
    stmt = stmt.order_by(rank, ReferenceDrug.name).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
