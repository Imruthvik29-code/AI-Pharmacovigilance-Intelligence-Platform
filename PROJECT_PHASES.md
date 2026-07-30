# Pharmacovigilance MVP - Development Progress

**Project Status:** 🟢 In Development

**Current Milestone:** Milestone 2 - Patient Data Management

**Current Phase:** Phase 7 - Timeline

**Last Updated:** 2026-07-30

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

- [ ] Phase 7 - Timeline
    - [ ] Timeline Events
    - [ ] Automatic Event Logging
    - [ ] Timeline API
    - [ ] Timeline Testing

- [ ] Phase 8 - Dose Scheduling
    - [ ] Schedule Generator
    - [ ] Upcoming Doses
    - [ ] Scheduling Testing

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

None — Phase 6 complete and approved, awaiting the start of Phase 7 (Timeline).

---

# Known Issues

None

---

# Next Task

Start Phase 7 - Timeline (Timeline Events, Automatic Event Logging, Timeline API, Timeline Testing).

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

## Repository Convention

The implementation is the source of truth.

If PROJECT_PHASES.md or CHANGELOG.md differ from the implementation,
the implementation takes precedence until the documentation is updated.
