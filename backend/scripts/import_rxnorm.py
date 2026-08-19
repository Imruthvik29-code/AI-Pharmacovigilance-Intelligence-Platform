"""
RxNorm reference-drug catalog importer — multi-TTY, bounded-memory pipeline.

Populates/expands `reference_drugs` (and, opt-in, `rxnorm_concept_relations`)
from the RxNorm terminology, published via NLM's public RxNav REST API
(https://rxnav.nlm.nih.gov/REST/) -- no UMLS account, no API key, no license
agreement required. See backend/scripts/README.md for full usage instructions.

## Scope

The Phase 1 seed data (002_seed_data.sql) intentionally shipped only a small,
hand-curated drug list (spec section 3). This script is the "scale later"
step for the `reference_drugs` catalog and the `rxnorm_concept_relations`
edge table -- it does NOT touch `interaction_rules` or `adr_rules`, which
remain hand-curated and are out of scope here.

### Multi-TTY import (default behavior)

A bare `python -m scripts.import_rxnorm` imports the full supported TTY set
(`IN PIN MIN SCD SBD GPCK BPCK DF` — the clinically meaningful structural
levels for a pharmacovigilance platform; see ARCHITECTURE_DECISIONS.md
§6.2/§7.3), automatically:

  1. Ensure a cached RxNav response per TTY (`getAllConceptsByTTY` has no
     server-side pagination, so one cached bulk fetch per TTY is the design;
     the HTTP download necessarily lands on disk first — parsing,
     transformation, and persistence remain streaming/bounded-memory).
  2. Derive the concept count for each TTY from the cached data (never
     hard-coded).
  3. Log an import plan (per TTY: discovered count, resume offset, batches).
  4. Stream-process each TTY in bounded batches (default 500 via
     `rxnorm_import_batch_size` in `app.core.config.Settings` or
     `--batch-size`), one DB transaction per batch.
  5. Continue to completion with per-batch checkpoints
     (`backend/scripts/.rxnorm_cache/checkpoint_<tty>.json`), written only
     after a batch commits, so an interrupted run resumes exactly where it
     stopped. No manual `--offset` arithmetic is required.

`--tty <TTY> [TTY ...]` restricts the run to specific TTYs; `--limit` is a
per-TTY cap for controlled/testing imports. Both remain available for
debugging but are not required for a normal full import.

### TTY identity and idempotency

Every concept is identified by its RxCUI (unique on `reference_drugs`).
Upsert semantics per concept:

  - RxCUI already imported and provenance already this source -> no-op
    (counted `already_current`).
  - RxCUI already imported with a different provenance -> refresh
    `source`/`source_updated_at`; `term_type` is backfilled only if still
    NULL (first TTY wins). `id` is never changed.
  - RxCUI not present and TTY is `IN` (ingredient) -> a case-insensitive
    EXACT name match against an existing row backfills that row in place
    (this is how the original hand-curated seed drugs get their RxCUI);
    the row's `id` — and therefore every existing
    `medications.drug_id` / `interaction_rules.drug_a_id`/`drug_b_id` /
    `adr_rules.drug_id` foreign key — is preserved exactly.
  - Otherwise -> a new row is INSERTed with a fresh UUID and its TTY
    recorded in `term_type`.

Name matching is deliberately reserved for `IN`: RxCUI + TTY identity is
authoritative, so the same name under a different TTY/RxCUI (e.g. an SCD
named "Warfarin" vs the IN ingredient "Warfarin") is NEVER merged. A name
match with a *different* existing `rxcui` is logged and skipped, never
silently overwritten; a name shared by multiple existing rows is treated as
ambiguous (skipped, logged) rather than guessed.

This script NEVER deletes or renumbers a row. Re-running any slice — or the
whole import — is a safe no-op for rows already imported.

### Relationship capture (opt-in `--related`)

The bulk endpoint returns only `rxcui`, `name`, `tty` per concept — no
hierarchy fields (verified against NLM's RxNav documentation). RxNorm's
structural relationships are exposed per-concept by
`getRelatedByRelationship` (`/REST/rxcui/<rxcui>/related.json?rela=<type>`).
The `--related` mode walks the already-imported RxCUIs (optionally filtered
with `--tty`), fetches each requested relationship type
(`--rela`, default: has_ingredient has_precise_ingredient has_tradename isa
has_form has_dose_form has_part), and stores typed edges in
`rxnorm_concept_relations` with `ON CONFLICT DO NOTHING` upserts.

Because the API response tags results only by TTY group (not by relation
type), one HTTP lookup is issued per (rxcui, relation type). Each lookup is
disk-cached (`related_<rxcui>_<rela>.json`, atomic `.partial` write), so a
re-run never re-fetches what it already has and the mode is resumable at
any point — simply re-run it. This mode is inherently per-concept HTTP and
is therefore opt-in; it is not part of the default concept import. Only
relationships actually returned by the RxNorm API are stored; nothing is
derived or invented.

## Streaming vs download

The bounded-memory guarantee covers **parsing, transformation, and
persistence**: the importer never holds the entire concept list in memory
at once (streaming via `ijson`, bounded batch buffers, batched DB writes).
The HTTP download step necessarily writes the full response to disk first
(RxNav limitation).

## Clean shutdown

`main()` disposes the shared async engine (`app.db.session.engine`) in a
`finally` block, on the still-open event loop. Without this, `asyncio.run()`
closes the loop while the engine's pool still holds asyncpg connections, and
interpreter shutdown then tries to close their SSL transports on the dead
loop — the misleading `Fatal error on SSL transport` /
`AttributeError: 'NoneType' object has no attribute 'send'` /
`RuntimeError: Event loop is closed` tracebacks that used to appear *after*
a successful (already-committed) import.

## Usage

See backend/scripts/README.md. Quick examples (run from backend/):

    python -m scripts.import_rxnorm                    # full import, all supported TTYs
    python -m scripts.import_rxnorm --tty IN           # one TTY only
    python -m scripts.import_rxnorm --tty IN --limit 100   # controlled/testing import
    python -m scripts.import_rxnorm --dry-run          # report, write nothing
    python -m scripts.import_rxnorm --related          # capture RxNorm relationship edges

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
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Allow `python scripts/import_rxnorm.py` (run from backend/) to find `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import (  # noqa: E402
    ReferenceDrug,
    RxnormConceptRelation,
    rxnorm_term_type_enum,
)
from app.db.session import AsyncSessionLocal, engine  # noqa: E402

logger = logging.getLogger("scripts.import_rxnorm")

RXNAV_BASE_URL = "https://rxnav.nlm.nih.gov/REST"
SOURCE_NAME = "RxNorm"
CACHE_DIR = Path(__file__).resolve().parent / ".rxnorm_cache"

# ── Default full-import TTY set ────────────────────────────────────────────
# The clinically meaningful structural levels for a pharmacovigilance
# platform (ARCHITECTURE_DECISIONS.md §6.2/§7.3):
#   IN   ingredient          PIN  precise ingredient
#   MIN  multiple ingredients SCD semantic clinical drug
#   SBD  semantic branded drug  GPCK generic pack
#   BPCK branded pack          DF   dose form
# Every value is a member of rxnorm_term_type_enum (23-value NLM Appendix 5
# vocabulary, migration 0002).
DEFAULT_TTY_SET = ("IN", "PIN", "MIN", "SCD", "SBD", "GPCK", "BPCK", "DF")
DEFAULT_TTY = " ".join(DEFAULT_TTY_SET)

# ── Default relationship types for --related mode ──────────────────────────
# From RxNav `getRelaTypes`; direction is as the API reports it
# (source_rxcui <relation_type> target_rxcui). The inverse family
# (ingredient_of, tradename_of, form_of, dose_form_of, part_of, ...) is the
# same edge seen from the other end and is intentionally not captured by
# default, so each edge is stored once.
DEFAULT_RELA_SET = (
    "has_ingredient",
    "has_precise_ingredient",
    "has_tradename",
    "isa",
    "has_form",
    "has_dose_form",
    "has_part",
)
DEFAULT_RELA = " ".join(DEFAULT_RELA_SET)


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


def _related_cache_path(rxcui: str, rela: str) -> Path:
    return CACHE_DIR / f"related_{rxcui}_{rela}.json"


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
    return {p.strip().upper() for p in parts if p.strip()}


def _validate_tties(tty_set: set[str]) -> None:
    """Fail fast when a requested TTY is outside the DB enum vocabulary.

    `reference_drugs.term_type` is `rxnorm_term_type_enum`; a TTY outside its
    23-value vocabulary would otherwise fail deep inside the import with a
    raw Postgres enum error.
    """
    valid = set(rxnorm_term_type_enum.enums)
    invalid = sorted(tty_set - valid)
    if invalid:
        raise ValueError(
            f"TTY(s) {', '.join(invalid)} are not part of "
            f"rxnorm_term_type_enum. Valid values: {', '.join(sorted(valid))}"
        )


def _get_batch_size(cli_batch_size: int | None) -> int:
    if cli_batch_size is not None:
        return cli_batch_size
    try:
        from app.core.config import get_settings  # local import to avoid cycle

        return int(get_settings().rxnorm_import_batch_size)
    except Exception:  # noqa: BLE001
        return 500


# ---------------------------------------------------------------------------
# Cache fetch with atomic .partial handling (true streaming)
# ---------------------------------------------------------------------------

def _ensure_cache(
    tty: str,
    *,
    full_rxnorm: bool = False,  # noqa: FBT001,FBT002
    refresh_cache: bool = False,  # noqa: FBT001,FBT002
    timeout_seconds: float = 60.0,
) -> Path:
    """Ensure cached RxNav response exists, fetching atomically if needed.

    Uses ``httpx.stream()`` to stream the HTTP response directly to a
    ``.partial`` file, never holding the full JSON response in memory via
    ``resp.json()``. The file is atomically renamed only after the stream
    completes successfully, so an interrupted download never leaves a corrupt
    final cache file. Parsing/transformation/persistence remain streaming via
    ``ijson``; the download itself necessarily lands on disk (RxNav has no
    pagination).
    """
    cache_path = _cache_path(tty, full_rxnorm=full_rxnorm)
    if cache_path.exists() and not refresh_cache:
        logger.info("Using cached RxNorm concept list for tty=%s (%s)", tty, cache_path)
        return cache_path

    url = _rxnav_url(full_rxnorm=full_rxnorm)
    logger.info("Fetching RxNorm concepts from %s?tty=%s", url, tty)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    partial_path = cache_path.with_suffix(cache_path.suffix + ".partial")

    # Remove stale partial from a prior interrupted download before starting
    if partial_path.exists():
        try:
            partial_path.unlink()
        except Exception:  # noqa: BLE001
            pass

    try:
        with httpx.stream("GET", url, params={"tty": tty}, timeout=timeout_seconds) as resp:
            resp.raise_for_status()
            with open(partial_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    except Exception:
        # Do not leave a corrupt .partial as final; clean up partial on failure
        # but never create the final cache file. Re-raise so caller sees the error.
        try:
            if partial_path.exists():
                partial_path.unlink()
        except Exception:  # noqa: BLE001
            pass
        raise

    # Stream succeeded — atomically promote partial to final
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
    Client-side batching happens in the streaming pipeline.

    Backward-compat helper retaining whole-list semantics (small tests);
    the production `main()` path uses streaming (`_stream_concepts`) for
    bounded memory.
    """
    cache_path = _ensure_cache(
        tty, full_rxnorm=full_rxnorm, refresh_cache=refresh_cache, timeout_seconds=timeout_seconds
    )
    tty_filter = _parse_tty_filter(tty)
    concepts: list[RxNormConcept] = []
    # Use streaming parse even here to avoid json.loads(full_file) for large files,
    # but return a sorted list for compatibility (tests assert sorting).
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
    Does NOT load the whole file via json.loads. Yields one RxNormConcept at
    time. Applies tty_filter if provided (skips non-matching TTYs).

    The bulk endpoint's per-concept fields are exactly rxcui/name/tty (NLM
    docs); any extra fields in a payload are tolerated and ignored.
    """
    # ijson needs a binary file handle
    with open(cache_path, "rb") as f:
        try:
            # The RxNav payload is {"minConceptGroup": {"minConcept": [ {...}, ... ] }}
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
                    yield RxNormConcept(
                        rxcui=str(rxcui),
                        name=name,
                        tty=tty or (next(iter(tty_filter)) if tty_filter else ""),
                    )
                except Exception:  # noqa: BLE001
                    # Skip malformed entry, continue streaming
                    logger.debug("Skipping malformed concept entry: %r", obj, exc_info=True)
                    continue
        except ijson.JSONError as exc:
            logger.error("Failed to stream-parse RxNorm cache %s: %s", cache_path, exc)
            raise


def _count_streamed_concepts(cache_path: Path, tty_filter: set[str] | None) -> int:
    """Data-derived concept count for one cached TTY file (streaming pass).

    Counts what is actually available in the source data — never a
    hard-coded number.
    """
    count = 0
    for _ in _stream_concepts(cache_path, tty_filter=tty_filter):
        count += 1
    return count


def select_batch(
    concepts: list[RxNormConcept], *, offset: int, limit: int | None
) -> list[RxNormConcept]:
    """Client-side pagination slice over an already-fetched concept list (backward compat)."""
    if limit is None:
        return concepts[offset:]
    return concepts[offset : offset + limit]


# ---------------------------------------------------------------------------
# Concept upsert (per batch, 1–2 queries, one transaction)
# ---------------------------------------------------------------------------

@dataclass
class ImportStats:
    updated_existing_by_rxcui: int = 0
    already_current: int = 0
    backfilled_existing_by_name: int = 0
    inserted_new: int = 0
    skipped_ambiguous: int = 0

    def __iadd__(self, other: "ImportStats") -> "ImportStats":
        self.updated_existing_by_rxcui += other.updated_existing_by_rxcui
        self.already_current += other.already_current
        self.backfilled_existing_by_name += other.backfilled_existing_by_name
        self.inserted_new += other.inserted_new
        self.skipped_ambiguous += other.skipped_ambiguous
        return self


async def _import_batch_optimized(
    concepts: list[RxNormConcept],
    *,
    dry_run: bool,  # noqa: FBT001
    source_name: str = SOURCE_NAME,
) -> ImportStats:
    """
    Batch-optimized upsert for one persistence batch.

    Uses at most 2 SELECTs per batch (by rxcui IN (...), and by
    lower(name) IN (...) only when the batch contains IN/ingredient
    concepts) instead of N+1 per-concept SELECTs. Each call is its own
    transaction.

    Upsert semantics (RxCUI + TTY identity is authoritative):
      1. rxcui match, same source      -> no-op (`already_current`).
      2. rxcui match, different source -> refresh source/source_updated_at;
         term_type backfilled only if still NULL. `id` never changes.
      3. no rxcui match, TTY == IN, exact case-insensitive name match on a
         single existing row -> backfill that row in place (id preserved);
         a match on a row with a different rxcui, or on multiple rows, is
         ambiguous -> skipped and logged, never overwritten.
      4. otherwise                    -> INSERT new row (term_type = TTY).
    Non-IN TTYs never use name matching, so same-name concepts from
    different TTYs are never merged.
    """
    stats = ImportStats()
    if not concepts:
        return stats
    now = datetime.now(timezone.utc)
    has_ingredient = any(c.tty == "IN" for c in concepts)

    async with AsyncSessionLocal() as session:
        rxcui_list = [c.rxcui for c in concepts]

        # Batch preload: existing by rxcui
        existing_by_rxcui: dict[str, ReferenceDrug] = {}
        if rxcui_list:
            result = await session.execute(
                select(ReferenceDrug).where(ReferenceDrug.rxcui.in_(rxcui_list))
            )
            for drug in result.scalars().all():
                existing_by_rxcui[drug.rxcui] = drug  # type: ignore[attr-defined]

        # Batch preload: existing by lower(name) — IN concepts only.
        existing_by_name: dict[str, list[ReferenceDrug]] = {}
        if has_ingredient:
            lower_names = [c.name.lower() for c in concepts if c.tty == "IN"]
            if lower_names:
                result = await session.execute(
                    select(ReferenceDrug).where(
                        func.lower(ReferenceDrug.name).in_(lower_names)
                    )
                )
                for drug in result.scalars().all():
                    existing_by_name.setdefault(drug.name.lower(), []).append(drug)  # type: ignore[union-attr]

        for concept in concepts:
            # 1) rxcui match (fast path, including within-batch inserts)
            existing = existing_by_rxcui.get(concept.rxcui)
            if existing is not None:
                if existing.source == source_name:
                    stats.already_current += 1
                    continue
                logger.debug(
                    "rxcui=%s already imported (id=%s, source=%s) -- refreshing provenance",
                    concept.rxcui,
                    existing.id,
                    existing.source,
                )
                if not dry_run:
                    existing.source = source_name
                    existing.source_updated_at = now
                    if existing.term_type is None:
                        existing.term_type = concept.tty
                stats.updated_existing_by_rxcui += 1
                continue

            # 2) IN (ingredient) exact-name backfill of existing rows
            if concept.tty == "IN":
                lower = concept.name.lower()
                matches = existing_by_name.get(lower, [])
                if len(matches) > 1:
                    logger.warning(
                        "IN concept '%s' (rxcui=%s): %d existing rows share this "
                        "name -- skipping (ambiguous).",
                        concept.name,
                        concept.rxcui,
                        len(matches),
                    )
                    stats.skipped_ambiguous += 1
                    continue
                if len(matches) == 1:
                    row = matches[0]
                    if row.rxcui is None:
                        logger.info(
                            "Backfilling existing drug '%s' (id=%s) with rxcui=%s",
                            row.name,
                            row.id,
                            concept.rxcui,
                        )
                        if not dry_run:
                            row.rxcui = concept.rxcui
                            row.source = source_name
                            row.source_updated_at = now
                            if row.term_type is None:
                                row.term_type = concept.tty
                            # Register in rxcui map so later duplicate in same
                            # batch hits the rxcui path
                            existing_by_rxcui[concept.rxcui] = row
                        stats.backfilled_existing_by_name += 1
                        continue
                    logger.warning(
                        "Name match for '%s' already has a different rxcui "
                        "(%s != %s) -- skipping.",
                        concept.name,
                        row.rxcui,
                        concept.rxcui,
                    )
                    stats.skipped_ambiguous += 1
                    continue

            # 3) New row (non-IN TTYs always reach here without name matching)
            logger.info("Inserting new drug '%s' (rxcui=%s, tty=%s)", concept.name, concept.rxcui, concept.tty)
            if not dry_run:
                new_drug = ReferenceDrug(
                    id=uuid.uuid4(),
                    name=concept.name,
                    generic_name=None,
                    drug_class=None,
                    rxcui=concept.rxcui,
                    term_type=concept.tty,
                    source=source_name,
                    source_updated_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_drug)
                # Register immediately for within-batch idempotency
                existing_by_rxcui[concept.rxcui] = new_drug
                if concept.tty == "IN":
                    existing_by_name.setdefault(concept.name.lower(), []).append(new_drug)
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

    Backward-compatible wrapper that delegates to the batch-optimized
    implementation. Each call is one transaction.

    Never deletes or renumbers a row -- see module docstring.
    """
    return await _import_batch_optimized(concepts, dry_run=dry_run, source_name=source_name)


# ---------------------------------------------------------------------------
# Relationship capture (opt-in --related mode)
# ---------------------------------------------------------------------------

@dataclass
class RelationStats:
    source_concepts: int = 0
    lookups_fetched: int = 0
    lookups_cached: int = 0
    lookups_failed: int = 0
    edges_inserted: int = 0
    edges_already_present: int = 0


def _fetch_related(
    rxcui: str,
    rela: str,
    *,
    refresh_cache: bool = False,  # noqa: FBT001,FBT002
    timeout_seconds: float = 30.0,
) -> dict:
    """Fetch getRelatedByRelationship for one (rxcui, rela) with atomic disk cache.

    One call per (rxcui, rela) because the API response groups results by
    TTY only — it does not tag which requested relation produced each
    result, so relation types cannot be combined in a single lookup without
    losing attribution.
    """
    cache_path = _related_cache_path(rxcui, rela)
    if cache_path.exists() and not refresh_cache:
        return json.loads(cache_path.read_text())

    url = f"{RXNAV_BASE_URL}/rxcui/{rxcui}/related.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    partial_path = cache_path.with_suffix(cache_path.suffix + ".partial")
    if partial_path.exists():
        try:
            partial_path.unlink()
        except Exception:  # noqa: BLE001
            pass

    try:
        with httpx.stream("GET", url, params={"rela": rela}, timeout=timeout_seconds) as resp:
            resp.raise_for_status()
            with open(partial_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    except Exception:
        try:
            if partial_path.exists():
                partial_path.unlink()
        except Exception:  # noqa: BLE001
            pass
        raise

    partial_path.replace(cache_path)
    return json.loads(cache_path.read_text())


def _parse_related_edges(payload: dict, relation_type: str) -> list[tuple[str, str | None]]:
    """Extract (target_rxcui, target_tty) edges from a getRelatedByRelationship payload.

    Defensive parsing: per NLM's documentation, fields that would be empty
    may be null or left out, and multi-occurrence fields may be a single
    object instead of an array. `relation_type` is the type that was
    queried (the API does not tag results with it).
    """
    edges: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    group = payload.get("relatedGroup") or {}
    concept_groups = group.get("conceptGroup")
    if not concept_groups:
        return edges
    if isinstance(concept_groups, dict):
        concept_groups = [concept_groups]
    for cg in concept_groups:
        if not isinstance(cg, dict):
            continue
        props = cg.get("conceptProperties")
        if not props:
            continue
        if isinstance(props, dict):
            props = [props]
        for p in props:
            if not isinstance(p, dict):
                continue
            target = p.get("rxcui")
            if target in (None, "", 0):
                continue
            target = str(target)
            if target in seen:
                continue
            seen.add(target)
            # Property-level tty takes precedence; the group's tty applies to
            # every property in that group (defensive: either may be omitted).
            tty = p.get("tty") or cg.get("tty")
            edges.append((target, str(tty) if tty else None))
    return edges


async def _upsert_relation_edges(
    edges: list[tuple[str, str, str, str | None]],
    *,
    dry_run: bool,  # noqa: FBT001
    source_name: str = SOURCE_NAME,
) -> tuple[int, int]:
    """
    Bulk-upsert relation edges; returns (inserted, already_present).

    `edges` items are (source_rxcui, relation_type, target_rxcui, target_tty).
    Idempotent via ON CONFLICT DO NOTHING on the unique
    (source_rxcui, relation_type, target_rxcui) constraint, so re-running
    any slice never duplicates edges. Dry-run executes the upsert inside the
    batch transaction and rolls back (same convention as the concept import).
    """
    if not edges:
        return (0, 0)
    rows = [
        {
            "id": uuid.uuid4(),
            "source_rxcui": s,
            "target_rxcui": t,
            "relation_type": rt,
            "target_tty": tty,
            "source": source_name,
        }
        for (s, rt, t, tty) in edges
    ]
    async with AsyncSessionLocal() as session:
        stmt = (
            pg_insert(RxnormConceptRelation)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=["source_rxcui", "relation_type", "target_rxcui"]
            )
        )
        result = await session.execute(stmt)
        if dry_run:
            await session.rollback()
            return (len(rows), 0)
        await session.commit()
        inserted = getattr(result, "rowcount", None)
        if inserted is None or inserted < 0:
            inserted = len(rows)
        return (inserted, len(rows) - inserted)


async def _run_related_mode(args: argparse.Namespace, tty_set: set[str], batch_size: int) -> None:
    """Opt-in relationship capture over already-imported concepts."""
    rela_set = [r.strip() for r in args.rela.replace(",", " ").split() if r.strip()]
    if not rela_set:
        raise ValueError("--rela must name at least one relationship type (see RxNav getRelaTypes)")

    # 1) Load the RxCUIs to process (already-imported concepts only — this
    #    mode never imports concepts itself).
    async with AsyncSessionLocal() as session:
        stmt = select(ReferenceDrug.rxcui, ReferenceDrug.term_type).where(
            ReferenceDrug.rxcui.is_not(None)
        )
        if tty_set:
            stmt = stmt.where(ReferenceDrug.term_type.in_(sorted(tty_set)))
        result = await session.execute(stmt)
        rxcui_tty = {str(r[0]): (str(r[1]) if r[1] else None) for r in result.all()}

    if not rxcui_tty:
        logger.warning(
            "No imported concepts with a RxCUI found%s — run the concept import "
            "first (python -m scripts.import_rxnorm).",
            f" for TTYs {', '.join(sorted(tty_set))}" if tty_set else "",
        )
        return

    rxcui_list = list(rxcui_tty)
    total_lookups = len(rxcui_list) * len(rela_set)
    mode = "dry run" if args.dry_run else "live"
    logger.info(
        "RxNorm relationship plan (%s): %d source concepts, %d relation type(s) "
        "[%s] -> %d lookups (batch_size=%d, per-concept HTTP, disk-cached)",
        mode,
        len(rxcui_list),
        len(rela_set),
        ", ".join(rela_set),
        total_lookups,
        batch_size,
    )

    stats = RelationStats(source_concepts=len(rxcui_list))
    buffer: list[tuple[str, str, str, str | None]] = []
    lookups_done = 0
    flushed_buffers = 0

    async def _flush() -> None:
        nonlocal buffer, flushed_buffers
        if not buffer:
            return
        ins, present = await _upsert_relation_edges(buffer, dry_run=args.dry_run)
        stats.edges_inserted += ins
        stats.edges_already_present += present
        flushed_buffers += 1
        logger.info(
            "Related: buffer %d committed (edges inserted=%d already_present=%d)",
            flushed_buffers,
            ins,
            present,
        )
        buffer = []

    for rxcui in rxcui_list:
        for rela in rela_set:
            if args.related_limit is not None and lookups_done >= args.related_limit:
                break
            lookups_done += 1
            try:
                if _related_cache_path(rxcui, rela).exists() and not args.refresh_cache:
                    payload = json.loads(_related_cache_path(rxcui, rela).read_text())
                    stats.lookups_cached += 1
                else:
                    payload = _fetch_related(rxcui, rela, refresh_cache=args.refresh_cache)
                    stats.lookups_fetched += 1
                    if args.related_delay > 0:
                        await asyncio.sleep(args.related_delay)
            except Exception as exc:  # noqa: BLE001
                stats.lookups_failed += 1
                logger.warning(
                    "Related lookup failed for rxcui=%s rela=%s: %s "
                    "(not cached — will retry on next run)",
                    rxcui,
                    rela,
                    exc,
                )
                continue

            for target, tty in _parse_related_edges(payload, rela):
                buffer.append((rxcui, rela, target, tty))
            if len(buffer) >= batch_size:
                await _flush()
            if lookups_done % 500 == 0:
                logger.info(
                    "Related progress: %d/%d lookups (fetched=%d cached=%d failed=%d, "
                    "edges buffered=%d)",
                    lookups_done,
                    total_lookups,
                    stats.lookups_fetched,
                    stats.lookups_cached,
                    stats.lookups_failed,
                    len(buffer),
                )
        if args.related_limit is not None and lookups_done >= args.related_limit:
            break

    await _flush()

    logger.info("RxNorm Relationships Complete (%s)", mode)
    logger.info("----------------------")
    logger.info("Source concepts:        %d%s", stats.source_concepts,
                f" (tty filter: {', '.join(sorted(tty_set))})" if tty_set else "")
    logger.info("Relation types:         %s", ", ".join(rela_set))
    logger.info(
        "Lookups:                  fetched=%d cached=%d failed=%d (limit=%s)",
        stats.lookups_fetched,
        stats.lookups_cached,
        stats.lookups_failed,
        args.related_limit if args.related_limit is not None else "none",
    )
    logger.info(
        "Edges:                    inserted=%d already_present=%d",
        stats.edges_inserted,
        stats.edges_already_present,
    )
    if stats.lookups_failed:
        logger.warning(
            "%d lookups failed — re-run `--related` to retry them (failures are not cached).",
            stats.lookups_failed,
        )


# ---------------------------------------------------------------------------
# Concept import (multi-TTY, automatic)
# ---------------------------------------------------------------------------

def _tty_order(tty_set: set[str]) -> list[str]:
    """Deterministic TTY processing order: default set order first, then extras."""
    ordered = [t for t in DEFAULT_TTY_SET if t in tty_set]
    ordered.extend(sorted(t for t in tty_set if t not in DEFAULT_TTY_SET))
    return ordered


async def _import_tty(
    tty: str,
    cache_path: Path,
    *,
    args: argparse.Namespace,
    start_offset: int,
    batch_size: int,
    total: int,
) -> ImportStats:
    """Stream one TTY's cached concepts and upsert in bounded batches."""
    stats = ImportStats()
    if start_offset < 0:
        raise ValueError(f"--offset must be >= 0, got {start_offset}")

    remaining = total - start_offset
    if args.limit is not None:
        remaining = min(remaining, args.limit)
    total_batches = (remaining + batch_size - 1) // batch_size

    logger.info(
        "TTY %s: %d concepts discovered, resuming from offset %d, batch size %d "
        "-> %d batch(es)%s",
        tty,
        total,
        start_offset,
        batch_size,
        total_batches,
        " (dry run)" if args.dry_run else "",
    )

    current_batch: list[RxNormConcept] = []
    stream_index = -1
    batch_number = 0
    next_checkpoint = start_offset

    async def _flush_batch() -> None:
        nonlocal current_batch, batch_number, next_checkpoint
        if not current_batch:
            return
        batch_number += 1
        batch_start = next_checkpoint
        batch_end = batch_start + len(current_batch)
        try:
            batch_stats = await _import_batch_optimized(current_batch, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "TTY %s: Batch %d failed at offset %d..%d: %s (checkpoint remains at %d, "
                "resume by re-running without --offset)",
                tty,
                batch_number,
                batch_start,
                batch_end,
                exc,
                next_checkpoint,
            )
            raise RuntimeError(
                f"TTY {tty} — Batch {batch_number} failed at offset {batch_start}..{batch_end} "
                f"(checkpoint={next_checkpoint}): {exc}"
            ) from exc
        stats.__iadd__(batch_stats)
        logger.info(
            "TTY %s: Batch %d/%d done (offset %d..%d): inserted=%d updated=%d "
            "already_current=%d backfilled=%d ambiguous=%d",
            tty,
            batch_number,
            total_batches,
            batch_start,
            batch_end,
            batch_stats.inserted_new,
            batch_stats.updated_existing_by_rxcui,
            batch_stats.already_current,
            batch_stats.backfilled_existing_by_name,
            batch_stats.skipped_ambiguous,
        )
        if not args.dry_run and not args.no_checkpoint:
            next_checkpoint = batch_end
            _write_checkpoint(tty, next_checkpoint, full_rxnorm=args.full_rxnorm)
        current_batch = []

    processed_count = 0
    for concept in _stream_concepts(cache_path, tty_filter={tty}):
        stream_index += 1
        if stream_index < start_offset:
            continue
        if args.limit is not None and processed_count >= args.limit:
            break  # limit is a per-TTY cap on processed concepts
        current_batch.append(concept)
        processed_count += 1
        if len(current_batch) >= batch_size:
            await _flush_batch()

    await _flush_batch()
    if not args.dry_run and not args.no_checkpoint:
        _write_checkpoint(tty, next_checkpoint, full_rxnorm=args.full_rxnorm)
    return stats


def _log_import_summary(
    tty_order: list[str],
    counts: dict[str, int],
    per_tty: dict[str, ImportStats],
    processed: dict[str, int],
    failed_ttys: list[str],
    args: argparse.Namespace,
) -> None:
    """Final per-TTY + total summary (counts derived from source data)."""
    mode = "concepts (dry run)" if args.dry_run else "concepts"
    logger.info("RxNorm Import Complete")
    logger.info("----------------------")
    header = (
        f"{'TTY':<6} {'Discovered':>10} {'Processed':>9} {'Inserted':>9} {'Updated':>8} "
        f"{'Already':>8} {'Backfill':>9} {'Ambig':>6}"
    )
    logger.info(header)
    total_discovered = 0
    totals = ImportStats()
    for tty in tty_order:
        if tty in failed_ttys:
            logger.info("%-6s FETCH FAILED (skipped)", tty)
            continue
        total = counts.get(tty, 0)
        s = per_tty.get(tty, ImportStats())
        total_discovered += total
        totals.__iadd__(s)
        logger.info(
            f"{tty:<6} {total:>10d} {processed.get(tty, 0):>9d} {s.inserted_new:>9d} "
            f"{s.updated_existing_by_rxcui:>8d} {s.already_current:>8d} "
            f"{s.backfilled_existing_by_name:>9d} {s.skipped_ambiguous:>6d}"
        )
    logger.info("Total concepts discovered: %d (across %d TTYs)", total_discovered,
                max(0, len(tty_order) - len(failed_ttys)))
    logger.info(
        "Totals: inserted=%d updated=%d already_current=%d backfilled=%d "
        "skipped_ambiguous=%d",
        totals.inserted_new,
        totals.updated_existing_by_rxcui,
        totals.already_current,
        totals.backfilled_existing_by_name,
        totals.skipped_ambiguous,
    )
    logger.info("TTYs skipped (fetch failed): %d%s", len(failed_ttys),
                f" ({', '.join(failed_ttys)})" if failed_ttys else "")
    logger.info("Mode: %s", mode)


async def _run_concept_import(args: argparse.Namespace, tty_set: set[str], batch_size: int) -> None:
    """Automatic multi-TTY concept import (the default mode)."""
    tty_order = _tty_order(tty_set)
    failed_ttys: list[str] = []

    # 1) Ensure a cached RxNav response per TTY.
    cache_paths: dict[str, Path] = {}
    for tty in tty_order:
        try:
            cache_paths[tty] = _ensure_cache(
                tty,
                full_rxnorm=args.full_rxnorm,
                refresh_cache=args.refresh_cache,
                timeout_seconds=60.0,
            )
        except Exception as exc:  # noqa: BLE001
            if len(tty_order) == 1:
                # Explicit single-TTY run: a fetch failure is fatal.
                raise
            logger.error(
                "TTY %s: cache fetch failed (%s) — skipping this TTY, continuing with the rest",
                tty,
                exc,
            )
            failed_ttys.append(tty)

    # 2) Derive per-TTY counts from the cached data (never hard-coded).
    counts: dict[str, int] = {}
    for tty, path in cache_paths.items():
        counts[tty] = _count_streamed_concepts(path, tty_filter={tty})

    # 3) Import plan (what will be imported, and from where each TTY resumes).
    mode = "dry run" if args.dry_run else "live"
    logger.info("RxNorm import plan (%s): %d TTY(s), batch size %d", mode, len(tty_order), batch_size)
    for i, tty in enumerate(tty_order):
        if tty in failed_ttys:
            continue
        total = counts.get(tty, 0)
        start = 0
        if not args.no_checkpoint:
            start = args.offset if (args.offset is not None and i == 0) else _read_checkpoint(
                tty, full_rxnorm=args.full_rxnorm
            )
        state = (
            "already complete — will be skipped"
            if total and start >= total
            else "no concepts available" if total == 0 else "ready"
        )
        logger.info(
            "  TTY %-5s: %6d concepts, resume from offset %d — %s",
            tty,
            total,
            start,
            state,
        )

    # 4) Process each TTY in order.
    per_tty: dict[str, ImportStats] = {}
    processed: dict[str, int] = {}
    for i, tty in enumerate(tty_order):
        if tty in failed_ttys:
            continue
        total = counts.get(tty, 0)
        if total == 0:
            logger.info("TTY %s: no concepts available in source data — nothing to do", tty)
            continue
        start_offset = 0
        if not args.no_checkpoint:
            start_offset = args.offset if (args.offset is not None and i == 0) else _read_checkpoint(
                tty, full_rxnorm=args.full_rxnorm
            )
        if start_offset >= total:
            logger.info(
                "TTY %s: already complete (checkpoint %d >= %d concepts) — skipping",
                tty,
                start_offset,
                total,
            )
            continue
        stats = await _import_tty(
            tty,
            cache_paths[tty],
            args=args,
            start_offset=start_offset,
            batch_size=batch_size,
            total=total,
        )
        per_tty[tty] = stats
        processed[tty] = (
            stats.inserted_new
            + stats.updated_existing_by_rxcui
            + stats.already_current
            + stats.backfilled_existing_by_name
            + stats.skipped_ambiguous
        )

    # 5) Summary.
    _log_import_summary(tty_order, counts, per_tty, processed, failed_ttys, args)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tty",
        default=DEFAULT_TTY,
        help=(
            "RxNorm term type(s) to import, space/comma-separated "
            f"(default: the full supported set '{DEFAULT_TTY}'). "
            "Each TTY is processed automatically to completion."
        ),
    )
    parser.add_argument(
        "--full-rxnorm",
        action="store_true",
        help="Use full RxNorm catalog (/REST/allconcepts.json) instead of "
        "Prescribable Content (/REST/Prescribe/allconcepts.json). Default is Prescribable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max concepts to process PER TTY this run (default: all remaining "
        "after the checkpoint). For controlled/testing imports.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=None,
        help="Starting offset into the filtered, streamed concept list of the "
        "FIRST requested TTY. Defaults to that TTY's saved checkpoint. "
        "Normal runs do not need this — resume is automatic.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Persistence batch size (default: rxnorm_import_batch_size from "
        "config, 500).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned changes; write nothing, advance no checkpoint.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force a fresh fetch from RxNav instead of using the on-disk cache.",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Do not read or write the resumability checkpoint files.",
    )
    parser.add_argument(
        "--related",
        action="store_true",
        help="Capture RxNorm relationship edges (rxnorm_concept_relations) for "
        "already-imported concepts via per-concept getRelatedByRelationship "
        "lookups (disk-cached, resumable; see README). Implies concept mode is "
        "NOT run in the same invocation.",
    )
    parser.add_argument(
        "--rela",
        default=DEFAULT_RELA,
        help="Space/comma-separated relationship types for --related (RxNav "
        f"getRelaTypes). Default: '{DEFAULT_RELA}'.",
    )
    parser.add_argument(
        "--related-limit",
        type=int,
        default=None,
        help="Max (rxcui x relation type) lookups for --related this run.",
    )
    parser.add_argument(
        "--related-delay",
        type=float,
        default=0.0,
        help="Seconds to sleep between --related HTTP lookups (rate limiting).",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    tty_set = _parse_tty_filter(args.tty)
    if not tty_set:
        tty_set = set(DEFAULT_TTY_SET)
    try:
        _validate_tties(tty_set)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(2)

    batch_size = _get_batch_size(args.batch_size)

    try:
        if args.related:
            await _run_related_mode(args, tty_set, batch_size)
        else:
            await _run_concept_import(args, tty_set, batch_size)
    finally:
        # Close pooled asyncpg connections on the still-open event loop.
        # Without this, asyncio.run() closes the loop while app.db.session's
        # engine pool still holds connections, and interpreter shutdown tries
        # to close their SSL transports on the dead loop — the "Fatal error
        # on SSL transport" / "Event loop is closed" tracebacks after an
        # otherwise-successful import (see module docstring, Clean shutdown).
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
