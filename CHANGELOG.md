- **Phase B (0002) — `reference_drugs.term_type` enum + `is_active`:**
  - New Alembic migration `backend/alembic/versions/0002_add_term_type_is_active.py`
    (revision `0002_add_term_type_is_active`, revises `0001_baseline`):
    `CREATE TYPE rxnorm_term_type_enum` seeded with the full 23-value RxNorm
    TTY vocabulary (NLM Appendix 5: `IN, PIN, MIN, BN, SCD, SBD, SCDC, SCDF,
    SCDFP, SCDG, SCDGP, SBDC, SBDF, SBDFP, SBDG, GPCK, BPCK, DF, DFG, ET,
    PSN, SY, TMSY`), adds nullable `reference_drugs.term_type`
    (`rxnorm_term_type_enum`) and `reference_drugs.is_active` (`boolean NOT
    NULL DEFAULT true`). Additive only — `reference_drugs.id` is never
    changed, so `medications.drug_id` and the `interaction_rules`/`adr_rules`
    foreign keys stay valid and existing rows become `is_active=true`. Alembic
    history is now `0001_baseline -> 0002_add_term_type_is_active`; `alembic
    upgrade head` / `downgrade -1` are reproducible.
  - `backend/app/db/models.py`: `ReferenceDrug` exposes `term_type`
    (nullable, `rxnorm_term_type_enum`, `create_type=False` — the migration
    owns the type) and `is_active` (`Boolean`, `nullable=False`,
    `server_default=true`, Python `default=True`).
  - `backend/scripts/import_rxnorm.py` unchanged — importer stays `IN`-only
    and does not populate `term_type`/`is_active` yet. No `lower(name)` index
    is introduced.

- **Phase 14 — LangGraph Workflow:**
  - New module `app/analysis/timeline_engine.py` (per spec section 6's
    folder structure): `build_timeline_context(patient_id, db)` retrieves
    and structures a patient's full `timeline_events` history,
    chronologically ascending (oldest → newest) — the opposite of
    `GET /patients/{id}/timeline`'s most-recent-first ordering (Phase 7),
    since this output is meant to read as a narrative for the eventual
    LLM explanation step. Performs no pattern detection, trend analysis,
    or scoring — pure retrieval/structuring only, per explicit
    project-owner direction to keep this engine's scope strictly to
    retrieval.
  - New module `app/services/patient_context_builder.py`:
    `build_patient_context(patient_id, db)` builds a fresh
    `PatientContext` (demographics + active conditions/medications/
    symptoms) on every call, per spec section 5's documented "no
    patient_context table" design — never cached, so it can't go stale.
    Scope decisions: active medications (`status == "active"`, matching
    every other engine), active conditions (`status != "resolved"`),
    active symptoms (`resolved_date IS NULL`) — each a confirmed
    implementation default, not a spec-defined rule.
  - New module `app/services/llm_service.py`: defines the
    `generate_explanation()` interface and `LLMExplanationResult` shape
    the LLM Explanation Node calls. Intentionally raises
    `NotImplementedError` — the real Gemini/OpenRouter call is deferred
    to Phase 15 per explicit project-owner direction, so this phase can
    wire and test the full graph without fabricating LLM output.
  - New module `app/services/langgraph_workflow.py`: wires spec section
    8's full pipeline into a `langgraph.graph.StateGraph` —
    `patient_context_builder` → `safety_score_engine` →
    `evidence_retrieval` → `timeline_engine` → `llm_explanation` →
    `persist`. `AnalysisState` (`TypedDict, total=False`) threads
    progressively-populated state through every node; the DB session is
    not part of state (each node factory closes over it instead).
    - The Safety Score node reuses Phase 12's `calculate_safety_score()`
      directly (which already internally composes
      `detect_drug_interactions()`/`detect_adrs()`/`analyze_adherence()`
      and exposes all three raw finding lists) rather than re-invoking
      those three engines separately — confirmed with the project owner
      as the intended design, not a scope shortcut.
    - The Timeline Engine node runs *after* Evidence Retrieval — timeline
      context is narrative/explanatory input for the LLM step, not a
      scoring input, so it's kept separate from "things that feed the
      score."
    - The Persist Node serializes `SafetyScoreResult` into a JSON-safe
      dict (`_serialize_safety_score_result` and friends) for
      `analysis_runs.deterministic_result` — deliberately **excluding**
      `timeline_context`, since `timeline_events` remains the single
      source of truth for timeline data. `PenaltyEntry.source` (the live
      finding object reference) is also excluded from serialization as
      non-JSON-safe; each penalty's own `description` field already
      documents the "why" in readable prose, and the full finding is
      separately present in the same dict.
    - The Persist Node writes the `analysis_runs` row and logs the
      `analysis_run` timeline event (payload includes `safety_score`,
      `risk_level`, `llm_explanation_available`) via the existing
      `timeline_writer.py` helper — completing the last of the eight
      canonical `event_type` values from spec section 5.
    - The LLM Explanation node catches *only* `NotImplementedError` from
      `llm_service.generate_explanation()`, storing `llm_result: None`
      and a human-readable `llm_error`; any other exception propagates
      and fails the whole graph run. The deterministic pipeline persists
      successfully regardless of the LLM step's outcome.
  - New module `app/schemas/analysis.py`: `AnalysisRunResponse` —
    response-only schema (neither analysis route accepts a client-supplied
    body). `llm_summary`/`llm_reasoning`/`llm_recommendations`/
    `confidence_score`/`confidence_level` are nullable and `None` for
    every run until Phase 15.
  - New endpoints `app/api/v1/analysis.py`: `POST /patients/{id}/analyze`
    (runs the full workflow via `run_analysis()`, persists, and returns
    the resulting `analysis_runs` row) and `GET /patients/{id}/analysis`
    (lists a patient's full analysis history, ordered `created_at DESC` —
    most recent first, confirmed with the project owner). Ownership
    enforcement via the parent patient mirrors every other patient-scoped
    resource in this codebase (404 for missing/non-owned patient, never
    403).
  - `app/main.py` updated to additionally register the analysis router.
  - This phase is also the point at which Phases 10-13's engines/services
    (`drug_interaction_engine.py`, `adr_engine.py`,
    `safety_score_engine.py`, `adherence_engine.py`,
    `evidence_retrieval.py`) — previously internal-only, exercised only
    via direct-DB-session tests — become reachable via HTTP for the
    first time, through this workflow.
  - New test file `tests/test_langgraph_workflow.py`: calls
    `run_analysis()` directly against a live DB session. Covers a clean
    patient yielding a perfect score (100/low), LLM fields left null with
    a Phase-15-referencing `llm_error` message, `deterministic_result`
    correctness for a real Warfarin+Aspirin scenario (matching Phase 12's
    own combined-findings numbers: 1 interaction + 2 ADRs, 75 points
    deducted, score 25, risk "high") including confirmation that
    `timeline_context` is excluded from the persisted JSONB and that
    penalty dicts are JSON-safe (no raw finding reference), the
    `analysis_run` timeline event being logged with the correct payload,
    and running twice producing two distinct, separately versioned
    `analysis_runs` rows.
  - New test file `tests/test_analysis_api.py`: exercises both routes via
    `TestClient`. Covers `POST /analyze` creating and returning a
    persisted run (including null LLM fields), 404 for a nonexistent
    patient, 404 for a patient owned by another user, `GET /analysis`
    returning the full history most-recent-first across two runs, 404 for
    nonexistent/cross-user patients on the list route, and an empty list
    for a patient that has never been analyzed.
  - New test file `tests/test_patient_context_builder.py`: calls
    `build_patient_context()` directly. Covers an empty patient (empty
    lists, demographics populated), active-medication-included/
    discontinued-excluded, resolved-condition-excluded/others-included,
    resolved-symptom-excluded/unresolved-included, and patient scoping.
  - New test file `tests/test_timeline_engine.py`: calls
    `build_timeline_context()` directly. Covers an empty patient (no
    entries), chronological ascending ordering (opposite of `GET
    /timeline`'s DESC), patient scoping, and entry-field mapping against
    the source `timeline_events` row.
  - No dedicated cleanup fixtures needed for any of the four new test
    files — all reuse the existing `created_patient_ids` (and, where
    relevant, `created_condition_ids`) fixtures from `conftest.py`; none
    of the four new services/engines perform writes of their own outside
    the workflow's own Persist Node, which is covered by
    `created_patient_ids`' cascade-on-delete.

### Changed

None

### Fixed

None