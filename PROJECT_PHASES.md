# Pharmacovigilance MVP - Development Progress

**Project Status:** 🟢 In Development

**Current Milestone:** Milestone 2 - Patient Data Management

**Current Phase:** Phase 9 - Adherence

**Last Updated:** 2026-07-31

---

# Overall Progress

## 🟢 Milestone 1 - Foundation

- [x] Phase 1 - Database
    - [x] Initial Schema
    - [x] Enums
    - [x] Constraints
    - [x] Seed Data
    - [x] Database Testing

- [x] Phase 2 - Authentication
    - [x] Supabase Auth
    - [x] JWT Middleware
    - [x] Protected Routes
    - [x] Authentication Testing

- [x] Phase 3 - Patient CRUD
    - [x] Create Patient
    - [x] View Patient
    - [x] Update Patient
    - [x] Delete Patient *(see note below)*
    - [x] CRUD Testing

---

## 🟡 Milestone 2 - Patient Data Management

- [x] Phase 4 - Medication CRUD
    - [x] Add Medication
    - [x] Update Medication
    - [x] Delete Medication
    - [x] Medication Testing

- [x] Phase 5 - Conditions
    - [x] Add Condition
    - [x] Update Condition
    - [x] Status Management *(see note below)*
    - [x] Condition Testing

- [x] Phase 6 - Symptoms
    - [x] Add Symptoms
    - [x] Link to Medication
    - [x] Link to Condition
    - [x] Symptom Testing

- [x] Phase 7 - Timeline
    - [x] Timeline Events
    - [x] Automatic Event Logging *(see note below)*
    - [x] Timeline API
    - [x] Timeline Testing

- [x] Phase 8 - Dose Scheduling
    - [x] Schedule Generator *(see refinement note below)*
    - [x] Upcoming Doses
    - [x] Scheduling Testing

- [ ] Phase 9 - Adherence
    - [ ] Taken
    - [ ] Missed
    - [ ] Skipped
    - [ ] Adherence Statistics
    - [ ] Adherence Testing

---

## 🟠 Milestone 3 - Medication Intelligence

- [ ] Phase 10 - Drug Interaction Engine
    - [ ] Interaction Detection
    - [ ] Severity Calculation
    - [ ] Interaction Testing

- [ ] Phase 11 - ADR Engine
    - [ ] ADR Detection
    - [ ] Severity Matching
    - [ ] ADR Testing

- [ ] Phase 12 - Safety Score Engine
    - [ ] Score Calculation
    - [ ] Risk Level
    - [ ] Safety Score Testing

- [ ] Phase 13 - Evidence Retrieval
    - [ ] Medical Knowledge Retrieval
    - [ ] Patient History Retrieval
    - [ ] Retrieval Testing

---

## 🔵 Milestone 4 - AI Explanation Layer

- [ ] Phase 14 - LangGraph Workflow
    - [ ] Graph Nodes
    - [ ] Workflow Integration
    - [ ] LangGraph Testing

- [ ] Phase 15 - Gemini Integration
    - [ ] Prompt Engineering
    - [ ] Summary Generation
    - [ ] Recommendation Generation
    - [ ] AI Testing

---

## 🟣 Milestone 5 - Product Completion

- [ ] Phase 16 - Frontend
    - [ ] Authentication Pages
    - [ ] Dashboard
    - [ ] Patient Pages
    - [ ] Timeline UI
    - [ ] Analysis UI
    - [ ] Frontend Testing

- [ ] Phase 17 - Deployment
    - [ ] Backend Deployment
    - [ ] Frontend Deployment
    - [ ] Database Configuration
    - [ ] End-to-End Testing

---

# Current Tasks

None — Phase 8 complete and approved, awaiting the start of Phase 9 (Adherence).

---

# Known Issues

None

---

# Next Task

Start Phase 9 - Adherence (Taken, Missed, Skipped, Adherence Statistics, Adherence Testing).

---

# Notes

- Follow `pharmacovigilance-spec-v1.md` as the single source of truth.
- Do not redesign the architecture.
- Complete one phase before starting the next.
- Test every phase before marking it complete.
- Commit all working changes to Git before moving to the next phase.
- Phase 1 seed data (`002_seed_data.sql`) is intentionally a small, curated
  set (12 drugs, 7 interaction rules, 13 ADR rules) built from established
  FDA label facts. Expand later without touching the schema.
- **Phase 3 "Delete Patient" clarification:** `DELETE /patients/{id}` is
  deliberately **not** implemented. It is not part of the frozen API
  contract in `pharmacovigilance-spec-v1.md` section 7, and this was
  confirmed with the project owner during Phase 3 planning. The subtask
  checkbox above is marked complete in the sense that the decision was
  made and verified (`test_no_delete_endpoint_exists` asserts a 405 on
  that route), not because a delete endpoint exists.
- **Phase 4 note:** `DELETE /medications/{id}` **is** in the frozen API
  contract and is implemented as a genuine hard delete (unlike patients).
  `condition_id` on a medication is validated against the `conditions`
  table if provided (must belong to the same patient), even though
  Condition CRUD itself didn't exist yet at the time — this was a
  data-integrity guard, not an early implementation of Phase 5.
- **Phase 5 "Status Management" clarification:** the frozen spec does not
  define a condition lifecycle state machine or transition rules.
  `PUT /conditions/{id}` allows `status` to be set to any of the five enum
  values regardless of its current value, and does not auto-populate
  `resolved_date` when status is set to `resolved` — that remains an
  explicit client-supplied field. The subtask checkbox is marked complete
  because status is fully settable/updatable per the spec's actual scope,
  not because a transition-validation state machine was built.
- **Phase 5 scope note:** per the frozen spec (section 7), conditions only
  expose `POST /patients/{id}/conditions` and `PUT /conditions/{id}` —
  there is no `GET` or `DELETE` route for conditions. This was confirmed
  with the project owner during Phase 5 planning and implemented strictly
  as written.
- **Phase 6 scope note:** per the frozen spec (section 7), symptoms only
  expose `POST /patients/{id}/symptoms` and `GET /patients/{id}/symptoms`
  — there is no `PUT` or `DELETE` route for symptoms, confirmed and
  implemented strictly as written (`test_no_update_or_delete_endpoints_exist`
  asserts 405 on both).
- **Phase 6 "Link to Condition/Link to Medication" clarification:** these
  subtasks refer to the optional `condition_id`/`medication_id` fields on
  a symptom, each validated (if provided) to belong to the same patient
  the symptom is being logged for — a 400 data-integrity guard, the same
  pattern used for `medications.condition_id` in Phase 4. No cascading or
  automatic linkage behavior beyond this validation was implemented or
  required by the spec.
- **Phase 6 "onset_date" note:** the DB column defines
  `default current_date`, but this is applied in the application layer
  (`date.today()` if omitted by the client) rather than relied upon as a
  DB-side default reaching the ORM — consistent with how other date/time
  defaults (e.g. `created_at`) are handled throughout this codebase.
- **Phase 7 scope note:** per the frozen spec (section 7), the timeline
  only exposes `GET /patients/{id}/timeline` — read-only, no
  POST/PUT/DELETE, since events are never created directly by a client.
  Confirmed and implemented strictly as written
  (`test_no_post_put_delete_endpoints_exist` asserts 405 on all three).
- **Phase 7 "Automatic Event Logging" clarification:** of the eight
  `event_type` values documented in spec section 5, only the four
  producible by phases built so far are wired up: `medication_started`
  (medication creation), `medication_discontinued` (status transition
  *into* `discontinued` only — not on every PUT, and not on the hard
  `DELETE`, since the spec has no "medication deleted" event type),
  `condition_status_changed` (only when status value actually changes),
  and `symptom_reported` (symptom creation). `dose_taken`/`dose_missed`/
  `dose_skipped` are deferred to Phase 9 (Adherence) and `analysis_run` to
  Phase 12+ (Safety Score Engine), since neither dose marking nor
  analysis runs exist yet. The subtask checkbox is marked complete
  because all currently-possible event types are wired, not because all
  eight values are in use yet.
- **Phase 7 architecture note:** a new `app/services/timeline_writer.py`
  was added (`log_timeline_event` helper) — not explicitly named in the
  spec's section 6 folder listing, but an additive fit consistent with
  the existing `services/` convention, not an architecture change. It
  only calls `db.add(...)` and never commits, so every timeline event is
  written in the same transaction as the entity write that triggered it.
- **Phase 8 note:** `POST /medications/{id}/schedule` requires
  `duration_days` and **at least one** of (`times_per_day`,
  `interval_hours`) to already be set on the medication (400 otherwise).
  Two supported input shapes:
  - `times_per_day` set (with or without `interval_hours`): dose count is
    `times_per_day * duration_days`; spacing uses `interval_hours` if set,
    else an even daily spread (`24 / times_per_day`).
  - `times_per_day` absent, `interval_hours` set: spacing uses
    `interval_hours` directly; dose count is derived as
    `floor(duration_days * 24 / interval_hours)` (minimum 1), i.e. as many
    evenly-spaced doses as fit within the duration window, since there is
    no explicit per-day count to multiply by.
  Both shapes anchor the first dose at 08:00 UTC on `start_date`, reject
  (409) regeneration of an existing schedule, and are capped at
  `MAX_GENERATED_DOSES` (3650) as a defensive guard. The interval-only
  shape was added as a confirmed refinement after the initial Phase 8
  implementation, per project owner request — it does not alter any API
  contract, route, response model, or the database schema.
- **Phase 8 scope note:** `POST /doses/{id}/mark` is listed in the frozen
  spec's API contract (section 7) but is explicitly out of scope for
  Phase 8 — it belongs to Phase 9 (Adherence) per spec section 10, and is
  intentionally not registered on any router yet
  (`test_mark_endpoint_not_yet_implemented` confirms a 404, not 405,
  since the route doesn't exist).
- **Phase 8 "Upcoming Doses" clarification:**
  `GET /patients/{id}/doses/upcoming` returns only future
  (`scheduled_time >= now`), unmarked (`status IS NULL`) doses belonging
  to medications with `status == "active"` — doses for
  paused/discontinued/completed medications are excluded. Results are
  enriched with `drug_name`/`dose` via a join, ordered ascending by
  `scheduled_time`.
- **Phase 8 cleanup note:** no dedicated `created_*_ids` fixture is used
  for generated `medication_schedule`/`medication_doses` rows — both
  tables cascade away via existing `ON DELETE CASCADE` constraints
  (`001_initial_schema.sql`) when a test's `created_patient_ids` cleanup
  deletes the patient (cascading through medications).

## Repository Convention

The implementation is the source of truth.

If PROJECT_PHASES.md or CHANGELOG.md differ from the implementation,
the implementation takes precedence until the documentation is updated.
