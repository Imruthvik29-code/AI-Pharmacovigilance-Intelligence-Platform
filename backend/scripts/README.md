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

### How it works

1. Fetches the full RxNorm concept list for a term type (default `IN` =
   ingredients, matching the granularity of the existing curated seed
   drugs) via RxNav's `getAllConceptsByTTY` endpoint. This is the only
   RxNorm bulk-enumeration endpoint, and it has **no server-side
   pagination** (verified against NLM's own API docs) -- it returns the
   entire concept list for the given term type in one response.
2. Caches that raw response to
   `backend/scripts/.rxnorm_cache/allconcepts_<tty>.json` so repeated runs
   don't re-hit the network (`--refresh-cache` forces a refetch).
3. Applies `--offset`/`--limit` **client-side** over that cached,
   name-sorted list -- this is how batch size is controlled, since RxNav
   itself can't paginate.
4. Upserts each concept into `reference_drugs`, keyed on the unique
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
5. **Never deletes or renumbers** any row.
6. A checkpoint file (`backend/scripts/.rxnorm_cache/checkpoint_<tty>.json`)
   records the next offset to resume from, so a follow-up run without
   `--offset` continues automatically. This is a convenience -- every
   write is independently idempotent via the `rxcui` upsert above, so
   re-running any slice (or the whole catalog) twice is always safe.

### Usage

Run from `backend/`:

```bash
cd backend

# 1. Always dry-run first.
python -m scripts.import_rxnorm --tty IN --limit 500 --dry-run

# 2. Run for real.
python -m scripts.import_rxnorm --tty IN --limit 500

# 3. Next batch -- offset resumes automatically from the checkpoint.
python -m scripts.import_rxnorm --tty IN --limit 500

# Process everything at once (no --limit):
python -m scripts.import_rxnorm --tty IN

# Force a fresh RxNorm fetch instead of the cached response:
python -m scripts.import_rxnorm --tty IN --refresh-cache --dry-run
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--tty` | `IN` | RxNorm term type(s), space-separated (e.g. `"IN BN"`). `IN` = ingredients. |
| `--limit` | none (all remaining) | Max concepts to process this run. |
| `--offset` | last checkpoint | Starting position in the cached, name-sorted concept list. |
| `--dry-run` | off | Logs planned changes; writes nothing, advances no checkpoint. |
| `--refresh-cache` | off | Refetch from RxNav instead of using the disk cache. |
| `--no-checkpoint` | off | Don't read/write the resumability checkpoint file. |
| `--log-level` | `INFO` | Standard Python logging level. |

### What this script deliberately does NOT do

- Does not import `dose_form`, `strength`, `route`, `term_type`, or
  `atc_code` -- these columns do not exist on `reference_drugs` (out of
  scope for this phase).
- Does not import or modify `interaction_rules` / `adr_rules`.
- Does not expose an API by itself -- see `GET /api/v1/reference-drugs/search`
  (`backend/app/api/v1/reference_drugs.py`) for the read-only search
  endpoint that consumes this catalog.
