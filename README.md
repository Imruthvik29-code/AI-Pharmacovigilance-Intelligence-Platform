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
backend/
  app/
  supabase/migrations/
  tests/
  requirements.txt      <- single source of Python dependencies
  .env.example
  pytest.ini
frontend/
docs/
```

Dependencies live in exactly one place: `backend/requirements.txt`. There is
no root-level `requirements.txt` — if one exists in your local checkout from
before this note was added, delete it; it was a stale duplicate.

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
| `SUPABASE_JWT_SECRET` | Yes (Phase 2+) | Shared HMAC secret used to verify Supabase-issued JWTs, from Settings → API → JWT Settings. |
| `HTTP_TIMEOUT_SECONDS` | No (default `10.0`) | Timeout for outbound calls to Supabase Auth. |

See `backend/.env.example` for a ready-to-copy template.

#### Database setup

Before starting the backend for the first time, run the SQL migrations
against your Supabase project (SQL editor or `psql`), in order:

```bash
backend/supabase/migrations/001_initial_schema.sql
backend/supabase/migrations/002_seed_data.sql
```

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
