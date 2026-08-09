"""
RxNorm reference-drug catalog importer.

Populates/expands `reference_drugs` from the RxNorm terminology, published
via NLM's public RxNav REST API (https://rxnav.nlm.nih.gov/REST/) -- no
UMLS account, no API key, no license agreement required. See
backend/scripts/README.md for full usage instructions.

## Scope

Phase 1's seed data (002_seed_data.sql) intentionally ships only a small,
hand-curated drug list (spec section 3: "curated drug/interaction set,
schema built to scale later"). This script is the "scale later" step for
the `reference_drugs` catalog ONLY -- it does NOT touch `interaction_rules`
or `adr_rules`, which remain hand-curated and are out of scope here.

## RxNav API constraint (verified against NLM's own API documentation
## before writing this script)

RxNav's bulk enumeration endpoint, `getAllConceptsByTTY`
(`/REST/allconcepts.json?tty=...`), has exactly two parameters -- `format`
and `tty` -- and no offset/limit/pagination parameter of any kind. It
returns the *entire* concept list for the requested term type(s) in one
response. There is no server-side pagination to push `--limit`/`--offset`
down to.

This script therefore does CLIENT-SIDE batching over one cached bulk
fetch:
  1. Fetch `/REST/allconcepts.json?tty=<TTY>` once per configured TTY and
     cache the raw JSON response to disk
     (`backend/scripts/.rxnorm_cache/allconcepts_<tty>.json`), so repeat
     runs (including resumed/limited runs) never re-hit the network unless
     `--refresh-cache` is passed.
  2. `--offset`/`--limit` slice that cached, name-sorted concept list
     client-side.
  3. A small local checkpoint file
     (`backend/scripts/.rxnorm_cache/checkpoint_<tty>.json`) records the
     next offset to resume from -- a convenience, not a correctness
     requirement (see idempotency note below).

## Idempotency and resumability

Every database write is an upsert keyed on the new, unique `rxcui` column:
  - If a row with this `rxcui` already exists -> only `source` and
    `source_updated_at` are refreshed. Re-running any slice, or the whole
    catalog, is always a safe no-op for rows already imported.
  - Else if an EXISTING row's `name` matches the RxNorm concept name
    case-insensitively (this is how the original hand-curated seed drugs
    get backfilled) -> that same row is updated in place. Its `id` (and
    therefore every existing `medications.drug_id` /
    `interaction_rules.drug_a_id`/`drug_b_id` / `adr_rules.drug_id`
    foreign key referencing it) is preserved exactly.
  - Else if a name match exists but that row already carries a DIFFERENT
    rxcui -> skipped and logged (never silently overwritten); a human can
    review this case manually.
  - Else -> a new row is INSERTed with a fresh UUID.

This script NEVER deletes or renumbers a row. It only ever adds new rows
or fills in `rxcui`/`source`/`source_updated_at` on existing ones.

## Usage

See backend/scripts/README.md. Quick example (run from backend/):

    python -m scripts.import_rxnorm --tty IN --limit 500 --dry-run
    python -m scripts.import_rxnorm --tty IN --limit 500
    python -m scripts.import_rxnorm --tty IN --limit 500   # continues via checkpoint
"""
import argparse
import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

# Allow `python scripts/import_rxnorm.py` (run from backend/) to find `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import ReferenceDrug  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

logger = logging.getLogger("scripts.import_rxnorm")

RXNAV_BASE_URL = "https://rxnav.nlm.nih.gov/REST"
DEFAULT_TTY = "IN"  # ingredients -- matches the granularity of the existing curated seed drugs
SOURCE_NAME = "RxNorm"
CACHE_DIR = Path(__file__).resolve().parent / ".rxnorm_cache"


@dataclass(frozen=True)
class RxNormConcept:
    rxcui: str
    name: str
    tty: str


def _cache_path(tty: str) -> Path:
    return CACHE_DIR / f"allconcepts_{tty.replace(' ', '_')}.json"


def _checkpoint_path(tty: str) -> Path:
    return CACHE_DIR / f"checkpoint_{tty.replace(' ', '_')}.json"


def _read_checkpoint(tty: str) -> int:
    path = _checkpoint_path(tty)
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text()).get("next_offset", 0))
    except (ValueError, json.JSONDecodeError):
        return 0


def _write_checkpoint(tty: str, next_offset: int) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path(tty).write_text(json.dumps({"next_offset": next_offset}))


def fetch_all_concepts(
    tty: str, *, refresh_cache: bool = False, timeout_seconds: float = 60.0
) -> list[RxNormConcept]:
    """
    Fetch (or load from disk cache) the full RxNorm concept list for `tty`
    via RxNav's getAllConceptsByTTY endpoint. This is a single, unpaginated
    network call -- RxNav does not support offset/limit on this endpoint.
    Client-side batching happens in `select_batch` below.
    """
    cache_path = _cache_path(tty)
    if cache_path.exists() and not refresh_cache:
        logger.info("Using cached RxNorm concept list for tty=%s (%s)", tty, cache_path)
        raw = json.loads(cache_path.read_text())
    else:
        url = f"{RXNAV_BASE_URL}/allconcepts.json"
        logger.info("Fetching RxNorm concepts from %s?tty=%s", url, tty)
        resp = httpx.get(url, params={"tty": tty}, timeout=timeout_seconds)
        resp.raise_for_status()
        raw = resp.json()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(raw))
        logger.info("Cached RxNorm response to %s", cache_path)

    group = raw.get("minConceptGroup") or {}
    concepts_raw = group.get("minConcept") or []

    concepts = [
        RxNormConcept(rxcui=str(c["rxcui"]), name=c["name"], tty=c.get("tty", tty))
        for c in concepts_raw
        if c.get("rxcui") and c.get("name")
    ]
    # Sorted deterministically so offset/limit windows are stable across
    # runs, regardless of the order RxNav happened to return concepts in.
    concepts.sort(key=lambda c: (c.name.lower(), c.rxcui))
    return concepts


def select_batch(
    concepts: list[RxNormConcept], *, offset: int, limit: int | None
) -> list[RxNormConcept]:
    """Client-side pagination slice over an already-fetched concept list."""
    if limit is None:
        return concepts[offset:]
    return concepts[offset : offset + limit]


async def _find_by_rxcui(session, rxcui: str) -> ReferenceDrug | None:
    result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.rxcui == rxcui))
    return result.scalar_one_or_none()


async def _find_by_name_ci(session, name: str) -> ReferenceDrug | None:
    result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.name.ilike(name)))
    return result.scalar_one_or_none()


@dataclass
class ImportStats:
    updated_existing_by_rxcui: int = 0
    backfilled_existing_by_name: int = 0
    inserted_new: int = 0
    skipped_ambiguous: int = 0


async def import_batch(
    concepts: list[RxNormConcept], *, dry_run: bool, source_name: str = SOURCE_NAME
) -> ImportStats:
    """
    Upsert one batch of RxNorm concepts into `reference_drugs`.

    Never deletes or renumbers a row -- see module docstring for the full
    match-then-upsert-or-insert decision order.
    """
    stats = ImportStats()
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        for concept in concepts:
            existing_by_rxcui = await _find_by_rxcui(session, concept.rxcui)
            if existing_by_rxcui is not None:
                logger.debug(
                    "rxcui=%s already imported (id=%s) -- refreshing metadata only",
                    concept.rxcui, existing_by_rxcui.id,
                )
                if not dry_run:
                    existing_by_rxcui.source = source_name
                    existing_by_rxcui.source_updated_at = now
                stats.updated_existing_by_rxcui += 1
                continue

            existing_by_name = await _find_by_name_ci(session, concept.name)
            if existing_by_name is not None:
                if existing_by_name.rxcui is not None and existing_by_name.rxcui != concept.rxcui:
                    logger.warning(
                        "Name match for '%s' already has a different rxcui (%s != %s) -- skipping.",
                        concept.name, existing_by_name.rxcui, concept.rxcui,
                    )
                    stats.skipped_ambiguous += 1
                    continue
                logger.info(
                    "Backfilling existing drug '%s' (id=%s) with rxcui=%s",
                    existing_by_name.name, existing_by_name.id, concept.rxcui,
                )
                if not dry_run:
                    existing_by_name.rxcui = concept.rxcui
                    existing_by_name.source = source_name
                    existing_by_name.source_updated_at = now
                stats.backfilled_existing_by_name += 1
                continue

            logger.info("Inserting new drug '%s' (rxcui=%s)", concept.name, concept.rxcui)
            if not dry_run:
                session.add(
                    ReferenceDrug(
                        id=uuid.uuid4(),
                        name=concept.name,
                        generic_name=None,
                        drug_class=None,
                        rxcui=concept.rxcui,
                        source=source_name,
                        source_updated_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            stats.inserted_new += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return stats


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tty", default=DEFAULT_TTY,
        help=f"RxNorm term type(s), space-separated (default: {DEFAULT_TTY!r} = ingredients).",
    )
    parser.add_argument("--limit", type=int, default=None,
                         help="Max concepts to process this run (default: all remaining).")
    parser.add_argument("--offset", type=int, default=None,
                         help="Starting offset into the cached, name-sorted concept list. "
                              "Defaults to the last saved checkpoint for this --tty.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Report planned inserts/updates without writing to the database.")
    parser.add_argument("--refresh-cache", action="store_true",
                         help="Force a fresh fetch from RxNav instead of using the on-disk cache.")
    parser.add_argument("--no-checkpoint", action="store_true",
                         help="Do not read or write the resumability checkpoint file.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    concepts = fetch_all_concepts(args.tty, refresh_cache=args.refresh_cache)
    logger.info("Loaded %d RxNorm concepts for tty=%s", len(concepts), args.tty)

    offset = args.offset
    if offset is None:
        offset = 0 if args.no_checkpoint else _read_checkpoint(args.tty)

    batch = select_batch(concepts, offset=offset, limit=args.limit)
    logger.info(
        "Processing batch: offset=%d limit=%s size=%d%s",
        offset, args.limit, len(batch), " (dry run)" if args.dry_run else "",
    )

    stats = await import_batch(batch, dry_run=args.dry_run)

    logger.info(
        "Done. updated_existing_by_rxcui=%d backfilled_existing_by_name=%d "
        "inserted_new=%d skipped_ambiguous=%d",
        stats.updated_existing_by_rxcui, stats.backfilled_existing_by_name,
        stats.inserted_new, stats.skipped_ambiguous,
    )

    if not args.dry_run and not args.no_checkpoint:
        _write_checkpoint(args.tty, offset + len(batch))


if __name__ == "__main__":
    asyncio.run(main())
