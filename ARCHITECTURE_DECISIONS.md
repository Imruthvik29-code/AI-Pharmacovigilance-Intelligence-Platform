# ARCHITECTURE_DECISIONS.md

**Part 1 of 3**

---

## 1. Project Vision

An AI-powered medication safety and pharmacovigilance platform. The system tracks a patient's conditions, medications, dosing adherence, and symptoms over time; runs deterministic safety analysis (drug interactions, adverse drug reactions, adherence patterns); and uses a large language model exclusively to explain deterministic findings in plain language. The platform is designed to scale toward production use supporting large patient populations, large medication catalogs, and integration with external regulatory and clinical knowledge sources, without requiring structural redesign at each growth stage.

---

## 2. Design Principles

| Principle | Statement |
|---|---|
| Deterministic source of truth | All safety-relevant conclusions (interactions, ADRs, safety scores, risk levels) are computed by deterministic, rule-based engines. The LLM never computes, invents, or overrides a safety finding. |
| Explain, never compute | The LLM layer's sole function is to explain already-computed deterministic output using retrieved evidence. It cannot originate a clinical claim. |
| Additive evolution over redesign | Schema and architecture changes should be additive (new columns, new tables, new relationships) rather than requiring existing structures to be altered or replaced, wherever this is achievable without compromising correctness. |
| High data quality over maximum catalog size | A smaller, fully safety-checkable drug catalog is preferred over a larger catalog containing entries the deterministic engines cannot evaluate. |
| Curated over scraped | Safety-critical reference data (interaction rules, ADR rules) is hand-curated from authoritative sources, not bulk-imported without review. |
| No speculative architecture | Schema elements, tables, and abstractions are not introduced ahead of a concrete, approved consumer. Deferring a currently-unused table costs nothing; deferring a column on an actively-written table can cost real, unrecoverable ambiguity later — this distinction governs every deferral decision in this document. |
| Verify, do not assume | Claims about external systems (RxNorm, DailyMed, OpenFDA, FAERS, WHO ATC, SNOMED, CVX) are verified against official documentation before being treated as fact. Unverified claims are explicitly labeled as such rather than presented as settled. |

---

## 3. Non-Goals

- The platform does not attempt to be a comprehensive, universal drug database. It imports only what its deterministic engines can act on.
- The platform does not license or redistribute commercially-restricted datasets (e.g., DrugBank's full dataset) in the open-source repository.
- The platform does not perform live, request-time queries against third-party medical APIs as part of any user-facing request path. All external reference data is imported offline and reviewed before being served.
- The platform does not implement product-level (strength/dose-form/pack) drug modeling until a concrete, approved feature requires it.
- The LLM layer is never a source of medical fact; it is not evaluated or trusted as one.

---

## 4. Current Repository Overview

**VERIFIED** (from direct repository inspection):

- Backend: FastAPI, SQLAlchemy (async), Pydantic, PostgreSQL (Supabase-hosted), LangGraph for AI workflow orchestration.
- Eleven database tables: `patients`, `conditions`, `reference_drugs`, `medications`, `medication_schedule`, `medication_doses`, `symptoms`, `interaction_rules`, `adr_rules`, `timeline_events`, `analysis_runs`.
- Migrations are flat, sequentially numbered SQL files at the repository root (`001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql`), applied manually. No automated migration-tracking tool is in use.
- Nine API routers under `backend/app/api/v1/`: `auth`, `patients`, `medications`, `conditions`, `symptoms`, `timeline`, `schedule`, `analysis`, `reference_drugs`.
- Deterministic analysis modules under `backend/app/analysis/`: `drug_interaction_engine.py`, `adr_engine.py`, `adherence_engine.py`, `safety_score_engine.py`.
- AI orchestration under `backend/app/services/`: `patient_context_builder.py`, `evidence_retrieval.py`, `llm_service.py`, `llm_providers.py`, `langgraph_workflow.py`.
- An offline RxNorm import script exists at `backend/scripts/import_rxnorm.py`, sourcing data from NLM's public RxNav REST API.
- Seven Postgres native `ENUM` types are used for every constrained-vocabulary column in the schema (`severity_level`, `risk_level_enum`, `condition_status_enum`, `condition_reason_enum`, `medication_status_enum`, `dose_status_enum`, `confidence_level_enum`) — this is a fully consistent, unbroken convention across the entire existing schema.

---

## 5. Architecture Overview

```
[Patient Data Layer]  patients, conditions, medications, symptoms
        |
        v
[Reference Data Layer]  reference_drugs (RxNorm-sourced), interaction_rules, adr_rules (hand-curated)
        |
        v
[Deterministic Analysis Layer]  drug_interaction_engine, adr_engine, adherence_engine -> safety_score_engine
        |
        v
[Evidence Retrieval]  structures medical + personal evidence per finding
        |
        v
[Timeline Engine]  narrative context, unscoped
        |
        v
[LLM Explanation Layer]  Gemini primary / OpenRouter fallback, explains only
        |
        v
[Persistence]  analysis_runs, timeline_events
```

All patient-facing writes flow through ownership-checked REST endpoints. All reference data (drug catalog, interaction rules, ADR rules) is populated offline, never at request time.

---

## 6. Database Architecture

### 6.1 Conventions (VERIFIED, established and consistent)

- UUID primary keys (`gen_random_uuid()`) on every table.
- `created_at`/`updated_at` timestamptz columns on every mutable table; append-only tables (`timeline_events`, `analysis_runs`) carry `created_at` only, by design.
- Constrained-vocabulary columns use native Postgres `ENUM` types, without exception, across the existing schema.
- Row Level Security is enabled per-table, scoped through ownership chains rooted at `patients.user_id`.
- Foreign keys use `ON DELETE CASCADE` for owned child data and `ON DELETE SET NULL` for optional cross-references (e.g., `medications.condition_id`).

### 6.2 Accepted correction to prior guidance: constrained-vocabulary fields must use `ENUM`, not free `text`

An earlier design draft proposed a `term_type` column (RxNorm TTY classification) as unconstrained `text`, reasoning that a `CHECK` constraint would require a migration to extend later. This reasoning was incorrect: a Postgres `ENUM` type requires an identical migration (`ALTER TYPE ... ADD VALUE`) to extend, so the stated justification did not actually distinguish `text` from a constrained type. Given the schema's unbroken convention of using `ENUM` for every other constrained-vocabulary field, an unconstrained `text` column would be the only inconsistent field in the table.

**Final decision:** `reference_drugs.term_type` is a Postgres `ENUM` (`rxnorm_term_type_enum`), seeded with the **full documented RxNorm TTY vocabulary** (all values from NLM's RxNorm Appendix 5 — `IN, PIN, MIN, BN, SCD, SBD, SCDC, SCDF, SCDFP, SCDG, SCDGP, SBDC, SBDF, SBDFP, SBDG, GPCK, BPCK, DF, DFG, ET, PSN, SY, TMSY`), even though only a subset is currently imported. This resolves the original tension cleanly: the database enum enforces "this value is a real RxNorm term type" (data integrity, verified against official documentation), while the **importer's own internal allow-list** enforces "this term type is currently approved for import" (business policy). Expanding which TTYs are imported in a future phase is then a code change to the importer's allow-list, not a database migration — the enum never needs to be altered as import scope grows, because it was seeded with the complete real vocabulary from the start.

### 6.3 Indexing

| Index | Status | Rationale |
|---|---|---|
| `idx_reference_drugs_name_lower` — functional index on `lower(name)` | **ACCEPTED** | Verified to directly accelerate the importer's case-insensitive exact-name backfill lookup and the search endpoint's exact-match ranking clause. Explicitly does **not** accelerate substring/prefix (`ILIKE '%...%'`) search — that requires `pg_trgm` trigram indexing, which remains a deferred, unapproved enhancement. |
| `medications(patient_id, status)` composite index | **DEFERRED pending empirical verification** | Originally proposed as required. Subsequent review found this recommendation in direct tension with an earlier, separately-accepted scalability argument: per-patient active-medication row counts stay small regardless of total table size, meaning a sequential scan over an already `patient_id`-filtered row set is unlikely to meaningfully benefit from a trailing low-cardinality `status` column in the index. **Final decision:** do not implement until an `EXPLAIN ANALYZE` against representative data confirms real benefit over the existing `idx_medications_patient` alone. |
| `idx_medications_patient` (pre-existing) | **RETAINED, unchanged** | No case has been made to remove it. |

### 6.4 Migration tooling

**Accepted correction to prior phasing:** migration tooling adoption (e.g., Alembic, or an equivalent tracked-migration mechanism) was originally placed in a late-stage "enterprise scale" phase, reasoned to matter only once team/environment count grows. This ordering was reconsidered: the cost of adopting tracked migrations is proportional to how much untracked migration history exists at adoption time — every additional manually-applied file between now and eventual adoption increases the retroactive-reconciliation burden. **Final decision:** migration tooling adoption should occur while migration-file count remains low (early), not deferred to a late phase. See Section 24 (Roadmap) for exact placement.

---

## 7. Drug Catalog Architecture

### 7.1 Source

**VERIFIED**, checked directly against NLM's own API documentation this review cycle:

- RxNorm's full, unfiltered concept set (`/REST/allconcepts.json`) includes clinically out-of-scope entries for this platform's purpose — allergenic extracts (e.g., pollen/food extracts used in immunotherapy), veterinary-only substances, and entries sourced from non-clinical vocabularies — because these are legitimately active, non-suppressed RxNorm concepts, not obsolete data.
- NLM publishes a separate, actively maintained subset, **RxNorm Current Prescribable Content** (`/REST/Prescribe/allconcepts.json`), explicitly documented as excluding obsolete/suppressed data, non-US/foreign-only drugs, and drugs for exclusive veterinary use, and restricted to `SAB=RXNORM` + `SAB=MTHSPL` (FDA-regulated drug-labeling sources only). NLM's own 2014 release notes confirm non-standardized allergenic-label products were explicitly removed from this subset.

**Final decision:** the importer sources exclusively from the **Prescribable Content** endpoint, not full RxNorm. This structurally satisfies the "active only," "no obsolete," "no veterinary-only," and "no allergenic-extract" exclusion requirements using NLM's own maintained curation, rather than a custom keyword-blocklist approach (rejected — see Section 20).

### 7.2 Term Type (TTY) scope

**VERIFIED**, against NLM's RxNorm Appendix 5: TTY encodes structural granularity (ingredient vs. ingredient+strength vs. ingredient+strength+form+brand), not therapeutic category. There is no dedicated TTY for vaccines, biologics, monoclonal antibodies, blood products, or contrast agents — these appear as ordinary `IN`-level ingredient concepts provided they carry real FDA drug labeling, which they do.

**Final decision:** Phase 1 imports **`IN` (Ingredient) only**. `PIN` (Precise Ingredient) is deferred — not rejected — because both `IN` and `PIN` are equally compatible with the deterministic engines, so scope discipline, not engine correctness, is the deciding factor, and `PIN`'s later addition carries zero backfill or ambiguity cost (same importer, same mechanism, additional `--tty` value, no schema change).

**Rejected for the current phase:** `MIN` (combination products) and `BN` (brand names) as import targets. Both are technically importable via the same mechanism, but both introduce a real, verified functional gap: the deterministic engines match `medications.drug_id` directly against `interaction_rules`/`adr_rules`, which are curated at `IN`-level granularity, with **no decomposition logic anywhere in the codebase**. A `MIN` or `BN` row selected as a medication's `drug_id` currently produces zero interaction/ADR findings — not because the patient is safe, but because the catalog row does not structurally connect to the safety data. This is a silent, confidence-eroding failure mode, not a cosmetic gap, and is disqualifying for import until ingredient-decomposition support exists (Section 24, Phase C).

**Important correction to prior framing:** enabling `MIN`/`BN` import safely was previously described as achievable via "a small, additive change to two engine query functions." This understated the actual cost. The engines' core matching primitive (`_get_active_drug_ids`, verified identical in both `drug_interaction_engine.py` and `adr_engine.py`) currently returns a flat set of `Medication.drug_id` values directly. Supporting decomposition requires **rewriting this primitive** to resolve each `drug_id` through a future ingredient-mapping table and return the union of underlying ingredient IDs — a genuine modification to tested, safety-relevant matching logic in two files, not a pure addition alongside unchanged code. The catalog table itself remains additively extensible; the engines do not.

### 7.3 `reference_drugs` schema (current + Phase 1 additions)

| Column | Type | Nullable | Default | Status |
|---|---|---|---|---|
| `id` | uuid | No | `gen_random_uuid()` | Existing |
| `name` | text | No | — | Existing |
| `generic_name` | text | Yes | — | Existing, currently unpopulated by the importer |
| `drug_class` | text | Yes | — | Existing, currently unpopulated by the importer |
| `rxcui` | text | Yes | — | Existing (unique constraint) — idempotency key for import |
| `source` | text | Yes | — | Existing — provenance tag, e.g. `"RxNorm"` |
| `source_updated_at` | timestamptz | Yes | — | Existing |
| `term_type` | `rxnorm_term_type_enum` | Yes | — | **Phase 1 addition** — see Section 6.2. Nullable because pre-existing hand-curated rows have no known TTY; `NULL` is a distinct, meaningful state, not an omission. |
| `is_active` | boolean | No | `true` | **Phase 1 addition** — every row, including legacy rows, is active by definition until a future mechanism proves otherwise. No `NULL` state exists for this column, unlike `term_type`. |
| `created_at` / `updated_at` | timestamptz | No | — | Existing |

**UNVERIFIED / REQUIRES RESEARCH:** whether a plain boolean is structurally sufficient to represent RxNorm concept retirement. RxNorm's retirement process may involve remapping a retired concept to a successor RxCUI rather than simple deactivation; if so, a boolean cannot represent "retired, and here is the replacement," and a future `superseded_by_rxcui` field would be needed. This has not been verified against official documentation and is recorded as an open research item (Section 22), not acted upon.

### 7.4 Catalog size

**ENGINEERING ESTIMATE**, not independently verified against a live query this cycle: `IN`-only import under Prescribable Content is estimated at approximately 4,000–6,000 rows, based on a 2013 NLM-published historical baseline (4,320) with expected growth since. The first real implementation step should be a `--dry-run` execution to replace this estimate with a measured count.

---

*Continued in Part 2 of 3 — sections 8 through 19.*
