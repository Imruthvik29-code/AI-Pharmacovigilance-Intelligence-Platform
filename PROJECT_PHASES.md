# Pharmacovigilance MVP - Development Progress

**Project Status:** 🟢 In Development

**Current Milestone:** Milestone 3 - Medication Intelligence

**Current Phase:** Phase 13 - Evidence Retrieval

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
    - [x] Adherence Statistics *(see note below — deferred, not in frozen API contract)*
    - [x] Adherence Testing

---

## 🟢 Milestone 3 - Medication Intelligence

- [x] Phase 10 - Drug Interaction Engine
    - [x] Interaction Detection
    - [x] Severity Calculation *(see note below — scope confirmed)*
    - [x] Interaction Testing

- [x] Phase 11 - ADR Engine
    - [x] ADR Detection
    - [x] Severity Matching *(see note below — scope confirmed)*
    - [x] ADR Testing

- [x] Phase 12 - Safety Score Engine
    - [x] Score Calculation
    - [x] Risk Level
    - [x] Safety Score Testing

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

None — Phase 12 complete and approved, awaiting the start of Phase 13 (Evidence Retrieval).

---

# Known Issues

None

---

# Next Task

Start Phase 13 - Evidence Retrieval (Medical Knowledge Retrieval, Patient History Retrieval, Retrieval Testing).

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
  defaults are handled throughout this codebase.
- **Phase 7 scope note:** per the frozen spec (section 7), the timeline
  only exposes `GET /patients/{id}/timeline` — read-only, no
  POST/PUT/DELETE, since events are never created directly by a client.
  Confirmed and implemented strictly as written
  (`test_no_post_put_delete_endpoints_exist` asserts 405 on all three).
- **Phase 7 "Automatic Event Logging" clarification:** of the eight
  `event_type` values documented in spec section 5, all eight are wired
  up as of Phase 9: `medication_started`, `medication_discontinued`
  (Phase 4/7), `condition_status_changed` (Phase 5/7), `symptom_reported`
  (Phase 6/7), and `dose_taken`/`dose_missed`/`dose_skipped` (Phase 9,
  including auto-detected misses from the lazy sweep). `analysis_run`
  remains deferred to Phase 14 (LangGraph's Persist Node), since no
  analysis run is persisted to `analysis_runs` yet even though Phase 12
  now computes a score in-memory.
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
- **Phase 8 "Upcoming Doses" clarification:**
  `GET /patients/{id}/doses/upcoming` returns only future
  (`scheduled_time >= now`), unmarked (`status IS NULL`) doses belonging
  to medications with `status == "active"` — doses for
  paused/discontinued/completed medications are excluded. Results are
  enriched with `drug_name`/`dose` via a join, ordered ascending by
  `scheduled_time`. As of Phase 9, this route also runs the missed-dose
  sweep before querying (see Phase 9 note below) — this is a documented
  write side-effect added on top of the original Phase 8 behavior, not a
  change to the response contract.
- **Phase 8 cleanup note:** no dedicated `created_*_ids` fixture is used
  for generated `medication_schedule`/`medication_doses` rows — both
  tables cascade away via existing `ON DELETE CASCADE` constraints
  (`001_initial_schema.sql`) when a test's `created_patient_ids` cleanup
  deletes the patient (cascading through medications).
- **Phase 9 "Taken/Missed/Skipped" implementation:** `POST /doses/{id}/mark`
  (frozen spec section 7) sets a dose's status exactly once via
  `app/api/v1/schedule.py`'s `mark_dose`. A dose already marked (whether
  by a prior explicit mark or by the automatic sweep) is rejected with
  409 — there is no spec-defined "correct a mark" flow, matching the
  "schedule already exists" 409 precedent from Phase 8. `actual_time`
  defaults to `now()` when marking "taken" if omitted by the client, and
  is left null for "missed"/"skipped". Each mark logs the corresponding
  `dose_taken`/`dose_missed`/`dose_skipped` timeline event via the
  existing `timeline_writer.py` helper.
- **Phase 9 "missed-dose background check" clarification:** the tech
  stack (spec section 4/section 2 functional requirements) has no job
  scheduler/cron component, so this is implemented as a **lazy,
  query-time sweep** (`_sweep_missed_doses` in `app/api/v1/schedule.py`)
  rather than a true background job. It flips any dose belonging to the
  relevant patient whose `scheduled_time` has already passed and is
  still unmarked to `missed`, logging a `dose_missed` timeline event
  (with `payload.auto_detected = true`) per affected dose. It runs (and
  commits) at the top of both `GET /patients/{id}/doses/upcoming` and
  `POST /doses/{id}/mark`, so any read or write touching a patient's
  doses first brings overdue doses up to date. This was confirmed with
  the project owner as an acceptable substitute for a true background
  job, given the frozen tech stack has no scheduler.
- **Phase 9 "Adherence Statistics" clarification:** adherence statistics
  (e.g. taken/missed/skipped counts, an adherence percentage) were
  explicitly out of scope for Phase 9's own API surface — not part of
  the frozen section 7 API contract. This aggregation is now built as of
  Phase 12's `adherence_engine.py`, but purely as an internal input to
  the Safety Score Engine, not as a standalone endpoint.
- **Phase 9 note:** dose marking is intentionally immutable once set —
  there is no "unmark" or "correct a mark" endpoint, consistent with how
  Phase 8 treats schedule generation (409 on regeneration) rather than
  allowing silent overwrites of clinically meaningful records.
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
  the Safety Score Engine (Phase 12), which combines this with ADR and
  adherence findings into a composite score/risk_level.
- **Phase 10 direction-independence note:** `interaction_rules` rows
  store a fixed `drug_a_id`/`drug_b_id` direction, but detection matches
  a rule whenever both ids are present among the patient's active drug
  ids (pure set membership) — clinically, an interaction is symmetric
  regardless of which drug is stored as "a" vs "b," and regardless of
  the order the patient's medications were created in. Verified by a
  dedicated test using the Omeprazole/Warfarin rule (stored in the
  opposite order from the test's medication-creation order).
- **Phase 11 architecture note:** a new module `app/analysis/adr_engine.py`
  was added alongside Phase 10's `drug_interaction_engine.py`, in the
  same `app/analysis/` package created in Phase 10 (no new package
  needed). Like the interaction engine, this is a pure, internal,
  deterministic service — **not** exposed via any HTTP route in this
  phase; it will be wired in as another analysis node in Phase 14
  (LangGraph). Phase 11's tests call the engine directly against a live
  DB session, mirroring Phase 10's testing approach exactly.
- **Phase 11 scope note (confirmed during planning, consistent with
  Phase 10):** only medications with `status == "active"` count as "the
  patient's drugs" for ADR detection — the same reasoning as Phase 10's
  interaction-detection scope decision.
- **Phase 11 "Severity Matching" clarification (confirmed during
  planning, mirrors Phase 10):** each finding surfaces its matched
  `adr_rules` row's own `severity` (and `frequency_class`) as-is — no new
  severity is computed or invented. A `highest_severity()` convenience
  utility (re-implemented locally, not shared with the interaction
  engine, per this codebase's per-module helper convention) reports the
  single worst severity across a set of findings; it is explicitly **not**
  the Safety Score Engine (Phase 12).
- **Phase 11 "multiple ADRs per drug" note:** unlike drug interactions
  (which require a *pair* of active drugs to match a rule), an ADR is a
  property of a single drug, so a single active medication can surface
  more than one finding if it has multiple seeded `adr_rules` rows (e.g.
  Lisinopril → "Dry cough" *and* "Hyperkalemia", both returned as
  separate findings). Detection is therefore a simple
  `adr_rules.drug_id IN (patient's active drug ids)` membership query,
  with no directionality concerns (unlike `interaction_rules`'
  drug_a/drug_b pairing).
- **Phase 12 spec-gap note (raised and resolved during planning):** the
  frozen spec's folder structure (section 6) lists `adherence_engine.py`
  alongside `safety_score_engine.py` under `analysis/`, but
  PROJECT_PHASES.md's Milestone 3 had no standalone "Adherence Engine"
  phase. Resolved by treating Phase 12 as necessarily including a small
  `adherence_engine.py` (confirmed with the project owner) — since spec
  section 5/8/10 all describe the Safety Score Engine as merging
  interaction + ADR + **adherence** findings, Phase 12 could not be
  completed without some adherence analysis feeding it. `timeline_engine.py`
  (also listed in section 6) was deliberately **not** built in this
  phase, since nothing in Phase 12's description requires timeline
  findings, and its need (if any) is deferred until Phase 13/15 make that
  clear.
- **Phase 12 "separation of measurement and interpretation" note
  (confirmed during planning):** `adherence_engine.py` returns **only**
  raw counts/rates (`taken`, `missed`, `skipped`, `due`,
  `adherence_rate`) via `analyze_adherence()` — it performs no severity
  classification. Unlike `interaction_rules`/`adr_rules`, there is no
  authoritative "adherence severity" reference table in the schema, so
  classifying a rate as mild/moderate/severe is a scoring *policy*
  choice, not a lookup — and that responsibility belongs entirely in
  `safety_score_engine.py`. All thresholds, penalty weights, and
  risk-level cutoffs are consolidated there as named, individually
  commented module-level constants (`BASE_SCORE`, `MIN_SCORE`,
  `INTERACTION_PENALTY_POINTS`, `ADR_PENALTY_POINTS`,
  `ADHERENCE_ADEQUATE_THRESHOLD`/`ADHERENCE_MODERATE_THRESHOLD`/
  `ADHERENCE_SEVERE_THRESHOLD`, `ADHERENCE_PENALTY_POINTS`,
  `RISK_LEVEL_LOW_THRESHOLD`/`RISK_LEVEL_MODERATE_THRESHOLD`), each
  explicitly documented as an implementation default rather than a
  clinical guideline or spec requirement — only the 80% adherence cutoff
  has any cited external basis (a common rule-of-thumb in
  medication-adherence outcomes research); the rest were confirmed with
  the project owner as a reasonable starting point pending future
  clinical review.
- **Phase 12 "due dose" note:** `analyze_adherence()` computes "due" and
  "missed" independently of whether Phase 9's lazy missed-dose sweep has
  run for a given patient — an overdue, unmarked dose counts as missed
  for measurement purposes regardless of its persisted `status` value.
  This avoids a correctness bug where adherence measurements would
  silently depend on incidental API call ordering (whether
  `GET /patients/{id}/doses/upcoming` or `POST /doses/{id}/mark` happened
  to run recently). It performs no writes and does not duplicate or
  invoke the Phase 9 sweep — the persisted `medication_doses.status`
  values and the sweep's own behavior are unchanged.
- **Phase 12 "audit trail" note (confirmed during planning):**
  `calculate_safety_score()` returns a `SafetyScoreResult` exposing not
  just `safety_score`/`risk_level` but also `starting_score`,
  `total_points_deducted`, all three raw finding lists, and a full
  `penalties: list[PenaltyEntry]` breakdown — each entry carrying its
  category, a human-readable description, assigned severity, point cost,
  and a direct reference to the originating finding object. This was a
  deliberate requirement so a later phase (Evidence Retrieval, the LLM
  explanation node, or a report view) can explain exactly how a score
  was produced without recomputing anything.
- **Phase 12 scope note:** like Phases 10/11, `safety_score_engine.py`
  is **not** exposed via any HTTP route in this phase, and nothing here
  is persisted to `analysis_runs` yet — both happen in Phase 14
  (LangGraph)'s Persist Node.

## Repository Convention

The implementation is the source of truth.

If PROJECT_PHASES.md or CHANGELOG.md differ from the implementation,
the implementation takes precedence until the documentation is updated.
