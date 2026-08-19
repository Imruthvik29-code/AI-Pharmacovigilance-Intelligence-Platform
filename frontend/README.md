# Frontend — Pharmacovigilance Intelligence

First vertical slice: login → patient → catalog medication picker → run analysis → real safety report + timeline.

This is a Next.js App Router client of the existing FastAPI backend. It does **not** mock analysis results, invent findings, or add backend routes.

## Prerequisites

- Node 20+
- Backend running (`uvicorn app.main:app --reload --host 0.0.0.0` from `backend/`)
- Live Supabase + seed data (`002_seed_data.sql`) + Alembic head `0003`

The frontend cannot create those. Without a configured backend, screens still render but API calls fail honestly.

## Setup

```bash
cd frontend
cp .env.example .env.local   # optional; default backend is http://127.0.0.1:8000
npm install
npm run dev
```

Open `http://localhost:3000`.

`BACKEND_URL` is **server-side only**. Next.js rewrites browser `/api/:path*` to `${BACKEND_URL}/api/:path*`. Do not put `DATABASE_URL`, service-role keys, or LLM keys in frontend env files.

## Routes

| Path | Screen |
|---|---|
| `/login` | Sign in |
| `/signup` | Create account (handles 201 session and 202 email confirmation) |
| `/dashboard` | Patient list + create |
| `/patients/[patientId]` | Medications, picker, run analysis, report, timeline |

## API used

Same-origin paths (proxied to FastAPI `/api/v1`):

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/signup`
- `GET /api/v1/auth/me` (session helper)
- `GET/POST /api/v1/patients`
- `GET /api/v1/patients/{id}`
- `GET /api/v1/reference-drugs/search?q=`
- `GET/POST /api/v1/patients/{id}/medications`
- `POST /api/v1/patients/{id}/analyze`
- `GET /api/v1/patients/{id}/analysis`
- `GET /api/v1/patients/{id}/timeline`

## Honesty notes

- Safety score, risk, findings, and penalties are rendered from the backend response.
- `MedicationResponse` has `drug_id` only. Names are cached from catalog search in `localStorage`. After a refresh in a browser that has not seen the catalog result, the list shows “Name not cached in this browser” — never a raw UUID.
- If `llm_summary` is null, the report says “AI explanation unavailable for this analysis.”
- No refresh-token flow: the backend has no refresh route.

## Scripts

```bash
npm run dev
npm test
npm run typecheck
npm run lint
npm run build
```
