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

backend/

frontend/

docs/

---

## Getting Started

### Backend

```bash
cd backend

pip install -r requirements.txt

uvicorn app.main:app --reload
```

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
