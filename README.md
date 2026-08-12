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
001_initial_schema.sql          <- initial schema (Postgres enums + tables + indexes + RLS)
002_seed_data.sql               <- 12 seed drugs + 7 interaction + 13 ADR rules (FDA Label provenance)
003_reference_drugs_external_reference.sql <- adds rxcui/source/source_updated_at to reference_drugs

backend/
  app/
    main.py                     <- FastAPI entrypoint (liveness /health + 9 routers) — single source of truth
    api/v1/                     <- auth, patients, medications, conditions, symptoms, timeline, schedule, analysis, reference_drugs
    analysis/                   <- deterministic engines (interaction, ADR, adherence, safety score, timeline)
    services/                   <- patient_context_builder, evidence_retrieval, llm_service, llm_providers, langgraph_workflow, timeline_writer
    core/                       <- config (DATABASE_URL, Supabase JWKS derived), security (ES256)
    db/                         <- models.py (typed ORM mirrors 001), session.py (async engine)
  scripts/
    import_rxnorm.py            <- offline RxNorm Prescribable Content importer (IN-only, --dry-run)
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

Before starting the backend for the first time, run the SQL migrations
against your Supabase project (SQL editor or `psql`), in order:

```bash
# From repository root — migrations are flat, sequential SQL files at root (source of truth per ARCHITECTURE_DECISIONS.md §6.1)
# Apply in order:

001_initial_schema.sql          # enums, tables, indexes, RLS — 11 tables, 7 ENUMs, 11 indexes
002_seed_data.sql               # 12 seed reference_drugs + 7 interaction_rules + 13 adr_rules (source='FDA Label')
003_reference_drugs_external_reference.sql  # adds rxcui unique, source, source_updated_at to reference_drugs (for RxNorm importer)

# Example via psql (replace with your Supabase connection string):
# psql "$DATABASE_URL" -f 001_initial_schema.sql
# psql "$DATABASE_URL" -f 002_seed_data.sql
# psql "$DATABASE_URL" -f 003_reference_drugs_external_reference.sql

# Or via Supabase SQL editor: copy-paste each file in order and run.
```

Note: After `001`–`003`, future schema changes will be managed via
Alembic (see Section 24 Phase B roadmap). Existing databases should be
brought under Alembic via `alembic stamp <baseline_revision>` (marks schema
as already at baseline without re-executing DDL). New databases can either
continue using `001`–`003` until a full baseline migration is generated, or
use a proper baseline revision that builds schema from scratch.

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
