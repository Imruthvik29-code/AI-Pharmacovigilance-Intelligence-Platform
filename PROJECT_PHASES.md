# Pharmacovigilance MVP - Development Progress

**Project Status:** 🟢 In Development

**Current Milestone:** Milestone 3 - Medication Intelligence

**Current Phase:** Phase 11 - ADR Engine

**Last Updated:** 2026-08-01

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

## 🟢 Milestone 2 - Patient Data Management

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

- [x] Phase 9 - Adherence
    - [x] Taken
    - [x] Missed
    - [x] Skipped
    - [x] Adherence Statistics *(see note below — deferred, out of scope)*
    - [x] Adherence Testing

---

## 🟡 Milestone 3 - Medication Intelligence

- [x] Phase 10 - Drug Interaction Engine
    - [x] Interaction Detection
    - [x] Severity Calculation *(see note below — scope confirmed)*
    - [x] Interaction Testing

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

None — Phase 10 complete and approved, awaiting the start of Phase 11 (ADR Engine).

---

# Known Issues

None

---

# Next Task

Start Phase 11 - ADR Engine (ADR Detection, Severity Matching, ADR Testing).

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
  `event_type` values documented in spec section 5, `dose_taken`/
  `dose_missed`/`dose_skipped` and `analysis_run` were, at the time of
  Phase 7, deferred to Phase 9 (Adherence) and Phase 12+ (Safety Score
  Engine) respectively. `dose_taken`/`dose_missed`/`dose_skipped` are now
  wired up as of Phase 9; `analysis_run` remains deferred to Phase 12+.
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
- **Phase 8 scope note (superseded by Phase 9):** at the time of Phase 8,
  `POST /doses/{id}/mark` was listed in the frozen spec's API contract
  but explicitly out of scope, with the route unregistered (404, not
  405). This is no longer the current state — the route is now
  implemented as of Phase 9. Retained here only for historical accuracy.
- **Phase 8 "Upcoming Doses" clarification:**
  `GET /patients/{id}/doses/upcoming` returns only future
  (`scheduled_time >= now`), unmarked (`status IS NULL`) doses belonging
  to medications with `status == "active"` — doses for
  paused/discontinued/completed medications are excluded. Results are
  enriched with `drug_name`/`dose` via a join, ordered ascending by
  `scheduled_time`. As of Phase 9, this route also runs the missed-dose
  sweep before querying.
- **Phase 8 cleanup note:** no dedicated `created_*_ids` fixture is used
  for generated `medication_schedule`/`medication_doses` rows — both
  tables cascade away via existing `ON DELETE CASCADE` constraints
  (`001_initial_schema.sql`) when a test's `created_patient_ids` cleanup
  deletes the patient (cascading through medications).
- **Phase 9 — `POST /doses/{id}/mark` implementation note:** a dose's
  `status` is set exactly once. If the dose is already marked (whether by
  a prior explicit mark or by the automatic sweep), the request is
  rejected with 409 — the spec defines no "correct a mark" flow, so
  marking is treated as immutable once set, consistent with the
  "schedule already exists" 409 precedent from Phase 8. `actual_time`
  defaults to `now()` when marking "taken" if omitted, and stays null for
  "missed"/"skipped".
- **Phase 9 — missed-dose background check note:** the tech stack (spec
  section 4) has no job scheduler/cron component, so the spec's
  "missed-dose background check" is implemented as a **lazy,
  query-time sweep** (`_sweep_missed_doses` in `app/api/v1/schedule.py`)
  rather than a true background job. It flips any dose belonging to the
  relevant patient whose `scheduled_time` has passed and is still
  unmarked to `missed`, logging a `dose_missed` timeline event per
  affected dose. It runs (and commits) at the start of both
  `GET /patients/{id}/doses/upcoming` and `POST /doses/{id}/mark`. The
  sweep applies regardless of the parent medication's status. This
  design was confirmed with the project owner during Phase 9 planning.
- **Phase 9 — Adherence Statistics clarification:** adherence statistics
  are explicitly deferred — confirmed with the project owner during
  Phase 9 planning as out of scope, since it is not part of the frozen
  section 7 API contract; will feed the Safety Score Engine in Phase
  12+.
- **Phase 9 — Automatic Event Logging update:** `dose_taken`,
  `dose_missed`, and `dose_skipped` timeline events (deferred since
  Phase 7) are now wired up via `POST /doses/{id}/mark` and the missed-
  dose sweep. `analysis_run` remains deferred to Phase 12+.
- **Phase 9 cleanup note:** no dedicated `created_*_ids` fixture is
  needed for dose-mark timeline events or sweep-generated status
  changes — they cascade away via `ON DELETE CASCADE` when a test's
  `created_patient_ids` cleanup deletes the patient.
- **Phase 10 architecture note:** a new `app/analysis/` package was
  created (`drug_interaction_engine.py`), per the spec's section 6
  folder structure. This engine is a pure, internal, deterministic
  service — it is **not** exposed via any HTTP route in this phase.
  `api/v1/analysis.py` and the `POST /patients/{id}/analyze` /
  `GET /patients/{id}/analysis` routes are wired only in Phase 14
  (LangGraph), which will call into this engine (and the ADR/adherence/
  safety-score engines from later phases) as analysis nodes. Phase 10's
  tests therefore call the engine directly against a live DB session
  rather than through any endpoint.
- **Phase 10 scope note (confirmed during planning):** only medications
  with `status == "active"` count as "the patient's drugs" for
  interaction detection — a paused/completed/discontinued medication is
  not currently being taken, so it cannot be interacting with anything
  right now. This mirrors the same `status == "active"` filter already
  used by `GET /patients/{id}/doses/upcoming` (Phase 8).
- **Phase 10 "Severity Calculation" clarification (confirmed during
  planning):** each finding simply surfaces its matched `interaction_rules`
  row's own `severity` value as-is — no new severity is computed or
  invented. A small `highest_severity()` convenience utility reports the
  single worst severity across a set of findings; it is explicitly **not**
  the Safety Score Engine (Phase 12), which will combine this with ADR
  and adherence findings into a composite score/risk_level.
- **Phase 10 direction-independence note:** `interaction_rules` rows
  store a fixed `drug_a_id`/`drug_b_id` direction, but detection matches
  a rule whenever both ids are present among the patient's active drug
  ids (pure set membership) — clinically, an interaction is symmetric
  regardless of which drug is stored as "a" vs "b," and regardless of
  the order the patient's medications were created in. Verified by a
  dedicated test using the Omeprazole/Warfarin rule (stored in the
  opposite order from the test's medication-creation order).

## Repository Convention

The implementation is the source of truth.

If PROJECT_PHASES.md or CHANGELOG.md differ from the implementation,
the implementation takes precedence until the documentation is updated.
