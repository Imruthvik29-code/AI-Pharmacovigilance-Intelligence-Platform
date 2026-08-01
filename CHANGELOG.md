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
      `analysis_run` (Phase 14) are intentionally not wired yet, since
      neither dose marking nor analysis runs exist yet at this point.
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

- **Phase 9 — Adherence:**
  - New endpoint (`app/api/v1/schedule.py`): `POST /doses/{id}/mark` —
    the third and final route in the frozen section 7 API contract for
    dose scheduling/adherence, completing the surface `schedule.py`
    started in Phase 8.
  - `mark_dose` sets a dose's `status` to `taken`, `missed`, or `skipped`
    exactly once. A dose that is already marked (via a prior explicit
    call or via the automatic sweep, see below) is rejected with 409 —
    there is no spec-defined "correct a mark" flow, mirroring the
    "schedule already exists" 409 precedent from Phase 8's
    `POST /medications/{id}/schedule`.
  - `actual_time` defaults to `now()` when marking `taken` if the client
    omits it, and is left `null` for `missed`/`skipped` (there is no
    meaningful "actual" time for a dose that was not taken).
  - New reusable helper `_sweep_missed_doses()` (`app/api/v1/schedule.py`)
    implements the spec's "missed-dose background check" (section 10) as
    a **lazy, query-time sweep** rather than a true scheduled job, since
    the frozen tech stack (spec section 4) has no job scheduler/cron
    component. It flips any unmarked dose whose `scheduled_time` has
    already passed to `missed` and logs a `dose_missed` timeline event
    (`payload.auto_detected = true`) per affected dose. It runs at the
    top of both `GET /patients/{id}/doses/upcoming` and
    `POST /doses/{id}/mark`, committing alongside whatever else that
    request does, so any dose-related read or write for a patient first
    brings their overdue doses up to date.
  - Automatic event logging completes the canonical `event_type` list
    from spec section 5: `dose_taken`, `dose_missed`, and `dose_skipped`
    are now logged via the existing `app/services/timeline_writer.py`
    helper (unchanged from Phase 7), in the same transaction as the dose
    update. `dose_missed` events distinguish explicit marks from
    sweep-detected misses via `payload.auto_detected`.
  - Ownership enforcement for the new route follows the same pattern as
    prior phases: a dose is resolved through its medication's parent
    patient, and a dose not owned by the caller (or not existing) returns
    404, never 403.
  - New Pydantic request schema (`app/schemas/schedule.py`):
    `MedicationDoseMarkRequest` (`status`, optional `actual_time`).
    `status` is constrained via `Literal` to the same three values as the
    database's `dose_status_enum`, matching the precedent set for other
    enum-backed fields throughout the codebase.
  - Adherence statistics (taken/missed/skipped counts, adherence
    percentage) are explicitly **out of scope** for this phase — not
    part of the frozen section 7 API contract; that aggregation is
    deferred to feed the Safety Score Engine (Phase 12+) instead of being
    exposed as a standalone endpoint now.
  - `app/main.py` unchanged — `POST /doses/{id}/mark` is registered on
    the existing `schedule.router`, which was already included in Phase 8.
  - Integration tests (`tests/test_schedule_api.py`, Phase 9 section):
    marking `taken` (default and explicit `actual_time`), marking
    `missed`/`skipped` (confirming `actual_time` stays `null`),
    corresponding timeline event logging for all three statuses
    (parametrized), double-mark 409, nonexistent/cross-user dose 404,
    invalid `status` value 422, the lazy sweep triggered via
    `GET /patients/{id}/doses/upcoming` (including timeline verification
    and confirming subsequent explicit marks on swept doses 409 as
    "already marked as 'missed'"), the sweep triggered directly via
    `POST /doses/{id}/mark` on an overdue dose without a prior
    `GET .../upcoming` call, and confirmation that a genuinely future
    dose remains unmarked and markable after a sweep-triggering call.
    The Phase 8 placeholder test asserting `POST /doses/{id}/mark` was
    unregistered has been removed and replaced with this real coverage.
  - No dedicated cleanup fixture needed — dose rows continue to cascade
    away via the existing `ON DELETE CASCADE` constraints from
    `001_initial_schema.sql`, same as Phase 8.

- **Phase 10 — Drug Interaction Engine:**
  - New package `app/analysis/` (per spec section 6's folder structure),
    with `drug_interaction_engine.py`:
    - `detect_drug_interactions(patient_id, db)` — queries the patient's
      distinct `status == "active"` medication drug ids, then matches
      them against `interaction_rules` where both `drug_a_id` and
      `drug_b_id` are present in that active set. This is a pure
      set-membership check, so it is inherently direction-independent
      (does not depend on which of the rule's two drugs the patient's
      medication history matches, or the order medications were
      created in).
    - `highest_severity(findings)` — a small convenience utility
      returning the single most severe result among a list of findings
      (`mild` < `moderate` < `severe`), or `None` for an empty list.
      Explicitly documented as distinct from the Safety Score Engine
      (Phase 12), which computes a composite score/risk_level from
      this plus ADR and adherence findings.
    - `DrugInteractionFinding` — a frozen dataclass carrying the
      matched rule's id, both drug ids/names, severity, mechanism,
      recommendation, and source.
  - Deliberately **not** exposed via any HTTP route in this phase —
    `api/v1/analysis.py` and the `/patients/{id}/analyze` /
    `/patients/{id}/analysis` endpoints are wired only in Phase 14
    (LangGraph), which will call into this engine as an analysis node.
  - Scope decisions confirmed with the project owner during Phase 10
    planning: (1) only `status == "active"` medications count as "the
    patient's drugs" for detection; (2) severity is surfaced per-match
    from the seeded rule as-is, with no new severity computed beyond the
    `highest_severity()` convenience helper.
  - New test file (`tests/test_drug_interaction_engine.py`): calls the
    engine directly against a live DB session (no endpoint exists yet to
    exercise). Covers no-active-medications and single-active-medication
    (both empty), a known severe interaction (Warfarin+Aspirin),
    direction-independence (Omeprazole+Warfarin, created in the reverse
    order from the rule's own storage direction), a true negative
    (Metformin+Levothyroxine, no seeded rule), exclusion of a
    discontinued medication, multiple simultaneous interactions
    (Warfarin+Aspirin+Ibuprofen surfacing two findings), patient
    scoping, and `highest_severity()` in isolation (empty, single,
    mixed-order, tied severities).
  - No dedicated cleanup fixture needed — reuses the existing
    `created_patient_ids` fixture from `conftest.py`; the engine performs
    no writes of its own.

- **Phase 11 — ADR Engine:**
  - New module `app/analysis/adr_engine.py`, added to the existing
    `app/analysis/` package created in Phase 10 (no new package needed):
    - `detect_adrs(patient_id, db)` — queries the patient's distinct
      `status == "active"` medication drug ids, then matches them against
      `adr_rules` on `drug_id` membership. Unlike drug interactions
      (which need a *pair* of active drugs), an ADR is a property of a
      single drug, so a single active medication can surface more than
      one finding if it has multiple seeded ADR rules (e.g. Lisinopril →
      "Dry cough" and "Hyperkalemia," both returned as separate
      findings).
    - `highest_severity(findings)` — a small convenience utility
      returning the single most severe result among a list of findings
      (`mild` < `moderate` < `severe`), or `None` for an empty list.
      Re-implemented locally rather than imported from
      `drug_interaction_engine.py`, matching this codebase's existing
      convention of keeping small per-module helpers private to their
      own file. Explicitly documented as distinct from the Safety Score
      Engine (Phase 12).
    - `ADRFinding` — a frozen dataclass carrying the matched rule's id,
      drug id/name, reaction description, severity, frequency_class, and
      source.
  - Deliberately **not** exposed via any HTTP route in this phase —
    same as Phase 10's `drug_interaction_engine.py`; `api/v1/analysis.py`
    and the `/patients/{id}/analyze` / `/patients/{id}/analysis`
    endpoints are wired only in Phase 14 (LangGraph), which will call
    into this engine as an additional analysis node alongside the drug
    interaction engine.
  - Scope decisions confirmed with the project owner during Phase 11
    planning, mirroring Phase 10 exactly: (1) only `status == "active"`
    medications count as "the patient's drugs" for ADR detection; (2)
    severity (and frequency_class) is surfaced per-match from the seeded
    rule as-is, with no new severity computed beyond the
    `highest_severity()` convenience helper.
  - New test file `tests/test_adr_engine.py`: calls the engine directly
    against a live DB session (no endpoint exists yet to exercise, same
    approach as Phase 10). Covers no-active-medications (empty), a
    single drug with a single seeded ADR rule (Warfarin), a single drug
    with multiple seeded ADR rules returned as separate findings
    (Lisinopril → Dry cough + Hyperkalemia), a drug with no seeded ADR
    rules (Levothyroxine, empty), exclusion of a discontinued medication,
    combined findings across multiple simultaneously active drugs
    (Warfarin + Simvastatin → 3 findings), patient scoping, and
    `highest_severity()` in isolation (empty, single, mixed-order, tied
    severities).
  - No dedicated cleanup fixture needed — reuses the existing
    `created_patient_ids` fixture from `conftest.py`; the engine performs
    no writes of its own.

- **Phase 12 — Safety Score Engine:**
  - New module `app/analysis/adherence_engine.py`, added to the existing
    `app/analysis/` package (no new package needed):
    - `analyze_adherence(patient_id, db)` — returns one `AdherenceFinding`
      (pure counts: `taken`, `missed`, `skipped`, `due`,
      `adherence_rate`) per active medication with at least one due dose.
      Performs **no** severity classification — see design rationale
      below.
    - "Due" and "missed" doses are computed independently of whether
      Phase 9's lazy missed-dose sweep has run for the patient: a due,
      unmarked dose (`status IS NULL`, `scheduled_time <= now`) counts
      toward `missed` for measurement purposes without mutating
      `medication_doses.status` or invoking/duplicating the sweep. This
      avoids adherence measurements silently depending on incidental API
      call ordering.
    - Scope decision (mirrors Phase 10/11): only `status == "active"`
      medications are evaluated.
  - New module `app/analysis/safety_score_engine.py`:
    - `calculate_safety_score(patient_id, db)` — composes
      `detect_drug_interactions()` (Phase 10), `detect_adrs()` (Phase
      11), and `analyze_adherence()` (Phase 12) into a single composite
      `safety_score` (0-100, floored at 0) and `risk_level`
      (`low`/`moderate`/`high`), per spec section 5/8's
      `analysis_runs.safety_score`/`risk_level` and the LangGraph "Safety
      Score Engine" node description.
    - Sole owner of all thresholds and weights in the system: `BASE_SCORE`
      (100), `MIN_SCORE` (0), `INTERACTION_PENALTY_POINTS`/
      `ADR_PENALTY_POINTS` (mild=5, moderate=15, severe=30),
      `ADHERENCE_ADEQUATE_THRESHOLD`/`ADHERENCE_MODERATE_THRESHOLD`/
      `ADHERENCE_SEVERE_THRESHOLD` (0.80/0.50/0.25) with
      `ADHERENCE_PENALTY_POINTS` (mild=5, moderate=10, severe=20), and
      `RISK_LEVEL_LOW_THRESHOLD`/`RISK_LEVEL_MODERATE_THRESHOLD`
      (70/40) — every value is a named, individually-commented
      module-level constant explicitly documented as an implementation
      default rather than a clinical citation (only the 80% adherence
      cutoff has any external basis, per medication-adherence outcomes
      research; the rest were confirmed with the project owner as a
      starting point pending clinical review).
    - `_classify_adherence_severity()` is the single place in the
      codebase that turns an adherence rate into a mild/moderate/severe
      judgment — kept out of `adherence_engine.py` deliberately, since
      unlike `interaction_rules`/`adr_rules` there is no authoritative
      severity reference table for adherence, making that classification
      a scoring *policy* choice rather than a lookup.
    - `SafetyScoreResult` exposes `safety_score`, `risk_level`,
      `starting_score`, `total_points_deducted`, all three raw finding
      lists (`interaction_findings`, `adr_findings`,
      `adherence_findings`), and a full `penalties: list[PenaltyEntry]`
      audit trail — each `PenaltyEntry` carries its category, a
      human-readable description, assigned severity, point cost, and a
      direct reference to the originating finding object, so a later
      phase (Evidence Retrieval, the LLM explanation node, or a report
      view) can explain exactly how the score was produced without
      recomputing anything.
  - Deliberately **not** exposed via any HTTP route in this phase, and
    nothing is persisted to `analysis_runs` yet — both happen in Phase 14
    (LangGraph)'s Persist Node, same as Phases 10/11's deferred wiring.
  - `timeline_engine.py` (also listed in the spec's section 6 folder
    structure) was explicitly **not** built in this phase — confirmed
    with the project owner that nothing in Phase 12's description
    requires timeline findings; its need, if any, is deferred until a
    later phase makes it clear.
  - New test file `tests/test_adherence_engine.py`: live-DB integration
    tests calling `analyze_adherence()` directly. Covers no-active-
    medications (empty), a medication with no due doses yet (excluded
    entirely), full-miss adherence computed without the sweep having run,
    a mixed taken/missed/skipped medication, fully-adherent medication
    (rate == 1.0), exclusion of discontinued medications, multiple active
    medications each producing their own finding, and patient scoping.
  - New test file `tests/test_safety_score_engine.py`: two layers of
    coverage —
    - Isolated, DB-free unit tests for `_classify_adherence_severity()`
      and `_risk_level_for_score()`, pinning down every threshold
      boundary precisely (e.g. exactly 0.80 adherence lands on the
      "adequate" side, exactly 0.50 lands on "mild," exactly the
      `RISK_LEVEL_LOW_THRESHOLD` score lands on "low").
    - Live-DB integration tests for `calculate_safety_score()`: a clean
      patient (perfect score of 100), an isolated interaction penalty, a
      hand-computed combined interaction+ADR scenario (Warfarin+Aspirin
      → 75 points deducted, score 25, risk_level "high"), an
      adherence-only penalty scenario, confirmation that adequate
      adherence produces no penalty (while still appearing in
      `adherence_findings`), and confirmation that each `PenaltyEntry`'s
      `source` is the real originating finding object.
  - No dedicated cleanup fixture needed for either new test file —
    reuses the existing `created_patient_ids` fixture; neither engine
    performs any writes of its own.

### Changed

None

### Fixed

None
