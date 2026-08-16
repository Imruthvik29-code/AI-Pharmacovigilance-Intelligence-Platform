# backend/scripts

## import_rxnorm.py

Reproducible, idempotent, resumable importer that expands `reference_drugs`
using NLM's public RxNorm terminology, via the RxNav REST API
(https://rxnav.nlm.nih.gov/REST/). No UMLS account, API key, or license
agreement is required for this API.

Scoped to `reference_drugs` only. Does **not** import or modify
`interaction_rules` / `adr_rules` -- those remain hand-curated per the
frozen spec (section 3).

### Prerequisites

- `backend/.env` configured with a working `DATABASE_URL`.
- Migration `003_reference_drugs_external_reference.sql` (repo root)
  already applied.
- `ijson` installed (`pip install -r backend/requirements.txt`).

### How it works

1. Fetches the full RxNorm concept list for a term type (default `IN` =
   ingredients, matching the granularity of the existing curated seed
   drugs) via RxNav's `getAllConceptsByTTY` endpoint. This is the only
   RxNorm bulk-enumeration endpoint, and it has **no server-side
   pagination** (verified against NLM's own API docs) -- it returns the
   entire concept list for the given term type in one response.
   - Default source is **RxNorm Current Prescribable Content**
     (`/REST/Prescribe/allconcepts.json?tty=...`) — structurally excludes
     obsolete/suppressed, non-US, and veterinary-only concepts.
   - `--full-rxnorm` uses the full catalog (`/REST/allconcepts.json?tty=...`)
     as an explicit fallback/full-catalog mode.
   - The HTTP download necessarily writes the full response to disk first
     (RxNav limitation); bounded-memory claims cover parsing/transformation/
     persistence, not the download.
2. Caches that raw response to
   `backend/scripts/.rxnorm_cache/allconcepts_<tty>.json` (Prescribable) or
   `allconcepts_<tty>_full.json` (full) via an atomic `.partial` write so
   repeat runs don't re-hit the network (`--refresh-cache` forces a refetch).
   Interrupted downloads never leave a corrupt final cache file — the partial
   is written to `*.partial` then atomically renamed.
3. **Streaming parse** — the cached file is parsed incrementally with `ijson`
   (`ijson.items(f, "minConceptGroup.minConcept.item")`) without
   `json.loads(full_file)`. Concepts are yielded one at a time, TTY-filtered
   (`--tty IN` default; space/comma-separated), and buffered only up to
   `--batch-size` (default `rxnorm_import_batch_size=500` from
   `app.core.config.Settings`, overridable via `--batch-size`).
4. **Batch database writes** — each persistence batch uses 2 batched SELECTs
   (`WHERE rxcui IN (...)` and `WHERE lower(name) IN (...)`) instead of
   N+1 per-concept queries, then bulk-upserts in a single transaction.
   Earlier successful batches remain committed if a later batch fails.
5. Upserts each concept into `reference_drugs`, keyed on the unique
   `rxcui` column:
   - Already imported (same `rxcui`) -> only `source`/`source_updated_at`
     refreshed. Safe no-op on repeat runs.
   - Matches an existing row's `name` case-insensitively (this is how the
     original curated seed drugs get their `rxcui` backfilled) -> updated
     in place. **`id` is never changed**, so every existing
     `medications.drug_id` / `interaction_rules.drug_a_id`/`drug_b_id` /
     `adr_rules.drug_id` foreign key stays valid.
   - No match -> a new row is INSERTed with a fresh UUID.
   - A name match with a *different* existing `rxcui` is logged and
     skipped, never silently overwritten.
6. **Never deletes or renumbers** any row.
7. A checkpoint file (`backend/scripts/.rxnorm_cache/checkpoint_<tty>.json`
   or `checkpoint_<tty>_full.json` for `--full-rxnorm`) records the next
   offset to resume from, written atomically (`*.tmp` → rename) and updated
   **only after a batch commits**. On failure, the error reports batch number
   and offset range, checkpoint stays at last success, and a retry resumes
   exactly — no duplicates. This is a convenience — every write is
   independently idempotent via the `rxcui` upsert, so re-running any slice
   twice is always safe.
8. **CLI filtering is wired through the pipeline** — `--tty IN` (default)
   is applied during streaming parse, so `BN` rows are 0 on the default path
   unless explicitly requested or `--full-rxnorm` is used with a broader TTY.

### Usage

Run from `backend/`:

```bash
cd backend

# 1. Always dry-run first (Prescribable, IN only).
python -m scripts.import_rxnorm --tty IN --limit 500 --dry-run

# 2. Run for real (batched, checkpointed).
python -m scripts.import_rxnorm --tty IN --limit 500

# 3. Next batch -- offset resumes automatically from the checkpoint.
python -m scripts.import_rxnorm --tty IN --limit 500

# Process everything at once with custom batch size:
python -m scripts.import_rxnorm --tty IN --batch-size 500

# Full RxNorm catalog (bypasses Prescribable filtering):
python -m scripts.import_rxnorm --tty IN --full-rxnorm --limit 500 --dry-run

# Broader TTY (explicit):
python -m scripts.import_rxnorm --tty "IN BN" --full-rxnorm --dry-run

# Force a fresh RxNav fetch instead of the cached response:
python -m scripts.import_rxnorm --tty IN --refresh-cache --dry-run
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--tty` | `IN` | RxNorm term type(s), space/comma-separated (e.g. `"IN"`, `"IN BN"`). `IN` = ingredients. Filtering is applied during streaming, not ignored. |
| `--full-rxnorm` | off | Use full catalog (`/REST/allconcepts.json`) instead of Prescribable Content (`/REST/Prescribe/allconcepts.json`). Prescribable is default. |
| `--limit` | none (all remaining) | Max concepts to process this run (after offset, after TTY filtering). |
| `--offset` | last checkpoint | Starting position in the filtered, streamed concept list. |
| `--batch-size` | `rxnorm_import_batch_size` (500) | Persistence batch size (configurable via `app.core.config.Settings` or `RXNORM_IMPORT_BATCH_SIZE` env). Bounded-memory buffer. |
| `--dry-run` | off | Logs planned changes; writes nothing, advances no checkpoint. |
| `--refresh-cache` | off | Refetch from RxNav instead of using the disk cache (atomic .partial handling). |
| `--no-checkpoint` | off | Don't read/write the resumability checkpoint file. |
| `--log-level` | `INFO` | Standard Python logging level. |

### Performance & correctness guarantees

- **Streaming/bounded-memory**: `ijson` incremental parsing + batch buffers; verified flat ~0.71 MB peak across 5k/20k/80k synthetic catalogs (original scaled linearly). Download itself lands on disk whole — RxNav has no pagination.
- **Batch efficiency**: 2 queries per batch (batched `IN`), not N+1.
- **Atomic cache/checkpoint**: `.partial` + atomic rename for downloads; `*.tmp` → rename for checkpoints.
- **Idempotency**: second import inserts 0, duplicates 0, row count stable.
- **Failure durability**: earlier batches remain, checkpoint stays at last success, error reports batch/offset, resume continues without duplicates.

### What this script deliberately does NOT do

- Does not import `dose_form`, `strength`, `route`, `term_type`, or
  `atc_code` -- these columns do not exist on `reference_drugs` (out of
  scope for this phase; no `term_type`/`is_active`/`rxnorm_term_type_enum`
  or `lower(name)` index is created).
- Does not import or modify `interaction_rules` / `adr_rules`.
- Does not expose an API by itself -- see `GET /api/v1/reference-drugs/search`
  (`backend/app/api/v1/reference_drugs.py`) for the read-only search
  endpoint that consumes this catalog.
