"""
RxNorm reference-drug catalog importer — optimized bounded-memory pipeline.

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
(`/REST/allconcepts.json?tty=...` and `/REST/Prescribe/allconcepts.json?tty=...`),
has exactly two parameters -- `format` and `tty` -- and no offset/limit/pagination
parameter of any kind. It returns the *entire* concept list for the requested
term type(s) in one response. There is no server-side pagination.

This script therefore does CLIENT-SIDE batching over one cached bulk fetch:

  1. Fetch `/REST/Prescribe/allconcepts.json?tty=<TTY>` (Prescribable Content,
     the default) or `/REST/allconcepts.json?tty=<TTY>` (`--full-rxnorm`)
     once per configured TTY and cache the raw JSON response to disk
     (`backend/scripts/.rxnorm_cache/allconcepts_<tty>.json` for Prescribable,
     `allconcepts_<tty>_full.json` for full) via an atomic `.partial` write,
     so repeat runs (including resumed/limited runs) never re-hit the network
     unless `--refresh-cache` is passed. The HTTP download itself is NOT
     bounded — the full response lands on disk first because RxNav does not
     provide pagination.

  2. Stream-parse that cached file incrementally with `ijson` (bounded memory)
     and apply `--tty` filtering, `--offset`/`--limit`, and batch-size slicing
     client-side. No `json.loads(full_file)` is used for the large catalog.

  3. Persist in configurable batches (default 500 via
     `rxnorm_import_batch_size` in `app.core.config.Settings` or
     `--batch-size` CLI override). Each batch is a single DB transaction
     with batched SELECTs (2 queries per batch, not N+1), so earlier
     successful batches remain durable if a later batch fails.

  4. A small local checkpoint file
     (`backend/scripts/.rxnorm_cache/checkpoint_<tty>.json`) records the
     next offset to resume from — written atomically, updated only after a
     batch commits successfully, so a failed batch's offset is reportable
     and resumable without duplication.

## Streaming vs download

The bounded-memory guarantee covers **parsing, transformation, and persistence**:
the importer never holds the entire concept list in memory at once (streaming
via `ijson`, bounded batch buffers, batched DB writes). The HTTP download
step necessarily writes the full response to disk first (RxNav limitation).

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

Checkpoint/resume: checkpoint records the *last successful* offset (start of
next batch). On failure, the exception message includes batch number and
offset range, checkpoint stays at last success, and a retry without
`--offset` resumes exactly from that checkpoint.

## Usage

See backend/scripts/README.md. Quick examples (run from backend/):

    python -m scripts.import_rxnorm --tty IN --limit 500 --dry-run
    python -m scripts.import_rxnorm --tty IN --limit 500
    python -m scripts.import_rxnorm --tty IN --limit 500   # continues via checkpoint
    python -m scripts.import_rxnorm --tty IN --full-rxnorm --limit 500 --dry-run  # full catalog

"""
import argparse
import asyncio
import json
import logging
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import ijson
from sqlalchemy import func, select

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


# ---------------------------------------------------------------------------
# Paths & checkpoint helpers (atomic)
# ---------------------------------------------------------------------------

def _cache_path(tty: str, full_rxnorm: bool = False) -> Path:  # noqa: FBT001,FBT002
    base = tty.replace(" ", "_")
    if full_rxnorm:
        return CACHE_DIR / f"allconcepts_{base}_full.json"
    return CACHE_DIR / f"allconcepts_{base}.json"


def _checkpoint_path(tty: str, full_rxnorm: bool = False) -> Path:  # noqa: FBT001,FBT002
    base = tty.replace(" ", "_")
    if full_rxnorm:
        return CACHE_DIR / f"checkpoint_{base}_full.json"
    return CACHE_DIR / f"checkpoint_{base}.json"


def _read_checkpoint(tty: str, full_rxnorm: bool = False) -> int:  # noqa: FBT001,FBT002
    path = _checkpoint_path(tty, full_rxnorm=full_rxnorm)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
        return int(data.get("next_offset", 0))
    except (ValueError, json.JSONDecodeError, AttributeError):
        return 0


def _write_checkpoint(tty: str, next_offset: int, full_rxnorm: bool = False) -> None:  # noqa: FBT001,FBT002
    """Atomically write checkpoint to avoid corrupt file on interruption."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(tty, full_rxnorm=full_rxnorm)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"next_offset": next_offset}))
    tmp.replace(path)


def _rxnav_url(*, full_rxnorm: bool) -> str:  # noqa: FBT001
    if full_rxnorm:
        return f"{RXNAV_BASE_URL}/allconcepts.json"
    return f"{RXNAV_BASE_URL}/Prescribe/allconcepts.json"


def _parse_tty_filter(tty: str) -> set[str]:
    """Parse space/comma separated TTY string into a set of TTYs."""
    if not tty:
        return set()
    # Support both space and comma separators
    parts = tty.replace(",", " ").split()
    return {p.strip() for p in parts if p.strip()}


def _get_batch_size(cli_batch_size: int | None) -> int:
    if cli_batch_size is not None:
        return cli_batch_size
    try:
        from app.core.config import get_settings  # local import to avoid cycle

        return int(get_settings().rxnorm_import_batch_size)
    except Exception:  # noqa: BLE001
        return 500


# ---------------------------------------------------------------------------
# Cache fetch with atomic .partial handling
# ---------------------------------------------------------------------------

def _ensure_cache(
    tty: str,
    *,
    full_rxnorm: bool = False,  # noqa: FBT001,FBT002
    refresh_cache: bool = False,  # noqa: FBT001,FBT002
    timeout_seconds: float = 60.0,
) -> Path:
    """Ensure cached RxNav response exists, fetching atomically if needed."""
    cache_path = _cache_path(tty, full_rxnorm=full_rxnorm)
    if cache_path.exists() and not refresh_cache:
        logger.info("Using cached RxNorm concept list for tty=%s (%s)", tty, cache_path)
        return cache_path

    url = _rxnav_url(full_rxnorm=full_rxnorm)
    logger.info("Fetching RxNorm concepts from %s?tty=%s", url, tty)
    resp = httpx.get(url, params={"tty": tty}, timeout=timeout_seconds)
    resp.raise_for_status()
    # Validate JSON before writing atomically
    try:
        raw = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to parse RxNav JSON for tty={tty!r}: {exc}") from exc

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    partial_path = cache_path.with_suffix(cache_path.suffix + ".partial")
    # Write to .partial then atomically replace
    partial_path.write_text(json.dumps(raw))
    partial_path.replace(cache_path)
    logger.info("Cached RxNorm response to %s", cache_path)
    return cache_path


def fetch_all_concepts(
    tty: str,
    *,
    refresh_cache: bool = False,
    timeout_seconds: float = 60.0,
    full_rxnorm: bool = False,  # noqa: FBT001,FBT002
) -> list[RxNormConcept]:
    """
    Fetch (or load from disk cache) the full RxNorm concept list for `tty`
    via RxNav's getAllConceptsByTTY endpoint. This is a single, unpaginated
    network call -- RxNav does not support offset/limit on this endpoint.
    Client-side batching happens in `select_batch` / streaming pipeline.

    Note: this helper retains backward-compat whole-list semantics for small
    tests and sorts deterministically. The production `main()` path uses
    streaming (`_stream_concepts`) for bounded memory.
    """
    cache_path = _ensure_cache(
        tty, full_rxnorm=full_rxnorm, refresh_cache=refresh_cache, timeout_seconds=timeout_seconds
    )
    # Use streaming parse even here to avoid json.loads(full_file) for large files,
    # but return a sorted list for compatibility (tests assert sorting).
    tty_filter = _parse_tty_filter(tty)
    concepts: list[RxNormConcept] = []
    # If cache file is small, streaming is still correct
    for concept in _stream_concepts(cache_path, tty_filter=None):
        # fetch_all_concepts historically returned already TTY-filtered list
        # since RxNav was queried with ?tty=, all results match the filter.
        # Preserve that: if tty_filter is non-empty, ensure concept's tty is in filter
        # when the json payload includes tty; if payload missing tty, assume match.
        if tty_filter and concept.tty and concept.tty not in tty_filter:
            continue
        concepts.append(concept)
    concepts.sort(key=lambda c: (c.name.lower(), c.rxcui))
    return concepts


def _stream_concepts(
    cache_path: Path,
    tty_filter: set[str] | None = None,
) -> Iterator[RxNormConcept]:
    """
    Streaming, bounded-memory iterator over cached RxNav JSON using ijson.
    Does NOT load the whole file via json.loads. Yields one RxNormConcept at a time.
    Applies tty_filter if provided (skips non-matching TTYs).
    """
    # ijson needs a binary file handle
    with open(cache_path, "rb") as f:
        try:
            # The RxNav payload is {"minConceptGroup": {"minConcept": [ {...}, ... ] } }
            # Stream each item under minConceptGroup.minConcept.item
            objects = ijson.items(f, "minConceptGroup.minConcept.item")
            for obj in objects:
                try:
                    rxcui = obj.get("rxcui")
                    name = obj.get("name")
                    tty = obj.get("tty", "")
                    if not rxcui or not name:
                        continue
                    if tty_filter is not None and tty_filter:
                        # Only filter when tty is present in payload; if payload tty missing,
                        # treat as matching (backward compat with old payloads that omitted tty)
                        if tty and tty not in tty_filter:
                            continue
                    yield RxNormConcept(rxcui=str(rxcui), name=name, tty=tty or (next(iter(tty_filter)) if tty_filter else ""))
                except Exception:  # noqa: BLE001
                    # Skip malformed entry, continue streaming
                    logger.debug("Skipping malformed concept entry: %r", obj, exc_info=True)
                    continue
        except ijson.JSONError as exc:
            logger.error("Failed to stream-parse RxNorm cache %s: %s", cache_path, exc)
            raise


def select_batch(
    concepts: list[RxNormConcept], *, offset: int, limit: int | None
) -> list[RxNormConcept]:
    """Client-side pagination slice over an already-fetched concept list (backward compat)."""
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


async def _import_batch_optimized(
    concepts: list[RxNormConcept],
    *,
    dry_run: bool,  # noqa: FBT001
    source_name: str = SOURCE_NAME,
) -> ImportStats:
    """
    Batch-optimized upsert for one persistence batch.

    Uses 2 SELECTs per batch (by rxcui IN (...) and lower(name) IN (...))
    instead of N+1 per-concept SELECTs. Each call is its own transaction.
    """
    stats = ImportStats()
    if not concepts:
        return stats
    now = datetime.now(timezone.utc)

    # Deduplicate within-batch rxcui/name to avoid redundant work
    # but preserve stats semantics: duplicate rxcui in same batch should be
    # treated as rxcui match on second occurrence (idempotent within batch).
    async with AsyncSessionLocal() as session:
        rxcui_list = [c.rxcui for c in concepts]
        lower_names = [c.name.lower() for c in concepts]

        # Batch preload: existing by rxcui
        existing_by_rxcui: dict[str, ReferenceDrug] = {}
        if rxcui_list:
            result = await session.execute(select(ReferenceDrug).where(ReferenceDrug.rxcui.in_(rxcui_list)))
            for drug in result.scalars().all():
                existing_by_rxcui[drug.rxcui] = drug  # type: ignore[attr-defined]

        # Batch preload: existing by lower(name)
        existing_by_name: dict[str, ReferenceDrug] = {}
        if lower_names:
            result = await session.execute(
                select(ReferenceDrug).where(func.lower(ReferenceDrug.name).in_(lower_names))
            )
            for drug in result.scalars().all():
                # drug.name.lower() is the lookup key
                existing_by_name[drug.name.lower()] = drug  # type: ignore[union-attr]

        for concept in concepts:
            # 1) rxcui match (fast path, including within-batch inserted)
            existing_by_rxcui_match = existing_by_rxcui.get(concept.rxcui)
            if existing_by_rxcui_match is not None:
                logger.debug(
                    "rxcui=%s already imported (id=%s) -- refreshing metadata only",
                    concept.rxcui,
                    existing_by_rxcui_match.id,
                )
                if not dry_run:
                    existing_by_rxcui_match.source = source_name
                    existing_by_rxcui_match.source_updated_at = now
                stats.updated_existing_by_rxcui += 1
                continue

            lower = concept.name.lower()
            existing_by_name_match = existing_by_name.get(lower)
            if existing_by_name_match is not None:
                # Ambiguous: name matches but rxcui differs and existing already has an rxcui
                if existing_by_name_match.rxcui is not None and existing_by_name_match.rxcui != concept.rxcui:
                    logger.warning(
                        "Name match for '%s' already has a different rxcui (%s != %s) -- skipping.",
                        concept.name,
                        existing_by_name_match.rxcui,
                        concept.rxcui,
                    )
                    stats.skipped_ambiguous += 1
                    continue
                logger.info(
                    "Backfilling existing drug '%s' (id=%s) with rxcui=%s",
                    existing_by_name_match.name,
                    existing_by_name_match.id,
                    concept.rxcui,
                )
                if not dry_run:
                    existing_by_name_match.rxcui = concept.rxcui
                    existing_by_name_match.source = source_name
                    existing_by_name_match.source_updated_at = now
                    # Register in rxcui map so later duplicate in same batch hits rxcui path
                    existing_by_rxcui[concept.rxcui] = existing_by_name_match
                stats.backfilled_existing_by_name += 1
                continue

            logger.info("Inserting new drug '%s' (rxcui=%s)", concept.name, concept.rxcui)
            if not dry_run:
                new_drug = ReferenceDrug(
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
                session.add(new_drug)
                # Register immediately for within-batch idempotency
                existing_by_rxcui[concept.rxcui] = new_drug
                existing_by_name[lower] = new_drug
            stats.inserted_new += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return stats


async def import_batch(
    concepts: list[RxNormConcept], *, dry_run: bool, source_name: str = SOURCE_NAME  # noqa: FBT001
) -> ImportStats:
    """
    Upsert one batch of RxNorm concepts into `reference_drugs`.

    Backward-compatible wrapper that delegates to batch-optimized implementation.
    Each call is one transaction. For large imports, callers should slice
    into multiple `import_batch` calls (or use the streaming main pipeline)
    to get checkpoint durability.

    Never deletes or renumbers a row -- see module docstring.
    """
    return await _import_batch_optimized(concepts, dry_run=dry_run, source_name=source_name)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tty",
        default=DEFAULT_TTY,
        help=f"RxNorm term type(s), space/comma-separated (default: {DEFAULT_TTY!r} = ingredients).",
    )
    parser.add_argument(
        "--full-rxnorm",
        action="store_true",
        help="Use full RxNorm catalog (/REST/allconcepts.json) instead of Prescribable Content (/REST/Prescribe/allconcepts.json). Default is Prescribable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max concepts to process this run (default: all remaining after --offset).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=None,
        help="Starting offset into the filtered, streamed concept list. Defaults to the last saved checkpoint for this --tty (--full-rxnorm distinct).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Persistence batch size (default: rxnorm_import_batch_size from config, 500).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned inserts/updates without writing to the database or advancing checkpoint.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force a fresh fetch from RxNav instead of using the on-disk cache.",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Do not read or write the resumability checkpoint file.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    tty_filter = _parse_tty_filter(args.tty)
    # Default TTY wiring: if --tty not provided, DEFAULT_TTY is already set; ensure at least IN
    if not tty_filter:
        tty_filter = {DEFAULT_TTY}

    batch_size = _get_batch_size(args.batch_size)

    # Ensure cache exists (atomic .partial handling)
    cache_path = _ensure_cache(
        args.tty,
        full_rxnorm=args.full_rxnorm,
        refresh_cache=args.refresh_cache,
        timeout_seconds=60.0,
    )
    logger.info(
        "RxNorm cache ready: %s (tty=%s full_rxnorm=%s)", cache_path, args.tty, args.full_rxnorm
    )

    # Determine starting offset (checkpoint or explicit)
    start_offset = args.offset
    if start_offset is None:
        start_offset = 0 if args.no_checkpoint else _read_checkpoint(args.tty, full_rxnorm=args.full_rxnorm)
    if start_offset < 0:
        raise ValueError(f"--offset must be >= 0, got {start_offset}")

    # Streaming pipeline: iterate, skip to offset, filter, batch, persist, checkpoint per batch
    total_processed = 0
    total_stats = ImportStats()
    current_batch: list[RxNormConcept] = []
    stream_index = -1  # filtered stream index (after tty filtering)
    batch_number = 0
    next_checkpoint = start_offset

    logger.info(
        "Processing: offset=%d limit=%s batch_size=%d tty=%s full_rxnorm=%s%s",
        start_offset,
        args.limit,
        batch_size,
        args.tty,
        args.full_rxnorm,
        " (dry run)" if args.dry_run else "",
    )

    try:
        for concept in _stream_concepts(cache_path, tty_filter=tty_filter):
            stream_index += 1
            if stream_index < start_offset:
                continue
            if args.limit is not None and total_processed >= args.limit:
                break

            current_batch.append(concept)
            total_processed += 1

            # Flush when batch full
            if len(current_batch) >= batch_size:
                batch_number += 1
                batch_start = next_checkpoint
                batch_end = batch_start + len(current_batch)
                logger.info("Importing batch %d: offset %d..%d (%d concepts)", batch_number, batch_start, batch_end, len(current_batch))
                try:
                    stats = await _import_batch_optimized(current_batch, dry_run=args.dry_run)
                except Exception as exc:
                    # Do NOT advance checkpoint; report actionable failure
                    logger.error(
                        "Batch %d failed at offset %d..%d: %s (checkpoint remains at %d, resume with --offset %d or rerun without --offset to resume from checkpoint)",
                        batch_number,
                        batch_start,
                        batch_end,
                        exc,
                        next_checkpoint,
                        next_checkpoint,
                    )
                    raise RuntimeError(
                        f"Batch {batch_number} failed at offset {batch_start}..{batch_end} (checkpoint={next_checkpoint}): {exc}"
                    ) from exc

                # Merge stats
                total_stats.updated_existing_by_rxcui += stats.updated_existing_by_rxcui
                total_stats.backfilled_existing_by_name += stats.backfilled_existing_by_name
                total_stats.inserted_new += stats.inserted_new
                total_stats.skipped_ambiguous += stats.skipped_ambiguous

                if not args.dry_run and not args.no_checkpoint:
                    next_checkpoint = batch_end
                    _write_checkpoint(args.tty, next_checkpoint, full_rxnorm=args.full_rxnorm)

                current_batch = []

                if args.limit is not None and total_processed >= args.limit:
                    break

        # Flush remaining partial batch
        if current_batch:
            if args.limit is None or total_processed <= args.limit:
                batch_number += 1
                batch_start = next_checkpoint
                batch_end = batch_start + len(current_batch)
                logger.info("Importing batch %d: offset %d..%d (%d concepts)", batch_number, batch_start, batch_end, len(current_batch))
                try:
                    stats = await _import_batch_optimized(current_batch, dry_run=args.dry_run)
                except Exception as exc:
                    logger.error(
                        "Batch %d failed at offset %d..%d: %s (checkpoint remains at %d)",
                        batch_number,
                        batch_start,
                        batch_end,
                        exc,
                        next_checkpoint,
                    )
                    raise RuntimeError(
                        f"Batch {batch_number} failed at offset {batch_start}..{batch_end} (checkpoint={next_checkpoint}): {exc}"
                    ) from exc

                total_stats.updated_existing_by_rxcui += stats.updated_existing_by_rxcui
                total_stats.backfilled_existing_by_name += stats.backfilled_existing_by_name
                total_stats.inserted_new += stats.inserted_new
                total_stats.skipped_ambiguous += stats.skipped_ambiguous

                if not args.dry_run and not args.no_checkpoint:
                    next_checkpoint = batch_end
                    _write_checkpoint(args.tty, next_checkpoint, full_rxnorm=args.full_rxnorm)

    except RuntimeError:
        # Re-raise batch failure with context, already logged
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Import failed at stream_index=%d checkpoint=%d: %s", stream_index, next_checkpoint, exc, exc_info=True)
        raise

    logger.info(
        "Done. processed=%d updated_existing_by_rxcui=%d backfilled_existing_by_name=%d inserted_new=%d skipped_ambiguous=%d next_offset=%d",
        total_processed,
        total_stats.updated_existing_by_rxcui,
        total_stats.backfilled_existing_by_name,
        total_stats.inserted_new,
        total_stats.skipped_ambiguous,
        next_checkpoint if not args.dry_run and not args.no_checkpoint else start_offset,
    )


if __name__ == "__main__":
    asyncio.run(main())
