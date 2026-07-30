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

### Changed

None

### Fixed

None
