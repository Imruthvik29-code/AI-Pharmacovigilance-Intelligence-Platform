# backend/scripts

## import_rxnorm.py

Reproducible, idempotent, resumable importer that expands `reference_drugs`
— and, opt-in, `rxnorm_concept_relations` — using NLM's public RxNorm
terminology, via the RxNav REST API (https://rxnav.nlm.nih.gov/REST/).
No UMLS account, API key, or license agreement is required for this API.

Scoped to `reference_drugs` / `rxnorm_concept_relations` only. Does
**not** import or modify `interaction_rules` / `adr_rules` -- those remain
hand-curated per the frozen spec (section 3).

### Supported TTYs

The default import covers the clinically meaningful structural levels for
a pharmacovigilance platform (all members of `rxnorm_term_type_enum`,
migration `0002_add_term_type_is_active`):

| TTY  | Meaning                          |
|------|----------------------------------|
| `IN`   | Ingredient                       |
| `PIN`  | Precise ingredient               |
| `MIN`  | Multiple ingredients             |
| `SCD`  | Semantic clinical drug           |
| `SBD`  | Semantic branded drug            |
| `GPCK` | Generic pack                     |
| `BPCK` | Branded pack                     |
| `DF`   | Dose form                        |

Concepts are **not** flattened into interchangeable "drugs": every row
keeps its TTY in `reference_drugs.term_type`, and its RxCUI remains the
authoritative identity. Same name under a different TTY/RxCUI (e.g. the
SCD "Warfarin" vs the IN ingredient "Warfarin") is a **separate row** —
names are never merged across RxCUIs/TTYs.

### Prerequisites

- `backend/.env` configured with a working `DATABASE_URL`.
- Alembic at least at `0003_add_rxnorm_concept_relations`:
  ```bash
  python -m alembic -c alembic.ini upgrade head
  ```
  (brings the schema from `0001_baseline` through `0002` —
  `term_type`/`is_active` — and `0003` — `rxnorm_concept_relations`).
- `ijson` installed (`pip install -r backend/requirements.txt`).

### How the (automatic) import works

A bare `python -m scripts.import_rxnorm` runs the **full import for all
supported TTYs, to completion** — no manual `--offset` arithmetic:

1. **Fetch/cache per TTY.** For each TTY in the requested set, ensure a
   cached RxNav `getAllConceptsByTTY` response
   (`/REST/Prescribe/allconcepts.json?tty=<TTY>` by default — Prescribable
   Content, structurally excluding obsolete/suppressed concepts — or
   `/REST/allconcepts.json` with `--full-rxnorm`). This is the only RxNorm
   bulk-enumeration endpoint and it has **no server-side pagination**
   (verified against NLM's API docs), so one cached bulk fetch per TTY is
   the design. The HTTP download necessarily lands on disk first (atomic
   `.partial` write); parsing, transformation, and persistence remain
   streaming/bounded-memory (`ijson`, no `json.loads(full_file)`).
2. **Count from the data.** The concept count for each TTY is derived by a
   streaming pass over the cached file — **never hard-coded** — and an
   import plan (per TTY: discovered count, resume offset, batch count) is
   logged before anything is written.
3. **Process in batches.** Each TTY is streamed and upserted in bounded
   batches (default 500 via `rxnorm_import_batch_size` in
   `app.core.config.Settings` or `--batch-size`), one DB transaction per
   batch. Per-TTY, at most 2 queries per batch (`WHERE rxcui IN (...)` and,
   only for IN/ingredient concepts, `WHERE lower(name) IN (...)`) — not N+1.
4. **Checkpoint & resume.** A checkpoint file
   (`backend/scripts/.rxnorm_cache/checkpoint_<tty>.json`) records the next
   offset, written atomically and only **after a batch commits**. An
   interrupted/failed run resumes exactly where it stopped — just re-run
   the same command. A TTY whose checkpoint has reached its (data-derived)
   count is skipped as already complete.
5. **Per-TTY failure isolation.** If a TTY's fetch fails during a
   multi-TTY run, that TTY is skipped and reported (the run continues and
   the summary lists it); a fetch failure on an explicitly requested
   single TTY is fatal.
6. **Summary.** A final per-TTY + totals summary is logged
   (discovered / processed / inserted / updated / already_current /
   backfilled / ambiguous / fetch failures).

Upsert semantics (RxCUI + TTY identity is authoritative):

- **RxCUI already imported, same source** → no-op (counted `already_current`).
- **RxCUI already imported, different source** → refresh
  `source`/`source_updated_at`; `term_type` backfilled only if still NULL
  (first TTY wins). `id` never changes, so every existing
  `medications.drug_id` / `interaction_rules.drug_a_id`/`drug_b_id` /
  `adr_rules.drug_id` foreign key stays valid.
- **No RxCUI match, TTY = `IN`**, exact case-insensitive name match on a
  single existing row → that row is backfilled in place (this is how the
  original hand-curated seed drugs get their RxCUI). A match on a row that
  already carries a *different* `rxcui`, or on *multiple* rows with the
  same name, is ambiguous → skipped and logged, never overwritten.
- **Otherwise** → a new row is INSERTed with a fresh UUID, its TTY in
  `term_type`, and `is_active` true (server default). Non-IN TTYs never
  use name matching.

The script **never deletes or renumbers** a row. Re-running any slice — or
the whole import — is a safe no-op for rows already imported.

### Relationships (`--related`, opt-in)

The bulk endpoint returns only `rxcui`, `name`, `tty` per concept — no
hierarchy fields (NLM docs). RxNorm's structural relationships are exposed
per-concept by `getRelatedByRelationship`
(`/REST/rxcui/<rxcui>/related.json?rela=<type>`). Because that response
tags results by TTY group only (not by relation type), the mode issues one
lookup per (RxCUI, relation type) and stores typed edges in
`rxnorm_concept_relations`:

```
source_rxcui <relation_type> target_rxcui   (+ target_tty, source)
```

Default relation set: `has_ingredient has_precise_ingredient has_tradename
isa has_form has_dose_form has_part` (a direction per edge; the `*_of`
inverse family is the same edge from the other end and is not captured by
default). Only relationships **actually returned by the RxNorm API** are
stored — nothing is derived or invented. Each lookup is disk-cached
(`related_<rxcui>_<rela>.json`, atomic), so re-runs never re-fetch, the
mode is resumable at any point (just re-run it), and failed lookups are
not cached (re-run to retry). Edges upsert via `ON CONFLICT DO NOTHING` on
the unique `(source_rxcui, relation_type, target_rxcui)` constraint, so
re-runs never duplicate.

This mode is inherently per-concept HTTP (tens of thousands of lookups for
a full catalog), which is why it is opt-in and not part of the default
concept import.

### Usage

Run from `backend/`:

```bash
cd backend

# Full import — all supported TTYs (IN PIN MIN SCD SBD GPCK BPCK DF),
# automatic batching + resume to completion:
python -m scripts.import_rxnorm

# One TTY only:
python -m scripts.import_rxnorm --tty SCD

# Controlled/testing import (per-TTY cap):
python -m scripts.import_rxnorm --tty IN --limit 100

# Report planned changes without writing (no checkpoint advance):
python -m scripts.import_rxnorm --dry-run

# Refresh the on-disk cache from RxNav:
python -m scripts.import_rxnorm --refresh-cache

# After concepts are imported: capture RxNorm relationship edges
# (per-concept, disk-cached, resumable — re-run to continue/retry):
python -m scripts.import_rxnorm --related

# Relationships for specific TTYs only, smaller relation set:
python -m scripts.import_rxnorm --related --tty "SBD SCD" --rela "has_ingredient isa"

# Cap relationship work this run (e.g. while the network is flaky):
python -m scripts.import_rxnorm --related --related-limit 500
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--tty` | `IN PIN MIN SCD SBD GPCK BPCK DF` | TTY(s) to import (space/comma-separated). Concept mode: which TTYs to import. `--related` mode: which imported TTYs' RxCUIs to walk. |
| `--full-rxnorm` | off | Use the full catalog (`/REST/allconcepts.json`) instead of Prescribable Content (`/REST/Prescribe/allconcepts.json`). |
| `--limit` | none | Max concepts to process **per TTY** this run (controlled/testing imports). |
| `--offset` | checkpoint | Starting offset for the **first** requested TTY. Normal runs do not need this — resume is automatic. |
| `--batch-size` | `rxnorm_import_batch_size` (500) | Persistence batch size (config or CLI override). Bounded-memory buffer. |
| `--dry-run` | off | Logs planned changes; writes nothing, advances no checkpoint. |
| `--refresh-cache` | off | Refetch RxNorm responses instead of using the disk cache. |
| `--no-checkpoint` | off | Don't read/write resumability checkpoint files. |
| `--related` | off | Capture RxNorm relationship edges (see above). Not combined with concept import in the same invocation. |
| `--rela` | `has_ingredient has_precise_ingredient has_tradename isa has_form has_dose_form has_part` | Relationship types for `--related` (RxNav `getRelaTypes`). |
| `--related-limit` | none | Max (RxCUI × relation type) lookups for `--related` this run. |
| `--related-delay` | `0.0` | Seconds to sleep between `--related` HTTP lookups (rate limiting). |
| `--log-level` | `INFO` | Standard logging level. |

### Performance & correctness guarantees

- **Streaming/bounded-memory**: `ijson` incremental parsing + batch
  buffers; verified flat peak memory across 5k/20k/80k synthetic catalogs.
  The download itself lands on disk whole — RxNav has no pagination.
- **Batch efficiency**: at most 2 queries per concept batch (batched
  `IN`), not N+1; non-IN TTYs use 1.
- **Atomic cache/checkpoint**: `.partial` + atomic rename for downloads,
  `*.tmp` → rename for checkpoints.
- **Idempotency**: a second full run inserts 0, duplicates 0, and reports
  everything as `already_current`.
- **Failure durability**: earlier batches remain committed, the checkpoint
  stays at the last success, the error reports batch/offset, and a re-run
  resumes without duplicates — automatically, no manual offsets.
- **Clean shutdown**: `main()` disposes the shared async engine
  (`app.db.session.engine`) on the still-open event loop, so a completed
  import exits cleanly. (Previously the engine's pooled asyncpg
  connections were closed by the interpreter *after* `asyncio.run()` had
  closed the loop, producing misleading `Fatal error on SSL transport` /
  `Event loop is closed` tracebacks after a successful import.)

### What this script deliberately does NOT do

- Does not import `dose_form`/`strength`/`route` as separate columns, or
  `atc_code`. `term_type` (the 23-value NLM Appendix 5 TTY enum) and
  `is_active` (boolean, default true) exist on `reference_drugs` since
  migration `0002_add_term_type_is_active` and are populated by the import
  itself (`term_type` = the concept's TTY; `is_active` = true for every
  Prescribable-Content concept, which by definition excludes obsolete/
  suppressed concepts).
- Does not import or modify `interaction_rules` / `adr_rules`.
- Does not invent relationships: `rxnorm_concept_relations` only ever
  receives edges returned by the RxNav API.
- Does not expose an API by itself — see
  `GET /api/v1/reference-drugs/search`
  (`backend/app/api/v1/reference_drugs.py`), which now returns each
  concept's `term_type` and accepts an optional `term_type` filter
  (e.g. `?term_type=IN` for ingredients only).
