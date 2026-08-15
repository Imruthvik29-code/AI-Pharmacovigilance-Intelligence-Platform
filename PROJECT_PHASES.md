# Pharmacovigilance MVP - Development Progress

**Project Status:** 🟢 In Development

**Current Milestone:** Milestone 4 - AI Explanation Layer — Complete

**Current Phase:** Phase 15 - Gemini Integration — Complete (verified 2026-08-14: prompt engineering explicit explanation-only, summary generation preserves deterministic findings, recommendation generation grounded explanatory/suggestive, provider abstraction Gemini primary/OpenRouter fallback fail-closed, deterministic persistence still succeeds when LLM fails; verification tests merged 2026-08-15) — next: Phase 16 Frontend/PWA

**Last Updated:** 2026-08-14

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

- [x] Phase 13 - Evidence Retrieval
    - [x] Medical Knowledge Retrieval *(see note below — structured from existing findings, no duplicate query)*
    - [x] Patient History Retrieval *(see note below — scoped per finding)*
    - [x] Retrieval Testing

---

## 🔵 Milestone 4 - AI Explanation Layer

- [x] Phase 14 - LangGraph Workflow
    - [x] Graph Nodes *(6 nodes: patient_context_builder, safety_score_engine, evidence_retrieval, timeline_engine, llm_explanation, persist)*
    - [x] Workflow Integration *(POST /patients/{id}/analyze, GET /patients/{id}/analysis wired to run_analysis)*
    - [x] LangGraph Testing

- [x] Phase 15 - Gemini Integration
    - [x] Prompt Engineering *(grounded, explanation-only prompt; LLM never computes safety_score/risk_level/severity)*
    - [x] Summary Generation *(llm_summary/llm_reasoning from deterministic findings + retrieved evidence)*
    - [x] Recommendation Generation *(llm_recommendations, suggestive only; never replaces the safety engine)*
    - [x] AI Testing *(provider mocks only -- no real API key needed; Gemini success, fallback, malformed output, total failure, no-log-leakage, deterministic invariance)*

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

None — Phase 15 complete and verified, awaiting the start of Phase 16 (Frontend).

Phase 15 complete and verified — all 4 tasks (Prompt Engineering, Summary Generation, Recommendation Generation, AI Testing) implemented and tested:
- AI Testing is now backed by executable coverage in the repository: 9 new test functions (13 parametrized cases) across `tests/test_llm_service.py` and `tests/test_langgraph_workflow.py` — summary generation, recommendation generation, prompt grounding, malformed-output rejection, and deterministic safety_score/risk_level invariance under every LLM outcome
- 105 passed for auth, analysis API, llm_service, llm_providers, langgraph workflow (pytest tests/test_auth_api.py tests/test_analysis_api.py tests/test_llm_service.py tests/test_llm_providers.py tests/test_langgraph_workflow.py -q)
- Prompt explicitly states Gemini is explanation layer only, must NOT calculate safety_score/risk_level/severity/deterministic findings, must consume already-produced analysis/evidence, grounded explanations only, no unsupported medical recommendations, structured JSON output
- Summary generation preserves deterministic findings exactly, distinguishes facts from generated explanation, no hallucinated meds/conditions/symptoms/evidence
- Recommendation generation based only on deterministic findings/evidence, explanatory/suggestive not replacing deterministic engine, no unsupported clinical claims, failure behavior explicit (LLMExplanationError → NULL LLM fields, deterministic persists)
- Provider behavior: Gemini primary, OpenRouter fallback, missing keys fail-closed at call time, deterministic persistence still succeeds when every LLM provider fails, no hardcoded secrets
- Analysis endpoint still returns deterministic fields + additive LLM fields, provider failure does not break deterministic persistence — verified via test_langgraph_workflow.py (mocked providers)
- Tests use provider mocks only — no real Gemini/OpenRouter API key is required to run the suite; live-provider verification remains a manual step

Next: Phase 16 Frontend/PWA per roadmap.

---

# Known Issues

- E2E verification suite `test_e2e_verification.py::test_02_signup` isolated failure in arena due to Supabase Auth TLS + IPv6-only DB host network unreachable — documented in GitHub issue #2 — defer until E2E stabilization after backend stable — not blocking for Phase 15

---

# Next Task

Start Phase 16 - Frontend (Authentication Pages, Dashboard, Patient Pages, Timeline UI, Analysis UI, Frontend Testing) per recommended next phase after Phase 15.

For backend, next highest-priority implementation per dependency order remains Phase B term_type/is_active migration (unblocked by Alembic 0001_baseline) or Prescribe importer switch (can be verified via --dry-run without live DB).

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
  including auto-detected misses from the lazy sweep). `analysis_run` was
  the last remaining event type and is now wired in Phase 14's Persist
  Node (see Phase 14 note below).
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
  service — it was **not** exposed via any HTTP route in Phase 10.
  `api/v1/analysis.py` and the `POST /patients/{id}/analyze` /
  `GET /patients/{id}/analysis` routes were wired in Phase 14
  (LangGraph), which calls into this engine (and the ADR/adherence/
  safety-score/evidence services from later phases) as analysis/workflow
  nodes. Phase 10's tests therefore call the engine directly against a
  live DB session rather than through any endpoint.
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
  deterministic service — was **not** exposed via any HTTP route until
  Phase 14; wired in as an analysis node in the Safety Score Engine.
  Phase 11's tests call the engine directly against a live DB session,
  mirroring Phase 10's testing approach exactly.
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
  (also listed in section 6) was deliberately **not** built in Phase 12,
  since nothing in that phase's description required timeline findings —
  it was subsequently built in Phase 14 (see Phase 14 note below).
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
  silently depend on incidental API call ordering. It performs no writes
  and does not duplicate or invoke the Phase 9 sweep.
- **Phase 12 "audit trail" note (confirmed during planning):**
  `calculate_safety_score()` returns a `SafetyScoreResult` exposing not
  just `safety_score`/`risk_level` but also `starting_score`,
  `total_points_deducted`, all three raw finding lists, and a full
  `penalties: list[PenaltyEntry]` breakdown — each entry carrying its
  category, a human-readable description, assigned severity, point cost,
  and a direct reference to the originating finding object. This was a
  deliberate requirement so a later phase (Evidence Retrieval, the LLM
  explanation node, or a report view) can explain exactly how a score
  was produced without recomputing anything — and Phase 13 confirmed
  this worked as intended, and Phase 14 now persists it end-to-end.
- **Phase 12 scope note:** like Phase 11, `safety_score_engine.py`
  was **not** exposed via any HTTP route until Phase 14, when it became
  the Safety Score Node in the LangGraph workflow.
- **Phase 13 architecture note (confirmed during planning):**
  `app/services/evidence_retrieval.py` is an **application service**, not
  an `app/analysis/` engine — its job is to retrieve/structure supporting
  evidence for the LLM explanation layer, not to detect findings or
  compute a score. This placement mirrors spec section 6's
  `services/` listing (`patient_context_builder.py`, `llm_service.py`,
  `langgraph_workflow.py`), even though `evidence_retrieval.py` itself
  isn't explicitly named there.
- **Phase 13 "medical evidence, no duplicate retrieval" note (confirmed
  during planning):** medical evidence is structured directly from
  `DrugInteractionFinding`/`ADRFinding`'s already-fetched fields
  (`mechanism`, `recommendation`, `reaction_description`,
  `frequency_class`, `source`) — Phase 13 does **not** re-query
  `interaction_rules`/`adr_rules`, since Phase 10/11 already joined
  against them. Adherence findings get no medical evidence at all — no
  rules table backs an adherence "fact," the same reasoning Phase 12
  used to keep severity classification out of `adherence_engine.py`.
- **Phase 13 "personal evidence, scoped per finding" note (confirmed
  during planning):** personal evidence is retrieved via a single,
  targeted `timeline_events` query per finding, scoped to exactly the
  medication(s) (via `ref_id` for medication_started/discontinued, or
  `payload.medication_id` for dose/symptom events) and any condition that
  medication is linked to (`condition_status_changed` via the condition's
  `ref_id`) — never the patient's full timeline. Verified by a dedicated
  test confirming an unrelated third active medication's events do not
  leak into a finding that doesn't involve it.
- **Phase 13 "traceability" note:** each `FindingEvidence` carries the
  original finding object directly (not just an id), mirroring Phase
  12's `PenaltyEntry.source` pattern — `EvidenceItem` additionally
  carries an `occurred_at` timestamp (populated for personal evidence
  from `timeline_events.event_time`, `None` for medical evidence), added
  as a reasonable extension beyond the literal request to preserve
  *when* a personal-history fact happened.
- **Phase 13 scope note:** like Phases 10-12, `evidence_retrieval.py`
  was **not** exposed via any HTTP route until Phase 14, which calls
  `retrieve_evidence()` as the Evidence Retrieval Node immediately after
  the Safety Score Engine merge.
- **Phase 14 architecture note:** `app/services/langgraph_workflow.py`
  implements the full spec section 8 pipeline as a `langgraph.graph.
  StateGraph` with six nodes: `patient_context_builder` →
  `safety_score_engine` → `evidence_retrieval` → `timeline_engine` →
  `llm_explanation` → `persist`. The Safety Score node stands in for
  spec section 8's whole "Deterministic Analysis Layer" box (Drug
  Interaction / ADR / Adherence engines), since `calculate_safety_score()`
  already internally calls all three and exposes their raw findings —
  calling them again separately in the graph would duplicate work. A new
  `app/analysis/timeline_engine.py` (`build_timeline_context`) was added
  in this phase, per spec section 6's folder listing, structuring the
  patient's full timeline chronologically ascending as narrative context
  for the LLM step — deliberately placed *after* Evidence Retrieval in
  the graph, since it's explanatory context, not a scoring input.
- **Phase 14 "why not three separate engine calls" note:** confirmed
  with the project owner — the Safety Score node's internal reuse of
  Phase 12's already-composed `SafetyScoreResult` (rather than
  re-invoking `detect_drug_interactions`/`detect_adrs`/
  `analyze_adherence` directly in the graph) is intentional, not a
  scope-narrowing shortcut.
- **Phase 14 persistence scope note (confirmed during planning):** the
  Persist Node writes only deterministic findings/penalties/score/
  risk_level to `analysis_runs.deterministic_result` (via
  `_serialize_safety_score_result`) — `timeline_context` is deliberately
  **excluded** from that JSONB blob, since `timeline_events` is already
  the single source of truth for timeline data and a denormalized copy
  would create a second one. `timeline_context` exists only in-memory,
  as an LLM Explanation Node input. Verified by a dedicated test
  (`test_deterministic_result_contains_expected_findings_and_excludes_timeline`)
  asserting `"timeline_context" not in det`.
- **Phase 14 "analysis_run" event note:** the Persist Node logs an
  `analysis_run` timeline event (`event_title` includes risk level and
  score; `payload` includes `safety_score`, `risk_level`, and
  `llm_explanation_available`) via the existing `timeline_writer.py`
  helper — completing the last of the eight canonical `event_type`
  values from spec section 5 that remained unwired after Phase 9.
- **Phase 14 LLM stub handling note (intentional, confirmed scope):**
  `app/services/llm_service.py`'s `generate_explanation()` raises
  `NotImplementedError` by design — Phase 15's job to implement per
  explicit project-owner direction. The `llm_explanation` node catches
  *only* `NotImplementedError` (any other exception fails the whole
  graph run, since that would indicate a genuine bug); on the expected
  exception it stores `llm_result: None` and a human-readable
  `llm_error`, and the Persist Node writes `NULL` for
  `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_score`/
  `confidence_level` rather than fabricating output. The deterministic
  pipeline persists successfully regardless of the LLM step's status.
- **Phase 14 API scope note:** `app/api/v1/analysis.py` implements the
  full frozen section 7 contract for analysis — `POST
  /patients/{id}/analyze` (runs the workflow, returns the persisted row)
  and `GET /patients/{id}/analysis` (lists the full run history, most
  recent first — a deliberate ordering choice confirmed with the project
  owner, since the spec doesn't define ordering). Ownership enforcement
  (404 for missing/non-owned patient) mirrors every other patient-scoped
  resource in this codebase. This is also where `app/analysis/
  drug_interaction_engine.py` (Phase 10), `adr_engine.py` (Phase 11),
  `safety_score_engine.py`/`adherence_engine.py` (Phase 12), and
  `evidence_retrieval.py` (Phase 13) — all previously internal-only —
  become reachable via HTTP for the first time, through the workflow.
- **Phase 14 testing note:** `tests/test_langgraph_workflow.py` calls
  `run_analysis()` directly against a live DB session (graph wiring,
  state threading, persistence, LLM-`NotImplementedError` handling,
  repeated-run versioning), independent of the API layer.
  `tests/test_analysis_api.py` exercises the HTTP layer separately
  (both routes, ownership enforcement, empty history for a
  never-analyzed patient). This mirrors the existing convention of
  separating engine/service-level tests from API-level tests used
  throughout Phases 10-13.

## Repository Convention

The implementation is the source of truth.

If PROJECT_PHASES.md or CHANGELOG.md differ from the implementation,
the implementation takes precedence until the documentation is updated.