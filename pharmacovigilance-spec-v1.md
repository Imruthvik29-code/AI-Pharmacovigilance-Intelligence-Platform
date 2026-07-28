# Pharmacovigilance MVP — Project Specification v1.0

**Status: FROZEN.** This document is the single source of truth for the build. Do not redesign the architecture mid-implementation — only fix genuine implementation issues discovered during coding.

---

## 1. Product Overview

An AI-powered medication safety and pharmacovigilance platform. It tracks a patient's conditions, medications, dosing adherence, and symptoms over time, runs deterministic safety analysis (drug interactions, adverse drug reactions, adherence patterns), and uses an LLM purely to **explain** those deterministic findings in plain language — never to originate them.

## 2. Functional Requirements

- User authentication (signup/login, protected routes)
- Patient profile management
- Condition tracking with lifecycle status and diagnosis reason
- Medication tracking with lifecycle status, linked to a condition or free-text purpose
- Dose scheduling and adherence logging (taken/missed/skipped)
- Symptom tracking, optionally linked to a condition and/or suspected medication
- Unified patient timeline of all events
- Deterministic analysis: drug interactions, ADR matching, adherence patterns, composite safety score
- LLM-generated plain-language explanation, reasoning, and recommendations, grounded only in deterministic output + retrieved evidence
- Analysis report view (score, timeline, explanation), versioned

## 3. Non-Functional Requirements

- Runs on 8GB RAM / no GPU / Windows dev machine — no local heavy ML models
- All AI APIs free-tier (Gemini primary, OpenRouter fallback)
- No large dataset downloads; curated drug/interaction set, schema built to scale later
- MVP delivery target: ~1 week
- Deployment: Vercel (frontend), Render/Railway/Fly.io (backend), Supabase (DB)

## 4. Tech Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI |
| Frontend | Next.js |
| Database | Supabase PostgreSQL |
| AI orchestration | LangGraph |
| Primary LLM | Gemini (free tier) |
| Fallback LLM | OpenRouter |
| Retrieval (MVP) | Plain SQL (personal history + interaction rules) — pgvector added later without node changes |

## 5. Database Schema

```sql
-- auth.users via Supabase Auth

patients (
  id uuid pk,
  user_id uuid fk -> auth.users,
  name text,
  age int,
  sex text,
  weight_kg numeric,
  renal_flag boolean,
  hepatic_flag boolean,
  created_at timestamptz
)

conditions (
  id uuid pk,
  patient_id uuid fk -> patients,
  name text,
  status text,              -- Active / Improving / Resolved / Persistent / Recurred
  reason text,               -- Doctor diagnosis / User suspected / Unknown
  diagnosed_date date,
  resolved_date date nullable,
  notes text,
  created_at timestamptz
)

reference_drugs (
  id uuid pk,
  name text,
  generic_name text,
  drug_class text
)

-- Each row is one prescribing course. Re-prescribing the same drug later
-- creates a new row rather than reusing/overwriting an old one, so history
-- stays clean without needing a separate courses table.
medications (
  id uuid pk,
  patient_id uuid fk -> patients,
  condition_id uuid fk -> conditions nullable,
  purpose_text text nullable,    -- free-text reason if no linked condition
  drug_id uuid fk -> reference_drugs,
  dose text,
  times_per_day int,
  interval_hours numeric nullable,
  duration_days int nullable,
  status text,                   -- Active / Completed / Completed Early / Paused / Discontinued
  start_date date,
  end_date date nullable,
  created_at timestamptz,
  updated_at timestamptz
)

medication_schedule (
  id uuid pk,
  medication_id uuid fk -> medications,
  scheduled_time timestamptz,
  created_at timestamptz
)

medication_doses (
  id uuid pk,
  medication_id uuid fk -> medications,
  schedule_id uuid fk -> medication_schedule nullable,
  scheduled_time timestamptz,
  status text,                    -- Taken / Missed / Skipped
  actual_time timestamptz nullable,
  created_at timestamptz
)

symptoms (
  id uuid pk,
  patient_id uuid fk -> patients,
  condition_id uuid fk -> conditions nullable,
  medication_id uuid fk -> medications nullable,
  description text,
  severity text,                  -- mild/moderate/severe
  onset_date date,
  resolved_date date nullable,
  created_at timestamptz
)

interaction_rules (
  id uuid pk,
  drug_a_id uuid fk -> reference_drugs,
  drug_b_id uuid fk -> reference_drugs,
  severity severity_enum,
  mechanism text,
  recommendation text,
  source text,             -- e.g. "FDA Label", "OpenFDA", "FAERS"
  created_at timestamptz,
  updated_at timestamptz
)

adr_rules (
  id uuid pk,
  drug_id uuid fk -> reference_drugs,
  reaction_description text,
  severity severity_enum,
  frequency_class text nullable,   -- e.g. common/uncommon/rare, if known
  source text,
  created_at timestamptz,
  updated_at timestamptz
)

timeline_events (
  id uuid pk,
  patient_id uuid fk -> patients,
  event_type text,        -- medication_started / dose_taken / dose_missed / dose_skipped /
                           -- symptom_reported / condition_status_changed / analysis_run / medication_discontinued
  ref_id uuid,
  event_title text,
  event_description text,
  event_time timestamptz,
  payload jsonb,
  created_at timestamptz
)

-- NOTE: no patient_context table. Patient context is built dynamically by
-- patient_context_builder.py on each analysis run (queries active conditions/
-- medications/symptoms fresh), avoiding staleness. Add caching (Redis,
-- materialized view) later only if performance requires it.

analysis_runs (
  id uuid pk,
  patient_id uuid fk -> patients,
  analysis_version text,           -- e.g. "v1.0"
  deterministic_result jsonb,
  safety_score int,
  risk_level severity_enum,        -- Low / Moderate / High (reuse severity_enum)
  llm_summary text,
  llm_reasoning text,
  llm_recommendations text,
  confidence_score int,            -- 0-100
  confidence_level text,           -- Low / Moderate / High
  created_at timestamptz
)
```

`severity_enum` = one shared enum (`mild`, `moderate`, `severe` for symptoms/interactions/ADRs; `low`, `moderate`, `high` for risk_level — implemented as a single Postgres enum type or two related enums, whichever the ORM prefers). All tables above also gain `created_at` + `updated_at` audit columns where not already listed (patients, conditions, symptoms, medication_doses).

## 6. Folder Structure

**Backend (FastAPI):**
```
backend/app/
  main.py
  core/
    config.py
    security.py
  db/
    session.py
    models.py
  api/v1/
    auth.py
    patients.py
    conditions.py
    medications.py
    schedule.py
    symptoms.py
    timeline.py
    analysis.py
  analysis/
    drug_interaction_engine.py
    adr_engine.py
    adherence_engine.py
    timeline_engine.py
    safety_score_engine.py
  services/
    patient_context_builder.py
    llm_service.py
    langgraph_workflow.py
  schemas/
    patient.py
    condition.py
    medication.py
    symptom.py
    analysis.py
```

**Frontend (Next.js):**
```
frontend/app/
  (auth)/login/page.tsx
  (auth)/signup/page.tsx
  dashboard/page.tsx
  patients/[id]/page.tsx
  patients/[id]/conditions/page.tsx
  patients/[id]/symptoms/page.tsx
  patients/[id]/doses/page.tsx
  patients/[id]/analysis/page.tsx
frontend/components/
  MedicationForm.tsx
  ConditionForm.tsx
  SymptomForm.tsx
  DoseCheckIn.tsx
  SafetyScoreCard.tsx
  TimelineView.tsx
  LLMSummaryPanel.tsx
frontend/lib/
  api.ts
  supabaseClient.ts
```

## 7. API Contracts

```
POST   /auth/signup
POST   /auth/login

GET    /patients
POST   /patients
GET    /patients/{id}
PUT    /patients/{id}

POST   /patients/{id}/conditions
PUT    /conditions/{id}

GET    /patients/{id}/medications
POST   /patients/{id}/medications
PUT    /medications/{id}
DELETE /medications/{id}

POST   /medications/{id}/schedule
POST   /doses/{id}/mark
GET    /patients/{id}/doses/upcoming

POST   /patients/{id}/symptoms
GET    /patients/{id}/symptoms

GET    /patients/{id}/timeline

POST   /patients/{id}/analyze
GET    /patients/{id}/analysis
```

## 8. LangGraph Workflow

```
[Input: patient_id]
        │
        ▼
[Patient Context Builder Node] — builds context object fresh each run
                                  (active conditions/medications/symptoms;
                                   no stored cache table, so never stale)
        │
        ▼
[Deterministic Analysis Layer]
  ├─ Drug Interaction Engine
  ├─ ADR Engine
  ├─ Adherence Engine
  ├─ Timeline Engine
  └─ Safety Score Engine (merges above → score + risk_level)
        │
        ▼
[Evidence Retrieval Node] — SQL: interaction_rules/adr_rules (medical KB)
                             + patient's own timeline (personal KB)
                             [pgvector swap-in point for later]
        │
        ▼
[LLM Explanation Node] — Gemini: input = {patient_context, deterministic_result, evidence}
                          output = {summary, reasoning, recommendations, confidence_score, confidence_level}
        │
        ▼
[Persist Node] — writes analysis_runs + timeline_event, refreshes patient_context
        │
        ▼
[Output]
```

## 9. UI Wireframes (low-fi)

- **Dashboard**: patient list, "+ Add Patient"
- **Patient page**: demographics, active conditions, active medications, "Run Analysis" button
- **Conditions page**: list with status badges, reason field
- **Symptoms page**: log form (description, severity, linked condition/medication)
- **Doses page**: upcoming doses list, mark taken/missed/skipped
- **Analysis page**: safety score gauge (color = risk_level), unified timeline (color-coded by event_type), LLM summary panel with expandable reasoning/recommendations, confidence badge

## 10. Implementation Phases

1. **Database** — full schema migration, all tables, enums, seed reference_drugs/interaction_rules/adr_rules
2. **Authentication** — Supabase auth wiring, JWT middleware, protected routes
3. **Patient CRUD**
4. **Medication CRUD**
5. **Conditions**
6. **Symptoms**
7. **Timeline** — timeline_events writer, triggered by all prior modules
8. **Dose Scheduling** — schedule generation from times_per_day/interval_hours
9. **Adherence** — mark taken/missed/skipped, missed-dose background check
10. **Drug Interaction Engine**
11. **ADR Engine**
12. **Safety Score Engine** — merges interaction + ADR + adherence findings
13. **Evidence Retrieval** — SQL lookup, medical + personal evidence
14. **LangGraph** — wire all nodes, test each independently before connecting
15. **LLM Explanation Layer** — Gemini integration
16. **Frontend** — pages/components against the above APIs
17. **Deployment** — Vercel + Render/Railway/Fly.io

---

*This specification is frozen as of the planning phase. Implementation proceeds phase by phase against it.*
