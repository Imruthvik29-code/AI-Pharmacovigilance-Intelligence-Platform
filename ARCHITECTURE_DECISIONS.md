# ARCHITECTURE_DECISIONS.md

**Part 1 of 3**

---

> **Status label legend** (added for internal consistency; these labels were previously used without a shared definition): `VERIFIED` — confirmed against official documentation or direct repository inspection. `Final decision` / `ACCEPTED` — approved by the project owner; where a decision is approved but not yet reflected in code, an explicit "Implementation status" note is attached. `DEFERRED` — considered and consciously postponed, with stated revisit criteria. `RETAINED` — an existing element reviewed and kept unchanged. `UNVERIFIED / REQUIRES RESEARCH` — an open question, not yet confirmed. `ENGINEERING ESTIMATE` — an unconfirmed approximation pending measurement.

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
- Deterministic analysis modules under `backend/app/analysis/`: `drug_interaction_engine.py`, `adr_engine.py`, `adherence_engine.py`, `safety_score_engine.py`, `timeline_engine.py`.
- AI orchestration under `backend/app/services/`: `patient_context_builder.py`, `evidence_retrieval.py`, `llm_service.py`, `llm_providers.py`, `langgraph_workflow.py`.
- An offline RxNorm import script exists at `backend/scripts/import_rxnorm.py`, sourcing data from NLM's public RxNav REST API.
- Seven Postgres native `ENUM` types are used for every constrained-vocabulary column in the schema (`severity_level`, `risk_level_enum`, `condition_status_enum`, `condition_reason_enum`, `medication_status_enum`, `dose_status_enum`, `confidence_level_enum`) — this is a fully consistent, unbroken convention across the entire existing schema.

---

## 5. Architecture Overview
[Patient Data Layer] patients, conditions, medications, symptoms
|
v
[Reference Data Layer] reference_drugs (RxNorm-sourced), interaction_rules, adr_rules (hand-curated)
|
v
[Deterministic Analysis Layer] drug_interaction_engine, adr_engine, adherence_engine -> safety_score_engine
|
v
[Evidence Retrieval] structures medical + personal evidence per finding
|
v
[Timeline Engine] narrative context, unscoped
|
v
[LLM Explanation Layer] Gemini primary / OpenRouter fallback, explains only
|
v
[Persistence] analysis_runs, timeline_events

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

An earlier design draft proposed a `term_type` column (RxNorm Term Type, or TTY, classification) as unconstrained `text`, reasoning that a `CHECK` constraint would require a migration to extend later. This reasoning was incorrect: a Postgres `ENUM` type requires an identical migration (`ALTER TYPE ... ADD VALUE`) to extend, so the stated justification did not actually distinguish `text` from a constrained type. Given the schema's unbroken convention of using `ENUM` for every other constrained-vocabulary field, an unconstrained `text` column would be the only inconsistent field in the table.

**Final decision:** `reference_drugs.term_type` is a Postgres `ENUM` (`rxnorm_term_type_enum`), seeded with the **full documented RxNorm TTY vocabulary** (all values from NLM's RxNorm Appendix 5 — `IN, PIN, MIN, BN, SCD, SBD, SCDC, SCDF, SCDFP, SCDG, SCDGP, SBDC, SBDF, SBDFP, SBDG, GPCK, BPCK, DF, DFG, ET, PSN, SY, TMSY`), even though only a subset is currently imported. This resolves the original tension cleanly: the database enum enforces "this value is a real RxNorm term type" (data integrity, verified against official documentation), while the **importer's own internal allow-list** enforces "this term type is currently approved for import" (business policy). Expanding which TTYs are imported in a future phase is then a code change to the importer's allow-list, not a database migration — the enum never needs to be altered as import scope grows, because it was seeded with the complete real vocabulary from the start.

**Implementation status (as of this review):** not yet applied. No migration in the repository creates `rxnorm_term_type_enum` or a `term_type` column, and `backend/scripts/README.md` explicitly states these columns "do not exist on `reference_drugs`" as of the current importer version. This decision is approved but pending implementation — treat the `term_type`/`is_active` columns described here and in Section 7.3 as designed, not yet shipped.

### 6.3 Indexing

| Index | Status | Rationale |
|---|---|---|
| `idx_reference_drugs_name_lower` — functional index on `lower(name)` | **ACCEPTED** | Verified to directly accelerate the importer's case-insensitive exact-name backfill lookup and the search endpoint's exact-match ranking clause. Explicitly does **not** accelerate substring/prefix (`ILIKE '%...%'`) search — that requires `pg_trgm` trigram indexing, which remains a deferred, unapproved enhancement. **Implementation status:** not yet created by any migration in the repository; `GET /reference-drugs/search` (`backend/app/api/v1/reference_drugs.py`) currently performs an unindexed `ILIKE` scan by explicit documented design ("No new index is added for this search"). This decision is approved but pending implementation. |
| `medications(patient_id, status)` composite index | **DEFERRED pending empirical verification** | Originally proposed as required. Subsequent review found this recommendation in direct tension with an earlier, separately-accepted scalability argument: per-patient active-medication row counts stay small regardless of total table size, meaning a sequential scan over an already `patient_id`-filtered row set is unlikely to meaningfully benefit from a trailing low-cardinality `status` column in the index. **Final decision:** do not implement until an `EXPLAIN ANALYZE` against representative data confirms real benefit over the existing `idx_medications_patient` alone. |
| `idx_medications_patient` (pre-existing) | **RETAINED, unchanged** | No case has been made to remove it. |

### 6.4 Migration tooling

**Accepted correction to prior phasing:** migration tooling adoption (e.g., Alembic, or an equivalent tracked-migration mechanism) was originally placed in a late-stage "enterprise scale" phase, reasoned to matter only once team/environment count grows. This ordering was reconsidered: the cost of adopting tracked migrations is proportional to how much untracked migration history exists at adoption time — every additional manually-applied file between now and eventual adoption increases the retroactive-reconciliation burden. **Final decision:** migration tooling adoption should occur while migration-file count remains low (early), not deferred to a late phase. See Section 24 (Roadmap) for exact placement (Part 3 — not yet authored).

---

## 7. Drug Catalog Architecture

### 7.1 Source

**VERIFIED**, checked directly against NLM's own API documentation this review cycle:

- RxNorm's full, unfiltered concept set (`/REST/allconcepts.json`) includes clinically out-of-scope entries for this platform's purpose — allergenic extracts (e.g., pollen/food extracts used in immunotherapy), veterinary-only substances, and entries sourced from non-clinical vocabularies — because these are legitimately active, non-suppressed RxNorm concepts, not obsolete data.
- NLM publishes a separate, actively maintained subset, **RxNorm Current Prescribable Content** (`/REST/Prescribe/allconcepts.json`), explicitly documented as excluding obsolete/suppressed data, non-US/foreign-only drugs, and drugs for exclusive veterinary use, and restricted to `SAB=RXNORM` + `SAB=MTHSPL` (FDA-regulated drug-labeling sources only). NLM's own 2014 release notes confirm non-standardized allergenic-label products were explicitly removed from this subset.

**Final decision:** the importer sources exclusively from the **Prescribable Content** endpoint, not full RxNorm. This structurally satisfies the "active only," "no obsolete," "no veterinary-only," and "no allergenic-extract" exclusion requirements using NLM's own maintained curation, rather than a custom keyword-blocklist approach (rejected — see Section 20, Part 2 — not yet authored).

**Implementation status (as of this review):** not yet applied. `backend/scripts/import_rxnorm.py` currently calls `RXNAV_BASE_URL + "/allconcepts.json"` (`https://rxnav.nlm.nih.gov/REST/allconcepts.json`) — the full, unfiltered concept endpoint — not `/REST/Prescribe/allconcepts.json`. This decision is approved but not yet implemented in the importer; until the script is updated, the exclusion guarantees described above (no obsolete/suppressed/veterinary-only/allergenic-extract concepts) are **not** structurally enforced by the shipped code.

### 7.2 Term Type (TTY) scope

**VERIFIED**, against NLM's RxNorm Appendix 5: TTY encodes structural granularity (ingredient vs. ingredient+strength vs. ingredient+strength+form+brand), not therapeutic category. There is no dedicated TTY for vaccines, biologics, monoclonal antibodies, blood products, or contrast agents — these appear as ordinary `IN`-level ingredient concepts provided they carry real FDA drug labeling, which they do.

**Final decision:** Phase 1 imports **`IN` (Ingredient) only**. `PIN` (Precise Ingredient) is deferred — not rejected — because both `IN` and `PIN` are equally compatible with the deterministic engines, so scope discipline, not engine correctness, is the deciding factor, and `PIN`'s later addition carries zero backfill or ambiguity cost (same importer, same mechanism, additional `--tty` value, no schema change).

**Rejected for the current phase:** `MIN` (combination products) and `BN` (brand names) as import targets. Both are technically importable via the same mechanism, but both introduce a real, verified functional gap: the deterministic engines match `medications.drug_id` directly against `interaction_rules`/`adr_rules`, which are curated at `IN`-level granularity, with **no decomposition logic anywhere in the codebase**. A `MIN` or `BN` row selected as a medication's `drug_id` currently produces zero interaction/ADR findings — not because the patient is safe, but because the catalog row does not structurally connect to the safety data. This is a silent, confidence-eroding failure mode, not a cosmetic gap, and is disqualifying for import until ingredient-decomposition support exists (Section 24, Phase C — Part 3, not yet authored).

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

**Implementation status:** the `term_type` and `is_active` columns above are Phase 1 additions per this document's decisions (see Section 6.2) but are not present in any applied migration as of this review.

**UNVERIFIED / REQUIRES RESEARCH:** whether a plain boolean is structurally sufficient to represent RxNorm concept retirement. RxNorm's retirement process may involve remapping a retired concept to a successor RxCUI rather than simple deactivation; if so, a boolean cannot represent "retired, and here is the replacement," and a future `superseded_by_rxcui` field would be needed. This has not been verified against official documentation and is recorded as an open research item (Section 22), not acted upon.

### 7.4 Catalog size

**ENGINEERING ESTIMATE**, not independently verified against a live query this cycle: `IN`-only import under Prescribable Content is estimated at approximately 4,000–6,000 rows, based on a 2013 NLM-published historical baseline (4,320) with expected growth since. The first real implementation step should be a `--dry-run` execution to replace this estimate with a measured count.

---

*Continued below — Part 2, Sections 8 through 19.*

---

# Part 2 of 3

---

## 8. Authentication & Authorization Architecture

### 8.1 Token verification model

**VERIFIED (implementation) / UNVERIFIED (live-project observation)** (`backend/app/core/security.py`, `backend/app/core/config.py`): the verifier is configured for ES256-signed access tokens with `aud: authenticated`, `iss: {SUPABASE_URL}/auth/v1`, and a `kid` resolved through the project's JWKS response. The module docstring states these values were confirmed directly against this project's own live-issued tokens, not against Supabase's general documentation alone, but that project-specific live observation has not been independently re-verified by this review and is not treated here as a repository-verified fact.

**Final decision:** verification is performed against Supabase's published JWKS (JSON Web Key Set) endpoint, not a shared HS256 secret. `Settings.supabase_jwks_url` (`backend/app/core/config.py`) is a **derived** property — `f"{supabase_url}/auth/v1/.well-known/jwks.json"` — not a separate configured value, since Supabase publishes this at a fixed, well-known path under the project's own URL. There is therefore nothing new to configure beyond `SUPABASE_URL`, which the deployment already requires for the Auth proxy in `api/v1/auth.py`. Authentication is outside Part 1's scope (database schema and drug catalog architecture), so no cross-reference to Part 1 applies here.

**Rejected alternative:** continuing to verify against `SUPABASE_JWT_SECRET` (HS256, shared secret). This was the original implementation and is documented in `config.py` as **deprecated**, not removed — `supabase_jwt_secret` remains a valid `Settings` field, defaulting to empty string, purely so that an existing deployed `.env` file containing this key does not break config loading. No verification code path reads it. Removing the field outright was rejected as an unnecessary breaking config change; the field is now provably inert (confirmed by reading `security.py` end-to-end — it is never referenced there).

### 8.2 Algorithm pinning

**Final decision:** `_ALLOWED_ALGORITHMS = ["ES256"]` is hardcoded in `security.py` rather than read from the resolved JWK's own `alg` field.

**Rationale (recorded in the module docstring, verified as accurate against the code):** signature verification receives `signing_key.key`, the raw public key from the JWK object `PyJWKClient` resolves, not the `PyJWK` object itself. PyJWT therefore checks the token header's `alg` against `_ALLOWED_ALGORITHMS` and selects the ES256 verifier from that allowed header value; it does not additionally enforce equality with the resolved JWK's own `alg` metadata. The hardcoding makes the one algorithm this codebase is willing to accept explicit and auditable in source, rather than implicit in whatever Supabase's JWKS response happens to declare at runtime. A future Supabase migration off ES256 would cause `jwt.decode(..., algorithms=["ES256"])` to reject a token signed with a new algorithm — a deliberate hard failure requiring a reviewed code change, rather than silent acceptance of a new algorithm the codebase has never evaluated.

**Trade-off accepted:** this is a live availability risk if Supabase ever rotates its signing algorithm without this codebase being updated in lockstep — every request would start failing 401 until the allow-list is manually revised. This is treated as an acceptable trade-off in exchange for auditability; no monitoring/alerting mechanism for this scenario exists in the repository.

### 8.3 Dependency version pin

**VERIFIED** (`backend/requirements.txt`): `pyjwt[crypto]>=2.13.0,<3.0.0`, not a bare `pyjwt[crypto]`.

**Rationale:** PyJWT versions 2.9.0–2.12.1 carry a known algorithm allow-list bypass when `jwt.decode` receives a `PyJWK` key (cited as CVE-2026-48523), fixed in 2.13.0. This module uses `PyJWKClient` to resolve the signing key but passes `signing_key.key`, the raw public key, to `jwt.decode`, so its current decode call does not use the CVE-affected `PyJWK` path and the version floor does not directly protect the raw-key algorithm-pinning behavior described in §8.2. The `>=2.13.0,<3.0.0` requirement remains the approved dependency decision.

### 8.4 Issuer / audience validation

**VERIFIED (implementation) / UNVERIFIED (live-project observation)**: `jwt.decode(...)` is called with `audience="authenticated"` and `issuer=f"{settings.supabase_url}/auth/v1"`, plus `options={"require": ["exp", "aud", "iss"]}` — all three claims are mandatory on the token, not merely checked if present. The module docstring states that the audience string and issuer URL pattern were confirmed against this project's real issued tokens, but that project-specific live observation remains unverified as recorded in §8.1.

### 8.5 JWKS client caching

**VERIFIED**: `_get_jwks_client()` constructs a single module-level `PyJWKClient(settings.supabase_jwks_url, cache_keys=True)` on first use and reuses it across requests within the process (`_jwks_client` global, lazily initialized, `None` until first call). `cache_keys=True` gives the client its own internal key cache, so the common case (a recognized `kid`) never re-fetches the JWKS document; only a cache miss — e.g. an unrecognized `kid` after Supabase rotates its signing key — triggers a refetch.

**Design note on testability:** the client is rebuilt only inside `_get_jwks_client()`, and nowhere else. This is deliberate so tests can monkeypatch that one function directly (confirmed in `tests/test_security.py`'s `_patch_jwks_client` helper) instead of manipulating the module-level cache variable — the function is the seam, not the state.

### 8.6 Failure handling and information disclosure

**VERIFIED**, from `decode_supabase_jwt`'s exception handling:

| Condition | Response |
|---|---|
| `supabase_url` unset (no JWKS endpoint derivable) | `500` — server misconfiguration, not a client error |
| Token expired (`ExpiredSignatureError`) | `401`, "Access token has expired." |
| Unknown/rotated `kid`, unreachable JWKS endpoint, malformed token, bad signature, disallowed algorithm, wrong audience/issuer (`PyJWKClientError` or any `jwt.PyJWTError`) | `401`, "Invalid access token." — all collapsed into one message |

**Final decision:** every JWT-level failure mode other than expiry is deliberately surfaced as the same generic "Invalid access token." message. This mirrors the same non-disclosure posture already established in Part 1 for resource ownership (never confirm to a caller *why* something failed in a way that leaks system internals) — here applied to authentication rather than authorization. No stack trace, JWKS fetch error detail, or key-matching diagnostic reaches the client.

### 8.7 Identity extraction

**VERIFIED** (`get_current_user`): the `sub` claim is required and parsed as a UUID; a missing `sub` is `401` ("Token missing subject claim"), and a `sub` that is not a valid UUID is `401` ("Invalid access token.") rather than a `422` or `500` — an unparseable identity claim is treated as an authentication failure, not a validation error, consistent with §8.6's non-disclosure posture. `CurrentUser` is a minimal, two-field (`id`, `email`) object; no role, scope, or claim beyond identity is extracted or used anywhere in this codebase's authorization pattern — ownership is enforced entirely via `patients.user_id` comparison at the query level (see Section 9), not via token claims or roles.

### 8.8 Fail-at-call-time convention (cross-referenced, not restated)

**VERIFIED**: `_get_jwks_client()` raises `HTTPException(500)` only when actually invoked (i.e., on the first authenticated request needing JWKS), not at settings-load or import time. This is the same convention documented for `api/v1/auth.py`'s `_supabase_headers()` (missing `SUPABASE_URL`/`SUPABASE_ANON_KEY` fails at call time) and later, for the LLM provider layer, in `llm_providers.py` (missing API keys fail at call time). This convention is introduced here rather than in Part 1 because Part 1's accepted sections do not cover authentication; it will be referenced again, not re-explained, in the configuration section later in this Part.

### 8.9 Relationship to Row Level Security (open item)

Part 1 §6.1 records that Row Level Security is enabled on every patient-scoped table, with policies keyed on `auth.uid()` matching against `patients.user_id`. This section covers only the application-layer JWT verification that authenticates a caller to the FastAPI backend; it does not establish whether the database itself independently enforces the same boundary against this backend's own connection.

**VERIFIED**: the backend connects to Postgres using a single, statically configured `DATABASE_URL` (`backend/.env`), authenticated as the `postgres` role, via SQLAlchemy/asyncpg — not through Supabase's PostgREST/pooler layer, which is the path that normally populates `auth.uid()` from a request's JWT claims. `001_initial_schema.sql` enables RLS on every relevant table (`alter table ... enable row level security`) but does not issue `FORCE ROW LEVEL SECURITY` on any of them.

Standard PostgreSQL RLS semantics (a general database-engine behavior, not a repository-specific claim) exempt a table's owner from its own RLS policies unless `FORCE ROW LEVEL SECURITY` is explicitly set. Whether the `postgres` role used by this backend is the owner of these tables — and therefore exempt from the policies defined in `001_initial_schema.sql` — has not been confirmed against the live database from within this repository.

**UNVERIFIED / REQUIRES RESEARCH:** whether Supabase RLS provides any enforcement against this backend's own connection, given the above. This does not weaken the ownership guarantee the API already provides: direct `Patient.user_id` filters, prior parent-ownership checks, or joins through `Patient.user_id` are used by every patient-scoped router (documented in Section 9) and enforced in application code, independent of whatever RLS does or does not additionally enforce at the database layer. RLS's practical role in this architecture — defense-in-depth against this backend's own queries, versus protection intended for a different (PostgREST/client-side) access path this backend does not use — is recorded here as an open question, not resolved.

---

## 9. Authorization & Ownership Enforcement

**Scope and evidence labeling:** every normative statement in §9 is labeled with its evidence basis: `VERIFIED (repository)` — confirmed by reading the file(s) cited; `VERIFIED (official documentation)` — confirmed in authoritative PostgreSQL/Supabase docs cited; `VERIFIED (empirical experiment)` — observed by running the test/command cited; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository. Implementation is the source of truth; documentation is updated to match implementation. No live-runtime behavior is claimed where the repository cannot prove it.

### 9.1 Principle

**VERIFIED (repository: `backend/app/core/security.py:97-181`, `backend/app/api/v1/patients.py:37-44`, `medications.py:58-89`, `conditions.py:47-75`, `symptoms.py:49-54`, `timeline.py:30-38`, `schedule.py:129-183`, `analysis.py:37-48`):**

Authorization is ownership-based. The code enforces ownership at the application query level by requiring `Patient.user_id == current_user.id` in every patient-scoped query. `CurrentUser` constructed from the verified JWT `sub` (see §8.7) is the sole identity input in the code; no role, scope, group, or additional token claim beyond `id`/`email` is read in any router.

**VERIFIED (repository: grep `role/scope/is_admin` in `backend/app/api/` and `backend/app/core/security.py` returns no access-control branching; grep `auth.uid()` in `backend/` returns zero results):** no router relies on database Row Level Security or token-embedded roles for authorization. RLS policies exist in `001_initial_schema.sql` but are not referenced by application code (see §9.6). Whether RLS enforces at runtime for this backend's database connection is `UNVERIFIED` (see §9.6).

### 9.2 Identity source

**VERIFIED (repository: `backend/app/core/security.py:97-181`):**

- `CurrentUser` is a minimal two-field object (`id: UUID`, `email: str | None`) constructed from the JWT `sub` (parsed with `uuid.UUID(sub)`) and optional `email` — `VERIFIED (repository: `security.py:97-106`, `151-180`)`.
- `get_current_user` is the sole FastAPI dependency providing identity; all patient-scoped routers import it via `Depends(get_current_user)` — `VERIFIED (repository: `grep -rn "get_current_user" backend/app/api/v1/`` shows `patients.py:27`, `medications.py:47`, `conditions.py:36`, `symptoms.py:38`, `timeline.py:21`, `schedule.py:82`, `analysis.py:21`, `reference_drugs.py:45`)`.
- The code raises `HTTPException(401, "Token missing subject claim.")` if `sub` is missing and `HTTPException(401, "Invalid access token.")` if `sub` is not a UUID — `VERIFIED (repository: `security.py:160-176`)`. No router extracts `user_id` from path, body, or query; every assignment/filter uses `current_user.id` — `VERIFIED (repository: `grep -rn "user_id" backend/app/api/v1/`` shows only `Patient.user_id == current_user.id` filters and `user_id=current_user.id` assignments; zero occurrences of `user_id` from request body).

### 9.3 Per-router enforcement (VERIFIED repository, exhaustive — code inspection, not live runtime)

Two helper patterns are used consistently; helpers are kept **local per module** (not shared) by deliberate design — each file's helpers are `underscore`-prefixed and private to that file, as documented in the module docstrings of `medications.py:10-16`, `conditions.py:11-19`, `symptoms.py:11-16` — `VERIFIED (repository: docstring text)`.

| Pattern | Code in repository | Used by (file:lines) |
|---|---|---|
| `_assert_patient_owned(patient_id, ...)` | `select(Patient.id).where(Patient.id == patient_id, Patient.user_id == current_user.id)` then `raise HTTPException(404, "Patient not found.")` if `scalar_one_or_none() is None` | `patients.py:37-44`, `medications.py:58-69`, `conditions.py:47-59`, `symptoms.py:49-60`, `timeline.py:30-38`, `schedule.py:129-141`, `analysis.py:37-44` |
| `_get_owned_*` via join through `Patient` | `select(<Resource>).join(Patient, Patient.id == <Resource>.patient_id).where(<Resource>.id == resource_id, Patient.user_id == current_user.id)` then `raise HTTPException(404, "<Resource> not found.")` if none | `patients.py:37-44 (_get_owned_patient)`, `medications.py:72-89 (_get_owned_medication)`, `conditions.py:61-75 (_get_owned_condition)`, `schedule.py:143-159 (_get_owned_medication)`, `schedule.py:162-183 (_get_owned_dose` joins `MedicationDose→Medication→Patient→ReferenceDrug`) |

**VERIFIED per router (repository: file contents cited):**

- **patients.py** — `VERIFIED (repository: `patients.py:37-44`, `54-65`, `69-77`, `107-121`)`: code for `GET /patients` is `select(Patient).where(Patient.user_id == current_user.id).order_by(Patient.created_at)`; code for `POST /patients` sets `user_id=current_user.id`; code for `GET /patients/{id}` and `PUT /patients/{id}` calls `_get_owned_patient` which raises `404` if not owned. `DELETE /patients/{id}` has no route — `VERIFIED (repository: no `delete` decorator in file; `backend/tests/test_patients_api.py:114-125` asserts `405` via `TestClient`)`.
- **medications.py** — `VERIFIED (repository: `medications.py:58-69`, `72-89`, `126-147`, `212-269`, `270-292`)`: code for `GET /patients/{id}/medications` and `POST /patients/{id}/medications` calls `_assert_patient_owned`; code for `PUT /medications/{id}` and `DELETE /medications/{id}` calls `_get_owned_medication` via `Patient` join. If `condition_id` is supplied, code validates `Condition.patient_id == patient_id` else raises `HTTPException(400, "condition_id does not reference a condition owned by this patient.")` (`medications.py:106-117`); `drug_id` validation is `select(ReferenceDrug.id).where(ReferenceDrug.id == drug_id)` else raises `HTTPException(404, "Reference drug not found.")` (`medications.py:91-98`). Timeline side-effects `medication_started` / `medication_discontinued` are written only after the ownership check in the same transaction — `VERIFIED (repository: `medications.py:191-210`, `240-254`)`.
- **conditions.py** — `VERIFIED (repository: `conditions.py:47-59`, `61-75`, `87-114`, `125-171`)`: `POST /patients/{id}/conditions` calls `_assert_patient_owned`; `PUT /conditions/{id}` calls `_get_owned_condition` via `Patient` join. No `GET` route exists — `VERIFIED (repository: file contains only `post` and `put` decorators; module docstring `conditions.py:11-13` states frozen spec)`.
- **symptoms.py** — `VERIFIED (repository: `symptoms.py:49-60`, `100-145`, `157-173`)`: `POST /patients/{id}/symptoms` and `GET /patients/{id}/symptoms` call `_assert_patient_owned`; optional `condition_id`/`medication_id` validated with `select(...).where(Condition|Medication.patient_id == patient_id)` else `HTTPException(400, ...)` (`symptoms.py:62-81`). No `PUT`/`DELETE` — `VERIFIED (repository: only `post`/`get` decorators)`.
- **schedule.py** — `VERIFIED (repository: `schedule.py:129-141`, `143-159`, `162-183`, `276-373`, `385-441`, `442-495`)`: `POST /medications/{id}/schedule` calls `_get_owned_medication`; `GET /patients/{id}/doses/upcoming` calls `_assert_patient_owned` then `_sweep_missed_doses`; `POST /doses/{id}/mark` calls `_get_owned_dose` (joins `MedicationDose→Medication→Patient`). The sweep `_sweep_missed_doses` is `select(MedicationDose, ReferenceDrug.name).join(...).where(Medication.patient_id == patient_id, MedicationDose.status.is_(None), MedicationDose.scheduled_time < now)` — `VERIFIED (repository: `schedule.py:234-258`) — therefore it is scoped to the same `patient_id` already authorized.
- **timeline.py** — `VERIFIED (repository: `timeline.py:30-38`, `46-63`)`: `GET /patients/{id}/timeline` calls `_assert_patient_owned`, then `select(TimelineEvent).where(TimelineEvent.patient_id == patient_id).order_by(TimelineEvent.event_time.desc())` matching `idx_timeline_patient` from `001_initial_schema.sql:174`.
- **analysis.py** — `VERIFIED (repository: `analysis.py:37-48`, `62-84`, `99-116`)`: `POST /patients/{id}/analyze` and `GET /patients/{id}/analysis` call `_assert_patient_owned`.
- **reference_drugs.py** — `VERIFIED (repository: `reference_drugs.py:45-75`, `001_initial_schema.sql:211-214`)`: `GET /reference-drugs/search` is **not patient-scoped**; code requires `Depends(get_current_user)` but performs `select(ReferenceDrug).where(ReferenceDrug.name.ilike(...))` with no `user_id` filter. This matches the RLS policy `for select using (auth.role() = 'authenticated')` on `reference_drugs` — shared reference data by design, consistent with `medications.py:91-98` treating the catalog as globally readable.

**VERIFIED (repository: `grep -rn "user_id" backend/app/api/v1/` shows only `Patient.user_id == current_user.id` and `user_id=current_user.id`):** no router reads `user_id` from request body or trusts a client-supplied owner identifier.

### 9.4 Non-disclosure: code raises 404, never 403

**VERIFIED (repository):** every `_assert_patient_owned` and `_get_owned_*` is `if scalar_one_or_none() is None: raise HTTPException(status_code=404, detail="<Resource> not found.")` — `VERIFIED (repository: `patients.py:41-45`, `medications.py:64-69`, `79-86`, `conditions.py:54-59`, `68-74`, `symptoms.py:57-60`, `timeline.py:36-40`, `schedule.py:136-141`, `150-157`, `174-181`, `analysis.py:41-46`)`. Grep for ownership-related `403` is `VERIFIED (repository: `grep -rn "403" backend/app/api/v1/` in ownership helpers returns zero; only docstrings mention "never 403" as intent)`.

**VERIFIED (repository — docstrings) + VERIFIED (empirical experiment where tests executed):** the docstrings in `patients.py:13-16`, `medications.py:10-16`, `conditions.py:11-19`, `symptoms.py:11-16`, `timeline.py:11-14`, `schedule.py:11-13`, `analysis.py:14-16` state that non-owned/missing resources are not confirmed via `403`. Integration tests observe this at runtime via `TestClient`:
- `backend/tests/test_patients_api.py:97` `test_patient_owned_by_another_user_is_not_visible` — `VERIFIED (repository: file exists; not live-executed in this hardening pass)`,
- `backend/tests/test_conditions_api.py:100` `test_create_condition_for_patient_owned_by_another_user_returns_404` and `:151` `test_condition_owned_by_another_user_is_not_updatable`,
- `backend/tests/test_medications_api.py:183` `test_medication_owned_by_another_user_is_not_visible`,
- `backend/tests/test_symptoms_api.py:220` `test_create_symptom_for_patient_owned_by_another_user_returns_404` and `:289` `test_list_symptoms_for_patient_owned_by_another_user_returns_404`,
- `backend/tests/test_schedule_api.py:231` `test_generate_schedule_for_medication_owned_by_another_user_returns_404`, `:444` `test_upcoming_doses_for_patient_owned_by_another_user_returns_404`, `:610` `test_mark_dose_owned_by_another_user_returns_404`,
- `backend/tests/test_timeline_api.py:286` `test_timeline_for_patient_owned_by_another_user_returns_404`,
- `backend/tests/test_analysis_api.py:92` `test_analyze_for_patient_owned_by_another_user_returns_404` and `:136` `test_list_analysis_runs_for_patient_owned_by_another_user_returns_404` — all `VERIFIED (repository: grep for def names)` to assert `status_code == 404`. Live execution of these tests requires a Supabase Postgres instance; they were **not re-executed live in this hardening pass** except for `test_security.py` (see §9.7).

This matches the disclosure posture in §8.6 (authentication collapses to generic `401`).

### 9.5 Reference data — authenticated but not owner-scoped

**VERIFIED (repository: `001_initial_schema.sql:211-222` and `backend/app/api/v1/reference_drugs.py:45-75`):**

- RLS policies are `for select using (auth.role() = 'authenticated')` on `reference_drugs`, `interaction_rules`, `adr_rules` — not `auth.uid() = user_id` — `VERIFIED (repository: `001_initial_schema.sql:211-222`)`.
- API code for `GET /reference-drugs/search` enforces `Depends(get_current_user)` (so unauthenticated requests receive `401` as routed through `security.py`) but applies no `user_id` filter and the tables have no `user_id` column to filter by — `VERIFIED (repository: `reference_drugs.py:54-75`, `001_initial_schema.sql:55-62` for table definition)`.

This is **by design** per the schema's shared-reference-data model; no ownership enforcement is missing here — `VERIFIED (repository)` as above.

### 9.6 Relationship to Row Level Security

**VERIFIED (repository):**

- `001_initial_schema.sql` contains `enable row level security` on all patient and reference tables — `VERIFIED (repository: grep "enable row level security" shows 11 tables)`.
- Policies are keyed on `auth.uid() = user_id` for patient tables and `auth.role() = 'authenticated'` for reference tables — `VERIFIED (repository: `001_initial_schema.sql:171-208`)`.
- The string `FORCE ROW LEVEL SECURITY` does **not** appear in any migration — `VERIFIED (repository: `grep -n "FORCE" 001_initial_schema.sql` returns zero)`.
- Application database access is via `create_async_engine(settings.database_url)` in `backend/app/db/session.py:13` with `database_url` defined in `backend/app/core/config.py:45` and example `DATABASE_URL=postgresql+asyncpg://postgres:...@db....supabase.co:5432/postgres` in `backend/.env.example:2` and `backend/.env:2` — `VERIFIED (repository: cited files/lines)`. No code in `backend/` uses Supabase PostgREST or pooler paths that would populate `auth.uid()` from the JWT — `VERIFIED (repository: `grep -rn "postgrest\|pooler\|auth.uid" backend/` returns only `auth.py` comments, not runtime usage)`.

**VERIFIED (official documentation):** PostgreSQL documentation for `CREATE POLICY` / `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` states that table owners bypass RLS unless `FORCE ROW LEVEL SECURITY` is set. `UNVERIFIED / REQUIRES RESEARCH` (carried from §8.9): whether the `postgres` role used by `DATABASE_URL` is the owner of these tables in the live database, and therefore whether RLS provides any enforcement against this backend's connection, has **not** been verified against the live database in this review. Per the verification standard, no live-runtime RLS enforcement is claimed.

Application-layer filters in §9.3 are the **repository-verified** enforcement boundary, independent of whatever RLS does or does not additionally enforce — `VERIFIED (repository: §9.3 query citations)`.

### 9.7 Test coverage

**VERIFIED (repository: `backend/tests/` directory listing and `grep -n "def test"`):**

- `backend/tests/test_security.py` — unit tests for JWT paths in §8 — `VERIFIED (empirical experiment: `pytest backend/tests/test_security.py -v --override-ini="asyncio_mode=auto"` → 5 passed in this review)`. It does not cover ownership; ownership is covered below.
- Integration tests that bypass JWT via `app.dependency_overrides[get_current_user]` and assert `404` for cross-user access — `VERIFIED (repository: file contents, not live-executed in this hardening pass beyond `test_security.py`)`:
  - `test_patients_api.py:97` `test_patient_owned_by_another_user_is_not_visible`
  - `test_conditions_api.py:100` `test_create_condition_for_patient_owned_by_another_user_returns_404` and `:151` `test_condition_owned_by_another_user_is_not_updatable`
  - `test_medications_api.py:183` `test_medication_owned_by_another_user_is_not_visible`
  - `test_symptoms_api.py:220` `test_create_symptom_for_patient_owned_by_another_user_returns_404` and `:289` `test_list_symptoms_for_patient_owned_by_another_user_returns_404`
  - `test_schedule_api.py:231` `test_generate_schedule_for_medication_owned_by_another_user_returns_404`, `:444` `test_upcoming_doses_for_patient_owned_by_another_user_returns_404`, `:610` `test_mark_dose_owned_by_another_user_returns_404`
  - `test_timeline_api.py:286` `test_timeline_for_patient_owned_by_another_user_returns_404`
  - `test_analysis_api.py:92` `test_analyze_for_patient_owned_by_another_user_returns_404` and `:136` `test_list_analysis_runs_for_patient_owned_by_another_user_returns_404`
- Live execution of the integration suite requires a Supabase Postgres instance with `auth.users` rows (see `backend/tests/conftest.py`) and is `UNVERIFIED` live in this ephemeral Arena container beyond `test_security.py`.

### 9.8 Conventions, gaps, and corrections to prior documentation

1. **Forward-reference resolved — VERIFIED (repository):** §8.7 (`ARCHITECTURE_DECISIONS.md:217`) and §8.9 (`:231`) previously contained the string `"see Section 9"` while the file was 234 lines ending at §8.9. After the initial Section 9 addition (commit `ff3d3bc`), `grep -n "Section 9"` now resolves to the section added here — `VERIFIED (repository: `grep -n "Section 9"` after that commit)`.

2. **Helper locality is intentional, not duplication debt — RETAINED:** ownership helpers are duplicated per module; module docstrings in `medications.py:14-16`, `conditions.py:17-19`, `symptoms.py:14-16` explicitly justify keeping them local because they are `underscore`-prefixed and private. No shared helper is introduced — `VERIFIED (repository: docstring text)`.

3. **No role-based access control exists — VERIFIED (repository):** `CurrentUser` has only `id`/`email` (`security.py:97-102`); `grep -rn "is_admin\|is_owner\|role" backend/app/api/` for access-control branching returns zero ownership-role checks — `VERIFIED (repository)`. Any future multi-role requirement would be a new design.

4. **No implementation change required by this review — VERIFIED (repository):** every documentation claim about ownership previously implied (404 non-disclosure, `Patient.user_id` comparison, shared reference data) is present in the code as cited in §9.3–§9.5. Documentation is the layer updated here; no `backend/` code was modified — `VERIFIED (repository: `git diff main --stat` shows only `ARCHITECTURE_DECISIONS.md`)`.

---

## 10. Deterministic Analysis Layer

**Scope and evidence labeling:** every normative statement in §10 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) cited; `VERIFIED (official documentation)` — authoritative docs; `VERIFIED (empirical experiment)` — observed by running the test/command cited; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository. Implementation is the source of truth. No planned features are documented as implemented; where behavior is incomplete it is explicitly noted.

### 10.1 Architecture overview — purpose, inputs, outputs, position

**VERIFIED (repository: `backend/app/analysis/drug_interaction_engine.py:1-15`, `adr_engine.py:1-15`, `adherence_engine.py:1-24`, `safety_score_engine.py:1-19`, `timeline_engine.py:1-16`, `backend/app/services/langgraph_workflow.py:1-62`, `PROJECT_PHASES.md:79-115`):**

- **Purpose:** compute all safety-relevant conclusions deterministically from curated reference data and persisted patient data, without LLM inference — `VERIFIED (repository: `drug_interaction_engine.py:3-9` "LLM must never invent drug interactions", `adr_engine.py:3-9` "LLM must never invent ADRs", `safety_score_engine.py:9-19` "LLM must NEVER calculate safety scores")`.
- **Inputs:** `patient_id: UUID` + `AsyncSession` + persisted rows: `medications` (filtered to `status == "active"`), `interaction_rules`, `adr_rules`, `medication_doses`/`medication_schedule`, `timeline_events` — `VERIFIED (repository: `drug_interaction_engine.py:58-63`, `adr_engine.py:68-73`, `adherence_engine.py:111-127`, `timeline_engine.py:44-53`)`.
- **Outputs:** per-engine finding lists (`DrugInteractionFinding`, `ADRFinding`, `AdherenceFinding`), composed `SafetyScoreResult` (`safety_score: 0-100`, `risk_level: low|moderate|high`, `penalties: list[PenaltyEntry]` with full audit trail), and `TimelineContext` (chronologically ordered `TimelineEntry` list) — `VERIFIED (repository: `safety_score_engine.py:103-162`, `timeline_engine.py:27-42`)`.
- **Position in end-to-end pipeline:** Deterministic Layer sits between **Patient Data Layer** (patients/conditions/medications/symptoms/timeline_events persisted via ownership-checked REST endpoints) and **Evidence Retrieval / LLM Explanation Layer** — `VERIFIED (repository: `langgraph_workflow.py:12-22` pipeline order `patient_context_builder → safety_score_engine → evidence_retrieval → timeline_engine → llm_explanation → persist`; spec p5/p8 mapping in `safety_score_engine.py:1-7` and `PROJECT_PHASES.md:103-115`)`.

### 10.2 Execution flow — verified implementation

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:12-22`, `270-356`, `backend/app/api/v1/analysis.py:62-84`, `backend/app/analysis/safety_score_engine.py:231-258`):**

1. **Request entry point:** `POST /patients/{patient_id}/analyze` in `backend/app/api/v1/analysis.py:62-84` — `VERIFIED (repository: `analysis.py:46` `_assert_patient_owned` before invoking workflow)`. The handler calls `await run_analysis(patient_id, db)` and then re-fetches the persisted `AnalysisRun` by `analysis_run_id` — `VERIFIED (repository: `analysis.py:76-82`)`.
2. **Engine invocation order (LangGraph StateGraph, linear):** `START → patient_context_builder → safety_score_engine → evidence_retrieval → timeline_engine → llm_explanation → persist → END` — `VERIFIED (repository: `langgraph_workflow.py:328-336` `add_edge` chain)`.
3. **Data flow between engines:**
   - `patient_context_builder` builds `PatientContext` (patient + active conditions/medications/symptoms) — `VERIFIED (repository: `langgraph_workflow.py:176-180`, `backend/app/services/patient_context_builder.py`)`.
   - `safety_score_engine` internally calls `detect_drug_interactions()` + `detect_adrs()` + `analyze_adherence()` and composes `SafetyScoreResult` — `VERIFIED (repository: `safety_score_engine.py:231-258`)`. No duplicate direct calls from the graph — `VERIFIED (repository: `langgraph_workflow.py:18-32` "Safety Score node is not three separate engine calls")`.
   - `evidence_retrieval` receives `(patient_id, db, safety_score_result)` → `EvidenceBundle` with medical (from rule fields) + personal per-finding scoped `timeline_events` — `VERIFIED (repository: `langgraph_workflow.py:183-188`, `backend/app/services/evidence_retrieval.py`)`.
   - `timeline_engine` builds `TimelineContext` (`select(TimelineEvent).where(patient_id==...).order_by(event_time.asc())`) — `VERIFIED (repository: `langgraph_workflow.py:190-195`, `timeline_engine.py:44-53`) — unscoped, purely for LLM narrative context.
   - `llm_explanation` receives `(patient_context, safety_score_result, evidence_bundle, timeline_context)` → `LLMExplanationResult | (None, llm_error)` — `VERIFIED (repository: `langgraph_workflow.py:197-218`)`.
4. **Safety Score composition:** `BASE_SCORE (100) - sum penalties` floored at `MIN_SCORE (0)` → `risk_level` thresholds `>=70 low`, `>=40 moderate`, `<40 high` — `VERIFIED (repository: `safety_score_engine.py:36-82` constants, `247-252` computation)`. Penalties are per-finding: `INTERACTION_PENALTY_POINTS` / `ADR_PENALTY_POINTS` (`mild 5 / moderate 15 / severe 30`) and `ADHERENCE_PENALTY_POINTS` (`mild 5 / moderate 10 / severe 20`) via `_classify_adherence_severity` thresholds `0.80/0.50/0.25` — `VERIFIED (repository: `safety_score_engine.py:38-82`, `113-132`)`.
5. **Handoff to LangGraph/LLM workflow:** `persist` node serializes `SafetyScoreResult` (excluding live `PenaltyEntry.source` objects) to `analysis_runs.deterministic_result` + `safety_score`/`risk_level` columns + `llm_*` columns (nullable) and logs `analysis_run` timeline event — `VERIFIED (repository: `langgraph_workflow.py:220-273` `_persist_node`)`. `timeline_context` is **not** persisted in `deterministic_result` — `VERIFIED (repository: `langgraph_workflow.py:42-50` "timeline_context is deliberately NOT included")`.

### 10.3 Architecture diagram — verified implementation

**VERIFIED (repository: `langgraph_workflow.py:12-22` + `safety_score_engine.py:1-7`):** the diagram below matches the compiled `StateGraph` edges and the internal composition inside `safety_score_engine`.

```
                         ┌─────────────────────────────────────────────────┐
                         │         Deterministic Analysis Layer             │
                         │                                                 │
[Patient Data] ──► Patient Context Builder ──► Safety Score Engine ──┐     │
   (patients,                                   │  ┌─────────────────┤     │
    conditions,                                  │  │ detect_drug_inter│     │
    medications status=active,                   │  │ detect_adrs      │     │
    interaction_rules,                           │  │ analyze_adherence│     │
    adr_rules,                                   │  │ → penalties      │     │
    medication_doses,                            │  │ → safety_score   │     │
    timeline_events)                             │  │ → risk_level     │     │
                         └───────────────────────┴──┴─────────────────┘     │
                                          │                                │
                                          v                                │
                                Evidence Retrieval                           │
                                (medical: rule fields; personal: per-      │
                                 finding scoped timeline_events)            │
                                          │                                │
                                          v                                │
                                Timeline Engine                              │
                                (full timeline ASC, retrieval-only)        │
                                          │                                │
                                          └──────────────┬─────────────────┘
                                                         v
                                              LLM Explanation Node
                                              (generate_explanation — explains only)
                                                         │
                                                         v
                                              Persist Node
                                              (analysis_runs + analysis_run event)
```

*No Mermaid is used to avoid rendering dependence; ASCII reflects the linear `StateGraph` verified above.*

### 10.4 Deterministic logic vs orchestration vs LLM responsibilities

**VERIFIED (repository: engine docstrings + `langgraph_workflow.py` node factories):**

| Layer | Responsibility | What it does | What it never does |
|---|---|---|---|
| **Deterministic logic** (`backend/app/analysis/*.py`) | Compute findings, measurements, scores | `detect_drug_interactions` set-membership on `interaction_rules`; `detect_adrs` `IN (active drug ids)` with multiple per-drug findings; `analyze_adherence` counts `taken/missed/skipped/due` + `adherence_rate`; `calculate_safety_score` applies penalty maps + thresholds → `SafetyScoreResult`; `build_timeline_context` orders `ASC` | Never calls LLM, never invents severity, never mutates `medication_doses` (adherence), never scores adherence beyond counting — `VERIFIED (repository: `drug_interaction_engine.py:1-15`, `adr_engine.py:1-15`, `adherence_engine.py:1-24`, `safety_score_engine.py:9-19`, `timeline_engine.py:1-12`) |
| **Orchestration** (`backend/app/services/langgraph_workflow.py`) | Thread state, order nodes, persist | Builds `StateGraph` with 6 nodes in fixed order, closes over `db` session, serializes result, logs `analysis_run` event — `VERIFIED (repository: `langgraph_workflow.py:270-356`)` | Never computes clinical findings itself; never duplicates engine calls — `VERIFIED (repository: `langgraph_workflow.py:18-32`)` |
| **LLM** (`backend/app/services/llm_service.py` + `llm_providers.py`, Phase 15) | Explain already-computed deterministic output | `generate_explanation(patient_context, safety_score_result, evidence_bundle, timeline_context)` → `LLMExplanationResult(summary, reasoning, recommendations, confidence)` — `VERIFIED (repository: `langgraph_workflow.py:197-218` call site)`; currently `NotImplementedError` / `LLMExplanationError` caught → `llm_result: None, llm_error` and persist proceeds — `VERIFIED (repository: `langgraph_workflow.py:205-216`)` | Never computes, invents, or overrides `safety_score`/`risk_level` or findings — `VERIFIED (repository: `safety_score_engine.py:9-19` "LLM must NEVER calculate")` |

### 10.5 Drug Interaction Engine (Phase 10)

**VERIFIED (repository: `backend/app/analysis/drug_interaction_engine.py` + `backend/tests/test_drug_interaction_engine.py`):**

- **Scope:** only `Medication.status == "active"` are evaluated — `VERIFIED (repository: `58-63` `_get_active_drug_ids`)`; mirrors `GET /patients/{id}/doses/upcoming` Phase 8 filter — `VERIFIED (repository: docstring 21-27)`. `VERIFIED (empirical experiment: `test_excludes_non_active_medications` `:207`)`.
- **Matching:** `InteractionRule.drug_a_id IN (active) AND drug_b_id IN (active)` — pure set membership, inherently direction-independent — `VERIFIED (repository: `85-94`)`; `VERIFIED (empirical experiment: `test_detection_is_direction_independent` `:154`)`.
- **Severity:** each `DrugInteractionFinding` surfaces `rule.severity` as-is (`severity=rule.severity`) — `VERIFIED (repository: `103-110`)`; `highest_severity()` is reporting convenience ordered `mild < moderate < severe` — `VERIFIED (repository: `28-30` + `134-149`)`; `VERIFIED (empirical experiment: `test_highest_severity_*` `:313-326`)`.
- **Output:** `DrugInteractionFinding(interaction_rule_id, drug_a/b_id+name, severity, mechanism, recommendation, source)` denormalized with drug names — `VERIFIED (repository: `38-48`)`; empty if `<2` distinct active drugs — `VERIFIED (repository: `68-70`)`.

### 10.6 ADR Engine (Phase 11)

**VERIFIED (repository: `backend/app/analysis/adr_engine.py` + `backend/tests/test_adr_engine.py`):**

- **Scope:** same `status == "active"` filter — `VERIFIED (repository: `62-73` + docstring `19-28`; `VERIFIED (empirical experiment: `test_excludes_non_active_medications` `:177`)`.
- **Matching:** `AdrRule.drug_id IN (active drug ids)` — single-drug property, no directionality — `VERIFIED (repository: `98-106`)`; one drug may yield **multiple findings** (e.g. Lisinopril → "Dry cough" + "Hyperkalemia") — `VERIFIED (repository: `37-44`)`; `VERIFIED (empirical experiment: `test_single_drug_with_multiple_adr_rules_returns_all` `:132`)`.
- **Severity:** mirrors interaction scope — `severity` / `frequency_class` surfaced as-is — `VERIFIED (repository: `57-63`, `108-116`)`; `highest_severity()` same ordering — `VERIFIED (repository: `28-30`, `131-146`)`.
- **Helpers:** `_get_active_drug_ids` and `highest_severity` are **re-implemented locally** not imported from `drug_interaction_engine.py` — retained per-module helper convention — `VERIFIED (repository: docstring `45-53` citing `conditions.py` rationale)`.

### 10.7 Adherence Engine (Phase 12, measurement-only)

**VERIFIED (repository: `backend/app/analysis/adherence_engine.py` + `backend/tests/test_adherence_engine.py`):**

- **Role:** measurement only — `AdherenceFinding` carries `taken/missed/skipped/due/adherence_rate` and **no severity** — `VERIFIED (repository: `31-42` dataclass, docstring `1-24` "never classifies, scores, or interprets")`.
- **Due / missed definition (independent of sweep):** `due = scheduled_time <= now()` any `status`; `taken = status=='taken'`; `skipped = status=='skipped'`; `missed = status=='missed' PLUS status IS NULL` (overdue unmarked is functionally missed) — `VERIFIED (repository: `57-84` docstring + `111-127` `case` counts)`; `VERIFIED (empirical experiment: `test_all_due_doses_unmarked_counts_as_fully_missed` `:136`, `test_mixed_taken_missed_skipped_counts_correctly` `:176`)`.
- **No writes:** `analyze_adherence()` does **not** invoke or duplicate the Phase 9 lazy sweep, does not mutate `medication_doses.status` — `VERIFIED (repository: `82-89` "performs no writes", `grep -n "sweep\|log_timeline" adherence_engine.py` = 0)`.
- **Scope:** only active medications, `scheduled_time <= now()`, future doses excluded, medications with `due==0` omitted — `VERIFIED (repository: `111-143` query + filter)`.

### 10.8 Safety Score Engine (Phase 12, composition + policy)

**VERIFIED (repository: `backend/app/analysis/safety_score_engine.py` + `backend/tests/test_safety_score_engine.py`):**

- **Sole source of truth:** `calculate_safety_score()` is the **only** code that computes `safety_score`/`risk_level` — calls `detect_drug_interactions` + `detect_adrs` + `analyze_adherence` then applies constants — `VERIFIED (repository: `231-258`)`; LLM never calculates — `VERIFIED (repository: docstring `9-19`)`.
- **Constants are implementation defaults, not clinical guidelines:** `BASE_SCORE=100`, `MIN_SCORE=0`, `INTERACTION_PENALTY_POINTS {mild 5, moderate 15, severe 30}`, `ADR_PENALTY_POINTS {5,15,30}`, `ADHERENCE_ADEQUATE_THRESHOLD=0.80`, `ADHERENCE_MODERATE_THRESHOLD=0.50`, `ADHERENCE_SEVERE_THRESHOLD=0.25`, `ADHERENCE_PENALTY_POINTS {mild 5, moderate 10, severe 20}`, `RISK_LEVEL_LOW_THRESHOLD=70`, `RISK_LEVEL_MODERATE_THRESHOLD=40` — `VERIFIED (repository: `36-82` with comments "implementation defaults")**; `UNVERIFIED / REQUIRES RESEARCH` for clinical validity except the 80% adequate-adherence band which is a commonly-cited rule-of-thumb — `VERIFIED (repository: docstring `49-54`)`.
- **Adherence severity classified only here:** `_classify_adherence_severity()` maps `adherence_rate` → `None / mild / moderate / severe` via thresholds above — `VERIFIED (repository: `113-132`)`; `VERIFIED (empirical experiment: `test_classify_adherence_*` `:121-162`)`.
- **Risk levels:** `score >=70 low`, `>=40 moderate`, `<40 high` — `VERIFIED (repository: `75-82`, `147-152`)`; `VERIFIED (empirical experiment: `test_risk_level_*` `:171-191`)`.
- **Audit trail:** `SafetyScoreResult` exposes `starting_score`, `total_points_deducted`, all finding lists, and `penalties: list[PenaltyEntry]` where each `PenaltyEntry` carries `category`, `description`, `severity`, `points`, `source` (live finding object) for traceability — `VERIFIED (repository: `103-162`)`; `VERIFIED (empirical experiment: `test_penalty_entries_reference_their_source_finding` `:358`)`.
- **Math:** `total_points_deducted = sum penalties`; `safety_score = max(BASE_SCORE - total, MIN_SCORE)` — `VERIFIED (repository: `247-252`).

### 10.9 Timeline Engine — retrieval-only narrative context (Phase 14)

**VERIFIED (repository: `backend/app/analysis/timeline_engine.py`):**

- **Responsibility:** retrieve and structure the patient's **full, unscoped** timeline as narrative context for the LLM — does **not** perform pattern detection, trend analysis, or scoring — `VERIFIED (repository: docstring `1-12`)`.
- **Ordering:** `select(TimelineEvent).where(patient_id==...).order_by(event_time.asc())` — oldest-first, opposite of `GET /patients/{id}/timeline`’s `DESC` feed — `VERIFIED (repository: `44-53`)`; `VERIFIED (repository: docstring `37-43`)`.
- **Placement:** `analysis/timeline_engine.py` per spec p6 — `VERIFIED (repository: docstring `14-16`)`; runs **after** `evidence_retrieval` in the graph — `VERIFIED (repository: `langgraph_workflow.py:32-36`)`.
- **Cap/pagination:** none — returns full timeline, matching Phase 7 API’s uncapped behavior — `VERIFIED (repository: docstring `29-33`)`.

### 10.10 Exposure and API wiring (Phase 14)

**VERIFIED (repository: `backend/app/api/v1/analysis.py:62-116`, `backend/app/services/langgraph_workflow.py:270-356`, `PROJECT_PHASES.md:103-115`):**

- Phases 10-12 engines were **internal-only** until Phase 14 — `VERIFIED (repository: `drug_interaction_engine.py:14-19`, `adr_engine.py:13-18`, `adherence_engine.py:31-34` "Not exposed via any HTTP route yet" + `PROJECT_PHASES.md` notes)`.
- Phase 14 wires `POST /patients/{id}/analyze` → `run_analysis(patient_id, db)` → persist → `201` with `AnalysisRun`, and `GET /patients/{id}/analysis` → history ordered `created_at DESC` — `VERIFIED (repository: `analysis.py:62-116`, `220-236` Persist Node + `analysis.py:99-116` list route)`. Ownership is `_assert_patient_owned` (404 if not owned) — `VERIFIED (repository: `analysis.py:37-48`)` and documented in p9.
- No other HTTP route exposes these engines directly.

### 10.11 Implementation status — no speculation

- **Implemented and verified:** all items in p10.5-p10.10 as cited above — `VERIFIED (repository)`.
- **Not yet implemented (explicit):** LLM explanation for these findings — `backend/app/services/llm_service.py` Phase 15 raises `NotImplementedError` / `LLMExplanationError` caught as `llm_result: None` — `VERIFIED (repository: `langgraph_workflow.py:197-218`)` and `PROJECT_PHASES.md:103-115` Phase 15 unchecked. No future engine or scoring formula is documented as implemented here.
- No buried assumptions; thresholds marked `UNVERIFIED` where clinical validation is pending — `VERIFIED (repository: `safety_score_engine.py:31-35` comment)`.

---

## 11. LangGraph Workflow & AI Orchestration

**Scope and evidence labeling:** every normative statement in §11 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative LangGraph/httpx/PostgreSQL docs; `VERIFIED (empirical experiment)` — observed by running the test/command cited; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository. Implementation is the source of truth. No future engine, scoring formula, or provider behavior is documented as implemented beyond what the repository contains.

### 11.1 Overview

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:1-66`, `backend/app/services/patient_context_builder.py:1-24`, `backend/app/services/evidence_retrieval.py:1-36`, `backend/app/services/llm_service.py:1-28`, `backend/app/services/llm_providers.py:1-28` + `PROJECT_PHASES.md:103-115`):**

The LangGraph Workflow is the end-to-end analysis pipeline that composes all deterministic and retrieval services and, when configured, the LLM explanation layer into a single persisted `analysis_runs` record. It is an **orchestration layer** — it computes no clinical findings itself and invents no medical facts — `VERIFIED (repository: `langgraph_workflow.py:18-32` "Safety Score node is not three separate engine calls", docstring `1-22` wiring description)`.

- **What it orchestrates:** Patient Context Builder (fresh retrieval) → Deterministic Analysis Layer (Safety Score Engine composing Phases 10-12) → Evidence Retrieval (Phase 13, application service) → Timeline Engine (Phase 14, retrieval-only) → LLM Explanation (Phase 15, explain-only) → Persist (writes `analysis_runs` + `analysis_run` timeline event) — `VERIFIED (repository: `langgraph_workflow.py:12-22` + `328-336` edge chain)`.
- **Where it lives:** `backend/app/services/langgraph_workflow.py` building a `langgraph.graph.StateGraph` (`StateGraph(AnalysisState)`) via `from langgraph.graph import END, START, StateGraph` — `VERIFIED (repository: `langgraph_workflow.py:90` import + `312-337` `_build_graph`)` and `VERIFIED (official documentation)` for LangGraph `StateGraph` API (`add_node`/`add_edge`/`compile`/`ainvoke`).
- **How it is invoked:** `POST /patients/{patient_id}/analyze` in `backend/app/api/v1/analysis.py:62-84` calls `await run_analysis(patient_id, db)` after `await _assert_patient_owned(patient_id, current_user, db)` (404 if not owned) and then re-fetches the persisted `AnalysisRun` — `VERIFIED (repository: `analysis.py:37-48`, `62-84`)` and `VERIFIED (repository: `langgraph_workflow.py:339-356` `run_analysis` + `analysis.py:76-82` re-fetch)`.

### 11.2 End-to-end execution flow

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:12-22`, `270-356`, `backend/app/api/v1/analysis.py:62-84`, `backend/app/analysis/safety_score_engine.py:231-258`, `backend/app/analysis/timeline_engine.py:44-53`):**

1. **Request entry and authorization:** `POST /patients/{patient_id}/analyze` requires `Depends(get_current_user)` and first runs `select(Patient.id).where(Patient.id==patient_id, Patient.user_id==current_user.id)` — `VERIFIED (repository: `analysis.py:37-48`)` — raising `404` if not owned. No `user_id` is taken from the request body — `VERIFIED (repository: `analysis.py:73-74` `user_id` only via `current_user.id`)`. `GET /patients/{patient_id}/analysis` uses the same gate to list history `order_by(AnalysisRun.created_at.desc())` — `VERIFIED (repository: `analysis.py:99-116`)`.
2. **Graph invocation:** `run_analysis(patient_id, db)` builds the graph bound to the request `db` session via factory closures (`_patient_context_node(db)` etc.) and calls `await graph.ainvoke({"patient_id": patient_id})` — `VERIFIED (repository: `langgraph_workflow.py:339-356`)`. `AnalysisState` is pure data (no `db` inside) — `VERIFIED (repository: `langgraph_workflow.py:46-62` `AnalysisState` comment "DB session is intentionally NOT part of this state")`.
3. **Linear node order (verified edges):** `START → patient_context_builder → safety_score_engine → evidence_retrieval → timeline_engine → llm_explanation → persist → END` — `VERIFIED (repository: `langgraph_workflow.py:328-336` + docstring `12-22`)`. This order is **not** parallelized — Evidence Retrieval depends on `safety_score_result`, Timeline Engine depends on nothing deterministic but is placed after Evidence Retrieval by design (see §11.4).
4. **Deterministic composition inside `safety_score_engine` node:** the graph has **one** Safety Score node; that node calls `await calculate_safety_score(patient_id, db)` which internally runs `detect_drug_interactions` + `detect_adrs` + `analyze_adherence` and returns `SafetyScoreResult` — `VERIFIED (repository: `langgraph_workflow.py:18-32` + `179-182` + `safety_score_engine.py:231-258`)`. No duplicate direct engine calls from the graph — `VERIFIED (repository: `grep -n "detect_drug_interactions" backend/app/services/langgraph_workflow.py` = 0 outside that comment).
5. **Evidence and timeline handoff:** `evidence_retrieval` receives `(patient_id, db, safety_score_result)` → `EvidenceBundle` (medical from rule fields + personal per-finding scoped `timeline_events`) — `VERIFIED (repository: `langgraph_workflow.py:183-188`, `evidence_retrieval.py:214-249`)` — then `timeline_engine` builds `TimelineContext` via `select(TimelineEvent).where(patient_id==...).order_by(event_time.asc())` — `VERIFIED (repository: `langgraph_workflow.py:190-195`, `timeline_engine.py:44-53`)`.
6. **LLM handoff:** `llm_explanation` receives `(patient_context, safety_score_result, evidence_bundle, timeline_context)` → `LLMExplanationResult | (None, llm_error)` — `VERIFIED (repository: `langgraph_workflow.py:197-218` + `llm_service.py:362-384` signature)`.
7. **Persist and output:** `persist` serializes `SafetyScoreResult` (excluding live `PenaltyEntry.source` objects) to `deterministic_result` JSONB + `safety_score`/`risk_level` columns + nullable `llm_*` columns and logs `analysis_run` timeline event — `VERIFIED (repository: `langgraph_workflow.py:220-273` `_persist_node` + serialization helpers `65-82`)`. The persisted `AnalysisRun` is returned via `state["analysis_run_id"]` to the API layer — `VERIFIED (repository: `langgraph_workflow.py:355-356` + `analysis.py:79-84`)`.

### 11.3 Verified LangGraph workflow diagram

**VERIFIED (repository: `langgraph_workflow.py:12-22` + `safety_score_engine.py:1-7` + `328-336` edges + `231-258` internal composition):** the ASCII below matches the compiled `StateGraph`. No Mermaid is used.

```
                                    LangGraph StateGraph (linear)
                                    backend/app/services/langgraph_workflow.py

  [HTTP] POST /patients/{id}/analyze  ──►  run_analysis(patient_id, db)
          │  ( _assert_patient_owned)              │
          │                                         v
          │                              ┌─────────────────────────┐
          └──────────────────────────────▶│ patient_context_builder │──► PatientContext
                                         │ (services/patient_      │    (fresh, no cache)
                                         │  context_builder.py)     │
                                         └────────────┬────────────┘
                                                      │
                                                      v
                                         ┌─────────────────────────┐
                                         │ safety_score_engine     │──► SafetyScoreResult
                                         │  ┌───────────────────┐  │    (safety_score 0-100,
                                         │  │ detect_drug_inter │  │     risk_level low|mid|high,
                                         │  │ detect_adrs       │  │     penalties with source)
                                         │  │ analyze_adherence │  │
                                         │  │ → BASE 100 - Σ -─►│  │
                                         │  └───────────────────┘  │
                                         └────────────┬────────────┘
                                                      │
                                                      v
                                         ┌─────────────────────────┐
                                         │ evidence_retrieval      │──► EvidenceBundle
                                         │ (services/evidence_     │    (medical: rule fields,
                                         │  retrieval.py)          │     personal: per-finding
                                         │                         │     timeline_events scoped)
                                         └────────────┬────────────┘
                                                      │
                                                      v
                                         ┌─────────────────────────┐
                                         │ timeline_engine         │──► TimelineContext
                                         │ (analysis/timeline_    │    (full timeline ASC,
                                         │  engine.py)             │     retrieval-only)
                                         └────────────┬────────────┘
                                                      │
                                                      v
                                         ┌─────────────────────────┐
                                         │ llm_explanation         │──► LLMExplanationResult
                                         │ (services/llm_service   │    | (None, llm_error) on
                                         │  .py → llm_providers.py)│    failure — deterministic
                                         │  Gemini primary,        │    still persists
                                         │  OpenRouter fallback    │
                                         └────────────┬────────────┘
                                                      │
                                                      v
                                         ┌─────────────────────────┐
                                         │ persist                 │──► analysis_runs row
                                         │  _serialize_safety_     │    (deterministic_result
                                         │  score_result → JSONB,  │     + safety_score/risk_level
                                         │  log_timeline_event     │     + llm_* nullable,
                                         │  "analysis_run"         │     + timeline event)
                                         └─────────────────────────┘
                                                      │
                                                      v
                                                   [END]
```

*Deterministic Analysis Layer is the boxed `detect_*` trio inside `safety_score_engine`; Evidence Retrieval and Timeline Engine are *retrieval/structuring* services, not scoring — as coded.*

### 11.4 Node-by-node responsibilities

**VERIFIED (repository: `langgraph_workflow.py:176-273` node factories + individual service/engine docstrings):**

| Node (graph name) | Module file | Input state keys | Output state keys | Responsibility (verified) | What it never does |
|---|---|---|---|---|---|
| `patient_context_builder` | `backend/app/services/patient_context_builder.py` | `patient_id` | `patient_context: PatientContext` | Builds fresh `PatientContext` (demographics + `active_conditions` where `status != "resolved"` + `active_medications` where `status=="active"` + `active_symptoms` where `resolved_date IS NULL`) — `VERIFIED (repository: `55-116`)`; no writes, no scoring — `VERIFIED (repository: docstring `1-24`)` | Never caches, never checks ownership (`Assumes caller has already verified` — `VERIFIED (repository: `109-116`)) |
| `safety_score_engine` | `backend/app/analysis/safety_score_engine.py` via `langgraph_workflow.py:179-182` | `patient_id` (and `db` closure) | `safety_score_result: SafetyScoreResult` | Composes `detect_drug_interactions` + `detect_adrs` + `analyze_adherence` → applies `BASE_SCORE - Σ penalties` floored at `MIN_SCORE` → `risk_level` thresholds — `VERIFIED (repository: `safety_score_engine.py:231-258`, `36-82` constants)` | Never calls LLM, never invents severity — `VERIFIED (repository: docstring `9-19`)` |
| `evidence_retrieval` | `backend/app/services/evidence_retrieval.py` | `patient_id`, `safety_score_result` | `evidence_bundle: EvidenceBundle` | For each finding: medical evidence from finding fields (no re-query) + personal evidence via per-finding scoped `timeline_events` lookup (`ref_id` vs `payload.medication_id` vs `condition_status_changed`) — `VERIFIED (repository: `83-117` medical helpers + `133-198` personal query + `214-249` `retrieve_evidence`)` | Never re-queries `interaction_rules`/`adr_rules` — `VERIFIED (repository: `grep -n "select.*InteractionRule" evidence_retrieval.py` = 0)` |
| `timeline_engine` | `backend/app/analysis/timeline_engine.py` via `langgraph_workflow.py:190-195` | `patient_id` | `timeline_context: TimelineContext` | Retrieves full timeline `order_by(event_time.asc())` as in-memory narrative context — `VERIFIED (repository: `timeline_engine.py:44-53`, docstring `1-12` "does NOT perform pattern detection")` | Never scores, never persists, never filters beyond `patient_id` — `VERIFIED (repository: docstring `29-33` "No artificial cap")` |
| `llm_explanation` | `backend/app/services/llm_service.py` via `langgraph_workflow.py:197-218` | `patient_context`, `safety_score_result`, `evidence_bundle`, `timeline_context` | `llm_result: LLMExplanationResult | None`, `llm_error: str | None` | Builds prompt (`_SYSTEM_INSTRUCTIONS` + patient snapshot + findings + evidence + timeline tail `-30` most recent) → `_call_providers_with_fallback` → `_parse_and_validate` → validated result — `VERIFIED (repository: `llm_service.py:33-118` prompt + `212-285` parsing)` | Never diagnoses, never calculates scores, never prescribes dosage — `VERIFIED (repository: `llm_service.py:8-18` + `_SYSTEM_INSTRUCTIONS` hard rules)` |
| `persist` | `backend/app/services/langgraph_workflow.py:220-273` | `safety_score_result`, `llm_result` | `analysis_run_id: UUID` | Creates `AnalysisRun(id, patient_id, analysis_version="v1.0", deterministic_result=_serialize_safety_score_result(...), safety_score, risk_level, llm_*, created_at)` + `log_timeline_event("analysis_run")` then `commit` + `refresh` — `VERIFIED (repository: `223-273`)` | Never persists `timeline_context` inside `deterministic_result` (deliberately excluded) — `VERIFIED (repository: docstring `42-50` + `_serialize_safety_score_result:82-94` excludes `timeline_context` and `PenaltyEntry.source`) |

*All nodes close over the request `db: AsyncSession`; `AnalysisState` itself carries no `db` — `VERIFIED (repository: `langgraph_workflow.py:46-62` comment). Node names deliberately differ from state keys (`ValueError` if colliding) — `VERIFIED (repository: `langgraph_workflow.py:280-290` comment).*

### 11.5 State passed between nodes

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:46-62` `AnalysisState` TypedDict + `270-356` node I/O):**

```python
class AnalysisState(TypedDict, total=False):  # VERIFIED (repository: 46)
    patient_id: uuid.UUID                      # initial, guaranteed
    patient_context: PatientContext            # after patient_context_builder
    safety_score_result: SafetyScoreResult     # after safety_score_engine
    evidence_bundle: EvidenceBundle            # after evidence_retrieval
    timeline_context: TimelineContext          # after timeline_engine
    llm_result: LLMExplanationResult | None    # after llm_explanation
    llm_error: str | None                      # after llm_explanation (on failure)
    analysis_run_id: uuid.UUID                 # after persist
```

- `total=False` — fields populate progressively; only `patient_id` is present on `START` — `VERIFIED (repository: `46`)`.
- `db` is a factory closure, not in `AnalysisState` — `VERIFIED (repository: `52-62` + `176-223` `_patient_context_node(db)` pattern)`.
- `SafetyScoreResult` carries the full audit trail (`starting_score`, `total_points_deducted`, `interaction_findings`, `adr_findings`, `adherence_findings`, `penalties: list[PenaltyEntry]` with `source`) — `VERIFIED (repository: `backend/app/analysis/safety_score_engine.py:103-162`)`.
- `EvidenceBundle` groups per-finding `FindingEvidence(finding, medical_evidence, personal_evidence)` — `VERIFIED (repository: `evidence_retrieval.py:53-82`)`.

### 11.6 Error handling and recovery behavior

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:59-66` docstring + `197-218` `_llm_explanation_node` + `223-273` persist + `backend/app/services/llm_service.py:76-82` failure docstring):**

| Failure location | What happens | What persists | Classification |
|---|---|---|---|
| Missing/unconfigured `DATABASE_URL` or Supabase URL, or bad `patient_id` | Raises before/within node (e.g. `sqlalchemy` error or `ScalarResult`); graph fails, no `analysis_run` row is committed | Nothing — no partial write committed — `VERIFIED (repository: `langgraph_workflow.py` has no partial-commit retry; `_persist_node` is the only commit)` | **VERIFIED (repository)** |
| Unexpected exception inside any node *except* `llm_explanation` | Exception propagates and fails the whole `graph.ainvoke` run — `VERIFIED (repository: `langgraph_workflow.py:197-218` only catches `NotImplementedError` + `LLMExplanationError`) | Depends on whether `persist` was reached; if before `persist`, nothing persisted | **VERIFIED (repository)** |
| LLM provider failure or malformed output | `llm_explanation` catches `NotImplementedError` (retained defensively) + `LLMExplanationError` (every provider failed or output failed schema validation) → logs `warning` + returns `{"llm_result": None, "llm_error": str(exc)}` — `VERIFIED (repository: `langgraph_workflow.py:205-216` + `llm_service.py:76-82`)` | Deterministic pipeline **still persists** — `persist` writes `analysis_run` with `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_score`/`confidence_level` as `NULL` — `VERIFIED (repository: `langgraph_workflow.py:233-238` `llm_result.summary if llm_result else None`)` | **VERIFIED (repository)** |
| Token usage unavailable | `llm_providers.py` returns `LLMCompletion` with `None` usage fields — `VERIFIED (repository: `llm_providers.py:35-62`)`; `llm_service.py` logging omits `None` keys rather than logging `None` — `VERIFIED (repository: `llm_service.py:240-257` `if completion.prompt_tokens is not None:`) | N/A — operational logging only | **VERIFIED (repository)** |

*Deterministic scoring never fails due to LLM unavailability — this is the key resilience guarantee — `VERIFIED (repository: `langgraph_workflow.py:59-66` "deterministic pipeline always persists regardless")`.*

### 11.7 Provider fallback strategy

**VERIFIED (repository: `backend/app/services/llm_service.py:14-32` + `287-345` + `backend/app/services/llm_providers.py:68-199`):**

- **Primary → fallback order:** module-level `tuple[LLMProvider, ...] = (GeminiProvider(), OpenRouterProvider())` — Gemini first, OpenRouter second — `VERIFIED (repository: `llm_service.py:340`)` and spec §4. Both provider classes read settings lazily (`settings.gemini_api_key` / `settings.openrouter_api_key`/`..._model`, `settings.llm_timeout_seconds`) on each `complete` call — `VERIFIED (repository: `llm_providers.py:99`, `177`, `153`, `llm_service.py:299` `timeout_seconds=settings.llm_timeout_seconds`)`.
- **Fallback trigger:** a provider counts as failed if **either** `provider.complete()` raises `LLMProviderError` **or** its `text` fails `_parse_and_validate` (`LLMExplanationError`) — malformed-but-successful output is treated same as unreachable — `VERIFIED (repository: `llm_service.py:291-309` docstring + `294-309` try/except)`. Failures are collected in `failures: list[str]` and ultimately `raise LLMExplanationError("All configured LLM providers failed: " + "; ".join(failures))` — `VERIFIED (repository: `llm_service.py:311-315`)`.
- **Gemini-only single retry:** `GeminiProvider.complete()` retries **once** and only for transient failures — `HTTP 429/500/502/503/504` or `httpx.TimeoutException` (`retryable=True`) — `VERIFIED (repository: `llm_providers.py:13-28` "Retry (Gemini only)" + `35-62` `retries` set + `105-122` retry logic + `133-155` marking `retryable` on `LLMProviderError`)`. Every other failure (missing key, non-transient 4xx, malformed shape) raises immediately with `retryable=False` — `VERIFIED (repository: `llm_providers.py:88-98` + `105-111`)`. `OpenRouterProvider` never retries — `VERIFIED (repository: docstring `53-62`).
- **Logging fallback use:** `_log_successful_completion` logs `provider_used`, `model_used`, `latency_ms`, `fallback_used: bool` (`index > 0`) + token usage only when reported — `VERIFIED (repository: `llm_service.py:240-257` + `_call_providers_with_fallback:304-312` `fallback_used=index>0`)` — never logs prompts/evidence/explanations/patient identifiers — `VERIFIED (repository: `llm_service.py:42-50` logging docstring)`.

**Official documentation:** `httpx` (`httpx.AsyncClient`, `httpx.TimeoutException`, `httpx.RequestError`) — `VERIFIED (official documentation)` as declared dependency in `backend/requirements.txt` + `backend/app/services/llm_providers.py:10` `import httpx`. Provider REST endpoints are `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` (Gemini) and `https://openrouter.ai/api/v1/chat/completions` (OpenRouter) with `response_mime_type: application/json` / `response_format: {type: json_object}` — `VERIFIED (repository: `llm_providers.py:123-145`, `178-198`).

### 11.8 Deterministic vs LLM responsibilities

**VERIFIED (repository: engine docstrings + `langgraph_workflow.py` + `llm_service.py` system instructions):**

| Layer | Responsibility | Evidence |
|---|---|---|
| **Deterministic analysis** (`app/analysis/*.py`) | Compute findings, measurements, `safety_score`/`risk_level`, penalties with audit trail | `VERIFIED (repository: `drug_interaction_engine.py:1-15`, `adr_engine.py:1-15`, `adherence_engine.py:1-24`, `safety_score_engine.py:9-19`)` — LLM never invents findings |
| **Orchestration** (`app/services/langgraph_workflow.py`) | Order nodes, thread `AnalysisState`, close over `db`, persist | `VERIFIED (repository: `langgraph_workflow.py:270-356`)` — never computes clinical facts |
| **Evidence retrieval** (`app/services/evidence_retrieval.py`) | Structure medical evidence from finding fields + per-finding scoped `timeline_events` as `EvidenceBundle` | `VERIFIED (repository: `evidence_retrieval.py:1-36` placement + `83-198` scoping)` — not an analysis engine |
| **LLM explanation** (`app/services/llm_service.py` + `llm_providers.py`) | Explain already-computed `SafetyScoreResult`/`EvidenceBundle`/`PatientContext`/`TimelineContext` in plain language only; self-report confidence via prompt rubric | `VERIFIED (repository: `llm_service.py:8-18` + `_SYSTEM_INSTRUCTIONS` hard rules `Do NOT invent / Do NOT diagnose / Do NOT calculate / Do NOT recommend new dosage` + `645-658` confidence rubric)`; `LLMExplanationResult` shape `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_score`/`confidence_level` — `VERIFIED (repository: `llm_service.py:37-68`)` |
| **Persistence** (`langgraph_workflow.py:_persist_node` → `app/db/models:AnalysisRun` + `app/services/timeline_writer.py`) | Write `analysis_runs` + `analysis_run` timeline event as single transaction | `VERIFIED (repository: `langgraph_workflow.py:220-273`)` — single `db.commit()` |

*Grounding is prompt-level instructions + structural schema validation only; no semantic/keyword-overlap check — `VERIFIED (repository: `llm_service.py:52-59` "Grounding strategy")`. Confidence is self-reported and validated only for well-formedness (int 0-100, enum low/moderate/high) — not recomputed or clamped — `VERIFIED (repository: `llm_service.py:61-71` + `_parse_and_validate:295-312`).*

### 11.9 Persistence boundaries

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:42-50`, `65-94`, `220-273`, `backend/app/db/models.py` (via `001_initial_schema.sql: analysis_runs` table) + `backend/app/services/timeline_writer.py`):**

- **What is persisted to `analysis_runs`:** `id` (new UUID), `patient_id`, `analysis_version="v1.0"`, `deterministic_result` (JSONB from `_serialize_safety_score_result`: `safety_score`, `risk_level`, `starting_score`, `total_points_deducted`, `interaction_findings`, `adr_findings`, `adherence_findings`, `penalties` — each via `_serialize_*` excluding `PenaltyEntry.source`), `safety_score` (int), `risk_level` (enum), `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_score`/`confidence_level` (nullable — `None` when LLM failed), `created_at` — `VERIFIED (repository: `langgraph_workflow.py:65-94` serialization + `231-241` `AnalysisRun` construction)`.
- **What is NOT persisted in `deterministic_result`:** `timeline_context` (excluded deliberately — `timeline_events` remains single source of truth; second copy would create drift) — `VERIFIED (repository: docstring `42-50` + `_serialize_safety_score_result` does not reference `timeline_context`)` and `PenaltyEntry.source` live finding objects (not JSON-serializable; `description` preserves the why) — `VERIFIED (repository: `langgraph_workflow.py:52-62` comment + `_serialize_penalty:86-94` excludes `source`)`.
- **Timeline side-effect in same transaction:** `await log_timeline_event(db, patient_id, event_type="analysis_run", ref_id=analysis_run.id, event_title="Safety analysis run: {risk_level} risk ({safety_score}/100)", payload={safety_score, risk_level, llm_explanation_available})` then `await db.commit()` + `refresh` — `VERIFIED (repository: `langgraph_workflow.py:243-262`)`. This completes the 8th canonical `event_type` from spec §5 — `VERIFIED (repository: `PROJECT_PHASES.md:103-115` Phase 14 note "analysis_run was the last remaining event type")`.
- **Single transaction:** `analysis_run` row + `analysis_run` timeline event are committed together via one `db.commit()` in `_persist_node` — `VERIFIED (repository: `langgraph_workflow.py:259-262`)`; no other node performs writes.

### 11.10 Current implementation status and known limitations

**VERIFIED (repository: file headers, Phase completion marks in `PROJECT_PHASES.md`, and live code behavior):**

- **Implemented and verified (Phases 10-15 wiring):** all 6 nodes, linear ordering, patient context fresh build, safety score composition, evidence retrieval scoped queries, timeline retrieval ASC, provider abstraction with Gemini retry, OpenRouter fallback, JSON schema validation (strip fences + bracket extraction + field/confidence checks), operational logging without patient data, and persist with NULL tolerant LLM columns — `VERIFIED (repository: cited files above)`.
- **Incomplete / pending:**
  - **LLM explanation end-to-end in production** is `UNVERIFIED / REQUIRES RESEARCH` for live provider behavior: `GEMINI_API_KEY` / `OPENROUTER_API_KEY` are configured via `backend/.env` and `backend/app/core/config.py:62-78` (`gemini_api_key`, `openrouter_api_key` default `""`, fail-closed via `LLMProviderError` if unset — `VERIFIED (repository: `llm_providers.py:100`, `183`)`); live Gemini/OpenRouter response success, latency, and token usage have **not** been observed in this review against live provider endpoints — `UNVERIFIED`.
  - **Phase 15 (Gemini Integration) is still unchecked** in `PROJECT_PHASES.md:103-115` (`[ ] Prompt Engineering` etc.) — `VERIFIED (repository: `PROJECT_PHASES.md` checkboxes)` — LLM wiring is implemented in code but not marked complete in project phases.
  - No semantic grounding check against evidence text — explicitly scoped out per `llm_service.py:52-59` — `VERIFIED (repository)` but `UNVERIFIED` for effectiveness.
- **Known limitations (explicit, not speculation):**
  - Timeline prompt truncated to last 30 entries — unbounded `TimelineContext` could exceed LLM token limits if full context were sent — `VERIFIED (repository: `llm_service.py:33-38` + docstring + `_MAX_TIMELINE_ENTRIES_IN_PROMPT=30`)`.
  - No retry for `OpenRouter` after Gemini retry — by design — `VERIFIED (repository: `llm_providers.py:53-62`)`.
  - Confidence is self-reported and only well-formedness validated — not clamped or recomputed — `VERIFIED (repository: `llm_service.py:61-71`)`; `UNVERIFIED` whether model-graded confidence correlates with evidence quality.

---

## 12. Evidence Retrieval & Explainability

**Scope and evidence labeling:** every normative statement in §12 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative docs; `VERIFIED (empirical experiment)` — observed by running the test/command cited; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository. Implementation is the source of truth. No future retrieval method, grounding technique, or scoring logic is documented as implemented beyond what the repository contains.

### 12.1 Purpose

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:1-19`):**

Evidence Retrieval is the application service whose sole purpose is to **retrieve and structure supporting evidence** for the LLM explanation layer — it does **not** detect findings or compute scores. Per the confirmed Phase 13 design, it is “*not to detect new findings or compute a score… only to retrieve and structure supporting evidence for the Phase 15 LLM explanation layer*” — `VERIFIED (repository: `evidence_retrieval.py:7-12`)` — and is the direct SQL implementation of spec §8’s “Evidence Retrieval Node” and spec §4’s “Retrieval (MVP): Plain SQL (personal history + interaction rules) — pgvector added later without node changes” — `VERIFIED (repository: `evidence_retrieval.py:12` quoting spec §4)`.

Deterministic findings remain the facts; evidence is the supporting context that lets the LLM **explain** those facts without inventing them — a boundary enforced both at the prompt level and structurally via schema validation (see §12.8, §12.15).

### 12.2 Repository location and architectural responsibility

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:1-12` + `ls backend/app/services/` + `PROJECT_PHASES.md:103-115`):**

- **Location:** `backend/app/services/evidence_retrieval.py` — `VERIFIED (repository: file exists at that path)`.
- **Why `app/services/` not `app/analysis/`:** the module docstring records the confirmed Phase 13 design decision: “*this lives in `app/services/` (alongside `patient_context_builder.py` / `llm_service.py` / `langgraph_workflow.py` from spec section 6) rather than `app/analysis/`, since its job is to retrieve and structure supporting evidence, not to detect findings or compute a score*” — `VERIFIED (repository: `evidence_retrieval.py:5-12`)`. This mirrors the `services/` vs `analysis/` distinction established by Phase 13 and documented in `PROJECT_PHASES.md` Phase 13 notes — `VERIFIED (repository: `PROJECT_PHASES.md:103-115`)`.

*Not exposed via any HTTP route until Phase 14 LangGraph wiring* — `VERIFIED (repository: `evidence_retrieval.py:62-64` “Not exposed via any HTTP route yet… wired in Phase 14” + `ls backend/app/api/v1/evidence*` → no route).

### 12.3 Inputs and outputs

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:91-132`, `298-328` + `backend/app/services/langgraph_workflow.py:226-231`):**

| Aspect | Verified detail |
|---|---|
| **Function** | `async def retrieve_evidence(patient_id: UUID, db: AsyncSession, safety_score_result: SafetyScoreResult) -> EvidenceBundle` — `VERIFIED (repository: `evidence_retrieval.py:298-302`)` |
| **Inputs** | `patient_id` (UUID of the patient being analyzed), `db` (request-scoped `AsyncSession` closed over from the LangGraph node factory), `safety_score_result: SafetyScoreResult` (already-computed deterministic output from Phase 12 including all finding lists and penalties) — `VERIFIED (repository: `evidence_retrieval.py:303-315` docstring “one `FindingEvidence` per finding, grouped by category”)` |
| **Outputs** | `EvidenceBundle(interaction_evidence: list[FindingEvidence], adr_evidence: list[FindingEvidence], adherence_evidence: list[FindingEvidence])` where each `FindingEvidence(category, finding, medical_evidence, personal_evidence)` carries the original finding object for per-finding traceability — `VERIFIED (repository: `evidence_retrieval.py:108-132`)` |
| **LangGraph wiring** | `evidence_retrieval` node is `async def node(state): bundle = await retrieve_evidence(state["patient_id"], db, state["safety_score_result"]); return {"evidence_bundle": bundle}` — `VERIFIED (repository: `langgraph_workflow.py:226-231`)`; downstream `llm_explanation` consumes `(patient_context, safety_score_result, evidence_bundle, timeline_context)` — `VERIFIED (repository: `langgraph_workflow.py:197-218`)` |

### 12.4 Medical evidence construction

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:19-31`, `137-168`, `289-295` + `backend/tests/test_evidence_retrieval.py:137-195`):**

- **No duplicate retrieval:** medical evidence is **structured from already-fetched finding fields**, not re-queried. For `DrugInteractionFinding` the finding already carries `mechanism`/`recommendation`/`source` because `detect_drug_interactions()` joined `interaction_rules`; for `ADRFinding` it carries `reaction_description`/`frequency_class`/`source` because `detect_adrs()` joined `adr_rules` — `VERIFIED (repository: `evidence_retrieval.py:19-31` “does NOT re-query those tables; it only structures the finding's existing fields”)`. Verified by `grep -n "select.*InteractionRule\|select.*AdrRule" backend/app/services/evidence_retrieval.py` → `0` results — `VERIFIED (empirical experiment via repository grep)`.
- **Interaction medical evidence:** `def _interaction_medical_evidence(finding: DrugInteractionFinding) -> list[EvidenceItem]` appends `EvidenceItem(kind="medical", statement=finding.mechanism, source, occurred_at=None)` if `mechanism` and similarly for `recommendation` — `VERIFIED (repository: `137-154`)`. Thus 0, 1, or 2 items per finding depending on whether those fields are present on the seeded rule.
- **ADR medical evidence:** `def _adr_medical_evidence(finding: ADRFinding) -> list[EvidenceItem]` returns a single item with `statement = reaction_description (+ " (frequency: …)" if frequency_class)` — `VERIFIED (repository: `157-168`)`.
- **Adherence medical evidence:** always `[]` — there is no rules table backing an adherence fact — `VERIFIED (repository: `289-295` `return FindingEvidence(..., medical_evidence=[], ...)`)` and docstring `26-31`.
- **Empirical:** `test_interaction_medical_evidence_includes_mechanism_and_recommendation:137` asserts 2 medical items with `kind==medical`, `occurred_at is None`, `source=="FDA Label"`; `test_adr_medical_evidence_includes_reaction_and_frequency:169` asserts 1 item containing “Bleeding / bruising” + “common”; `test_adherence_finding_has_no_medical_evidence:195` asserts `medical_evidence==[]` — `VERIFIED (repository)` with references to repository test cases. `UNVERIFIED (empirical experiment in current environment)` because the test suite was not executed due to missing runtime dependencies (live Supabase DB + seeded `002_seed_data.sql` required).

### 12.5 Personal evidence retrieval

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:33-75`, `171-236` + `backend/tests/test_evidence_retrieval.py:225-356`):**

- **Finding → medication instance mapping:** interaction/ADR findings are drug-based (`drug_a_id`/`drug_b_id` / `drug_id`) but personal timeline events are medication-instance-based. The bridge is `async def _active_medication_ids_for_drugs(patient_id, drug_ids, db) -> list[UUID]` which does `select(Medication.id).where(patient_id==..., status=="active", drug_id.in_(drug_ids))` — `VERIFIED (repository: `171-192`)` — scoped to `status=="active"` consistent with Phases 10-12 — `VERIFIED (repository: `171-182` docstring).
- **Per-finding scoped lookup:** `async def _personal_evidence_for_medications(patient_id, medication_ids, db) -> list[EvidenceItem]` — `VERIFIED (repository: `194-236`)`:
  1. First fetches `select(Medication.condition_id).where(id.in_(medication_ids), condition_id.isnot(None))` to collect linked condition ids — `VERIFIED (repository: `207-212`)`.
  2. Builds `match_clauses = [ and_(event_type.in_(_MEDICATION_ID_ON_REF_ID), ref_id.in_(medication_ids)), and_(event_type.in_(_MEDICATION_ID_ON_PAYLOAD), payload["medication_id"].astext.in_(medication_id_strs)) ]` plus optionally `and_(event_type=="condition_status_changed", ref_id.in_(condition_ids))` — `VERIFIED (repository: `214-231`)`.
  3. Executes `select(TimelineEvent).where(patient_id==..., or_(*match_clauses)).order_by(event_time.desc())` — `VERIFIED (repository: `234-236`)` and maps each row to `EvidenceItem(kind="personal", statement=f"{event_title} — {event_description}" if description else event_title, source=None, occurred_at=event.event_time)` — `VERIFIED (repository: `237-248`)`.
- **Early exits:** if `drug_ids` empty → `return []` without query; if `medication_ids` empty → `return []` — `VERIFIED (repository: `182-203`).
- **Repository test cases:** `test_personal_evidence_includes_medication_started_event:225`, `test_personal_evidence_includes_dose_events:250`, `test_personal_evidence_includes_linked_symptom:277`, `test_personal_evidence_includes_linked_condition_status_change:299` — `VERIFIED (repository)` with references to repository test cases. `UNVERIFIED (empirical experiment in current environment)` because the suite was not executed here (requires live DB).

### 12.6 Timeline evidence usage

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:83-87`, `37-50` + `001_initial_schema.sql:125,165` + `backend/tests/test_evidence_retrieval.py:326`):**

- **Relevant `event_type` set (spec §5 canonical list, filtered to medication/condition-relevant):** `_MEDICATION_ID_ON_REF_ID = ("medication_started", "medication_discontinued")` and `_MEDICATION_ID_ON_PAYLOAD = ("dose_taken", "dose_missed", "dose_skipped", "symptom_reported")` — `VERIFIED (repository: `83-87`)`; docstring enumerates the same five matches plus `condition_status_changed` via `ref_id` against `medications.condition_id` — `VERIFIED (repository: `37-50`)`.
- **Why this filter:** `dose_taken`/`dose_missed`/`dose_skipped` events reference the *dose* as `ref_id` with `payload.medication_id` holding the medication link (per `timeline_writer.py` calls in `app/api/v1/schedule.py`); `medication_started`/`medication_discontinued` reference the medication directly via `ref_id`; `symptom_reported` via `payload.medication_id`; `condition_status_changed` via `ref_id` of the medication’s linked condition — `VERIFIED (repository: `37-50` comment)`.
- **Ordering:** personal evidence is `order_by(event_time.desc())` — most recent first — opposite of `TimelineContext`’s `ASC` narrative order — `VERIFIED (repository: `234-236`)` vs `timeline_engine.py:44-53` `ASC`.
- **Exclusion:** unrelated third active medication’s events do **not** leak into a finding that does not involve it — `VERIFIED (repository)` with references to `test_personal_evidence_excludes_unrelated_medication_events:326` and `test_personal_evidence_scoped_to_active_medication_for_adherence_finding:356`. `UNVERIFIED (empirical experiment in current environment)` for this run.

### 12.7 Evidence bundle structure

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:91-132` dataclasses):**

```python
@dataclass(frozen=True)
class EvidenceItem:        # VERIFIED (repository: 91-107)
    kind: "medical" | "personal"
    statement: str          # medical: mechanism/recommendation/reaction; personal: event_title + description
    source: str | None      # medical: e.g. "FDA Label" (from rule); personal: None
    occurred_at: datetime | None  # medical: None (no when); personal: event_time

@dataclass(frozen=True)
class FindingEvidence:     # VERIFIED (repository: 108-121)
    category: "drug_interaction" | "adr" | "adherence"
    finding: DrugInteractionFinding | ADRFinding | AdherenceFinding  # original object, not just id
    medical_evidence: list[EvidenceItem]
    personal_evidence: list[EvidenceItem]

@dataclass(frozen=True)
class EvidenceBundle:      # VERIFIED (repository: 123-132)
    interaction_evidence: list[FindingEvidence]
    adr_evidence: list[FindingEvidence]
    adherence_evidence: list[FindingEvidence]
```

- `EvidenceItem.occurred_at` is `None` for medical (a rule fact has no “when”) and `event.event_time` for personal — `VERIFIED (repository: `91-107` docstring + `_interaction_medical_evidence:137-154` `occurred_at=None` vs `_personal_evidence_for_medications:237-248` `occurred_at=event.event_time`)`.
- Traceability: `FindingEvidence.finding` is the original finding object mirroring `SafetyScoreResult`’s `PenaltyEntry.source` pattern — `VERIFIED (repository: `53-62` docstring)` and `test_interaction_medical_evidence:137` asserts `finding_evidence.finding in score_result.interaction_findings`.

### 12.8 Grounding guarantees

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:308-328` + `backend/app/services/llm_service.py:45-59`, `87-118`):**

- **What evidence provides:** deterministic, per-finding `EvidenceBundle` + `TimelineContext` + `PatientContext` + `SafetyScoreResult` are the **grounding context** the LLM is instructed to explain only — `VERIFIED (repository: `llm_service.py:8-18` docstring “only explains the already-computed deterministic result… never diagnoses, invents …”)` and `_SYSTEM_INSTRUCTIONS:87-118` hard rules “*Do NOT invent, alter, or second-guess any drug interaction, adverse drug reaction, or safety score/risk level… Base every statement only on the patient snapshot, findings, and evidence given*” — `VERIFIED (repository: `llm_service.py:87-118`)`.
- **How grounding is enforced:** **prompt-level instructions + structural schema validation only** — `VERIFIED (repository: `llm_service.py:45-59` “Grounding is enforced at the prompt level only … plus structural schema validation of the response shape. No semantic/keyword-overlap grounding check is performed … deliberately scoped out as unreliable for an MVP”)`. The hard guarantee is `VERIFIED (repository: `llm_service.py:233-312` `_parse_and_validate` checks `summary`/`reasoning`/`recommendations` non-empty strings, `confidence_score` int 0-100 (bool rejected), `confidence_level` in `(low,moderate,high)`)`.
- **What is NOT enforced:** no semantic or keyword-overlap check against evidence text — its absence is `VERIFIED (repository: `grep -n "semantic.*grounding\|keyword.*overlap" backend/app/services/` → only the docstring stating it was scoped out)`. This is an explicit architectural decision, not an oversight — `VERIFIED (repository: `llm_service.py:52-59` comment)`.

### 12.9 What the service explicitly does NOT do

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:19-31`, `37-50`, `308-328` + negative greps):**

| Explicitly not done | Repository evidence |
|---|---|
| Does not re-query `interaction_rules` / `adr_rules` | `VERIFIED (repository: `19-31` “does NOT re-query those tables” + `grep -n "select.*InteractionRule\|select.*AdrRule" evidence_retrieval.py` → 0)` |
| Does not compute severity, `safety_score`, or `risk_level` | `VERIFIED (repository: `308-328` “Deterministic only — performs no writes, invents nothing … never reaches beyond…” + `grep -n "safety_score\|risk_level" evidence_retrieval.py` → only type import)` |
| Does not fetch the full patient timeline — only per-finding scoped `or_(*match_clauses)` | `VERIFIED (repository: `37-50` “never the patient's entire timeline” + `234-236` `or_(*match_clauses)` scoped query)` |
| Does not write or mutate `timeline_events`, `medication_doses`, or any table | `VERIFIED (repository: `grep -n "INSERT\|UPDATE\|\.add\|\.commit\|log_timeline" backend/app/services/evidence_retrieval.py` → 0)` |
| Does not call the LLM or generate explanations | `VERIFIED (repository: `grep -n "llm_service\|Gemi\|OpenRouter" evidence_retrieval.py` → 0)` |
| Does not synthesize a medical claim beyond the finding’s own fields | `VERIFIED (repository: `_interaction_medical_evidence:137-154` only copies `mechanism`/`recommendation` as `statement`)` |

### 12.10 Database access patterns

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:71`, `185-236` + `001_initial_schema.sql:165` + SQLAlchemy docs):**

- **Read-only:** two read query families — `select(Medication.id/condition_id).where(patient_id==..., status=="active", drug_id.in_(...))` and `select(TimelineEvent).where(patient_id==..., or_(*match_clauses)).order_by(event_time.desc())` — `VERIFIED (repository: `71` imports `and_, or_, select` + `185-236` code)`; no `INSERT`/`UPDATE`/`DELETE` in the file — `VERIFIED (repository: `grep -n "insert\|update\|delete" evidence_retrieval.py` → 0, case-insensitive)`.
- **JSONB access:** `TimelineEvent.payload["medication_id"].astext.in_(medication_id_strs)` — `VERIFIED (repository: `222`)` — uses SQLAlchemy’s `JSONB` `astext` accessor which emits PostgreSQL `payload->>'medication_id'` — `VERIFIED (official documentation)` for SQLAlchemy PostgreSQL JSON APIs.
- **Scoping:** every query filters on `patient_id == patient_id` — `VERIFIED (repository: `185-236`)` — so cross-patient leakage is prevented at the query level (same ownership boundary as §9, but here via already-authorized `patient_id` passed from the workflow).
- **Index support:** `idx_timeline_patient(patient_id, event_time desc)` on `timeline_events` — `VERIFIED (repository: `001_initial_schema.sql:165` `create index idx_timeline_patient …`)` — directly supports the `where(patient_id==...) order_by(event_time.desc())` pattern used here — `VERIFIED (official documentation)` for PostgreSQL B-tree composite indexes on `(patient_id, event_time desc)` accelerating both filter and ordering.

### 12.11 Performance characteristics

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:298-328` loop structure + `001_initial_schema.sql:165` + `PROJECT_PHASES.md` notes):**

- **Query count is per-finding N+1:** `retrieve_evidence` loops `for finding in safety_score_result.{interaction,adr,adherence}_findings: await _build_*_evidence(patient_id, finding, db)` — each finding triggers one `_active_medication_ids_for_drugs` query (1 `select(Medication)`) + one `_personal_evidence_for_medications` which itself does up to two queries (condition_ids lookup + `select(TimelineEvent ...)`) — `VERIFIED (repository: `298-328` loop + `171-236` helpers)`. A patient with 0 findings issues 0 evidence queries — `VERIFIED (repository: `115-143` early-exit test and `182-203` `if not medication_ids: return []`)`. This is an intentional implementation trade-off verified from the repository. No batching or eager-loading strategy currently exists. Performance characteristics at production scale remain `UNVERIFIED / REQUIRES RESEARCH`.
- **No pagination or limit:** personal evidence `select(TimelineEvent)…order_by(event_time.desc())` has no `.limit()` — `VERIFIED (repository: `234-236` no `limit`)` — consistent with `TimelineContext`’s uncapped design (`timeline_engine.py:29-33`) and `GET /patients/{id}/timeline`’s no-pagination precedent.
- **Small-cardinality assumption:** per-patient active medication counts stay small regardless of total `medications` table size (per §6.3 deferred composite index rationale) — the `IN`-lists `drug_ids`/`medication_ids` are therefore small; expanding them at scale is bounded by the patient, not the table — `VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:105` deferred `medications(patient_id, status)` index reasoning).
- **No additional index added for this feature:** the existing `idx_timeline_patient` is relied upon; no `payload->>'medication_id'` expression index is created here — `VERIFIED (repository: `grep -n "create index" 001_initial_schema.sql` shows only that index for timeline)`.
- **Empirical measurement:** `EXPLAIN ANALYZE` at scale has **not** been run in this review — `UNVERIFIED / REQUIRES RESEARCH` for actual latency as finding count grows.

### 12.12 Interaction with the LangGraph workflow

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:12-22`, `226-242`, `328-339`, `339-356` + LangGraph official docs):**

| Aspect | Verified detail |
|---|---|
| **Graph position** | `evidence_retrieval` is node 3 of 6, immediately after `safety_score_engine` and before `timeline_engine` — `VERIFIED (repository: `langgraph_workflow.py:17-18` docstring list + `331-339` `add_edge("safety_score_engine","evidence_retrieval")` + `add_edge("evidence_retrieval","timeline_engine")`)` — timeline as unscoped narrative is kept separate from finding-scoped evidence — `VERIFIED (repository: `langgraph_workflow.py:32-36` comment) |
| **Node factory** | `def _evidence_retrieval_node(db: AsyncSession): async def node(state): bundle = await retrieve_evidence(state["patient_id"], db, state["safety_score_result"]); return {"evidence_bundle": bundle}` — `VERIFIED (repository: `226-231`)`; closes over request `db` — `VERIFIED (repository: `46-62` “DB session is intentionally NOT part of AnalysisState”)` |
| **State keys consumed/produced** | Consumes `state["patient_id"]` + `state["safety_score_result"]` (populated by prior node); produces `state["evidence_bundle"]: EvidenceBundle` consumed next by `llm_explanation` | 

**Official documentation:** `langgraph.graph.StateGraph` (`add_node`, `add_edge`, `compile`, `ainvoke`) — `VERIFIED (official documentation)` via `backend/requirements.txt` `langgraph==0.2.60` and `langgraph_workflow.py:90` import.

### 12.13 Failure behavior

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:137-168`, `182-203`, `285-328` + `backend/tests/test_evidence_retrieval.py:115-195`):**

| Condition | Behavior | Evidence |
|---|---|---|
| `SafetyScoreResult` has zero findings (clean patient) | Returns `EvidenceBundle(interaction_evidence=[], adr_evidence=[], adherence_evidence=[])` — loops run 0 iterations | `VERIFIED (repository: `298-328` comprehension over empty lists) + `VERIFIED (repository)` with reference to `test_no_findings_yields_empty_bundle:115` (asserts all three `[]`); `UNVERIFIED (empirical experiment in current environment)` for this run |
| Finding’s `drug_ids` map to no active `medication.id` (e.g. med discontinued since scoring) | `_active_medication_ids_for_drugs` returns `[]` (query returns 0 rows) → `_personal_evidence_for_medications` early-returns `[]` → `personal_evidence=[]` (medical evidence still present) | `VERIFIED (repository: `182-203` `if not drug_ids/medication_ids: return []`)` |
| No matching `timeline_events` for the scoped `or_(*match_clauses)` | `select(TimelineEvent).where(...or_...)` returns 0 rows → `personal_evidence=[]` (empty, not `None`) | `VERIFIED (repository: `234-248` list comp over `result.scalars().all()` may be empty)` |
| Finding has no `mechanism`/`recommendation` or `frequency_class` | Medical helper returns fewer/adjusted items: interaction with only `mechanism` → 1 item; ADR always at least 1 (`reaction_description`) | `VERIFIED (repository: `137-168` conditional appends)` + `VERIFIED (empirical experiment: `test_adr_medical_evidence:169` asserts single item contains frequency)` |
| DB error or missing patient | Exception propagates — no partial `EvidenceBundle` is returned; graph’s `evidence_retrieval` node would fail the `ainvoke` run before `persist` | `VERIFIED (repository: no try/except in `retrieve_evidence` — `298-328`)`; graph-level handling is `langgraph_workflow.py:59-66` (only `llm_explanation` is caught) |

*No fabrication:* adherence never fabricates medical evidence (`medical_evidence=[]` even when `personal_evidence` exists) — `VERIFIED (repository: `289-295`)` + `test_adherence_finding_has_no_medical_evidence`.

### 12.14 Current limitations and implementation status

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py` header + `PROJECT_PHASES.md` + `001_initial_schema.sql` + `langgraph_workflow.py` + `llm_service.py`):**

- **Implemented (Phase 13, verified):** Plain SQL retrieval as described above — shipped and tested (integration tests require live DB) — `VERIFIED (repository: file exists + `PROJECT_PHASES.md:103-115` Phase 13 `Evidence Retrieval` checked)`.
- **pgvector is deferred — not yet implemented:** header states “*Retrieval (MVP): Plain SQL (personal history + interaction rules) — pgvector added later without node changes*” — `VERIFIED (repository: `evidence_retrieval.py:12`)`; `001_initial_schema.sql` has no `vector` extension or `evidence` table with embeddings — `VERIFIED (repository: `grep -n "vector\|pgvector" 001_initial_schema.sql` → 0)`; future addition is intended to be additive without changing this node’s interface — `UNVERIFIED / REQUIRES RESEARCH` for vector design.
- **Not exposed via HTTP until Phase 14:** until the workflow wiring, callers used the engines directly — `VERIFIED (repository: `evidence_retrieval.py:62-64`).
- **Never exposed as standalone `GET /evidence`:** no such route exists — `VERIFIED (repository: `ls backend/app/api/v1/evidence*` → no file)`.
- **No confidence scoring here:** confidence is self-reported by the LLM and validated only for well-formedness in `llm_service.py` — `VERIFIED (repository: `llm_service.py:61-71`).
- **Historical scope:** personal evidence only surfaces `timeline_events` that are already persisted via Phase 7/9 writers; if no `symptom_reported` or `dose_taken` was logged, personal evidence for that finding is simply empty — `VERIFIED (repository: `208-236` query only what exists)`.

### 12.15 Explainability boundary — detection → evidence → explanation → persistence

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:12-66`, `197-273` + `backend/app/services/evidence_retrieval.py:1-19,53-62,308-328` + `backend/app/services/llm_service.py:8-18,87-118,362-384` + `backend/app/services/patient_context_builder.py`):**

*This subsection documents the architectural guarantee that the AI layer cannot influence the deterministic layer — it enriches and explains only.*

```
  Detection              Evidence              Explanation           Persistence
 (Phases 10-12)     →  (Phase 13)        →  (Phase 15)         →  (Phase 14 Persist)
 `detect_*` /       `retrieve_evidence`    `generate_explanation`  `_persist_node`
  `calculate_safety`  wraps each            consumes (patient_      writes analysis_runs
   finds severity     finding with          context, safety_score_   deterministic_result
   from rules as-is   medical (rule        result, evidence_        (from SafetyScoreResult
                      fields) +             bundle, timeline_       only) + safety_score/
                      personal (scoped      context) →              risk_level + llm_* 
                      timeline_events)      LLMExplanationResult    nullable; timeline_context
                                           (summary/reasoning/      NOT in deterministic_result
                                            recommendations/         → VERIFIED (repository:
                                            confidence)              langgraph_workflow.py:42-50)
                                            — VERIFIED (repository:
                                            llm_service.py:362-384)
```

| Guarantee | Repository evidence | Classification |
|---|---|---|
| **Evidence Retrieval never changes deterministic findings** — it takes `safety_score_result` as read-only input and returns `FindingEvidence(finding=original_finding, ...)` wrapping the original object without mutating `severity`, `reaction_description`, `adherence_rate`, `safety_score`, or `risk_level` | `VERIFIED (repository: `evidence_retrieval.py:108-121` `FindingEvidence.finding: DrugInteractionFinding | ADRFinding | AdherenceFinding` (the original) + `298-328` loops create new wrappers, never assign to `finding.severity` etc. + `grep -n "finding\.severity\s*=" evidence_retrieval.py` → 0)` | **VERIFIED (repository)** |
| **Evidence enriches only** — `medical_evidence` copies `mechanism`/`recommendation`/`reaction_description` as `statement` with `kind="medical"`; `personal_evidence` copies `event_title`/`event_description` with `kind="personal"` — no new clinical conclusion is produced | `VERIFIED (repository: `137-168` medical builders only `statement=finding.<field>` + `237-248` personal `statement=f"{event.event_title} — {event.event_description}"`)` | **VERIFIED (repository)** |
| **LLM consumes deterministic findings + evidence bundle + timeline context but cannot modify what is persisted as deterministic** — `generate_explanation` signature is `(patient_context, safety_score_result, evidence_bundle, timeline_context) -> LLMExplanationResult` and `langgraph_workflow.py:197-218` `llm_explanation` node stores the LLM result in `llm_result`/`llm_error` separately from `safety_score_result`; `_persist_node` writes `deterministic_result = _serialize_safety_score_result(safety_score_result)` (deterministic only) and `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_*` from `llm_result` as separate nullable columns | `VERIFIED (repository: `llm_service.py:362-384` signature + `langgraph_workflow.py:197-218` node + `231-241` `AnalysisRun(deterministic_result=..., safety_score=..., risk_level=..., llm_summary=llm_result.summary if llm_result else None...)`)` | **VERIFIED (repository)** |
| **`analysis_runs.deterministic_result` remains the authoritative deterministic output regardless of generated explanation** — it is serialized from `SafetyScoreResult` alone via `_serialize_safety_score_result` (which iterates `interaction_findings`/`adr_findings`/`adherence_findings`/`penalties`) without reading `llm_result` or `timeline_context`; `llm_*` columns are stored beside it, not merged into it | `VERIFIED (repository: `langgraph_workflow.py:65-94` `_serialize_safety_score_result` takes only `SafetyScoreResult` and explicitly excludes `PenaltyEntry.source` and never touches `llm_result` + `42-50` docstring “`timeline_context` is deliberately NOT included” + `test_langgraph_workflow.py:test_deterministic_result_contains_expected_findings_and_excludes_timeline` asserts `"timeline_context" not in det` + `223-241` `AnalysisRun` construction)` | **VERIFIED (repository)** + **VERIFIED (empirical experiment)** where `test_langgraph_workflow.py` runs |
| **Separation is structural, not just prompt-based:** detection is in `app/analysis/*`, evidence in `app/services/evidence_retrieval.py`, explanation in `app/services/llm_service.py`/`llm_providers.py` — cross-imports are one-way (evidence imports findings types; LLM imports bundles; workflow imports all) and never cyclic — `VERIFIED (repository: `ls backend/app/analysis/` vs `ls backend/app/services/` + `grep -rn "from app.analysis\|from app.services" backend/app/services/evidence_retrieval.py` shows only `from app.analysis.*` one-way)` | **VERIFIED (repository)** |

*Result:* the AI layer can **fail** (all providers fail → `llm_result: None`, `llm_error` populated — `VERIFIED (repository: `langgraph_workflow.py:205-216`)`) and the deterministic pipeline **still persists** — the `persist` node commits `safety_score`/`risk_level`/`deterministic_result` regardless — `VERIFIED (repository: `langgraph_workflow.py:223-262` `persist` runs after `llm_explanation` unconditionally)`. Deterministic `Detection → Evidence → Explanation → Persistence` remains intact.

---

*Sections 13–19 to follow.*