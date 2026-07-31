# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

### Added

- Initial project structure
- Project specification
- SQL schema
- Development workflow
- Claude project instructions

- **Phase 1 — Database:**
  - Seed data migration (`002_seed_data.sql`): 12 curated reference drugs,
    7 interaction rules, 13 ADR rules, sourced from established FDA label
    facts.
  - SQLAlchemy async engine/session setup (`app/db/session.py`).
  - Environment-based configuration via `pydantic-settings` (`app/core/config.py`).
  - SQLAlchemy ORM models mirroring the frozen schema 1:1 (`app/db/models.py`).
  - Database integration tests (`tests/test_database.py`): connectivity,
    seed data integrity, FK cascade behavior, enum defaults.

- **Phase 2 — Authentication:**
  - Supabase Auth proxy endpoints: `POST /auth/signup`, `POST /auth/login`
    (`app/api/v1/auth.py`), forwarding credentials to Supabase Auth's REST
    API and returning the session it issues.
  - JWT verification utility and `get_current_user` FastAPI dependency for
    protected routes (`app/core/security.py`), validating Supabase-issued
    HS256 access tokens against the shared JWT secret.
  - Protected route example: `GET /auth/me`, proving the JWT dependency
    end-to-end ahead of Phase 3's protected resource routes.
  - Sanitized error handling: raw Supabase error payloads are never
    forwarded to clients; mapped to our own status codes/messages
    (`_map_supabase_error`).
  - Config addition: `http_timeout_seconds` for outbound calls to Supabase
    Auth (`app/core/config.py`).
  - Pydantic schemas for signup/login/auth responses (`app/schemas/auth.py`).
  - `app/main.py` created as the FastAPI entrypoint, registering the auth
    router.
  - Unit tests (`tests/test_security.py`): JWT decode/verify, including
    expired-token and wrong-secret cases.
  - API tests (`tests/test_auth_api.py`): signup, login, and `/auth/me`,
    with outbound Supabase calls mocked.

- **Phase 3 — Patient CRUD:**
  - Patient endpoints (`app/api/v1/patients.py`): `GET /patients`,
    `POST /patients`, `GET /patients/{id}`, `PUT /patients/{id}`.
  - Ownership enforcement: every patient lookup is scoped to
    `(id, user_id)` together, so a patient owned by another user returns
    404 rather than 403 (existence is never confirmed to a non-owner).
  - `PUT /patients/{id}` implements partial-update semantics
    (`exclude_unset=True`) rather than full-replace, since the frozen
    spec declares the route without specifying replace-vs-partial
    behavior.
  - `DELETE /patients/{id}` intentionally **not** implemented — confirmed
    not part of the frozen API contract (spec section 7); the corresponding
    `PROJECT_PHASES.md` subtask reflects this decision, not a built endpoint.
  - Pydantic schemas (`app/schemas/patient.py`), deliberately omitting
    `user_id` from request bodies so it can never be client-supplied.
  - `app/main.py` updated to additionally register the patients router.
  - Integration tests (`tests/test_patients_api.py`): create/get/list/update,
    404-on-nonexistent, cross-user isolation, and confirmation that
    `DELETE /patients/{id}` returns 405 (no such route).
  - Shared test fixtures (`tests/conftest.py`): `existing_auth_user_id`
    (pulls a real `auth.users` row for FK-valid test patients) and
    `created_patient_ids` with autouse cleanup.

- **Phase 4 — Medication CRUD:**
  - Medication endpoints (`app/api/v1/medications.py`):
    `GET /patients/{id}/medications`, `POST /patients/{id}/medications`,
    `PUT /medications/{id}`, `DELETE /medications/{id}`.
  - Ownership enforcement via the parent patient: medication routes scoped
    through `patients.user_id`, returning 404 for non-owned or nonexistent
    patients/medications.
  - `drug_id` validated against `reference_drugs` on create/update (404 if
    the id doesn't exist), so clients must select from the curated
    reference list rather than free-typing an id.
  - `condition_id`, if provided, validated as belonging to the same
    patient the medication is attached to (400 otherwise) — a
    data-integrity guard, independent of Phase 5's Condition CRUD.
  - `PUT /medications/{id}` implements partial-update semantics, matching
    the precedent set in Phase 3's `PUT /patients/{id}`.
  - `DELETE /medications/{id}` implemented as a genuine hard delete (in
    scope per the frozen API contract, unlike patients); dependent
    `medication_schedule`/`medication_doses` rows cascade away via the
    existing `ON DELETE CASCADE` constraints from `001_initial_schema.sql`.
  - Pydantic schemas (`app/schemas/medication.py`), with `status`
    constrained via `Literal` to the same five values as the database's
    `medication_status_enum`.
  - `app/main.py` updated to additionally register the medications router.
  - Integration tests (`tests/test_medications_api.py`): create/list,
    invalid-`drug_id` (404), nonexistent-patient (404), mismatched
    `condition_id` across patients (400), partial update, cross-user
    isolation, and delete.
  - Shared test fixtures (`tests/conftest.py`): `existing_drug_id` (pulls a
    real seeded `reference_drugs` row) and `created_medication_ids` with
    autouse cleanup.

- **Phase 5 — Conditions:**
  - Condition endpoints (`app/api/v1/conditions.py`):
    `POST /patients/{id}/conditions`, `PUT /conditions/{id}` — the only two
    routes in the frozen API contract (spec section 7) for conditions; no
    `GET` or `DELETE` route was added, confirmed with the project owner
    during Phase 5 planning.
  - Ownership enforcement via the parent patient, mirroring the pattern in
    `patients.py`/`medications.py`: a condition or patient not owned by
    the caller (or not existing) returns 404, never 403.
  - `PUT /conditions/{id}` implements partial-update semantics
    (`exclude_unset=True`), matching the precedent set in Phase 3/Phase 4.
    No status-transition state machine is enforced — `status` may be set
    to any of the five enum values regardless of current value, and
    `resolved_date` is not auto-populated when status becomes `resolved`;
    it remains an explicit client-supplied field, since the frozen spec
    does not define a condition lifecycle state machine.
  - Pydantic schemas (`app/schemas/condition.py`), with `status` and
    `reason` constrained via `Literal` to the same values as the
    database's `condition_status_enum` / `condition_reason_enum`, and
    deliberately omitting `patient_id` from request bodies (always taken
    from the path parameter).
  - `app/main.py` updated to additionally register the conditions router.
  - Integration tests (`tests/test_conditions_api.py`): condition creation
    with applied defaults (verified via direct DB query, since there is no
    `GET` route), nonexistent-patient (404), cross-user isolation on both
    create and update, partial update preserving untouched fields,
    nonexistent-condition update (404), and an end-to-end re-verification
    of Phase 4's `condition_id` cross-patient validation now using a real
    condition created through this phase's own endpoint (rather than a
    directly-inserted row, as Phase 4 had to do before Condition CRUD
    existed).
  - Shared test fixtures (`tests/conftest.py`): `created_condition_ids`
    with autouse cleanup, following the same explicit-tracking pattern as
    `created_patient_ids`/`created_medication_ids`.

- **Phase 6 — Symptoms:**
  - Symptom endpoints (`app/api/v1/symptoms.py`):
    `POST /patients/{id}/symptoms`, `GET /patients/{id}/symptoms` — the
    only two routes in the frozen API contract (spec section 7) for
    symptoms; no `PUT` or `DELETE` route was added.
  - Ownership enforcement via the parent patient, mirroring the pattern in
    `conditions.py`/`medications.py`: a symptom or patient not owned by
    the caller (or not existing) returns 404, never 403.
  - Optional `condition_id`/`medication_id` links, if provided, are
    validated as belonging to the same patient the symptom is logged for
    (400 on mismatch) — the same data-integrity guard pattern used for
    `medications.condition_id` in Phase 4.
  - `severity` defaults to `mild`, matching the DB's `severity_level`
    enum default, and is constrained via `Literal` to the same three
    values (`mild`/`moderate`/`severe`).
  - `onset_date` defaults to `date.today()` when omitted by the client,
    applied in the application layer rather than relied upon as a
    DB-side default reaching the ORM — consistent with how other
    date/time defaults are handled throughout the codebase.
  - `GET /patients/{id}/symptoms` returns results ordered chronologically
    by `onset_date` (then `created_at` as a same-day tiebreaker).
  - Pydantic schemas (`app/schemas/symptom.py`), deliberately omitting
    `patient_id` from request bodies (always taken from the path
    parameter), matching the precedent set in `schemas/condition.py`.
  - `app/main.py` updated to additionally register the symptoms router.
  - Integration tests (`tests/test_symptoms_api.py`): default-application
    on create, explicit-field overrides, condition-linked and
    medication-linked symptom creation, mismatched `condition_id`/
    `medication_id` across patients (400), nonexistent-patient (404),
    cross-user isolation on both create and list, list scoping and
    chronological ordering, and confirmation that `PUT`/`DELETE`
    `/symptoms/{id}` return 405 (no such routes).
  - Shared test fixtures (`tests/conftest.py`): `created_symptom_ids`
    with autouse cleanup, following the same explicit-tracking pattern as
    `created_patient_ids`/`created_medication_ids`/`created_condition_ids`.

- **Phase 7 — Timeline:**
  - Timeline endpoint (`app/api/v1/timeline.py`):
    `GET /patients/{id}/timeline` — the only route in the frozen API
    contract (spec section 7) for the timeline; read-only, since events
    are never created directly by a client.
  - New reusable event writer (`app/services/timeline_writer.py`):
    `log_timeline_event()` adds a `timeline_events` row to the current DB
    session without committing, so every event is persisted in the same
    transaction as the entity write that triggered it (medication insert,
    condition update, symptom insert).
  - Automatic event logging wired into prior phases' write paths:
    - `medications.py`: `medication_started` on creation;
      `medication_discontinued` only on a genuine status transition
      *into* `discontinued` (not on repeated PUTs, not on hard `DELETE`
      — the spec's event_type list has no "deleted" value).
    - `conditions.py`: `condition_status_changed` only when `status`
      actually changes value (a PUT resending the current status logs
      nothing).
    - `symptoms.py`: `symptom_reported` on every symptom creation.
    - `dose_taken`/`dose_missed`/`dose_skipped` (Phase 9) and
      `analysis_run` (Phase 12+) are intentionally not wired yet, since
      neither dose marking nor analysis runs exist in the codebase yet.
  - Ownership enforcement via the parent patient, mirroring
    `conditions.py`/`medications.py`/`symptoms.py`: a patient not owned
    by the caller (or not existing) returns 404, never 403.
  - `GET /patients/{id}/timeline` returns events ordered `event_time`
    descending (most recent first), matching the existing
    `idx_timeline_patient(patient_id, event_time desc)` index from
    `001_initial_schema.sql`.
  - Pydantic response schema (`app/schemas/timeline.py`) — read-only, no
    Create/Update schema, since timeline events have no client-facing
    write shape.
  - `app/main.py` updated to additionally register the timeline router.
  - Integration tests (`tests/test_timeline_api.py`): automatic logging
    verification for medication start/discontinue (including no-duplicate-
    event and no-event-on-delete checks), condition status change
    (including no-event-when-status-unchanged), symptom reporting,
    chronological ordering, patient scoping, cross-user isolation,
    nonexistent-patient 404, and confirmation that
    `POST`/`PUT`/`DELETE /patients/{id}/timeline` all return 405 (no such
    routes).
  - No new test fixture needed for cleanup — `timeline_events.patient_id`
    already has `ON DELETE CASCADE`, so rows are removed automatically
    when a test's `created_patient_ids` cleanup deletes the patient.

- **Phase 8 — Dose Scheduling:**
  - Schedule endpoints (`app/api/v1/schedule.py`):
    `POST /medications/{id}/schedule`, `GET /patients/{id}/doses/upcoming`.
    `POST /doses/{id}/mark` is intentionally **not** implemented here — it
    is explicitly scoped to Phase 9 (Adherence) per spec section 10.
  - `POST /medications/{id}/schedule` generates the full dose schedule for
    a medication in one call, requiring `duration_days` and **at least
    one** of (`times_per_day`, `interval_hours`) to already be set (400
    otherwise). Two supported input shapes:
    - `times_per_day` set: dose count is `times_per_day * duration_days`;
      spacing uses `interval_hours` if also set, else an even daily spread
      (`24 / times_per_day`). *(Original Phase 8 behavior.)*
    - `times_per_day` absent, `interval_hours` set: spacing uses
      `interval_hours` directly; dose count is
      `floor(duration_days * 24 / interval_hours)` (minimum 1) — as many
      evenly-spaced doses as fit within the duration window. *(Refinement,
      added after initial Phase 8 completion per project owner request.)*
  - The first dose in both shapes anchors at 08:00 UTC on `start_date`
    (`DEFAULT_FIRST_DOSE_TIME`), a documented convention rather than a
    silent guess, since `Medication.start_date` is a date, not a datetime.
  - Regenerating a schedule for a medication that already has one is
    rejected with 409 — regeneration/rescheduling is not defined by the
    spec.
  - Generated dose count is capped at `MAX_GENERATED_DOSES` (3650) as a
    defensive guard against pathological inputs (e.g. very small
    `interval_hours` over a long `duration_days`); not a spec requirement,
    purely a safety guard.
  - `GET /patients/{id}/doses/upcoming` returns only future
    (`scheduled_time >= now`), unmarked (`status IS NULL`) doses belonging
    to medications with `status == "active"`, ordered ascending by
    `scheduled_time`, and enriched with `drug_name`/`dose` via a join so
    the response is directly usable by a "take your medication" UI
    without a client-side re-lookup.
  - Ownership enforcement via the parent patient/medication, mirroring
    `conditions.py`/`medications.py`/`symptoms.py`/`timeline.py`: a
    medication or patient not owned by the caller (or not existing)
    returns 404, never 403.
  - Pydantic schemas (`app/schemas/schedule.py`): `MedicationDoseResponse`
    and `UpcomingDoseResponse` — response-only, since both routes generate
    or derive their output rather than accepting a client-supplied body.
  - `app/main.py` updated to additionally register the schedule router.
  - Integration tests (`tests/test_schedule_api.py`): expected dose count
    and even-spacing for the `times_per_day` shape, explicit
    `interval_hours` override, missing `times_per_day`/`duration_days`
    (400), duplicate schedule generation (409), exceeding
    `MAX_GENERATED_DOSES` (400), nonexistent/cross-user medication (404),
    upcoming-doses ordering/enrichment, exclusion of inactive medications,
    patient scoping, cross-user isolation, and confirmation that
    `POST /doses/{id}/mark` is unregistered (404, not 405). Refinement
    coverage: `interval_hours`-only dose count and spacing, flooring of a
    partial final dose (non-integer `duration_days * 24 / interval_hours`),
    the new "at least one of `times_per_day`/`interval_hours`" 400 error,
    and `MAX_GENERATED_DOSES` enforcement in the `interval_hours`-only
    shape.
  - No dedicated cleanup fixture needed for generated
    `medication_schedule`/`medication_doses` rows — both cascade away via
    existing `ON DELETE CASCADE` constraints (`001_initial_schema.sql`)
    when a test's `created_patient_ids` cleanup deletes the patient.

### Changed

None

### Fixed

None
