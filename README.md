# AI Pharmacovigilance Intelligence Platform

## Overview

An AI-powered medication safety and pharmacovigilance platform that helps users manage medications, monitor adherence, track symptoms, detect potential medication risks, and generate explainable AI-powered safety reports.

---

## Features

- Patient Management
- Medication Tracking
- Dose Scheduling
- Adherence Monitoring
- Symptom Tracking
- Timeline View
- Drug Interaction Detection
- ADR Detection
- Medication Safety Score
- AI-generated Explanations
- Analysis Reports

---

## Tech Stack

### Frontend
- Next.js
- TypeScript

### Backend
- FastAPI
- SQLAlchemy
- Pydantic

### Database
- Supabase PostgreSQL

### AI
- LangGraph
- Gemini API
- OpenRouter (Fallback)

---

## Project Structure

```
bootstrap_alembic_version.sql   <- version-table bootstrap for NEW databases (infrastructure, not schema)
001_initial_schema.sql          <- initial schema (Postgres enums + tables + indexes + RLS)
002_seed_data.sql               <- 12 seed drugs + 7 interaction + 13 ADR rules (FDA Label provenance)
003_reference_drugs_external_reference.sql <- adds rxcui/source/source_updated_at to reference_drugs
alembic.ini                     <- Alembic config (script_location = backend/alembic)

backend/
  alembic/
    versions/                   <- 0001_baseline (stamp for 001–003) through 0006 (patient daily routine)
  app/
    main.py                     <- FastAPI entrypoint (liveness /health + 9 routers) — single source of truth
    api/v1/                     <- auth, patients, medications, conditions, symptoms, timeline, schedule, analysis, reference_drugs
    analysis/                   <- deterministic engines (interaction, ADR, adherence, safety score, timeline)
    services/                   <- patient_context_builder, evidence_retrieval, llm_service, llm_providers, langgraph_workflow, timeline_writer
    core/                       <- config (DATABASE_URL, Supabase JWKS derived), security (ES256)
    db/                         <- models.py (typed ORM mirrors the SQL migrations), session.py (async engine)
  scripts/
    import_rxnorm.py            <- multi-TTY RxNorm importer (IN/PIN/MIN/SCD/SBD/GPCK/BPCK/DF, auto-batched + resumable, opt-in --related)
    README.md                   <- importer usage
  tests/                        <- integration + unit tests (require live Supabase for integration)
  requirements.txt              <- single source of Python dependencies
  .env.example
  pytest.ini

ARCHITECTURE_DECISIONS.md       <- Sections 1–24, v1.0 frozen — evidence-first, repository-verified
PROJECT_PHASES.md
pharmacovigilance-spec-v1.md
```

Dependencies live in exactly one place: `backend/requirements.txt`. There is
no root-level `requirements.txt` — if one exists in your local checkout from
before this note was added, delete it; it was a stale duplicate.

Note: `frontend/` is referenced in older docs but is not included in this minimal
backend-focused checkout. The backend API is fully functional without it. See
`ARCHITECTURE_DECISIONS.md` §§17.2, 19.2, 23.2 for frontend absence verification.

---

## Getting Started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real Supabase values (see below)
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`. `GET /health` is a basic liveness check.

#### Required environment variables (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Async Postgres connection string (`postgresql+asyncpg://...`), from Supabase project settings → Database → Connection string. |
| `SUPABASE_URL` | Yes (Phase 2+) | Your Supabase project URL, e.g. `https://xxxxxxxx.supabase.co`. |
| `SUPABASE_ANON_KEY` | Yes (Phase 2+) | Supabase anon/public API key, from Settings → API. |
| `SUPABASE_JWT_SECRET` | Deprecated; backward compatibility only | Retained only for compatibility with older setup docs. It is no longer used after the JWKS migration. |
| `HTTP_TIMEOUT_SECONDS` | No (default `10.0`) | Timeout for outbound calls to Supabase Auth. |

See `backend/.env.example` for a ready-to-copy template.

#### Database setup

Three kinds of file are involved, and they are not interchangeable:

| Kind | Files | Role |
|---|---|---|
| **Version-table bootstrap** | `bootstrap_alembic_version.sql` | Infrastructure only. Creates Alembic's bookkeeping table at the width this project's revision identifiers need. Defines no application schema. |
| **Legacy schema + seed** | `001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql` | The schema foundation, per ARCHITECTURE_DECISIONS.md §6.1. |
| **Alembic migration history** | `backend/alembic/versions/` | Every schema change after that foundation. |

##### New database

Run all six steps **in this order**, against an empty Supabase project:

```bash
# 1. Version-table bootstrap — FIRST, before any schema exists.
psql "$DATABASE_URL" -f bootstrap_alembic_version.sql

# 2-4. Legacy schema foundation.
psql "$DATABASE_URL" -f 001_initial_schema.sql                      # enums, 11 tables, 11 indexes, RLS
psql "$DATABASE_URL" -f 002_seed_data.sql                           # 12 reference_drugs + 7 interaction_rules + 13 adr_rules
psql "$DATABASE_URL" -f 003_reference_drugs_external_reference.sql  # rxcui unique, source, source_updated_at

# 5-6. Bring the database under Alembic and apply the tracked history.
python -m alembic -c alembic.ini stamp 0001_baseline
python -m alembic -c alembic.ini upgrade head
```

The SQL files can also be pasted into the Supabase SQL editor in the same
order. **Steps 5 and 6 must be run online** — connected directly to the
database. Alembic's offline `--sql` output emits its own version table at
the default width and is not a substitute for this sequence.

`bootstrap_alembic_version.sql` runs first deliberately: it refuses to
execute if `patients` already exists, so it can only distinguish a genuinely
new database from an established one while it runs ahead of
`001_initial_schema.sql`. It creates Alembic's `alembic_version` table with
`version_num VARCHAR(64)` because Alembic 1.13.2 would otherwise create it
as `VARCHAR(32)`, which is too narrow for
`0004_add_reference_drug_search_trigram_indexes` (46 characters) — the
upgrade would abort and roll back at the `0002 -> 0003` transition.

##### Existing database

Already-established databases need none of the above. Bring them up to date
with the tracked history:

```bash
python -m alembic -c alembic.ini upgrade head
```

A database that predates Alembic is reconciled once with
`alembic stamp 0001_baseline` (records the baseline without re-executing
DDL) before its first `upgrade`.

Current tracked history:

```
0001_baseline
  -> 0002_add_term_type_is_active              reference_drugs.term_type / is_active
  -> 0003_add_rxnorm_concept_relations         RxNorm relationship edges
  -> 0004_add_reference_drug_search_trigram_indexes
  -> 0005_add_patient_relation
  -> 0006_add_patient_daily_routine            patient timezone + meal times
```

The RxNorm importer (`backend/scripts/import_rxnorm.py`) requires the schema
at `0003` or later.

#### Running tests

```bash
cd backend
pytest -v
```

Note: the test suite (from Phase 1 onward) runs as integration tests
against your live Supabase instance — there's no mocked/in-memory DB layer.
Some tests additionally require at least one row in `auth.users`; sign up a
test user first via `POST /api/v1/auth/signup`.

### Frontend

```bash
cd frontend

npm install

npm run dev
```

---
## Development Workflow

Development follows a phase-based workflow:

1. Implement one project phase.
2. Test the implementation.
3. Update `PROJECT_PHASES.md`.
4. Update `CHANGELOG.md`.
5. Commit the completed phase to Git.
6. Proceed to the next phase.

The project specification (`pharmacovigilance-spec-v1.md`) is the single source of truth and should not be modified unless a new specification version is intentionally created.

## Roadmap

- Authentication
- Patient CRUD
- Medication Management
- Dose Scheduling
- Timeline
- Drug Interaction Engine
- ADR Engine
- LangGraph
- AI Reports

---

**Disclaimer**

This project is an educational and research-oriented pharmacovigilance application. It is not intended to replace professional medical advice, diagnosis, or treatment. The AI explains deterministic medication safety findings and should not be relied upon as the sole basis for clinical decisions.
