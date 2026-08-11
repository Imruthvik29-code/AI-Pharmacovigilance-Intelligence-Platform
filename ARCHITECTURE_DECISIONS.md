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

## 13. Persistence & Analysis Results

**Scope and evidence labeling:** every normative statement in §13 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative PostgreSQL/SQLAlchemy/LangGraph docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production latency, confidence calibration). Implementation is the source of truth. No future persistence, indexing, or scoring mechanism is documented as implemented beyond what the repository contains.

### 13.1 Purpose — versioned, auditable analysis results

**VERIFIED (repository: `001_initial_schema.sql:140-151` + `backend/app/api/v1/analysis.py:1-12` + `backend/tests/test_analysis_api.py:60,106` repository test cases):**

`analysis_runs` exists to store **versioned, auditable results** of the LangGraph pipeline — one row per `POST /patients/{id}/analyze`. The same patient analyzed twice produces two rows (versioned by `created_at`), not an update. Deterministic findings (`safety_score`, `risk_level`, `deterministic_result`) are the authoritative output; `llm_*` fields are optional explanation stored alongside, not merged into the deterministic JSONB — `VERIFIED (repository: `analysis.py:1-12` “*persists a row to `analysis_runs` regardless of whether the LLM step succeeded*” + `langgraph_workflow.py:65-94` serialization)**. `GET /patients/{id}/analysis` returns the full history ordered `created_at DESC` (most recent first) per spec §2 “Analysis report view … versioned” — `VERIFIED (repository: `analysis.py:99-116` `order_by(created_at.desc())`)`.

*Test case definitions* `test_analyze_creates_persisted_run:60` and `test_list_analysis_runs_ordered_most_recent_first:106` exist in the repository — `VERIFIED (repository)` with references to repository test cases; `UNVERIFIED (empirical experiment in current environment)` because the suite was not executed here (requires live DB).

### 13.2 Repository location and table definition

**VERIFIED (repository: `001_initial_schema.sql:140-151` `create table analysis_runs (...)` + `backend/app/db/models.py:230-253` `class AnalysisRun` + `models.py:11-28` `ENUM(..., create_type=False)`):**

| Layer | Evidence |
|---|---|
| **Migration (source of truth)** | `001_initial_schema.sql:140-151` — `id uuid primary key default gen_random_uuid()`, `patient_id uuid not null references patients(id) on delete cascade`, `analysis_version text not null default 'v1.0'`, `deterministic_result jsonb`, `safety_score int`, `risk_level risk_level_enum`, `llm_summary text`, `llm_reasoning text`, `llm_recommendations text`, `confidence_score int`, `confidence_level confidence_level_enum`, `created_at timestamptz not null default now()` — `VERIFIED (repository)` |
| **ORM mapping** | `backend/app/db/models.py:230-253` `class AnalysisRun` maps 1:1 onto the table; header `1-9` states “*These map 1:1 onto the tables/enums defined in 001_initial_schema.sql … does not define or alter schema*” — `VERIFIED (repository)`; all 7 ENUM bindings use `create_type=False` so SQLAlchemy never creates/alters types — `VERIFIED (repository: `models.py:11-28`)` |
| **PostgreSQL types** | `jsonb`, `uuid`, `risk_level_enum`, `confidence_level_enum`, `timestamptz` per PostgreSQL docs — `VERIFIED (official documentation)` for `JSONB`, `UUID`, `ENUM`, `TIMESTAMPTZ` |

*No `vector` extension or evidence table exists* — `grep -n "vector\|pgvector" 001_initial_schema.sql` → `0` — `VERIFIED (repository)`.

### 13.3 Inputs and outputs — persist node

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:220-262`, `339-356` + `backend/app/api/v1/analysis.py:76-84`):**

| Aspect | Verified detail |
|---|---|
| **Node** | `_persist_node(db: AsyncSession)` factory closing over request `db` — `VERIFIED (repository: `220-262`)` |
| **Inputs** | `state["safety_score_result"]: SafetyScoreResult` (from `safety_score_engine` node) + `state.get("llm_result"): LLMExplanationResult | None` (from `llm_explanation` node; `None` on `NotImplementedError`/`LLMExplanationError`) + `state["patient_id"]: UUID` + `db` closure — `VERIFIED (repository: `220-231` parameter unpacking)` |
| **Outputs** | `state["analysis_run_id"]: UUID` (new `uuid.uuid4()` for the `AnalysisRun` row) returned via `final_state["analysis_run_id"]` from `await graph.ainvoke({"patient_id": patient_id})` — `VERIFIED (repository: `339-356` `run_analysis` + `260-262` `return {"analysis_run_id": analysis_run.id}`)`; API layer re-fetches via `select(AnalysisRun).where(id==analysis_run_id)` — `VERIFIED (repository: `analysis.py:80-84`)` |
| **LangGraph wiring** | `persist` is final node: `builder.add_node("persist", _persist_node(db))` + `builder.add_edge("llm_explanation", "persist")` + `builder.add_edge("persist", END)` — `VERIFIED (repository: `312-337`)` |

### 13.4 Serialization boundaries — what is and is not persisted in `deterministic_result`

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:46-94` helpers + `42-50` docstring + `220-273` persist):**

- **What IS serialized to `analysis_runs.deterministic_result`:** `def _serialize_safety_score_result(result: SafetyScoreResult) -> dict` builds a JSON-safe dict by iterating only `SafetyScoreResult` — `VERIFIED (repository: `82-94`):`

```python
{
  "safety_score": result.safety_score,              # VERIFIED (repository: 82)
  "risk_level": result.risk_level,                  # VERIFIED (repository: 83)
  "starting_score": result.starting_score,          # VERIFIED (repository: 84)
  "total_points_deducted": result.total_points_deducted,  # 85
  "interaction_findings": [_serialize_interaction_finding(f) for f in ...],  # 86-88
  "adr_findings": [_serialize_adr_finding(f) for f in ...],                  # 89
  "adherence_findings": [_serialize_adherence_finding(f) for f in ...],      # 90-91
  "penalties": [_serialize_penalty(p) for p in result.penalties],            # 92
}
```

Each `_serialize_*` helper converts UUIDs via `str(...)` and copies finding fields (`drug_a_id`, `drug_a_name`, `severity`, `mechanism`, `recommendation`, `source`, etc.) — `VERIFIED (repository: `65-94` helpers)`.

- **What is NOT serialized there:**
  - `PenaltyEntry.source` (live `DrugInteractionFinding | ADRFinding | AdherenceFinding` object) is **excluded** — comment “*Excludes PenaltyEntry.source (the live finding object reference) since it is not JSON-serializable and is only needed for in-memory traceability*” — `VERIFIED (repository: `46-62`)` and `_serialize_penalty:86-94` returns only `category`, `description`, `severity`, `points`.
  - `timeline_context: TimelineContext` is **deliberately NOT included** — docstring “*timeline_context is deliberately NOT included in that JSONB blob. The `timeline_events` table is already the single source of truth*” — `VERIFIED (repository: `42-50`)`.
  - `llm_result` / `evidence_bundle` / `patient_context` are **never read** by `_serialize_safety_score_result` — its sole parameter is `SafetyScoreResult` — `VERIFIED (repository: `82-94` signature)`.
  - **Empirical:** `test_deterministic_result_contains_expected_findings_and_excludes_timeline:210` asserts `"timeline_context" not in det` and `penalties` lack `source` — `VERIFIED (repository)` with reference to repository test case; `UNVERIFIED (empirical experiment in current environment)` for this run.

### 13.5 JSONB structure and dual storage

**VERIFIED (repository: `langgraph_workflow.py:82-94` + `001_initial_schema.sql:143-145` + `models.py:237-241`) + `VERIFIED (official documentation)` for `JSONB`:**

| Column | Type | Content | Source |
|---|---|---|---|
| `deterministic_result` | `jsonb` | JSON object with 8 top-level keys: `safety_score` (int), `risk_level` (`"low"|"moderate"|"high"`), `starting_score` (int), `total_points_deducted` (int), `interaction_findings[]` (each `interaction_rule_id`, `drug_a_id`, `drug_a_name`, `drug_b_id`, `drug_b_name`, `severity`, `mechanism`, `recommendation`, `source`), `adr_findings[]` (each `adr_rule_id`, `drug_id`, `drug_name`, `reaction_description`, `severity`, `frequency_class`, `source`), `adherence_findings[]` (each `medication_id`, `drug_name`, `taken`, `missed`, `skipped`, `due`, `adherence_rate`), `penalties[]` (each `category`, `description`, `severity`, `points`) — `VERIFIED (repository: `65-94` serialization helpers define these keys)` | `langgraph_workflow.py:82-94` |
| `safety_score` | `int` | Duplicated top-level column — `safety_score_result.safety_score` — `VERIFIED (repository: `233-234` `safety_score=safety_score_result.safety_score`)` | `001_initial_schema.sql:144` |
| `risk_level` | `risk_level_enum` (`low`/`moderate`/`high`) | Duplicated top-level column — `safety_score_result.risk_level` | `001_initial_schema.sql:144` + `models.py:238` |
| `analysis_version` | `text` default `'v1.0'` | Hardcoded literal `analysis_version="v1.0"` — `VERIFIED (repository: `229` + `001_initial_schema.sql:142`) | — |
| `patient_id`, `id`, `created_at` | `uuid`, `timestamptz` | `uuid.uuid4()`, `patient_id` from state, `datetime.now(timezone.utc)` | `langgraph_workflow.py:227-232` |

*PostgreSQL `JSONB` stores the `deterministic_result` as binary JSON with GIN-index capability (no GIN index is created here) — `VERIFIED (official documentation)` for `JSONB` per PostgreSQL docs. The `jsonb` column is the **versioned snapshot**; the top-level `safety_score`/`risk_level` columns enable indexed filtering without JSONB extraction — a dual-storage trade-off verified by the code writing both.*

### 13.6 Audit trail

**VERIFIED (repository: `backend/app/analysis/safety_score_engine.py:103-162` + `langgraph_workflow.py:65-94` + `backend/tests/test_safety_score_engine.py:358` repository test case):**

- **In-memory audit trail:** `SafetyScoreResult` exposes `starting_score` (always `BASE_SCORE=100`), `total_points_deducted` (sum of penalties), plus the three raw finding lists and `penalties: list[PenaltyEntry]` — `VERIFIED (repository: `safety_score_engine.py:144-162`)`.
- **Per-penalty traceability:** `PenaltyEntry(category, description, severity, points, source)` where `source` is the **live finding object** (`DrugInteractionFinding | ADRFinding | AdherenceFinding`) so a caller can render why a penalty was applied without re-querying — `VERIFIED (repository: `safety_score_engine.py:103-112` docstring “*source is intentionally the original finding object … so a caller can render a full human-readable explanation without re-querying*”)`.
- **Serialized audit trail:** `deterministic_result.penalties[]` retains `category`/`description`/`severity`/`points` (human-readable `description` already documents the why; `source` excluded as above) alongside the full finding arrays — `VERIFIED (repository: `langgraph_workflow.py:86-94` `_serialize_penalty` + `82-94` full dict)`.
- **Repository test case:** `test_penalty_entries_reference_their_source_finding:358` asserts `penalty.source is finding` — `VERIFIED (repository)` with reference to repository test case; `UNVERIFIED (empirical experiment in current environment)`.

### 13.7 Deterministic vs LLM persistence — separate columns, deterministic authoritative

**VERIFIED (repository: `langgraph_workflow.py:231-241` `AnalysisRun` construction + `001_initial_schema.sql:144-149` nullable `llm_*` + `backend/app/services/llm_service.py:61-71` docstring):**

```python
analysis_run = AnalysisRun(
    id=uuid.uuid4(),                                          # VERIFIED (repository: 227)
    patient_id=state["patient_id"],                            # VERIFIED (repository: 228)
    analysis_version="v1.0",                                   # VERIFIED (repository: 229)
    deterministic_result=_serialize_safety_score_result(safety_score_result),  # VERIFIED (repository: 230)
    safety_score=safety_score_result.safety_score,             # VERIFIED (repository: 233)
    risk_level=safety_score_result.risk_level,                 # VERIFIED (repository: 234)
    llm_summary=llm_result.summary if llm_result else None,    # VERIFIED (repository: 235)
    llm_reasoning=llm_result.reasoning if llm_result else None,          # 236
    llm_recommendations=llm_result.recommendations if llm_result else None, # 237
    confidence_score=llm_result.confidence_score if llm_result else None,   # 238
    confidence_level=llm_result.confidence_level if llm_result else None,   # 239
    created_at=now,                                            # VERIFIED (repository: 232)
)
```

- **Deterministic columns** (`deterministic_result`, `safety_score`, `risk_level`) are **always** persisted from `SafetyScoreResult` — the sole source of truth.
- **LLM columns** (`llm_summary`, `llm_reasoning`, `llm_recommendations`, `confidence_score`, `confidence_level`) are **nullable** (`Text`/`Integer`/`confidence_level_enum` in `001_initial_schema.sql:144-149` + `models.py:238-248`) and are `None` when `llm_result is None` (all providers failed or output failed validation) — `VERIFIED (repository: `231-241` conditional `if llm_result else None`)`.
- **Repository test cases:** `test_llm_fields_populated_when_provider_succeeds:118` and `test_llm_fields_null_when_all_providers_fail:167` assert populated vs `NULL` LLM columns — `VERIFIED (repository)` with references to repository test cases; `UNVERIFIED (empirical experiment in current environment)`.

*The API layer logs `llm_explanation_available: llm_result is not None` in the `analysis_run` timeline event payload — `VERIFIED (repository: `langgraph_workflow.py:248-252` `payload={"safety_score": ..., "llm_explanation_available": llm_result is not None}`) — but this flag is metadata, not a merge of LLM output into the deterministic result.*

### 13.8 Idempotency — intentionally non-idempotent versioning

**VERIFIED (repository: `langgraph_workflow.py:227-232` + `backend/app/api/v1/analysis.py:62-84` + negative grep + repository test cases):**

- **Each `POST /patients/{id}/analyze` creates a new row** with `id = uuid.uuid4()` even for identical `patient_id` and identical deterministic inputs — `VERIFIED (repository: `langgraph_workflow.py:227` `id=uuid.uuid4()` + `api/v1/analysis.py:62-84` handler always calls `await run_analysis(patient_id, db)` with no `SELECT ... IF EXISTS` guard).
- **This is an intentional versioning decision. No repository evidence exists for deduplication, request hashing, optimistic locking, or idempotency keys** — `VERIFIED (repository):` `grep -rn "ON CONFLICT\|UPSERT\|ON_CONFLICT\|dedupl\|request.*hash\|optimistic.*lock\|idempotency.*key\|Idempotency-Key" backend/app/services/langgraph_workflow.py backend/app/api/v1/analysis.py backend/app/db/` → `0` results — *The implementation intentionally creates a new analysis record for every execution. No repository evidence exists for deduplication, request hashing, optimistic locking, or idempotency keys.*
- **History is versioned by `created_at`** and `GET /patients/{id}/analysis` returns all rows `order_by(AnalysisRun.created_at.desc())` (most recent first) — `VERIFIED (repository: `analysis.py:104-108`)`.
- **Repository test cases:** `test_running_twice_creates_two_separate_versioned_runs:270` asserts two rows with different `id`s and distinct `created_at` ordering — `VERIFIED (repository)` with reference to repository test case; `UNVERIFIED (empirical experiment in current environment)` for this run.

### 13.9 Transaction boundaries

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:243-262` `_persist_node` + `backend/app/services/timeline_writer.py:1-28` + `001_initial_schema.sql:140-151` + SQLAlchemy docs):**

```python
db.add(analysis_run)                                              # VERIFIED (repository: 243)
await log_timeline_event(                                         # VERIFIED (repository: 244-252)
    db, patient_id=..., event_type="analysis_run", ref_id=analysis_run.id,
    event_title=f"Safety analysis run: {risk_level} risk ({safety_score}/100)",
    payload={"safety_score": ..., "risk_level": ..., "llm_explanation_available": ...},
)
await db.commit()                                                 # VERIFIED (repository: 259)
await db.refresh(analysis_run)                                    # VERIFIED (repository: 260)
```

- **Both rows committed together:** `AnalysisRun` + its `analysis_run` `timeline_events` row are staged via `db.add` and committed in a **single transaction** via one `await db.commit()` in `_persist_node` — `VERIFIED (repository: `243-262`)`.
- **`timeline_writer.py` never commits:** `def log_timeline_event(db, ...): db.add(TimelineEvent(...))` — docstring “*only calls `db.add(...)` and never commits, so every timeline event is written in the same transaction as the entity write that triggered it*” — `VERIFIED (repository: `timeline_writer.py:1-28` + `grep -n "commit\|refresh" backend/app/services/timeline_writer.py` → `0`)`.
- **No other node writes:** `patient_context_builder`, `safety_score_engine`, `evidence_retrieval`, `timeline_engine`, `llm_explanation` perform only reads via `select` — `VERIFIED (repository: `grep -n "\.add\|commit\|INSERT" backend/app/services/langgraph_workflow.py` outside `_persist_node` → 0 + `grep -n "commit" backend/app/analysis/*.py` → 0)`.
- **Atomicity:** `analysis_run` and its timeline event succeed or fail together — if `db.commit()` raises (e.g. constraint violation), neither row is persisted — per SQLAlchemy `AsyncSession` `add`/`commit` semantics — `VERIFIED (official documentation)` for `add`/`commit`/`refresh`.
- **Empirical:** `test_analysis_run_logs_timeline_event:252` asserts timeline event exists after successful `run_analysis` — `VERIFIED (repository)` with reference to repository test case; `UNVERIFIED (empirical experiment in current environment)`.

### 13.10 Deterministic result authoritative regardless of LLM

**VERIFIED (repository: `langgraph_workflow.py:65-94` + `197-218` + `231-241` + `backend/tests/test_langgraph_workflow.py:167` repository test case):**

- **Deterministic serialization reads only `SafetyScoreResult`:** `_serialize_safety_score_result(result: SafetyScoreResult)` iterates `interaction_findings`/`adr_findings`/`adherence_findings`/`penalties` without ever reading `llm_result` or `timeline_context` — `VERIFIED (repository: `65-94` signature and body)`.
- **LLM failure still persists deterministic:** `_llm_explanation_node` catches `NotImplementedError` (defensive) and `LLMExplanationError` (every provider failed or output failed validation) → `{"llm_result": None, "llm_error": str(exc)}` and logs `warning` — `VERIFIED (repository: `197-218`)`; `_persist_node` then writes `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_score`/`confidence_level` as `None` — `VERIFIED (repository: `231-241` `if llm_result else None`)` — but `deterministic_result`/`safety_score`/`risk_level` are still populated from `safety_score_result`.
- **Deterministic-fatal vs LLM-tolerant:** any other unexpected exception propagates and fails the whole `graph.ainvoke` run — no `analysis_runs` row is committed — `VERIFIED (repository: `197-218` only those two exceptions caught + docstring `59-66` “*any other, unexpected exception propagates and fails the whole graph run*”)**. `llm_error` is stored only in `AnalysisState`, never in `analysis_runs` columns — `VERIFIED (repository: `46-62` `AnalysisState` has `llm_error: str | None` but `AnalysisRun` model has no `llm_error` column).
- **Repository test case:** `test_llm_fields_null_when_all_providers_fail:167` asserts LLM columns `NULL` while deterministic `safety_score`/`deterministic_result` still present — `VERIFIED (repository)` with reference; `UNVERIFIED (empirical experiment in current environment)`.

### 13.11 Database access patterns and indexes

**VERIFIED (repository: `001_initial_schema.sql:166` + `backend/app/api/v1/analysis.py:80`, `104-108` + `langgraph_workflow.py:243-262` + `backend/app/db/models.py:230-253`):**

| Access | SQL (verified) | Index / type | Source |
|---|---|---|---|
| **Write `analysis_runs`** | `db.add(AnalysisRun(...))` + `db.commit()` + `refresh` in `_persist_node` — `VERIFIED (repository: `243-262`)` | `gen_random_uuid()` default on `id`, `now()` on `created_at` — `001_initial_schema.sql:141` | — |
| **Write `timeline_events` (analysis_run event)** | `db.add(TimelineEvent(patient_id, event_type="analysis_run", ref_id=analysis_run.id, ...))` staged in same transaction — `VERIFIED (repository: `244-252`)` | `idx_timeline_patient(patient_id, event_time desc)` already exists, not used for this write | — |
| **Read single run** | `select(AnalysisRun).where(AnalysisRun.id == final_state["analysis_run_id"])` — `VERIFIED (repository: `analysis.py:80`)` | Primary key lookup on `analysis_runs.id` — `VERIFIED (official documentation)` for PK B-tree | — |
| **Read history** | `select(AnalysisRun).where(AnalysisRun.patient_id == patient_id).order_by(AnalysisRun.created_at.desc())` — `VERIFIED (repository: `analysis.py:104-108`)` | `create index idx_analysis_patient on analysis_runs(patient_id, created_at desc)` — `VERIFIED (repository: `001_initial_schema.sql:166`)` — composite B-tree supports `WHERE patient_id` + `ORDER BY created_at DESC` without sort — `VERIFIED (official documentation)` for PostgreSQL composite index semantics | — |
| **Read pattern for `deterministic_result`** | No server-side JSONB query in this path — `deterministic_result` is written as Python `dict` via `JSONB` column and read as `dict` via SQLAlchemy’s `JSONB` type — `VERIFIED (repository: `models.py:237` `deterministic_result: Mapped[dict | None] = mapped_column(JSONB)`)` | PostgreSQL `JSONB` binary JSON — `VERIFIED (official documentation)`; no GIN index is created on `deterministic_result` — `grep -n "deterministic_result" 001_initial_schema.sql` → only column definition | — |

### 13.12 Performance characteristics

**Repository-verified vs UNVERIFIED — explicitly distinguished:**

| **Repository verified** (`VERIFIED (repository)`) | **UNVERIFIED / REQUIRES RESEARCH** |
|---|---|
| - Composite index `idx_analysis_patient(patient_id, created_at desc)` **exists** — `VERIFIED (repository: `001_initial_schema.sql:166`)` | - Query **latency** for history list at large history size — `UNVERIFIED` (no `EXPLAIN ANALYZE` in repo) |
| - `GET /patients/{id}/analysis` has **no `LIMIT` / `OFFSET` / pagination** — returns full history — `VERIFIED (repository: `analysis.py:104-108` no `limit`/`offset`/`page`)` | - **Throughput** under concurrent `POST /analyze` (LangGraph + LLM latency dominates) — `UNVERIFIED` |
| - `deterministic_result` JSONB payload **size grows with findings** — one JSON object per `interaction_findings`/`adr_findings`/`adherence_findings`/`penalties` entry — `VERIFIED (repository: `langgraph_workflow.py:82-94` comprehension per finding)` | - **Memory behaviour** for large `EvidenceBundle` + `TimelineContext` in `AnalysisState` — `UNVERIFIED` |
| - No `ORDER BY` sort step needed when using `idx_analysis_patient` for the history query (index stores `created_at DESC` per patient) — per PostgreSQL composite index “supports `ORDER BY` matching index order” — `VERIFIED (official documentation)` for index `DESC` semantics, but **actual `EXPLAIN` output not in repo** | - PostgreSQL **execution plans** (`Index Scan` vs `Index Only Scan` vs `Sort`) — `UNVERIFIED` (no `EXPLAIN` in repo) |
| | - **Scalability under production workloads** (many patients × many runs) — `UNVERIFIED` |

*No benchmark is implied by the documentation — the table above states existence of the index and absence of pagination, not latency.*

### 13.13 Interaction with LangGraph workflow — persist as final node

**VERIFIED (repository: `backend/app/services/langgraph_workflow.py:281-337` `_build_graph` + `339-356` `run_analysis` + LangGraph official docs):**

| Aspect | Verified detail |
|---|---|
| **Node registration** | `builder.add_node("patient_context_builder", _patient_context_node(db))` through `builder.add_node("persist", _persist_node(db))` — 6 nodes — `VERIFIED (repository: `312-318`)` |
| **Edges** | `builder.add_edge(START, "patient_context_builder")` → `add_edge("patient_context_builder", "safety_score_engine")` → `add_edge("safety_score_engine", "evidence_retrieval")` → `add_edge("evidence_retrieval", "timeline_engine")` → `add_edge("timeline_engine", "llm_explanation")` → `add_edge("llm_explanation", "persist")` → `add_edge("persist", END)` — `VERIFIED (repository: `328-337`)`; `persist` is final before `END` |
| **State flow into persist** | `persist` receives `state["safety_score_result"]` (from `safety_score_engine`) and `state.get("llm_result")` (from `llm_explanation`) — `VERIFIED (repository: `220-231`)`; prior nodes never write `analysis_run_id` — only `persist` returns it |
| **Return to caller** | `run_analysis` does `graph = _build_graph(db)` → `final_state = await graph.ainvoke({"patient_id": patient_id})` → `return final_state` (now containing `analysis_run_id`) — `VERIFIED (repository: `339-356`)` |
| **LangGraph API** | `StateGraph(AnalysisState)` / `add_node` / `add_edge` / `compile` / `ainvoke` — `VERIFIED (official documentation)` via `langgraph==0.2.60` in `backend/requirements.txt` and `langgraph_workflow.py:90` import |

### 13.14 Failure behavior — LLM-tolerant vs deterministic-fatal

**VERIFIED (repository: `langgraph_workflow.py:59-66` docstring + `197-218` `_llm_explanation_node` + `223-262` `_persist_node` + repository test cases):**

| Failure | What happens | What persists |
|---|---|---|
| **LLM all providers fail or output fails validation** (`LLMProviderError` / `LLMExplanationError` per provider or `_parse_and_validate` failure) | `_llm_explanation_node` catches `NotImplementedError` (defensive) + `LLMExplanationError` → logs `warning` “*LLM explanation unavailable…*” → returns `{"llm_result": None, "llm_error": str(exc)}` — `VERIFIED (repository: `197-218`)`; graph continues to `persist` | `analysis_runs` row committed with `deterministic_result`/`safety_score`/`risk_level` populated, `llm_*` columns `NULL` — `VERIFIED (repository: `231-241` `if llm_result else None` + repository test case `test_llm_fields_null_when_all_providers_fail:167`)` |
| **Unexpected exception in any node except `llm_explanation`** (e.g. `detect_drug_interactions` raises `sqlalchemy` error or `build_patient_context` fails) | Exception propagates and fails `graph.ainvoke` — no `try/except` covers it — docstring “*any other, unexpected exception propagates and fails the whole graph run*” — `VERIFIED (repository: `59-66`)`; `persist` is never reached | **Nothing committed** — `persist`’s `db.commit()` never runs — `VERIFIED (repository: `197-218` only those two exceptions caught)` |
| **DB constraint / commit failure in `persist`** | `await db.commit()` raises — `AnalysisRun` + `analysis_run` timeline event not persisted (single transaction rolled back) — per SQLAlchemy `AsyncSession` semantics — `VERIFIED (official documentation)` for `commit` failure | Nothing persisted |

*LLM columns being `NULL` is the expected “success with partial explanation” state, not an error — the deterministic pipeline is designed to always persist regardless of LLM outcome — `VERIFIED (repository: `langgraph_workflow.py:59-66` “*deterministic pipeline always persists regardless of this step's outcome*”)**.*

### 13.15 Current limitations and implementation status

**VERIFIED (repository: `langgraph_workflow.py:229` + `001_initial_schema.sql:140-151` + `backend/app/api/v1/analysis.py:96-108` + `backend/app/services/llm_service.py:61-71`, `283-312`):**

- **Implemented (Phase 14, verified):** `analysis_runs` table, `idx_analysis_patient`, ORM mapping, `_serialize_safety_score_result`, `_persist_node` single transaction, `analysis_run` timeline event, `POST /analyze` (`201` + re-fetch) and `GET /analysis` (`DESC` history) — `VERIFIED (repository: cited above)`.
- **`analysis_version` hardcoded:** `analysis_version="v1.0"` literal in `_persist_node` (`229`) and `analysis_version text not null default 'v1.0'` in `001_initial_schema.sql:142` — `VERIFIED (repository: `grep -rn "analysis_version" backend/` → only `"v1.0"` literal — no increment/deprecation logic).
- **No `DELETE`/`PUT` on `analysis_runs`:** `backend/app/api/v1/analysis.py` exposes only `POST` + `GET`; no `delete`/`put` decorator for `analysis_runs` — `VERIFIED (repository: `grep -n "def test\|router\.\|@router" analysis.py` + `grep -n "delete\|put" backend/app/api/v1/analysis.py` → 0 for this resource)`. `timeline_events` `ON DELETE CASCADE` already handles patient deletion (via `patients.id` FK) — `VERIFIED (repository: `001_initial_schema.sql:141` `on delete cascade`)`.
- **No pagination on history:** `GET /analysis` returns full list — `VERIFIED (repository: `analysis.py:104-108` no `limit`/`offset`/`page`)` — listed as repository-verified in §13.12; scale behaviour `UNVERIFIED`.
- **Confidence is self-reported by the LLM:** **`VERIFIED (repository):` The application validates only the structure, type, and permitted range of `confidence_score` and `confidence_level`. It does not independently compute, calibrate, or verify the confidence values returned by the LLM. Therefore, these fields represent the LLM's self-reported confidence rather than a deterministic confidence metric** — `VERIFIED (repository: `llm_service.py:61-71` docstring “*self-reported by the model … this module does NOT recompute, clamp, or override*” + `283-312` `_parse_and_validate` checks `isinstance(score,bool) or not isinstance(score,int) or not (0<=score<=100)` and `level in ("low","moderate","high")` only — `grep -rn "confidence.*compute\|confidence.*calibrat\|confidence.*recomput" llm_service.py` → `0`)`. Accuracy/calibration of `confidence_score`/`confidence_level` is `UNVERIFIED / REQUIRES RESEARCH`.
- **LLM explanation not required for persistence:** `llm_summary`/`llm_reasoning`/`llm_recommendations`/`confidence_*` are `NULL` when all providers fail — by design, not a defect — `VERIFIED (repository: `langgraph_workflow.py:231-241`)`.

---

## 14. Timeline, Scheduling & Adherence

**Scope and evidence labeling:** every normative statement in §14 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative PostgreSQL/SQLAlchemy/FastAPI/LangGraph docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production latency, execution plans, confidence calibration). Implementation is the source of truth. No future scheduler, pagination, or scoring mechanism is documented as implemented beyond what the repository contains.

### 14.1 Purpose — auditable event log, deterministic scheduling, adherence marking

**VERIFIED (repository: `backend/app/services/timeline_writer.py:1-22` + `backend/app/api/v1/schedule.py:1-27` + `backend/app/api/v1/timeline.py:1-16` + `PROJECT_PHASES.md` Phase 7-9 notes + `001_initial_schema.sql:125-138`):**

- **Timeline:** records an **auditable, patient-scoped event log** as side effects of entity writes (`medication_started`/`medication_discontinued`, `condition_status_changed`, `symptom_reported`, `dose_taken`/`dose_missed`/`dose_skipped`, `analysis_run`) — 8 canonical `event_type` values from spec §5 — `VERIFIED (repository: `timeline_writer.py:9-14` comment listing 4 values + `schedule.py:45-62` mapping `taken→dose_taken` etc. + `langgraph_workflow.py:243-252` `event_type="analysis_run"` + `timeline.py:13-16` “*Read-only … no POST/PUT/DELETE, since events are never created directly*” + `001_initial_schema.sql:125-138` `timeline_events` table)`.
- **Scheduling:** generates **deterministic dose instances** (`medication_schedule` + `medication_doses` rows) from medication cadence (`duration_days` + `times_per_day`/`interval_hours`) anchored at `08:00 UTC` on `start_date`, capped at `3650` rows — `VERIFIED (repository: `schedule.py:100` `MAX_GENERATED_DOSES=3650` + `105` `DEFAULT_FIRST_DOSE_TIME=08:00 UTC` + `191-214` `_compute_schedule_params` + `321` `anchor = datetime.combine(start_date, DEFAULT_FIRST_DOSE_TIME)`)`.
- **Adherence:** records `taken`/`missed`/`skipped` via `POST /doses/{id}/mark` (with `actual_time` handling) and drives the **lazy missed-dose sweep** that flips overdue unmarked doses to `missed` — both feeding the deterministic safety analysis (`adherence_engine.py` counts) and evidence retrieval (`personal evidence` scoped to `ref_id`/`payload.medication_id`) — `VERIFIED (repository: `schedule.py:45-62` `_MARK_EVENT_TYPES` + `220-268` `_sweep_missed_doses` + `adherence_engine.py:57-84` `due`/`missed` definition)`.
- **Not an adherence statistics endpoint:** adherence `taken/missed/skipped/due` counts are an **internal input to the Safety Score Engine** (`adherence_engine.py` → `safety_score_engine.py`), not a standalone `GET /adherence` API — `VERIFIED (repository: `PROJECT_PHASES.md` Phase 9 “*Adherence Statistics … explicitly out of scope for Phase 9’s own API surface — not part of the frozen section 7 API contract*” + `adherence_engine.py:1-12` docstring)**.

### 14.2 Repository location and architectural responsibility

**VERIFIED (repository: `backend/app/api/v1/schedule.py:1-27` + `backend/app/api/v1/timeline.py:1-16` + `backend/app/services/timeline_writer.py:1-22` + `ls backend/app/api/v1/schedule.py`, `timeline.py`, `services/timeline_writer.py` + `001_initial_schema.sql:125-138` + Spec §6):**

| File | Responsibility | Why there |
|---|---|---|
| `backend/app/api/v1/schedule.py` | Dose schedule generation (`POST /medications/{id}/schedule`), upcoming doses (`GET /patients/{id}/doses/upcoming`), dose marking (`POST /doses/{id}/mark`), and the lazy missed-dose sweep (`_sweep_missed_doses`) | Patient-scoped REST resource per spec §7 — `VERIFIED (repository: module docstring `1-27`)` |
| `backend/app/api/v1/timeline.py` | Read-only timeline feed (`GET /patients/{id}/timeline`, ordered `event_time DESC`) — no `POST`/`PUT`/`DELETE` | Frozen spec §7 declares only `GET` for timeline — `VERIFIED (repository: `timeline.py:1-16` docstring “*Read-only … no POST/PUT/DELETE, since events are never created directly*”)` |
| `backend/app/services/timeline_writer.py` | Reusable helper `async def log_timeline_event(db, *, patient_id, event_type, event_title, ...)` that **only** does `db.add(TimelineEvent(...))` — callers commit atomically | Additive service, not exhaustive in spec §6 file list — docstring “*Deliberately NOT listed in the spec's folder structure (section 6) … additive fit alongside `patient_context_builder.py`*” — `VERIFIED (repository: `timeline_writer.py:6-12`)` |
| `001_initial_schema.sql` `timeline_events` | Table `id uuid PK default gen_random_uuid()`, `patient_id uuid FK cascade`, `event_type text`, `ref_id uuid`, `event_title text`, `event_description text`, `event_time timestamptz default now()`, `payload jsonb`, `created_at timestamptz default now()` — `VERIFIED (repository: `125-138`)` | Single source of truth for timeline data per `timeline_engine.py:29-33` + `langgraph_workflow.py:42-50` |

*`event_type` is intentionally `text`, not a Postgres `ENUM` — it mirrors `001_initial_schema.sql:128` `event_type text` per spec §5’s `timeline_events` schema — `VERIFIED (repository: `timeline_writer.py:9-12` + `001_initial_schema.sql:128`)` and `VERIFIED (official documentation)` for `text`/`jsonb`/`timestamptz`.*

### 14.3 Inputs and outputs

**VERIFIED (repository: `backend/app/api/v1/schedule.py:274-439` + `backend/app/api/v1/timeline.py:44-63` + `backend/app/services/timeline_writer.py:34-48` + `001_initial_schema.sql:125-138`):**

| Route / function | Inputs | Outputs | Verified |
|---|---|---|---|
| `POST /medications/{id}/schedule` (`generate_schedule`) | `medication_id` path + existing `medications` row with `duration_days` (int) + at least one of `times_per_day` (int) / `interval_hours` (numeric) + `start_date` (date) — all persisted on the medication | `201` + `list[MedicationDose]` with `id`, `medication_id`, `schedule_id` (FK to `medication_schedule.id`), `scheduled_time` (timestamptz), `status` (`None` initially), `actual_time` (`None`), `created_at`/`updated_at` — plus `medication_schedule` rows (one per dose) with `scheduled_time` — `VERIFIED (repository: `274-348` `MedicationDose` construction with `schedule_id=schedule_row.id`)` | — |
| `GET /patients/{id}/doses/upcoming` (`list_upcoming_doses`) | `patient_id` path + `current_user.id` via `_assert_patient_owned` (404 if not owned) — implicitly `now()` via `datetime.now(timezone.utc)` | `200` + `list[UpcomingDoseResponse]` (`id`, `medication_id`, `scheduled_time`, `drug_name`, `dose`) — only `scheduled_time >= now()` AND `status IS NULL` AND `Medication.status=="active"` ordered `scheduled_time ASC` — `VERIFIED (repository: `383-434` query + join `ReferenceDrug`)` | — |
| `POST /doses/{id}/mark` (`mark_dose`) | `dose_id` path + JSON `status` (`"taken"|"missed"|"skipped"`, validated via `MedicationDoseMarkRequest` → `dose_status_enum`) + optional `actual_time` (timestamptz) — `VERIFIED (repository: `schedule.py:439-463` + `models.py:dose_status_enum`)` | `200` + `MedicationDoseResponse` with updated `status`/`actual_time`/`updated_at` + `dose_taken`/`dose_missed`/`dose_skipped` `timeline_events` row in same transaction — `VERIFIED (repository: `439-495` + `45-62` `_MARK_EVENT_TYPES`)` | — |
| `GET /patients/{id}/timeline` (`get_timeline`) | `patient_id` path + `current_user.id` | `200` + `list[TimelineEventResponse]` ordered `event_time DESC` (most recent first) matching `idx_timeline_patient` — `VERIFIED (repository: `timeline.py:44-63`)` | — |
| `log_timeline_event(db, *, patient_id, event_type, event_title, ...)` | `db: AsyncSession` + required `patient_id`, `event_type` (plain `str`), `event_title` + optional `ref_id`, `event_description`, `payload` (JSONB dict) | Returns `TimelineEvent` (staged via `db.add`, **not committed** — caller commits) — `VERIFIED (repository: `timeline_writer.py:34-48`)` | — |

*Hard delete `DELETE /medications/{id}` and `PUT /conditions/{id}` etc. are documented in their own modules and log `medication_discontinued` / `condition_status_changed` via the same writer — `VERIFIED (repository: `medications.py:240-254` + `conditions.py:125-171`)` — but `DELETE /patients` does not exist per frozen spec — `VERIFIED (repository: `patients.py:13-16` “No DELETE /patients/{id}”)**.*

### 14.4 Schedule generation — cadence, dose count, spacing, anchoring, and caps

**VERIFIED (repository: `backend/app/api/v1/schedule.py:100-214`, `274-348` + `backend/tests/test_schedule_api.py:90-205` repository test cases):**

- **Preconditions (validated before any generation):** `if medication.duration_days is None: raise 400 "medication.duration_days must be set …"` — `VERIFIED (repository: `285-293`)*;* `if medication.times_per_day is None and medication.interval_hours is None: raise 400 "At least one of … must be set …"` — `VERIFIED (repository: `294-303`)*;* existing schedule check `if existing scalar_one_or_none() is not None: raise 409 "A schedule already exists …"` — `VERIFIED (repository: `294-303`)*;* all three are `HTTPException` with `status 400`/`409` — `VERIFIED (official documentation)` for HTTP 400/409 semantics.

- **Dose count and interval formulas (`_compute_schedule_params`):** — `VERIFIED (repository: `191-214`):*

  ```python
  if medication.times_per_day is not None:               # Branch 1
      total_doses = medication.times_per_day * medication.duration_days
      interval_hours = medication.interval_hours or (24 / medication.times_per_day)
  else:                                                  # Branch 2: interval_hours only
      interval_hours = float(medication.interval_hours)
      total_doses = math.floor(duration_days * 24 / interval_hours + _FLOOR_EPSILON)
      total_doses = max(total_doses, 1)
  ```

  `_FLOOR_EPSILON = 1e-9` guards `floor()` against floating-point `3.9999999` → `4.0` — `VERIFIED (repository: `110` + docstring `114-117`)*;* minimum `1` dose even when `duration*24/interval < 1` — `VERIFIED (repository: `214`)`.

- **Defensive cap:** `MAX_GENERATED_DOSES = 3650` — if `total_doses > 3650: raise 400 "Requested schedule would generate {total} doses, exceeding the maximum … Reduce …"` — `VERIFIED (repository: `100` + `311-317`)`. This guards pathological inputs (e.g. `times_per_day=24` × multi-year `duration_days` or very small `interval_hours`) — `VERIFIED (repository: `96-102` comment “*Defensive cap … Not a spec requirement; purely a safety guard*”)*.*

- **Anchoring:** first dose at `08:00 UTC` on `start_date` — `VERIFIED (repository: `105` `DEFAULT_FIRST_DOSE_TIME = time(hour=8, tzinfo=UTC)` + `321` `anchor = datetime.combine(medication.start_date, DEFAULT_FIRST_DOSE_TIME)` + `323-340` `scheduled_time = anchor + timedelta(hours=interval_hours * i)`)*;* deterministic, not “now”.*

- **Empirical repository test cases** (definitions exist — `VERIFIED (repository)` with references; `UNVERIFIED (empirical experiment in current environment)` because suite not executed here — requires live DB):

  `test_generate_schedule_creates_expected_dose_count:90`, `test_generate_schedule_spacing_defaults_to_even_daily_spread:110` (`times_per_day=2` → 12h even spread), `test_generate_schedule_respects_explicit_interval_hours:131`, `test_generate_schedule_with_interval_hours_only_creates_expected_dose_count:250` (`floor(duration*24/interval)`), `test_generate_schedule_with_interval_hours_only_floors_partial_dose:299` (epsilon guard), `test_generate_schedule_exceeding_max_doses_returns_400:205`, `test_generate_schedule_twice_returns_409:187`.

### 14.5 Upcoming doses — future, unmarked, active-medication filter

**VERIFIED (repository: `backend/app/api/v1/schedule.py:383-434` + `backend/tests/test_schedule_api.py:360-408` repository test cases):**

```python
select(MedicationDose.id, MedicationDose.medication_id, MedicationDose.scheduled_time,
       ReferenceDrug.name, Medication.dose)
.join(Medication, Medication.id == MedicationDose.medication_id)
.join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
.where(
    Medication.patient_id == patient_id,
    Medication.status == "active",          # VERIFIED (repository: 402)
    MedicationDose.status.is_(None),        # VERIFIED (repository: 403)
    MedicationDose.scheduled_time >= now(), # VERIFIED (repository: 404)
)
.order_by(MedicationDose.scheduled_time)    # VERIFIED (repository: 405)
```

- **Why `status=="active"` only:** a paused/completed/discontinued medication’s future doses are not “upcoming” in the clinical sense — mirrors the same filter in `detect_drug_interactions` + `detect_adrs` + `analyze_adherence` — `VERIFIED (repository: `schedule.py:1-27` docstring “*Only for medications with status == "active"*” + `adherence_engine.py:57-63`)`.
- **Enrichment:** `drug_name`/`dose` are joined so the response is directly usable by a “take your medication” UI without client-side re-lookup — `VERIFIED (repository: `385-408` comment “*Enriched with drug_name/dose…*”)**.*
- **Sweep side-effect:** `list_upcoming_doses` first runs `await _sweep_missed_doses(patient_id, db)` + `await db.commit()` — so any overdue unmarked doses are `missed` before the query, but the sweep never affects this query’s result set (`scheduled_time < now()` vs `>= now()`) — `VERIFIED (repository: `383-394` + `220-268` sweep)*;* documented as a small write side-effect on a read — `VERIFIED (repository: `385-408` docstring “*runs the missed-dose sweep … documented write side-effect*”)**.*
- **Repository test cases:** `test_upcoming_doses_returns_future_unmarked_doses_ordered:360`, `test_upcoming_doses_excludes_inactive_medication:385`, `test_upcoming_doses_scoped_to_patient:408` — `VERIFIED (repository)` with references; `UNVERIFIED (empirical experiment in current environment)`.

### 14.6 Missed-dose sweep — lazy, request-triggered consistency model

**VERIFIED (repository: `backend/app/api/v1/schedule.py:1-27` + `220-268` + `383-394` + `439-470` + `grep` for absence of scheduler):**

> **The repository implements a lazy, request-triggered consistency model rather than eventual consistency via a background scheduler.** — `VERIFIED (repository: `schedule.py:8-15` “*the tech stack (spec section 4) has no job scheduler/cron component, so this is implemented as a lazy, query-time sweep rather than a true background job*” + `grep -rn "cron\|scheduler\|apscheduler\|pg_cron\|celery\|background.*task" backend/` → `0` code hits (only docstrings mention absence)).

```python
async def _sweep_missed_doses(patient_id: UUID, db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)                                    # VERIFIED (repository: 230)
    result = await db.execute(
        select(MedicationDose, ReferenceDrug.name)                       # VERIFIED (repository: 231)
        .join(Medication, Medication.id == MedicationDose.medication_id)
        .join(ReferenceDrug, ReferenceDrug.id == Medication.drug_id)
        .where(
            Medication.patient_id == patient_id,                         # VERIFIED (repository: 235)
            MedicationDose.status.is_(None),                              # VERIFIED (repository: 236)
            MedicationDose.scheduled_time < now,                           # VERIFIED (repository: 237)
        )
    )
    for dose, drug_name in result.all():
        dose.status = "missed"; dose.updated_at = now                   # VERIFIED (repository: 238-241)
        await log_timeline_event(db, patient_id=patient_id,              # VERIFIED (repository: 243-252)
            event_type="dose_missed", ref_id=dose.id,
            event_title=f"Missed dose of {drug_name}" if drug_name else "Dose missed",
            payload={"medication_id": str(dose.medication_id),
                     "scheduled_time": dose.scheduled_time.isoformat(),
                     "auto_detected": True})
    # Does NOT commit — caller commits/flushes — VERIFIED (repository: 255-268 docstring)
```

- **Trigger points:** `list_upcoming_doses` does `await _sweep_missed_doses(patient_id, db)` + `await db.commit()` — `VERIFIED (repository: `383-394`)`; `mark_dose` does `await _sweep_missed_doses(patient_id, db)` + `await db.flush()` (so the `dose.status` just fetched reflects any sweep-applied `missed`) — `VERIFIED (repository: `439-470` + docstring `220-268`)*;* any overdue unmarked dose is therefore `missed` before either a read or a mark is processed.
- **Scope and independence from medication status:** sweep filters on `Medication.patient_id == patient_id` and `status IS NULL` + `scheduled_time < now` — it **does not filter on `Medication.status`** (active/paused/discontinued all sweep) — because a dose that was due is either taken or missed regardless of the medication’s current lifecycle state — `VERIFIED (repository: `231-237` query has no `Medication.status` predicate + `220-268` docstring “*Applies regardless of the parent medication's status*”)*.*
- **Operational behavior at production scale** (timeliness of `missed` if no request triggers sweep) is `UNVERIFIED / REQUIRES RESEARCH` unless measured — the sweep only runs when a dose-related route for that patient is hit, so an overdue dose could remain `status IS NULL` until the next `GET /upcoming` or `POST /mark` — `VERIFIED (repository: `220-268` docstring) + `PROJECT_PHASES.md` Phase 9 “*there is no job scheduler in the tech stack*” — production timeliness `UNVERIFIED`**.
- **Repository test cases:** `test_upcoming_doses_sweeps_overdue_unmarked_doses_to_missed:654` + `test_mark_dose_sweeps_overdue_dose_before_processing_the_mark:700` — `VERIFIED (repository)` with references; `UNVERIFIED (empirical experiment in current environment)`.

### 14.7 Dose marking — taken / missed / skipped

**VERIFIED (repository: `backend/app/api/v1/schedule.py:45-62` + `439-495` + `backend/tests/test_schedule_api.py:463-631` repository test cases):**

| Aspect | Verified detail |
|---|---|
| **Endpoint** | `POST /doses/{id}/mark` with `MedicationDoseMarkRequest(status, actual_time?)` where `status` is validated against `dose_status_enum` (`taken`/`missed`/`skipped` — `models.py:dose_status_enum`) → `422` if invalid — `VERIFIED (repository: `439-463` + `models.py:dose_status_enum` + `test_mark_dose_invalid_status:631` asserting `422`) |
| **Ownership** | `_get_owned_dose(dose_id, current_user, db)` joins `MedicationDose→Medication→Patient→ReferenceDrug` and filters `Patient.user_id == current_user.id` → `404 "Dose not found."` if not owned — `VERIFIED (repository: `162-183` + `439-463` first line `dose, patient_id, drug_name = await _get_owned_dose(...)`)` |
| **Sweep before mark** | `await _sweep_missed_doses(patient_id, db)` + `await db.flush()` ensures an overdue unmarked dose is already `missed` before the `if dose.status is not None` check — so a late `mark` on an overdue dose correctly sees it as already `missed` — `VERIFIED (repository: `439-470`)` |
| **Immutability** | If `dose.status is not None` (whether prior explicit `taken`/`missed`/`skipped` or sweep-applied `missed`) → `raise HTTPException(409, "Dose already marked as '{status}'.")` — `VERIFIED (repository: `463-470`)*;* there is **no `PUT /doses/{id}` “correct a mark”** — `VERIFIED (repository: `grep -n "correct a mark" schedule.py:462` docstring “*there is no spec-defined ‘correct a mark’ flow, so this is treated as immutable once set*” + `PROJECT_PHASES.md` Phase 9 “*intentionally immutable*”)*;* repository test `test_mark_dose_twice_returns_409:580` asserts this — `VERIFIED (repository)` with reference |
| **`actual_time` rule** | `dose.actual_time = payload.actual_time or (now if status=="taken" else None)` — defaults to `now()` only for `taken`, left `None` for `missed`/`skipped` — `VERIFIED (repository: `472-474`)`; `test_mark_dose_taken_sets_status_and_defaults_actual_time:463` + `test_mark_dose_taken_respects_explicit_actual_time:486` + `test_mark_dose_missed_leaves_actual_time_null:509` + `test_mark_dose_skipped_leaves_actual_time_null:531` — `VERIFIED (repository)` with references |
| **Timeline side-effect** | `await log_timeline_event(db, patient_id, event_type=_MARK_EVENT_TYPES[status], ref_id=dose.id, event_title=f"{verb} dose of {drug_name}" ...)` + `await db.commit()` + `refresh` — `VERIFIED (repository: `476-495`)`; `test_mark_dose_logs_corresponding_timeline_event:557` asserts `dose_taken`/`dose_missed`/`dose_skipped` event exists — `VERIFIED (repository)` with reference |

### 14.8 Timeline events — table, event types, and single source of truth

**VERIFIED (repository: `001_initial_schema.sql:125-138` + `backend/app/services/timeline_writer.py:1-48` + `backend/app/api/v1/timeline.py:1-63` + `backend/app/analysis/timeline_engine.py:1-53` + `backend/app/services/patient_context_builder.py`):**

| Aspect | Verified detail |
|---|---|
| **Table** | `timeline_events` (`id uuid PK default gen_random_uuid()`, `patient_id uuid FK cascade`, `event_type text`, `ref_id uuid`, `event_title text`, `event_description text`, `event_time timestamptz default now()`, `payload jsonb`, `created_at timestamptz default now()`) — `VERIFIED (repository: `001_initial_schema.sql:125-138`)` + ORM `models.py:TimelineEvent` — `VERIFIED (repository)`; `event_type` is plain `text`, not a Postgres `ENUM` — mirrors spec §5 schema — `VERIFIED (repository: `timeline_writer.py:9-12` + `001_initial_schema.sql:128`)` and `VERIFIED (official documentation)` for `text`/`jsonb`/`timestamptz` |
| **Writer** | `async def log_timeline_event(db, *, patient_id, event_type, event_title, ref_id=None, event_description=None, payload=None) -> TimelineEvent` — `VERIFIED (repository: `timeline_writer.py:34-48`)` — only does `db.add(TimelineEvent(...))` and `return event` — **never** `commit` — `VERIFIED (repository: `timeline_writer.py:22-48` docstring “*only calls `db.add(...)` — it never commits*” + `grep -n "commit\|refresh" timeline_writer.py` → `0`)`; callers add the event to the same session as the entity write and commit both together — `VERIFIED (repository: `medications.py:191-210` + `schedule.py:476-495` + `langgraph_workflow.py:243-262`)` |
| **8 canonical `event_type` values in use** | `medication_started` / `medication_discontinued` (medications), `condition_status_changed` (conditions), `symptom_reported` (symptoms), `dose_taken` / `dose_missed` / `dose_skipped` (doses + sweep), `analysis_run` (LangGraph persist) — `VERIFIED (repository: `timeline_writer.py:9-14` + `schedule.py:45-62` `_MARK_EVENT_TYPES` + `langgraph_workflow.py:243-252` + `medications.py:191-210` + `conditions.py:125-171` + `symptoms.py:100-145`)`; hard `DELETE /medications/{id}` and `DELETE /patients` deliberately do **not** log an event (no `medication_deleted` type in spec §5) — `VERIFIED (repository: `medications.py:268-292` docstring “*No timeline event is logged here … spec's event_type list has no ‘medication deleted’ value*” + `test_medication_delete_does_not_log_event:140`)` |
| **Feed API** | `GET /patients/{id}/timeline` is **read-only** — no `POST`/`PUT`/`DELETE` (405) — `VERIFIED (repository: `timeline.py:1-16` docstring + `test_no_post_put_delete_endpoints_exist:300` asserting `405`)`; implementation `select(TimelineEvent).where(patient_id==...).order_by(event_time.desc())` matching `idx_timeline_patient(patient_id, event_time desc)` — `VERIFIED (repository: `timeline.py:44-63` + `001_initial_schema.sql:165`)`; `TimelineContext` for LLM is the same source but ordered `ASC` (oldest→newest) as narrative context — `VERIFIED (repository: `timeline_engine.py:44-53` `order_by(ASC)`)` vs `timeline.py:44-63` `DESC` |
| **Ordering and traceability** | `event_time` is set to `now()` at write time (`datetime.now(timezone.utc)`) — `VERIFIED (repository: `timeline_writer.py:40-48`); `payload` is JSONB (e.g. `dose_missed` → `{"medication_id": "...", "scheduled_time": "...", "auto_detected": true}`) — `VERIFIED (repository: `schedule.py:243-252`)` |

### 14.9 Database access patterns and indexes — repository facts vs optimizer conclusions

**Explicitly distinguished:**

| **Repository-verified** | **UNVERIFIED / REQUIRES RESEARCH** |
|---|---|
| **Indexes exist:** `idx_schedule_medication(medication_id)`, `idx_doses_medication(medication_id)`, `idx_doses_scheduled_time(scheduled_time)`, `idx_timeline_patient(patient_id, event_time desc)` **exist** in `001_initial_schema.sql:160-166` — `VERIFIED (repository: `grep -n "create index" 001_initial_schema.sql` → 4 relevant indexes)` | **Execution plans / optimizer behavior** — `UNVERIFIED` unless supported by `EXPLAIN (ANALYZE)` output in the repository (none exists) — `VERIFIED (repository: `grep -rn "EXPLAIN" backend/` → 0)`; any statement that PostgreSQL **actually chooses** those indexes in production (e.g. `Index Scan` vs `Sequential Scan`, `Index Only Scan`) is `UNVERIFIED` |
| **Queries target indexed columns:** schedule generation `select(MedicationSchedule.id).where(medication_id==...)` targets `idx_schedule_medication`; timeline feed `select(TimelineEvent).where(patient_id==...).order_by(event_time.desc())` targets `idx_timeline_patient`; sweep `where(patient_id+status+scheduled_time)` uses `patient_id` filter that narrows the row set — `VERIFIED (repository: `schedule.py:274-348` + `timeline.py:44-63` + `schedule.py:231-237`)` | **Query latency, throughput, memory, scalability** at production scale — `UNVERIFIED` (no benchmark, no load test in repo) |
| **Index capability per PostgreSQL docs:** B-tree index on `(patient_id, event_time desc)` **can** accelerate `WHERE patient_id==... ORDER BY event_time DESC` without sort when `ORDER BY` matches index order — `VERIFIED (official documentation)` for PostgreSQL B-tree composite index semantics | **Chosen plan** for sweep (`WHERE patient_id + status IS NULL + scheduled_time < now`) — the trailing `status` column is low-cardinality; whether a composite `medications(patient_id, status)` helps is deferred pending `EXPLAIN ANALYZE` — `VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:105` deferred composite index reasoning) — plan itself `UNVERIFIED` |

*No additional index is created for this feature — the existing `idx_timeline_patient` is relied upon; no `payload->>'medication_id'` expression index is created here — `VERIFIED (repository: `grep -n "create index" 001_initial_schema.sql` shows only that index for timeline).*

### 14.10 Performance characteristics

**VERIFIED (repository: `schedule.py:100`, `311-317` + `timeline.py:44-63` + `timeline_engine.py:29-33` + `001_initial_schema.sql:165` + `PROJECT_PHASES.md` notes) — distinguished from UNVERIFIED scale conclusions:**

| **Repository verified** | **UNVERIFIED / REQUIRES RESEARCH** |
|---|---|
| - Defensive cap `MAX_GENERATED_DOSES = 3650` — if `total > 3650: raise 400` — `VERIFIED (repository: `100` + `311-317`)` — guards pathological inputs (e.g. `times_per_day=24` × long `duration_days`) — *Not a spec requirement; purely a safety guard* — `VERIFIED (repository: `96-102` comment)` | - **Latency / throughput / memory** for schedule generation of large but allowed counts (up to 3650) — `UNVERIFIED` (no load test, no `EXPLAIN ANALYZE`) |
| - **No pagination / `LIMIT` on `GET /timeline`** — returns full `timeline_events` for the patient — `VERIFIED (repository: `timeline.py:44-63` no `limit`/`offset`/`page`)` — same as `TimelineContext`’s uncapped design (`timeline_engine.py:29-33` “*No artificial cap on the number of events returned, consistent with `GET /timeline` which also returns the full timeline with no pagination*”) | - **Execution plans** (`Index Scan` vs `Seq Scan`, `Sort` node presence) — `UNVERIFIED` (no `EXPLAIN` in repo) |
| - **Per-medication schedule:** one `POST /schedule` creates `total_doses` `medication_schedule` rows (each `scheduled_time`) plus matching `medication_doses` rows linked via `schedule_id` (FK `on delete set null` for doses) — `VERIFIED (repository: `321-348` two-pass `add` + `flush` + `commit`)` | - **Scalability under production workloads** (many patients × long histories) — `UNVERIFIED` |
| - **Upcoming doses** is inherently bounded: `scheduled_time >= now()` + `status IS NULL` + `active` filter returns only future unmarked doses, not entire history — `VERIFIED (repository: `383-434`)` | - Any benchmark of timeline feed latency — `UNVERIFIED` (no benchmark implied) |

*This is an intentional implementation trade-off verified from the repository. No batching or pagination strategy currently exists for `GET /timeline`. Performance characteristics at production scale remain `UNVERIFIED / REQUIRES RESEARCH`.*

### 14.11 Interaction with LangGraph, evidence retrieval, and analysis

**Explicitly distinguished — two distinct consumers of `timeline_events`:**

| Consumer | Query shape | Purpose | Evidence |
|---|---|---|---|
| **Evidence Retrieval** | **Scoped retrieval** — `select(TimelineEvent).where(patient_id==..., or_(event_type.in_(_MEDICATION_ID_ON_REF_ID), event_type.in_(_MEDICATION_ID_ON_PAYLOAD), event_type=="condition_status_changed"))` via `ref_id`/`payload.medication_id` — per-finding, one `IN` list per finding — `VERIFIED (repository: `evidence_retrieval.py:33-75` docstring + `171-236` scoped query `or_(*match_clauses)`)` | Per-finding explainability: “what happened relevant to this specific drug-interaction/ADR/adherence finding” — `VERIFIED (repository: `evidence_retrieval.py:37-50`)` | Scoped personal `EvidenceItem`s with `occurred_at=event_time` |
| **Timeline Engine** | **Complete chronological retrieval** — `select(TimelineEvent).where(patient_id==...).order_by(event_time.asc())` — no `WHERE` beyond `patient_id`, no `LIMIT` — `VERIFIED (repository: `timeline_engine.py:44-53`)*;* opposite of the feed’s `DESC` — `VERIFIED (repository: `timeline_engine.py:37-43`)` | Unscoped narrative context for LLM: “what happened for this patient, period” — `VERIFIED (repository: `timeline_engine.py:1-12` “*retrieving and structuring the patient's timeline context … does NOT perform pattern detection*” + `langgraph_workflow.py:32-36` placement after Evidence Retrieval) | `TimelineContext(entries: list[TimelineEntry])` ordered `ASC` |

*These are **separate architectural responsibilities even though both read from `timeline_events`** — evidence is finding-scoped, timeline context is patient-scoped narrative — `VERIFIED (repository: `timeline_engine.py:1-24` vs `evidence_retrieval.py:1-19` docstrings explicitly contrast the two)`. `Analysis runs` persistence logs a third consumer: `analysis_run` timeline event in the same transaction as `analysis_runs` row — `VERIFIED (repository: `langgraph_workflow.py:243-262` `persist` + `timeline_writer.py:1-28`)`.*

### 14.12 Failure behavior — validation, ownership, conflict, and sweep race

**VERIFIED (repository: `schedule.py:284-311`, `294-303`, `383-495`, `models.py:dose_status_enum` + `timeline.py:30-38` + `backend/tests/test_schedule_api.py` + `test_timeline_api.py` repository test cases) + `VERIFIED (official documentation)` for HTTP 400/404/409/422:**

| Condition | HTTP | Repository evidence | Test case definition (repository — collected, not executed here) |
|---|---|---|---|
| `duration_days is None` | `400` | `schedule.py:285-293` `if medication.duration_days is None: raise HTTPException(400, "medication.duration_days must be set…")` | `test_generate_schedule_missing_duration_days:172` |
| `times_per_day is None and interval_hours is None` | `400` | `schedule.py:294-303` | `test_generate_schedule_missing_times_per_day:157` + `test_generate_schedule_missing_both:320` |
| `total_doses > 3650` | `400` | `schedule.py:311-317` | `test_generate_schedule_exceeding_max_doses:205` + `test_generate_schedule_interval_hours_only_exceeding_max_doses:342` |
| `schedule` already exists for `medication_id` | `409` | `schedule.py:294-303` `if existing scalar_one_or_none() is not None: raise 409` | `test_generate_schedule_twice_returns_409:187` |
| Non-existent `medication_id` / `patient_id` | `404` | `schedule.py:284-303` + `timeline.py:30-38` `_assert_patient_owned` | `test_generate_schedule_for_nonexistent_medication:223` + `test_upcoming_doses_for_nonexistent_patient:436` |
| Non-owned `medication_id` / `patient_id` / `dose_id` | `404` (never `403`) | `schedule.py:129-183` ownership helpers `Patient.user_id == current_user.id` (same as §9) + `timeline.py:30-38` | `test_generate_schedule_for_medication_owned_by_another_user:231` + `test_upcoming_doses_for_patient_owned_by_another_user:444` + `test_mark_dose_owned_by_another_user:610` + `test_timeline_for_patient_owned_by_another_user:286` |
| Already-marked `dose` (including sweep-applied `missed`) | `409` | `schedule.py:463-470` `if dose.status is not None: raise 409` | `test_mark_dose_twice_returns_409:580` + `test_mark_dose_sweeps_overdue_dose_before_processing_the_mark:700` |
| Mismatched `condition_id` / `medication_id` on symptom | `400` | `symptoms.py:62-81` (same pattern) — not in `schedule.py` but same ownership guard | `test_create_symptom_with_condition_from_another_patient:167` |
| Invalid `status` value (not `taken`/`missed`/`skipped`) | `422` | `models.py:dose_status_enum` (`taken`, `missed`, `skipped`) + Pydantic `MedicationDoseMarkRequest` validation → `422` via FastAPI | `test_mark_dose_invalid_status:631` |

*All `test_*` entries above are **repository test case definitions** — `VERIFIED (repository)` with references; `UNVERIFIED (empirical experiment in current environment)` because the integration suite requires live DB and was not executed here.*

### 14.13 Transaction boundaries — flush, stage-only writer, and atomic commits

**VERIFIED (repository: `backend/app/api/v1/schedule.py:321-348`, `439-470` + `backend/app/services/timeline_writer.py:22-48` + SQLAlchemy `add`/`flush`/`commit` docs — `VERIFIED (official documentation)`):**

| Operation | Transaction steps (verified) | Why this order |
|---|---|---|
| **`generate_schedule` (`POST /schedule`)** | `anchor = combine(start_date, 08:00 UTC)` → loop `total_doses`× `MedicationSchedule(..., scheduled_time)` + `db.add` each → `await db.flush()` (parents persisted, ids allocated) → loop `MedicationDose(..., schedule_id=schedule_row.id, scheduled_time=...)` + `db.add` each → `await db.commit()` → `refresh` each dose — `VERIFIED (repository: `321-348` two-pass `add` + `flush` + `commit`)` | `MedicationDose.schedule_id` is `ForeignKey(medication_schedule.id, ondelete=SET NULL)` — children need parent `id` — `VERIFIED (repository: `models.py:MedicationDose.schedule_id`)` |
| **`mark_dose` (`POST /doses/{id}/mark`)** | `dose, patient_id, drug_name = await _get_owned_dose(...)` → `await _sweep_missed_doses(patient_id, db)` → `await db.flush()` (so the just-swept `dose.status` is visible on the already-loaded `dose` object) → `if dose.status is not None: raise 409` → `dose.status = payload.status` + `dose.actual_time = payload.actual_time or (now if taken else None)` + `dose.updated_at = now` → `await log_timeline_event(...)` → `await db.commit()` + `refresh` — `VERIFIED (repository: `439-495`)` | `flush` before the `409` check ensures an overdue dose that the sweep just flipped to `missed` is correctly rejected, not overwritten — `VERIFIED (repository: `439-470` comment “*ensure `dose.status` reflects any sweep-applied change*” + `test_mark_dose_sweeps_overdue_dose_before_processing_the_mark:700`)* |
| **`log_timeline_event`** | `def log_timeline_event(db, *, patient_id, event_type, ...): event = TimelineEvent(...); db.add(event); return event` — **never** `commit` or `refresh` — `VERIFIED (repository: `timeline_writer.py:34-48` docstring “*only calls `db.add(...)` — it never commits*” + `grep -n "commit\|refresh" timeline_writer.py` → `0`)` — `VERIFIED (official documentation)` for `add` vs `flush` vs `commit` | Every caller adds the event to the **same session** as the entity write and commits both together — so the entity and its timeline event are always persisted atomically (never one without the other) — `VERIFIED (repository: `timeline_writer.py:6-12` docstring)` |
| **`list_upcoming_doses` sweep commit** | `await _sweep_missed_doses(patient_id, db)` → `await db.commit()` before the `select(...).where(status IS NULL ...)` — `VERIFIED (repository: `383-394`)` — the sweep’s `missed` writes are committed even though the caller is a `GET` (documented write side-effect) | `schedule.py:385-408` docstring “*Phase 9: runs the missed-dose sweep … documented write side-effect*” |

*No `celery`/`background task`/`pg_cron` is used — the two commit points above are the only places the sweep persists — `VERIFIED (repository: `grep -rn "commit" backend/app/api/v1/schedule.py` → only `list_upcoming` + `mark_dose` + `generate_schedule`)*.*

### 14.14 Current limitations and implementation status

**VERIFIED (repository: `schedule.py:96-102`, `1-27` + `PROJECT_PHASES.md` Phase 9 + `backend/app/api/v1/patients.py:13-16`, `conditions.py:1-13`, `symptoms.py:1-13`, `timeline.py:1-16` + `backend/tests/test_patients_api.py` + `test_symptoms_api.py` + `test_timeline_api.py` repository test cases):**

- **Implemented (Phases 7-9, verified):** `timeline_writer.py` additive service, `GET /patients/{id}/timeline` read-only feed (`DESC`), per-medication schedule generation with two branches (`times_per_day` / `interval_hours`) + `08:00 UTC` anchor + `3650` cap + `409` on duplicate, upcoming doses filtered + enriched, dose marking with `actual_time` rule + `409` immutability, lazy sweep scoped to `patient_id` (with `auto_detected:true`) — all as cited above — `VERIFIED (repository)`.
- **No background scheduler/cron** — intentionally substituted by the lazy, request-triggered sweep — `VERIFIED (repository: `schedule.py:1-27` + `PROJECT_PHASES.md` Phase 9 “*tech stack has no job scheduler … implemented as lazy, query-time sweep*”)*;* production timeliness of `missed` if no request triggers sweep is `UNVERIFIED / REQUIRES RESEARCH`**.
- **No adherence statistics endpoint** — not in frozen spec §7 (deferred) — `adherence_engine.py` is an internal input to `Safety Score` only, not a standalone `GET /adherence` API — `VERIFIED (repository: `PROJECT_PHASES.md` Phase 9 “*Adherence Statistics … explicitly out of scope for Phase 9’s own API surface — not part of the frozen section 7 API contract*”)**.*
- **Frozen-spec route scope (intentionally narrow, not a gap):** `DELETE /patients/{id}` does **not** exist — `VERIFIED (repository: `patients.py:13-16` “No DELETE /patients/{id}” + `test_patients_api.py:test_no_delete_endpoint_exists` asserting `405`)`; `conditions` exposes only `POST /patients/{id}/conditions` + `PUT /conditions/{id}` (no `GET`/`DELETE`) — `VERIFIED (repository: `conditions.py:1-13` + `test_conditions_api.py`)*;* `symptoms` exposes only `POST` + `GET` (no `PUT`/`DELETE`) — `VERIFIED (repository: `symptoms.py:1-13` + `test_symptoms_api.py:test_no_update_or_delete_endpoints_exist`)*;* `timeline` is read-only (`GET` only, `405` on others) — `VERIFIED (repository: `timeline.py:1-16` + `test_timeline_api.py:test_no_post_put_delete_endpoints_exist`)**.
- **No pagination on timeline/upcoming:** `GET /timeline` returns full `timeline_events` for the patient and `GET /upcoming` returns all future unmarked doses — both without `limit`/`offset`/`page` — `VERIFIED (repository: `timeline.py:44-63` no `limit` + `schedule.py:383-434` bounded only by `scheduled_time >= now()`)*;* scale behaviour `UNVERIFIED / REQUIRES RESEARCH`**.
- **No “correct a mark” flow:** a dose already `taken`/`missed`/`skipped` (whether explicit or sweep-applied) is rejected `409` — there is no spec-defined `PUT /doses/{id}` or “unmark” — `VERIFIED (repository: `schedule.py:462-470` docstring “*there is no spec-defined ‘correct a mark’ flow, so this is treated as immutable once set*” + `PROJECT_PHASES.md` Phase 9 “*intentionally immutable*”)**.*
- **No dedicated cleanup for generated `medication_schedule`/`medication_doses` rows** beyond `ON DELETE CASCADE` via `patients(id)` → `medications(id)` — `VERIFIED (repository: `001_initial_schema.sql:81-84` `on delete cascade` + `models.py:MedicationSchedule`/`MedicationDose` FKs + `PROJECT_PHASES.md` Phase 9 cleanup note)*.*

---

## 15. Configuration, Secrets & Environment

**Scope and evidence labeling:** every normative statement in §15 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative Pydantic/SQLAlchemy/httpx/FastAPI/LangGraph docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production latency, confidence calibration, pooler/RLS future). Implementation is the source of truth. No future env var, replica, or infra mechanism is documented as implemented beyond what the repository contains.

### 15.1 Purpose — single cached settings object, never hardcode secrets

**VERIFIED (repository: `backend/app/core/config.py:1-15` + `30-79` + `backend/.env.example:1-15`):**

`Settings(BaseSettings)` is the single runtime configuration object. It loads from environment variables (real env vars in deployment, `backend/.env` locally via `SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8")`) and is accessed via cached `get_settings()` — `VERIFIED (repository: `config.py:22` `BASE_DIR = Path(__file__).resolve().parents[2]` (`backend/`) + `56` `model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", ...)` + `77-79` `@lru_cache def get_settings(): return Settings()`)`. Module docstring states “*Loads settings from environment variables (.env locally, real env vars in deployment). Never hardcode secrets here*” — `VERIFIED (repository: `config.py:1-15`)`.

The repository defines **9 env vars** (see §15.2) plus one **derived** property `supabase_jwks_url`; the application reads them as `settings.<field>` — never from a second settings object or a separate `SUPABASE_JWKS_URL` env var (none exists — `VERIFIED (repository: `grep -n "SUPABASE_JWKS_URL" backend/app/core/config.py backend/.env.example` → `0`)**).

### 15.2 Repository location and architectural responsibility

**VERIFIED (repository: `backend/app/core/config.py:1-15` + `backend/.env.example:1-15` + `backend/app/db/session.py:11` + `backend/app/core/security.py:64-66` + `backend/app/api/v1/auth.py:25-30` + `backend/app/services/llm_providers.py:51-54` + `ls`):**

| File | Responsibility | Evidence |
|---|---|---|
| `backend/app/core/config.py` | Defines `class Settings(BaseSettings)` + cached `get_settings()` + derived `supabase_jwks_url`; documents that `supabase_jwt_secret` is deprecated and `LLM keys default to ""` (fail-closed, see §15.6) | `VERIFIED (repository: `1-15` docstring + `30-79` class + derived property)` |
| `backend/.env.example` | Template documenting all required keys with placeholder values (`password`, `https://xxxxxxxx.supabase.co`, empty `SUPABASE_JWT_SECRET`, `HTTP_TIMEOUT_SECONDS=10.0`) and comments pointing to Supabase project settings | `VERIFIED (repository: `1-15` template exists)` |
| `backend/.env` | Real local values (`postgresql+asyncpg://postgres:***@db....supabase.co:5432/postgres`, `SUPABASE_URL=https://***.supabase.co`, `SUPABASE_ANON_KEY=***`, `SUPABASE_JWT_SECRET=***`) — not a template; `.gitignore` contains `.env` so it is never committed | `VERIFIED (repository: `ls backend/.env` exists + `grep -n "\.env" backend/.gitignore` → `.env`)` |
| `backend/app/db/session.py` | Consumes `settings.database_url` via `create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)` with `AsyncSessionLocal(expire_on_commit=False)` and `async def get_db()` yielding and closing | `VERIFIED (repository: `11-22`)` |
| `backend/app/core/security.py` | Consumes `settings.supabase_jwks_url` and `settings.supabase_url` (issuer) for JWKS verification | `VERIFIED (repository: `64-66` + `88-93`, `123`)` |
| `backend/app/api/v1/auth.py` | Consumes `settings.supabase_url`, `settings.supabase_anon_key`, `settings.http_timeout_seconds` for the Supabase Auth proxy (`_supabase_headers`) | `VERIFIED (repository: `25-30` + `34-40`)` |
| `backend/app/services/llm_providers.py` | Consumes `settings.gemini_api_key`/`gemini_model`/`openrouter_api_key`/`openrouter_model`/`llm_timeout_seconds` per-provider | `VERIFIED (repository: `51-54` + `136`, `222`, `165`, `236`)` |

*All consumers import via `from app.core.config import get_settings; settings = get_settings()` — `VERIFIED (repository: `grep -rn "from app.core.config import get_settings" backend/app/` → 4 consumers).*

### 15.3 Inputs and outputs — the 9 env vars, derived JWKS URL, and cached instance

**VERIFIED (repository: `backend/app/core/config.py:32-79` + `backend/.env.example:1-15` + `backend/app/db/session.py:11` + Pydantic `@lru_cache` docs — `VERIFIED (official documentation)`):**

| Env var / property | Type / default | Description | Evidence |
|---|---|---|---|
| `DATABASE_URL` | `str` **required** (no `=`) | Async Postgres URL — deployment example `postgresql+asyncpg://postgres:password@db.xxxxxxxx.supabase.co:5432/postgres` — `VERIFIED (repository: `config.py:32` required vs `33-55` optional)` | `32` |
| `SUPABASE_URL` | `str = ""` | Project URL `https://xxxxxxxx.supabase.co` — `VERIFIED (repository: `33`)` | `33` |
| `SUPABASE_ANON_KEY` | `str = ""` | Anon key for Auth proxy `apikey` header | `34` |
| `SUPABASE_JWT_SECRET` | `str = ""` | **Deprecated, inert** — see §15.4 | `38` |
| `HTTP_TIMEOUT_SECONDS` | `float = 10.0` | Timeout for Supabase Auth `httpx.AsyncClient` | `35` |
| `GEMINI_API_KEY` | `str = ""` (`gemini_api_key`) | Empty = “not configured” → `LLMProviderError` at `complete()` | `42` |
| `GEMINI_MODEL` | `str = "gemini-2.0-flash"` | Configurable model name, not hardcoded | `43` |
| `OPENROUTER_API_KEY` | `str = ""` (`openrouter_api_key`) | Empty = “not configured” | `47` |
| `OPENROUTER_MODEL` | `str = "meta-llama/llama-3.1-8b-instruct:free"` | Configurable fallback model | `48` |
| `LLM_TIMEOUT_SECONDS` | `float = 30.0` (`llm_timeout_seconds`) | Shared timeout for Gemini + OpenRouter `httpx` calls | `54` |
| `supabase_jwks_url` (derived) | `str` property | `""` if `supabase_url` empty else `f"{supabase_url}/auth/v1/.well-known/jwks.json"` — **not a separate env var** | `57-75` property + docstring `10-15` + `grep SUPABASE_JWKS_URL` → `0` |

**Outputs:** a cached `Settings` instance via `@lru_cache def get_settings() -> Settings: return Settings()` — parsed once per process; every consumer reuses `settings = get_settings()` at import — `VERIFIED (repository: `77-79`)` and `VERIFIED (official documentation)` for `functools.lru_cache` singleton caching.

*Deployment note from `config.py:40-55` docstring: “*Model names are configurable rather than hardcoded since free-tier model availability changes over time; the defaults below are reasonable starting points, not guarantees*” — `VERIFIED (repository).*

### 15.4 Required vs optional — can initialize with optional config unset

**VERIFIED (repository: `backend/app/core/config.py:32-55` + `backend/app/core/security.py:88-93` + `backend/app/api/v1/auth.py:34-40` + `backend/app/services/llm_providers.py:139-140`, `225-226` + `backend/tests/test_security.py:93` repository test case):**

- **`DATABASE_URL` is required (no default)** — `database_url: str` on line `32` has no `= ""` — `VERIFIED (repository: `32`)`. All other Supabase/LLM keys default to `""` or to the documented defaults (`10.0`, `30.0`, model names) — `VERIFIED (repository: `33-55`)`.
- **The application can initialize with optional configuration unset; features requiring those settings fail at call time rather than during settings construction** — `VERIFIED (repository: `config.py:1-15` docstring + `40-55` “*Empty string means ‘not configured’ — GeminiProvider fails closed … rather than raising at settings-load time*” + `security.py:88-93` `if not settings.supabase_jwks_url: raise 500` only inside `_get_jwks_client()` + `auth.py:34-40` `if not settings.supabase_url or not settings.supabase_anon_key: raise 500` only inside `_supabase_headers()` + `llm_providers.py:139-140` `if not settings.gemini_api_key: raise LLMProviderError(...)` only inside `complete()`)*.* This wording is intentionally narrow — it does **not** imply every runtime path functions normally with optional config absent, only that `Settings()` construction succeeds.

*Empirical:* `test_decode_missing_config_raises_500:93` (empty `supabase_url` → `HTTPException(500)` at `_get_jwks_client()` call time) and `test_llm_providers.py` missing `GEMINI_API_KEY` → `LLMProviderError` at `complete()` — `VERIFIED (repository)` with references to repository test cases; `UNVERIFIED (empirical experiment in current environment)` for this run where DB-dependent suites were not executed.

### 15.5 Supabase Auth config — derived JWKS URL, not a separate env var

**VERIFIED (repository: `backend/app/core/config.py:10-15` + `57-75` + `backend/app/core/security.py:88-93`, `123` + `grep SUPABASE_JWKS_URL` → 0):**

`supabase_jwks_url` is a **derived property**, not a separate env var — `VERIFIED (repository: `config.py:10-15` “*supabase_jwks_url is a derived property, not a separate env var*” + `57-75` implementation `if not self.supabase_url: return ""` / `return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"`)`. Supabase publishes the JWKS at the fixed well-known path under the project’s own URL — `VERIFIED (repository: `config.py:12` comment)`. The verifier uses `PyJWKClient(settings.supabase_jwks_url, cache_keys=True)` and validates `audience="authenticated"` + `issuer=f"{settings.supabase_url}/auth/v1"` — `VERIFIED (repository: `security.py:88-93` + `123`)`.

- **No separate `SUPABASE_JWKS_URL` env var exists** — `grep -n "SUPABASE_JWKS_URL" backend/app/core/config.py backend/.env.example` → `0` — `VERIFIED (repository)`; also no additional `SUPABASE_JWKS_URL` definition via `grep -rn "SUPABASE_JWKS_URL" backend/` → `0`.

### 15.6 `SUPABASE_JWT_SECRET` is deprecated and inert — retained for backward compatibility

**VERIFIED (repository: `backend/app/core/config.py:19-24` + `33-38` + `backend/app/core/security.py` full-file `grep` → 0 reads + `backend/.env.example:7`):**

`supabase_jwt_secret: str = ""` remains only with the docstring:

> “*DEPRECATED … JWT verification now uses JWKS … so this field is no longer read by any verification code path. It is kept (rather than removed) purely for backward compatibility with existing `.env` files that still set it*” — `VERIFIED (repository: `config.py:19-24` + `33-38`)`.

- **`SUPABASE_JWT_SECRET` is retained for backward compatibility with existing configuration files; the repository does not reference it during JWT verification** — `VERIFIED (repository: `grep -rn "supabase_jwt_secret" backend/app/` → only `config.py` field definition + `.env.example` line + never read in `security.py` — `grep -rn "supabase_jwt_secret" backend/app/core/security.py` → `0` reads)**.* The stronger inference “removing it would be breaking” is **not** claimed — only retention and non-reference are `VERIFIED`.

### 15.7 Database engine — `settings.database_url` passthrough vs deployment example

**Distinguished:**

| What is repository-verified | Evidence |
|---|---|
| **Repository:** engine **receives `settings.database_url`** — the code stores a string and passes it to `create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)` with `AsyncSessionLocal(expire_on_commit=False)` and `async def get_db()` yielding and closing — `VERIFIED (repository: `config.py:32` `database_url: str` (no driver enforcement) + `session.py:13` `create_async_engine(settings.database_url, ...)` + `session.py:1-22` full file)` | — |
| **Deployment example:** the example files **use `postgresql+asyncpg://`** — `DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxxxxx.supabase.co:5432/postgres` in `backend/.env.example:1` and `DATABASE_URL=postgresql+asyncpg://postgres:***@db....supabase.co:5432/postgres` in `backend/.env` — `VERIFIED (repository: example file contents)` | — |

*The repository does **not** assert that every deployment must use `postgresql+asyncpg://` — it only verifies that the engine receives the configured `settings.database_url` string, while the deployment example happens to use that scheme — `VERIFIED (repository)` for the distinction.*

SQLAlchemy `create_async_engine` accepting a URL string and `asyncpg` as the async driver are `VERIFIED (official documentation)` for SQLAlchemy.

### 15.8 LLM keys and models — configurable, not hardcoded, shared timeouts

**VERIFIED (repository: `backend/app/core/config.py:40-55` + `backend/app/services/llm_providers.py:136`, `222`, `165`, `236` + `backend/app/services/llm_service.py:299` + `backend/app/api/v1/auth.py:110` + `httpx` docs — `VERIFIED (official documentation)`):**

- `gemini_api_key`/`gemini_model` and `openrouter_api_key`/`openrouter_model` default as in §15.3; `llm_timeout_seconds` (`30.0`) is shared for both providers while `http_timeout_seconds` (`10.0`) is for Supabase Auth — `VERIFIED (repository: `config.py:40-55`)`.
- `GeminiProvider.model` is `return settings.gemini_model` and `OpenRouterProvider.model` is `return settings.openrouter_model` — **read fresh from settings on each call, never hardcoded** — `VERIFIED (repository: `llm_providers.py:136` + `222`)` — used for logging `model_used`.
- `GeminiProvider._request_once` sends `headers = {"x-goog-api-key": settings.gemini_api_key, ...}` and `OpenRouterProvider.complete` sends `headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}` — `VERIFIED (repository: `llm_providers.py:165` + `236`)`.
- Both providers are called via `httpx.AsyncClient(timeout=timeout_seconds)` where `timeout_seconds` is `settings.llm_timeout_seconds` (LLM) or `settings.http_timeout_seconds` (Supabase) — `VERIFIED (repository: `llm_service.py:299` + `auth.py:110` + `llm_providers.py:133-155`)` and `VERIFIED (official documentation)` for `httpx.AsyncClient(timeout=)`.

### 15.9 Settings is a cached singleton — no per-request re-parse

**VERIFIED (repository: `backend/app/core/config.py:77-79` + `backend/app/db/session.py:11` + `backend/app/core/security.py:64-66` + `backend/app/api/v1/auth.py:25-30` + `backend/app/services/llm_providers.py:51-54` + `functools.lru_cache` docs — `VERIFIED (official documentation)`):**

`@lru_cache def get_settings() -> Settings: return Settings()` — so `Settings()` is parsed **once per process**; every consumer does `settings = get_settings()` at import and reuses the cached singleton (e.g. `settings.database_url`, `settings.supabase_url`, `settings.gemini_api_key`) — `VERIFIED (repository: `77-79` + consumer imports)`.

- **Repository verifies:** `@lru_cache` and cached singleton — `VERIFIED (repository: `77-79` + `grep -n "lru_cache" config.py` → `@lru_cache`)**;* `VERIFIED (official documentation)` for `functools.lru_cache` singleton caching.
- **Repository tests demonstrate monkeypatching (separate from architectural behavior):** `test_security.py:27` does `monkeypatch.setattr(security.settings, "supabase_url", TEST_SUPABASE_URL)` and `test_auth_api.py:40` does `monkeypatch.setattr(settings, "supabase_url", "https://example...")` — `VERIFIED (repository)` with references to repository test cases as *examples* of patching the cached instance — **monkeypatching is not a required mechanism, only a test seam** — the architectural guarantee is the cached singleton; tests happen to use `monkeypatch.setattr` on that instance.

### 15.10 Secrets handling — template vs real file; reviewed modules avoid logging

**VERIFIED (repository: `backend/.env.example:1-15` + `backend/.gitignore` + `backend/app/api/v1/auth.py:1-12` + `backend/app/services/llm_service.py:42-50`):**

- **Template vs real file:** `backend/.env.example` documents all keys with placeholder values (`password`, `https://xxxxxxxx.supabase.co`, empty `SUPABASE_JWT_SECRET`, `HTTP_TIMEOUT_SECONDS=10.0`) and comments (“*Get this from Supabase project settings …*”) — `VERIFIED (repository: `1-15`)`; real `backend/.env` contains actual `postgres:...` URL and keys but `.gitignore` contains `.env` so it is never committed — `VERIFIED (repository: `grep -n "\.env" backend/.gitignore` → `.env` + `ls backend/.env` exists)`.
- **Narrow logging guarantee (not a global “never logs secrets” claim):** **The reviewed authentication and LLM modules explicitly document avoiding logging passwords, tokens, prompts, explanations, and patient identifiers** — `VERIFIED (repository: `auth.py:1-12` docstring “*Email addresses are logged … passwords and tokens are never logged, in request bodies or responses*” + `llm_service.py:42-50` “*Only metadata — never the prompt, the patient snapshot/evidence that fed it, the generated explanation, or any patient identifier. Token usage fields are added to `extra` only when the provider actually reported them*” + `llm_providers.py:36-45` `LLMProviderError` never logs raw token)**.* This is a **reviewed-modules** guarantee, not a repository-wide global claim.*

### 15.11 Environment differences — local `.env` vs deployment env var precedence

**VERIFIED (repository: `backend/app/core/config.py:22`, `56` + Pydantic Settings precedence docs — `VERIFIED (official documentation)`):**

`SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8")` where `BASE_DIR = Path(__file__).resolve().parents[2]` (`backend/`) — `VERIFIED (repository: `22` + `56`)` — loads `backend/.env` **only if present**; in deployment real env vars **override** via `BaseSettings` precedence (`environment variable > dotenv file > defaults`) per Pydantic Settings docs — `VERIFIED (official documentation)` for Pydantic Settings env precedence. No `DATABASE_URL` fallback logic beyond that precedence is coded — `VERIFIED (repository: `grep -n "env_file" config.py` → 1 hit)`.

*`get_settings()` itself does not branch on `ENV` / `DEBUG` — no `if settings.env == "production"` logic exists — `VERIFIED (repository: `grep -n "ENV\|DEBUG\|environment.*production" config.py` → 0).*

### 15.12 Failure behavior — two distinct modes, not merged

**VERIFIED (repository: `backend/app/core/config.py:32` + `backend/app/db/session.py:11-13` + `backend/app/core/security.py:88-93` + `backend/app/services/llm_providers.py:139-140`, `225-226` + Pydantic `ValidationError` + SQLAlchemy `create_async_engine` docs — `VERIFIED (official documentation)`):**

| Mode | Trigger | What raises | When | Evidence |
|---|---|---|---|---|
| **Missing required variable** | `DATABASE_URL` not set (no default) | `pydantic.ValidationError` from `Settings()` construction — at import time (`settings = get_settings()` in `session.py` before any request) | Settings construction, before any request | `VERIFIED (repository: `config.py:32` `database_url: str` required vs `33-55` optional defaults + Pydantic `BaseSettings` required-field validation — `VERIFIED (official documentation)` for `ValidationError`) |
| **Malformed URL** | `DATABASE_URL=not-a-url` or missing `postgresql+asyncpg://` scheme or invalid host | `create_async_engine(settings.database_url, ...)` raises (SQLAlchemy `ArgumentError` / `ModuleNotFoundError` for unknown driver) | Engine initialization at `session.py:13`, still before any request but after `Settings()` succeeds | `VERIFIED (repository: `session.py:13` `create_async_engine(settings.database_url, ...)` executed at import; not merged with `ValidationError` case — two distinct failure types)** — `VERIFIED (official documentation)` for `create_async_engine` raising on malformed URL |
| **Optional Supabase config unset** | `SUPABASE_URL=""` or `SUPABASE_ANON_KEY=""` | `HTTPException(500, "Server is not configured with Supabase URL/anon key.")` from `_supabase_headers()` or `HTTPException(500, "Server is not configured with a Supabase URL.")` from `_get_jwks_client()` | **Call time** — first `POST /auth/signup`/`/auth/login` or first authenticated request — per `auth.py:34-40` + `security.py:88-93` | `VERIFIED (repository: `auth.py:34-40` 500 only when `_supabase_headers()` called + `security.py:88-93` 500 only when `_get_jwks_client()` called)` |
| **Optional LLM keys unset** | `GEMINI_API_KEY=""` or `OPENROUTER_API_KEY=""` | `LLMProviderError("GEMINI_API_KEY is not configured.")` / `("OPENROUTER_API_KEY is not configured.")` from `provider.complete()` | **Call time** — only inside `GeminiProvider.complete()` / `OpenRouterProvider.complete()` at LLM call time — `VERIFIED (repository: `llm_providers.py:139-140` + `225-226`)` | `VERIFIED (repository)` |

*Repository test cases:* `test_decode_missing_config_raises_500:93` asserts call-time `500` for empty `supabase_url` and `test_llm_providers.py` missing-key → `LLMProviderError` at `complete()` — `VERIFIED (repository)` with references to repository test cases; `UNVERIFIED (empirical experiment in current environment)` for this run where DB-dependent suites were not executed.

### 15.13 Comparison to other config approaches (not adopted) — no additional infra env vars

**VERIFIED (repository: `backend/app/core/config.py:32-55` + `backend/.env.example:1-15` + `grep` for absence):**

The repository defines a **single `DATABASE_URL` configuration value and contains no configuration for replicas, poolers, Redis, Celery, Sentry, or similar infrastructure** — `VERIFIED (repository: `config.py:32-55` only 9 env vars defined (`database_url`, `supabase_url`, `supabase_anon_key`, `supabase_jwt_secret`, `http_timeout_seconds`, `gemini_api_key`, `gemini_model`, `openrouter_api_key`, `openrouter_model`, `llm_timeout_seconds`) + `backend/.env.example:1-15` same 9 + `grep -rn "REDIS\|CELERY\|SENTRY\|REPLICA\|POOLER\|REDIS_URL\|CELERY_BROKER\|SENTRY_DSN\|LOG_LEVEL" backend/app/core/config.py backend/.env.example` → `0`)*.*

*No `LOG_LEVEL`, `ENV`, or `DEBUG` env var exists — `VERIFIED (repository: `grep -rn "LOG_LEVEL\|ENV\|DEBUG" config.py` → 0 for env-driven level).* Timeout handling is via two separate configurable values: `http_timeout_seconds` (`10.0`) for Supabase Auth and `llm_timeout_seconds` (`30.0`) for LLM providers — `VERIFIED (repository: `35` + `54`)`.

**UNVERIFIED / REQUIRES RESEARCH** for pooler/RLS future and timeout tuning at scale — explicitly not claimed as optimal.

### 15.14 Current limitations and implementation status

**VERIFIED (repository: `backend/app/core/config.py` + `backend/.env.example` + `backend/app/db/session.py` + `backend/app/services/llm_providers.py` + `backend/app/services/llm_service.py` + `langgraph_workflow.py`):**

- **Implemented (Phase 2/15, verified):** single cached `Settings(BaseSettings)` with `@lru_cache`, `BASE_DIR/.env` loading, 9 env vars + derived `supabase_jwks_url`, fail-closed-at-call-time for Supabase/LLM, fail-at-`Settings()`-construction for required `DATABASE_URL` vs malformed-URL engine failure, configurable models/timeouts, deprecated `supabase_jwt_secret` inert — all as cited above — `VERIFIED (repository)`.
- **`supabase_jwt_secret` inert but retained** — no code reads it; removing it would require updating existing `.env` files but is not a code dependency — `VERIFIED (repository: `config.py:19-24` + `grep` → 0 reads)`.
- **Single `DATABASE_URL` only** — no read-replica or Supabase pooler `auth.uid()` propagation is configured (see §8.9/§9.6 RLS `UNVERIFIED` — the backend’s `postgres` role may bypass RLS unless `FORCE` is set; this remains `UNVERIFIED` as before).
- **No `LOG_LEVEL`/`ENV` branching in settings** — `VERIFIED (repository: `grep -n "LOG_LEVEL\|ENV" config.py` → 0)`; `echo=False` in `session.py:13` is production default — `VERIFIED (repository: `session.py:13`)*.*
- **No secrets rotation logic in code** — rotation is operational (update env vars and restart), not coded as `Settings` logic — `VERIFIED (repository: `grep -rn "rotation\|rotate" backend/app/core/config.py` → 0)`.
- **LLM keys are fail-closed, not fail-open:** with `GEMINI_API_KEY=""` and `OPENROUTER_API_KEY=""` the deterministic pipeline (`calculate_safety_score` → `persist` → `analysis_runs` + `analysis_run` event) **still persists** with `llm_*` columns `NULL` — `VERIFIED (repository: `langgraph_workflow.py:197-218` catches `LLMExplanationError` → `llm_result: None` + `223-262` `persist` writes `llm_summary if llm_result else None`)**;* this is the intended production behavior with optional LLM config unset.

---

## 16. Testing & Quality Assurance

**Scope and evidence labeling:** every normative statement in §16 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative `pytest`/`pytest-asyncio`/`TestClient`/`FastAPI`/`PyJWT` docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production coverage, CI as shipped). Implementation is the source of truth. No future test harness, coverage gate, or CI workflow is documented as implemented beyond what the repository contains.

### 16.1 Purpose — mix of unit, engine-integration, and API integration tests

**VERIFIED (repository: `backend/tests/conftest.py:1-22` + `backend/tests/test_security.py:1-12` + `backend/tests/test_llm_service.py` + `backend/tests/test_drug_interaction_engine.py:1-15` + `backend/tests/test_patients_api.py:1-12` + `PROJECT_PHASES.md` + `ls backend/tests/test_*.py`):**

The repository contains a **mix of unit, engine-integration, and API integration tests**. Many integration tests are designed to run against a **live PostgreSQL/Supabase database**, while **pure unit tests (for example, security and LLM service tests) mock external dependencies** — `VERIFIED (repository: `conftest.py:1-12` describes integration majority as “*integration tests against a live database, run via the synchronous `TestClient`*” but `test_security.py:1-12` header states “*pure unit tests … JWKS client is mocked*” and `test_llm_service.py` mocks `httpx` — demonstrating the mix; `ls backend/tests/test_*.py | wc -l` → `21` files)**.**

Per `PROJECT_PHASES.md` (“*Test every phase before marking it complete*”), every phase from Database (Phase 1) through Evidence Retrieval (Phase 13) and LangGraph wiring (Phase 14) has a corresponding `test_*` file — `VERIFIED (repository: `PROJECT_PHASES.md` Phase notes + `ls` 21 files + `grep -l "TestClient" backend/tests/test_*.py` → 10 API integration files vs `grep -l "PyJWKClient\|httpx" backend/tests/test_security.py` for unit)**.**

### 16.2 Repository organization — 21 test files, dual `conftest.py`, `pytest.ini`

**VERIFIED (repository: `ls backend/tests/` + `pytest.ini` + `backend/tests/conftest.py` + `conftest.py` (root)):**

| Item | Verified detail |
|---|---|
| **Location & count** | `backend/tests/` contains **21** files: `test_adherence_engine.py`, `test_adr_engine.py`, `test_analysis_api.py`, `test_auth_api.py`, `test_conditions_api.py`, `test_drug_interaction_engine.py`, `test_evidence_retrieval.py`, `test_import_rxnorm.py`, `test_langgraph_workflow.py`, `test_llm_providers.py`, `test_llm_service.py`, `test_medications_api.py`, `test_patient_context_builder.py`, `test_patients_api.py`, `test_reference_drugs_search_api.py`, `test_safety_score_engine.py`, `test_schedule_api.py`, `test_security.py`, `test_symptoms_api.py`, `test_timeline_api.py`, `test_timeline_engine.py` + `conftest.py` — `VERIFIED (repository: `ls backend/tests/test_*.py | wc -l` → `21`)` |
| **`conftest.py` duality** | `backend/tests/conftest.py` defines the shared fixtures (`existing_auth_user_id`, `existing_drug_id`, `created_*_ids`, `_cleanup_*`) — `VERIFIED (repository: 31-125)`; root `conftest.py` adds `backend/` to `sys.path` (`BACKEND_DIR = ROOT / "backend"; sys.path.insert(0, str(BACKEND_DIR))`) so `from app.*` imports work when `pytest` is run from repo root — `VERIFIED (repository: root `conftest.py:9-15`)` |
| **`pytest.ini`** | Single file at repo root `pytest.ini` containing `[pytest]\nasyncio_mode = auto` — `VERIFIED (repository: `cat pytest.ini`)`; no `testpaths`, no `addopts`, no `pythonpath` beyond `conftest.py` insertion — `VERIFIED (repository: `grep -v "asyncio_mode" pytest.ini` → `0` other keys)` |
| **Dependencies** | `backend/requirements.txt` pins `pytest==8.3.3` + `pytest-asyncio==0.24.0` — `VERIFIED (repository: `grep -n "pytest" backend/requirements.txt`)` and `VERIFIED (official documentation)` for `pytest-asyncio` `asyncio_mode = auto` |

### 16.3 Test layers — three layers, three seams

**VERIFIED (repository: `backend/tests/test_security.py:1-12` + `backend/tests/test_drug_interaction_engine.py:1-15` + `backend/tests/test_patients_api.py:1-12` + `PROJECT_PHASES.md` Phase notes + `grep` for `TestClient` vs `AsyncSessionLocal`):**

| Layer | What it tests | How it runs | Example files | Evidence |
|---|---|---|---|---|
| **Pure unit** | JWT verification, LLM prompt/parse/fallback, provider retry — no DB, no `TestClient`; external I/O mocked (`PyJWKClient` via monkeypatch, `httpx` via injected fake providers or `monkeypatch`) | `pytest` with `test_security.py`’s `es256_keypair` fixture generating a keypair + `_patch_jwks_client` helper; `test_llm_service.py`’s `monkeypatch.setattr` on `_PROVIDERS` tuple | `test_security.py` (5 tests: valid/expired/unknown-kid/missing-config/malformed-sub), `test_llm_service.py` (29 tests: prompt determinism, fence/JSON recovery, missing-field, confidence `bool` rejection, Gemini→OpenRouter fallback, `fallback_used` logging) | `VERIFIED (repository: `test_security.py:1-12` “*pure unit tests … JWKS client is mocked, while JWT signature verification still runs*” + `test_security.py:40-72` `es256_keypair` + `_patch_jwks_client`)` |
| **Engine-integration (deterministic)** | Drug interaction, ADR, adherence, safety score, timeline, patient context, evidence retrieval **engines** — called directly with `AsyncSessionLocal` against a live DB, not via HTTP | `async with AsyncSessionLocal() as session: await detect_drug_interactions(patient_id, session)` — `VERIFIED (repository: `test_drug_interaction_engine.py:1-15` header “*Phase 10's tests therefore call the engine directly against a live DB session rather than through any endpoint*” + `PROJECT_PHASES.md` Phase 10 note same) | `test_drug_interaction_engine.py`, `test_adr_engine.py`, `test_adherence_engine.py`, `test_safety_score_engine.py`, `test_timeline_engine.py`, `test_patient_context_builder.py`, `test_evidence_retrieval.py` | `VERIFIED (repository: `grep -n "AsyncSessionLocal" backend/tests/test_drug_interaction_engine.py` + Phase 10 header)` |
| **API integration (contract)** | Frozen spec §7 HTTP contracts + ownership + validation — every route via `TestClient` (`client.post`/`get`/`put`/`delete`) with `dependency_overrides[get_current_user]` | `app = FastAPI(...); client = TestClient(app)` + `app.dependency_overrides[get_current_user] = _override_current_user(user_id)`; `conftest.py` provides `existing_auth_user_id` + `existing_drug_id` + `created_*_ids` | `test_patients_api.py`, `test_medications_api.py`, `test_conditions_api.py`, `test_symptoms_api.py`, `test_schedule_api.py` (schedule + adherence), `test_timeline_api.py`, `test_analysis_api.py`, `test_auth_api.py`, `test_reference_drugs_search_api.py` | `VERIFIED (repository: `test_patients_api.py:1-12` “*Authentication is bypassed via dependency override … about patient CRUD + ownership*” + `grep -l "from fastapi.testclient import TestClient" backend/tests/test_*.py` → 10 files)` |

*The repository currently contains no evidence of a fourth layer (e.g. browser E2E, load, or chaos tests) — `grep -rn "playwright\|cypress\|k6\|locust" backend/` → `0` — `VERIFIED (repository)` for absence, phrased as absence of repository evidence (not as proof such tests do not exist outside the repository).*

### 16.4 Pytest configuration

**VERIFIED (repository: `pytest.ini` + `backend/requirements.txt` + `backend/tests/conftest.py` + `conftest.py` root + Pydantic `BaseSettings` docs — `VERIFIED (official documentation)` for `pytest-asyncio`):**

- `pytest.ini` at repo root:

```ini
[pytest]
asyncio_mode = auto
```

`VERIFIED (repository: `cat pytest.ini` + `ls backend/pytest.ini 2>&1` → `No such file` — only root)**.

- No `testpaths`, no `addopts`, no `pythonpath`, no `markers`, no `xfail` strict config — `VERIFIED (repository: `grep -v "asyncio_mode" pytest.ini` → `0` other keys)**.
- Dependencies: `pytest==8.3.3` and `pytest-asyncio==0.24.0` in `backend/requirements.txt` — `VERIFIED (repository: `grep -n "pytest" backend/requirements.txt`)` and `VERIFIED (official documentation)` for `pytest-asyncio`’s `asyncio_mode = auto` (allows `async def test_*` without `@pytest.mark.asyncio`).
- Path handling: root `conftest.py` inserts `backend/` into `sys.path` so `from app.core.config import get_settings` works when `pytest` is invoked from repo root — `VERIFIED (repository: root `conftest.py:9-15` `BACKEND_DIR = ROOT / "backend"; sys.path.insert(0, str(BACKEND_DIR))`)` — `backend/tests/conftest.py` does **not** duplicate that insertion; it only defines fixtures (and imports `AsyncSessionLocal` via the already-inserted path).

### 16.5 Shared fixtures — FK-aware setup (`existing_auth_user_id`, `existing_drug_id`)

**VERIFIED (repository: `backend/tests/conftest.py:31-58` + `001_initial_schema.sql` FKs + `002_seed_data.sql`):**

```python
@pytest.fixture
async def existing_auth_user_id():   # VERIFIED (repository: conftest.py:31-43)
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id FROM auth.users LIMIT 1"))
        row = result.first()
    if row is None:
        pytest.skip("No rows in auth.users -- sign up at least one test user via POST /auth/signup ...")
    return row[0]

@pytest.fixture
async def existing_drug_id():        # VERIFIED (repository: conftest.py:45-58)
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id FROM reference_drugs LIMIT 1"))
        row = result.first()
    if row is None:
        pytest.skip("No rows in reference_drugs -- run 002_seed_data.sql ...")
    return row[0]
```

- **Why `existing_auth_user_id`:** `patients.user_id` has a real FK to `auth.users(id)` (`001_initial_schema.sql` `patients.user_id uuid not null references auth.users(id) on delete cascade`) — fabricating a UUID would violate the FK, as noted in Phase 1 caveats — `VERIFIED (repository: `conftest.py:1-12` docstring + `001_initial_schema.sql` FK definition)`.
- **Why `existing_drug_id`:** `medications.drug_id` has a real FK to `reference_drugs(id)` seeded in `002_seed_data.sql` (12 drugs, 7 interaction rules, 13 ADR rules per `PROJECT_PHASES.md` Phase 1 note “*Phase 1 seed data (002_seed_data.sql) is intentionally a small, curated set (12 drugs, 7 interaction rules, 13 ADR rules)*” — `VERIFIED (repository: `PROJECT_PHASES.md` + `002_seed_data.sql` row counts)**).
- **No `existing_condition_id` / `existing_symptom_id` is needed** — conditions/symptoms have no external FK beyond `patient_id`, which tests create directly via the patients API — `VERIFIED (repository: `conftest.py:10-12` docstring for Phase 5/6)**.
- **Both fixtures are `async def` and use `AsyncSessionLocal`** — `VERIFIED (repository: `conftest.py:31-58`)` and `VERIFIED (official documentation)` for `pytest-asyncio` `async def` fixtures with `asyncio_mode = auto`.

### 16.6 Shared fixtures — explicit tracking for isolation (autouse cleanup, not `SAVEPOINT` rollback)

**VERIFIED (repository: `backend/tests/conftest.py:60-125` + `14-22` docstring + `grep` for `SAVEPOINT` → 0 in app code):**

```python
@pytest.fixture
def created_patient_ids() -> list[uuid.UUID]:   # VERIFIED (repository: 60-68)
    return []

@pytest.fixture(autouse=True)                    # VERIFIED (repository: 70-85)
async def _cleanup_created_patients(created_patient_ids: list[uuid.UUID]):
    yield                                        # test runs here
    if not created_patient_ids:
        return
    stmt = text("DELETE FROM patients WHERE id IN :ids").bindparams(bindparam("ids", expanding=True))
    async with AsyncSessionLocal() as session:
        await session.execute(stmt, {"ids": created_patient_ids})
        await session.commit()
```

- **Same pattern for `created_medication_ids` / `created_condition_ids` / `created_symptom_ids`** with 3 additional `autouse` fixtures `_cleanup_created_medications` / `_cleanup_created_conditions` / `_cleanup_created_symptoms` each `DELETE FROM <table> WHERE id IN :ids` — `VERIFIED (repository: `conftest.py:70-125`)`.
- **Why not `SAVEPOINT`-rollback:** docstring records the Phase 3 review decision: “*A per-test SAVEPOINT-rollback pattern would require binding the async session to that same loop, which `TestClient` doesn't expose — forcing it risks cross-event-loop `asyncpg` errors. Instead, tests explicitly track the ids … and an autouse fixture deletes exactly those rows afterward, so repeated runs don't accumulate data.*” — `VERIFIED (repository: `conftest.py:14-22`)` and `VERIFIED (official documentation)` for `TestClient`’s synchronous ASGI thread model + `pytest-asyncio` event loop isolation.
- **Yield-then-delete:** `yield` suspends the fixture until the test completes; code after `yield` is teardown and runs **regardless of pass/fail** — `VERIFIED (official documentation)` for `pytest` `yield` fixtures + `VERIFIED (repository: `70-85` `yield` then `DELETE` + `commit`)`.

*The repository currently contains no evidence of `SAVEPOINT`/`ROLLBACK`/`begin_nested` in `backend/tests/conftest.py` — `grep -n "SAVEPOINT\|ROLLBACK\|begin_nested" backend/tests/conftest.py` → `0` — `VERIFIED (repository)` for absence (not as proof such a pattern could not exist outside the repository).*

### 16.7 Dependency overrides — ownership mocking without JWT

**VERIFIED (repository: `backend/tests/test_patients_api.py:14-28` + `backend/tests/test_medications_api.py:8-22` + `grep -rn "dependency_overrides\[get_current_user\]" backend/tests/` + FastAPI docs — `VERIFIED (official documentation)`):**

```python
def _override_current_user(user_id):                                         # VERIFIED (repository: test_patients_api.py:14-22)
    async def _fake_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="test@example.com")
    return _fake_current_user

@pytest.fixture(autouse=True)
def _clear_dependency_overrides():                                             # VERIFIED (repository: test_patients_api.py:24-28)
    yield
    app.dependency_overrides.clear()

def test_patient_owned_by_another_user_is_not_visible(existing_auth_user_id, created_patient_ids):
    app.dependency_overrides[get_current_user] = _override_current_user(existing_auth_user_id)
    # ... create as user A ...
    app.dependency_overrides[get_current_user] = _override_current_user(other_user_id)  # B
    resp = client.get(f"/api/v1/patients/{created['id']}")                   # VERIFIED (repository: 97-110)
    assert resp.status_code == 404
```

- **Seam:** `get_current_user` (`backend/app/core/security.py:141-180` — `CurrentUser` from `sub` UUID + `HTTPBearer(auto_error=False)`) is the sole FastAPI dependency providing identity; `app.dependency_overrides[get_current_user]` is the FastAPI DI override mechanism — `VERIFIED (official documentation)` for `app.dependency_overrides` (FastAPI docs).
- **Per-test clearing:** `_clear_dependency_overrides` is `autouse` and does `app.dependency_overrides.clear()` after `yield` — `VERIFIED (repository: `test_patients_api.py:24-28` + `test_medications_api.py` same pattern)**;* `backend/tests/conftest.py` itself does **not** mock `get_current_user` — it only provides `existing_auth_user_id`/`existing_drug_id` — `VERIFIED (repository: `grep -n "get_current_user" backend/tests/conftest.py` → 0)**.*
- **Coverage:** `grep -rn "dependency_overrides\[get_current_user\]" backend/tests/` → ~12 files (`test_patients_api.py`, `test_medications_api.py`, `test_conditions_api.py`, `test_symptoms_api.py`, `test_schedule_api.py`, `test_timeline_api.py`, `test_analysis_api.py`, etc.) — `VERIFIED (repository)` for breadth.

### 16.8 Environment requirements — live DB, seeded data, and `sys.path`

**VERIFIED (repository: `backend/tests/conftest.py:1-15` + `conftest.py` root `9-15` + `PROJECT_PHASES.md` Phase 1 note + `backend/.env.example:1-15` + `001_initial_schema.sql`):**

| Requirement | Verified detail |
|---|---|
| **Live Supabase Postgres** | `DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxxxxx.supabase.co:5432/postgres` in `backend/.env.example:1` (template) and `backend/.env` (real value) — `VERIFIED (repository: `ls backend/.env` exists + `grep -n "DATABASE_URL" backend/.env.example`)`; tests use `AsyncSessionLocal` (which reads `settings.database_url` at import via `session.py:11`) and `TestClient` against the ASGI app — both hit the same live DB |
| **Seeded reference data** | `002_seed_data.sql` (not `001_initial_schema.sql` alone) must be applied before medication/analysis tests — `VERIFIED (repository: `conftest.py:45-58` `existing_drug_id` `pytest.skip("No rows in reference_drugs -- run 002_seed_data.sql before running medication tests.")` + `PROJECT_PHASES.md` Phase 1 seed `12/7/13` counts)` |
| **At least one `auth.users` row** | `existing_auth_user_id` `SELECT id FROM auth.users LIMIT 1` or `pytest.skip("No rows in auth.users -- sign up at least one test user via POST /auth/signup before running patient tests.")` — `VERIFIED (repository: `conftest.py:31-43`)`; signup is via `POST /api/v1/auth/signup` (`auth.py:62-84` proxies to `POST {SUPABASE_URL}/auth/v1/signup`) — `VERIFIED (repository: `auth.py:62-84`)` |
| **`sys.path` for `pytest` from repo root** | Root `conftest.py` does `BACKEND_DIR = ROOT / "backend"; if str(BACKEND_DIR) not in sys.path: sys.path.insert(0, str(BACKEND_DIR))` so `from app.db.session import AsyncSessionLocal` works when `pytest` is invoked from repo root — `VERIFIED (repository: root `conftest.py:9-15`)`; `backend/tests/conftest.py` does **not** insert `sys.path` — it relies on the root one |

*The repository currently contains no evidence of an in-memory SQLite fake, `fakeredis`, or `pytest-postgresql` `tmp_path` factory for these integration tests — `grep -rn "sqlite\|fakeredis\|pytest-postgresql\|tmp_path.*db" backend/tests/conftest.py` → `0` — `VERIFIED (repository)` for absence, phrased as absence of repository evidence.*

### 16.9 API contract coverage — every frozen spec §7 route has a TestClient test

**VERIFIED (repository: `pharmacovigilance-spec-v1.md` §7 + `PROJECT_PHASES.md` Phase 3-9 frozen-spec notes + `grep -n "client\.(post\|get\|put\|delete)" backend/tests/test_*.py`):**

| Spec §7 route (frozen) | Test file | Verified `TestClient` call | Frozen-spec exclusion test (405) |
|---|---|---|---|
| `POST /auth/signup` + `POST /auth/login` | `test_auth_api.py` | `client.post("/api/v1/auth/signup", json={email,password})` → `201` (signup) + `client.post("/api/v1/auth/login", ...)` → `200` | — |
| `POST /patients` + `GET /patients` + `GET /patients/{id}` + `PUT /patients/{id}` | `test_patients_api.py` | `client.post("/api/v1/patients", json={name,age,sex,weight_kg})` → `201` + `client.get("/api/v1/patients")` + `client.get(f"/api/v1/patients/{id}")` + `client.put(f"/api/v1/patients/{id}", json={age:31})` → `200` (partial via `exclude_unset`) | `test_no_delete_endpoint_exists:114` — `client.delete(f"/api/v1/patients/{id}")` → `405` — per `patients.py:1-12` “*No DELETE /patients/{id} — not part of the frozen API contract*” + `PROJECT_PHASES.md` Phase 3 `DELETE Patient` note |
| `POST /patients/{id}/medications` + `GET /patients/{id}/medications` + `PUT /medications/{id}` + `DELETE /medications/{id}` | `test_medications_api.py` | `client.post(f"/api/v1/patients/{id}/medications", json={drug_id,start_date})` → `201` + `client.get` + `client.put` + `client.delete` → `204` | — (medications **is** `DELETE`, unlike patients) |
| `POST /patients/{id}/conditions` + `PUT /conditions/{id}` | `test_conditions_api.py` | `client.post(f"/api/v1/patients/{id}/conditions", json={name,diagnosed_date})` → `201` + `client.put(f"/api/v1/conditions/{id}", json={status:"improving"})` → `200` | `grep -n "GET.*conditions\|DELETE.*conditions" test_conditions_api.py` → `0`; `test_conditions_api.py` header: no `GET`/`DELETE` for conditions per frozen spec §7 + `conditions.py:1-13` — **no `GET` test exists, by design** |
| `POST /patients/{id}/symptoms` + `GET /patients/{id}/symptoms` | `test_symptoms_api.py` | `client.post(f"/api/v1/patients/{id}/symptoms", json={description,medication_id})` + `client.get(f"/api/v1/patients/{id}/symptoms")` | `test_no_update_or_delete_endpoints_exist:303` — `client.put`/`delete` on symptoms → `405` — per `symptoms.py:1-13` “*No PUT or DELETE routes — the frozen spec lists only these two*” |
| `POST /medications/{id}/schedule` + `GET /patients/{id}/doses/upcoming` + `POST /doses/{id}/mark` | `test_schedule_api.py` | `client.post(f"/api/v1/medications/{id}/schedule")` → `201` (or `409` if exists) + `client.get(f"/api/v1/patients/{id}/doses/upcoming")` + `client.post(f"/api/v1/doses/{id}/mark", json={status:"taken"})` | — |
| `GET /patients/{id}/timeline` | `test_timeline_api.py` | `client.get(f"/api/v1/patients/{id}/timeline")` → `200` ordered `DESC` | `test_no_post_put_delete_endpoints_exist:300` — `client.post/put/delete` on timeline → `405` — per `timeline.py:1-16` read-only |
| `POST /patients/{id}/analyze` (`201`) + `GET /patients/{id}/analysis` (history `DESC`) | `test_analysis_api.py` | `client.post(f"/api/v1/patients/{id}/analyze")` → `201` + `client.get(f"/api/v1/patients/{id}/analysis")` → `200` | — |
| `GET /reference-drugs/search` | `test_reference_drugs_search_api.py` | `client.get("/api/v1/reference-drugs/search?q=war&limit=20")` → `200` with `q.strip()` + `case` ranking | — |

*Each API test file also covers **ownership** (`404` for non-owned/missing `patient_id` + `medication_id`/`condition_id` mismatch `400`) and **validation** (`422` for invalid enums, `405` for missing routes) — e.g. `test_patient_owned_by_another_user_is_not_visible:97` + `test_create_condition_for_patient_owned_by_another_user_returns_404:100` + `test_medication_owned_by_another_user_is_not_visible:183` — `VERIFIED (repository)` with references; `UNVERIFIED (empirical experiment in current environment)` where suite not executed here.*

### 16.10 Engine / wiring tests — direct call vs via HTTP, two suites for LangGraph

**VERIFIED (repository: `PROJECT_PHASES.md` Phase 10 + Phase 14 notes + `backend/tests/test_drug_interaction_engine.py:1-15` header + `backend/tests/test_langgraph_workflow.py:1-15` header + `backend/tests/test_analysis_api.py:1-15` header):**

| Suite | How it runs | What it verifies | Evidence |
|---|---|---|---|
| **Deterministic engines direct** | `async with AsyncSessionLocal() as session: await detect_drug_interactions(patient_id, session)` — no HTTP, no `TestClient`, no `dependency_overrides` | Engine `detect_drug_interactions` is direction-independent, `detect_adrs` allows multiple per drug, `analyze_adherence` counts overdue `NULL` as `missed`, `calculate_safety_score` composes penalties → `SafetyScoreResult`, `build_timeline_context` orders `ASC` | `VERIFIED (repository: `test_drug_interaction_engine.py:1-15` header “*Phase 10's tests therefore call the engine directly against a live DB session rather than through any endpoint*” + `grep -n "AsyncSessionLocal" backend/tests/test_drug_interaction_engine.py` + `PROJECT_PHASES.md` Phase 10 note)* |
| **LangGraph wiring direct** | `async with AsyncSessionLocal() as session: final_state = await run_analysis(patient_id, session)` — calls `langgraph_workflow.py:339-356` `run_analysis` directly against a live `AsyncSession`; tests graph wiring, state threading (`AnalysisState`), `NotImplementedError`/`LLMExplanationError` → `llm_result: None`, and `deterministic_result` excludes `timeline_context` | `test_langgraph_workflow.py:1-15` header “*calls `run_analysis()` directly against a live DB session (graph wiring, state threading, persistence, LLM-NotImplementedError handling, repeated-run versioning), independent of the API layer*” | `VERIFIED (repository: `test_langgraph_workflow.py:1-15` header + `grep -n "run_analysis" backend/tests/test_langgraph_workflow.py`)` |
| **LangGraph wiring via HTTP** | `client.post(f"/api/v1/patients/{id}/analyze")` via `TestClient` — tests `POST /analyze` `201` + `GET /analysis` history `DESC` + ownership `404` | HTTP contract, ownership via `get_current_user`, re-fetch via `analysis_run_id`, empty history for never-analyzed patient | `VERIFIED (repository: `test_analysis_api.py:1-15` header “*exercises the HTTP layer separately (both routes, ownership enforcement, empty history)*” + `PROJECT_PHASES.md` Phase 14 “*test_analysis_api.py exercises the HTTP layer separately*”)* |

*The repository currently contains no evidence of a single test that exercises both layers in one function — the two suites are deliberately separate per `PROJECT_PHASES.md` Phase 14 “*mirrors the existing convention of separating engine/service-level tests from API-level tests used throughout Phases 10-13*” — `VERIFIED (repository)` for separation.*

### 16.11 CI / coverage — no coverage gate or GitHub Actions workflow in the repository

**VERIFIED (repository: `ls .github/workflows/ 2>&1` + `grep -rn "coverage\|coveragerc\|\.coveragerc\|--cov\|fail_under" backend/` + `cat pytest.ini` + `backend/requirements.txt`):**

- **The repository currently contains no evidence of a coverage measurement tool** — `grep -rn "coverage\|coveragerc\|\.coveragerc\|--cov\|fail_under" backend/` → `0` results and `pytest.ini` contains no `addopts = --cov` or `fail_under` — `VERIFIED (repository)` for absence.
- **The repository currently contains no evidence of a GitHub Actions workflow** (no `.github/workflows/*.yml`) — `ls .github/workflows/ 2>&1` → `No such file or directory` — `VERIFIED (repository)` for absence (not as proof CI does not exist outside the repository — e.g. in a fork or external CI system — only that this repository as shipped has no workflow YAML).
- **The repository currently contains no evidence of a coverage gate** (`fail_under`, `threshold`, `min_coverage`) — `grep -rn "fail_under\|threshold" backend/` → `0` — `VERIFIED (repository)` for absence.
- **Therefore, CI, coverage, and quality gates are `UNVERIFIED / REQUIRES RESEARCH` for this repository as shipped** — the engineering standard for `pytest` exists (see §16.4), but automated enforcement does not — `VERIFIED (repository)` for absence, phrased as absence of repository evidence.

### 16.12 Performance / parallelism — synchronous `TestClient`, no `xdist`

**VERIFIED (repository: `backend/tests/conftest.py:14-22` + `backend/requirements.txt` + `grep -n "xdist" backend/requirements.txt pytest.ini`):**

| Aspect | Verified detail |
|---|---|
| **`TestClient` is synchronous** | “*run via the synchronous `TestClient`, which executes the ASGI app on its own thread/event loop*” — `VERIFIED (repository: `conftest.py:14-22` docstring)` and `VERIFIED (official documentation)` for Starlette `TestClient` synchronous ASGI execution |
| **No `pytest-xdist`** | `grep -n "xdist" backend/requirements.txt pytest.ini` → `0` and `pytest.ini` has no `addopts = -n auto` — `VERIFIED (repository)` for absence; therefore **the repository currently contains no evidence of parallel test execution via `xdist`** — not as proof parallelism does not exist outside the repository |
| **No dedicated load/stress harness** | `grep -rn "k6\|locust\|pytest-benchmark\|benchmark" backend/tests/` → `0` — `VERIFIED (repository)` for absence |
| **Each test creates its own `AsyncSessionLocal` and tracks `created_*_ids`** | No shared mutable state beyond that explicit per-test list — `VERIFIED (repository: `conftest.py:60-125`)`; the async `existing_auth_user_id` / `existing_drug_id` are `async def` with `asyncio_mode = auto` — `VERIFIED (repository: `31-58`)` |

*The repository currently contains no evidence of a performance budget, timeout, or `httpx.TimeoutException` being asserted as a performance gate in `backend/tests/` — `grep -rn "TimeoutException" backend/tests/` shows only `llm_providers` timeout handling, not a perf gate — `VERIFIED (repository)` for absence.*

### 16.13 Failure behavior — skip vs fail vs cleanup regardless of outcome

**VERIFIED (repository: `backend/tests/conftest.py:31-58` `pytest.skip` + `70-125` `yield` then `DELETE` + `grep -n "pytest.skip" backend/tests/conftest.py` + `pytest.skip` docs — `VERIFIED (official documentation)`):**

| Condition | What the test harness does | Evidence |
|---|---|---|
| **Live DB has 0 rows in `auth.users`** (no user ever signed up via `POST /auth/signup`) | `existing_auth_user_id` fixture executes `SELECT id FROM auth.users LIMIT 1` → `row is None` → `pytest.skip("No rows in auth.users -- sign up at least one test user via POST /auth/signup before running patient tests.")` — dependent tests are **skipped**, not failed | `VERIFIED (repository: `conftest.py:31-43` `if row is None: pytest.skip(...)`)` + `VERIFIED (official documentation)` for `pytest.skip` semantics |
| **Live DB has 0 rows in `reference_drugs`** (no `002_seed_data.sql`) | `existing_drug_id` similarly `pytest.skip("No rows in reference_drugs -- run 002_seed_data.sql ...")` | `VERIFIED (repository: `conftest.py:45-58`)` |
| **Test creates patients/medications/conditions/symptoms then the test passes or fails** | `autouse` fixtures `_cleanup_created_patients` / `_cleanup_created_medications` / `_cleanup_created_conditions` / `_cleanup_created_symptoms` do `yield` (suspend until test completes) then `if not created_*_ids: return` else `DELETE FROM <table> WHERE id IN :ids` + `await session.commit()` — `VERIFIED (repository: `conftest.py:70-125` `yield` then `DELETE` + `commit`)`; this runs **regardless of pass/fail** per `pytest` `yield` fixture teardown semantics — `VERIFIED (official documentation)` for `yield` teardown | `VERIFIED (repository: `conftest.py:70-125`)` + `VERIFIED (official documentation)` for `yield` |
| **Wrong `DATABASE_URL` or DB unreachable at import** | `AsyncSessionLocal` construction at `session.py:11` (`engine = create_async_engine(settings.database_url, ...)`) would raise at import/first `await session.execute` before any test runs — no `try` in `conftest.py` catches this | `VERIFIED (repository: `session.py:11` engine at import)**; not a `pytest.skip` — would be an import/collection error |

### 16.14 Current limitations — frozen-spec scope, live-DB requirement, no SQLite, no load test

**VERIFIED (repository: `backend/tests/test_patients_api.py:114` + `backend/tests/test_symptoms_api.py:303` + `backend/tests/test_timeline_api.py:300` + `backend/tests/test_import_rxnorm.py:1-15` + `PROJECT_PHASES.md` Phase 3-9 notes + `grep` for absence):**

| Limitation | Verified detail |
|---|---|
| **Live DB required — no in-memory SQLite/Fake FK** | Integration tests require a live Supabase Postgres with `DATABASE_URL` and seeded `reference_drugs` — `VERIFIED (repository: `conftest.py:1-12` header + `002_seed_data.sql` dependency + `grep -rn "sqlite\|fakeredis\|pytest-postgresql\|tmp_path.*db" backend/tests/conftest.py` → `0` — **The repository currently contains no evidence of an in-memory SQLite fake, `fakeredis`, or `pytest-postgresql` `tmp_path` factory**)** |
| **Frozen-spec exclusions are `405` by design, and their tests are `VERIFIED`** | `test_patients_api.py:114` `test_no_delete_endpoint_exists` (`DELETE /patients/{id}` → `405`) + `test_symptoms_api.py:303` `test_no_update_or_delete_endpoints_exist` (`PUT`/`DELETE /symptoms` → `405`) + `test_timeline_api.py:300` `test_no_post_put_delete_endpoints_exist` (`POST`/`PUT`/`DELETE /timeline` → `405`) — each asserts `405` per `PROJECT_PHASES.md` Phase 3 “*No DELETE /patients*”, Phase 5 “*no `GET`/`DELETE` for conditions*”, Phase 6 “*no `PUT`/`DELETE` for symptoms*” — `VERIFIED (repository)` with references; these are frozen-spec scope, not gaps |
| **Seeded Phase 1 additions still pending per §6.2** | No test seeds `term_type`/`is_active` Phase 1 additions (still pending per `ARCHITECTURE_DECISIONS.md:99` `Implementation status: not yet applied`) — `VERIFIED (repository: `grep -n "term_type\|is_active" backend/tests/` → `0` beyond docstring)** |
| **No load/performance benchmark in repo** | `grep -rn "k6\|locust\|pytest-benchmark\|benchmark" backend/` → `0` — **The repository currently contains no evidence of a load/performance benchmark** — `VERIFIED (repository)` for absence; any statement about API latency under production load is `UNVERIFIED / REQUIRES RESEARCH` |
| **RxNorm import test hits real network** | `backend/tests/test_import_rxnorm.py:1-15` header “*sourcing data from NLM's public RxNav REST API*” (`https://rxnav.nlm.nih.gov/REST/allconcepts.json` vs `…/Prescribe/allconcepts.json` per §7.1) — requires network or is skipped if offline — `VERIFIED (repository: `test_import_rxnorm.py:1-15`)` + `VERIFIED (official documentation)` for RxNav REST API per NLM |

---

## 17. Deployment & Infrastructure

**Scope and evidence labeling:** every normative statement in §17 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative PostgreSQL/SQLAlchemy/FastAPI/Pydantic/Uvicorn/GitHub Actions/Docker docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production throughput, execution plans, pooler future). Implementation is the source of truth. No future container, CI, or infra mechanism is documented as implemented beyond what the repository contains.

### 17.1 Overall deployment model — Supabase-hosted PostgreSQL, FastAPI on Uvicorn

**VERIFIED (repository: `README.md` Tech Stack + `backend/app/main.py:1-19` + `backend/requirements.txt: uvicorn[standard]==0.30.6` + `grep -rn "docker\|supabase/config\|fly.io\|vercel\|render" backend/ .` → `0` infra files + `ls supabase/ 2>&1` → `No such file or directory` + `ls backend/Dockerfile* 2>&1` → `No such file`):**

**The repository contains no evidence of a self-hosted database, container image, or orchestration configuration.** The documented deployment targets **Supabase PostgreSQL** with a **FastAPI application served by Uvicorn** (`app.main:app`) — `VERIFIED (repository: `README.md` Tech Stack: `Database - Supabase PostgreSQL` + `backend/app/main.py:19` `app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")` + `backend/requirements.txt` `uvicorn[standard]==0.30.6` + absence evidence above)`. `Supabase Auth` owns `auth.users` and issues ES256 JWTs verified via `PyJWKClient` against the derived JWKS (`§8`, `§15.5`) — `VERIFIED (repository: `backend/app/core/security.py:88-93`, `backend/app/core/config.py:57-75`)`.

**The repository currently contains no evidence of Dockerfiles, Compose manifests, or Supabase CLI configuration** — `VERIFIED (repository: `ls backend/Dockerfile*` → `No such file`, `ls docker-compose*` → `No such file`, `ls supabase/config.toml` → `No such file`, `grep -rn "docker" backend/ .` → `0` code hits — see §17.6 for detailed absence, phrased as absence of repository evidence, not as proof such artifacts do not exist outside the repository).*

### 17.2 Repository location, build artifact, and checkout layout

**VERIFIED (repository: `README.md` Project Structure + `ls backend/requirements.txt` + `ls frontend/ 2>&1` + `backend/requirements.txt` 13 lines + `.gitignore`):**

| Item | Verified detail |
|---|---|
| **Backend** | `backend/app/` contains `main.py`, `api/v1/`, `core/`, `db/`, `services/`, `analysis/` — additive router registrations via `app.include_router` — `VERIFIED (repository: `ls backend/app/` + `backend/app/main.py:19-45` `app.include_router` calls)` |
| **Build artifact** | **Single source** `backend/requirements.txt` (`fastapi==0.115.0`, `sqlalchemy==2.0.35`, `asyncpg==0.29.0`, `uvicorn[standard]==0.30.6`, `pydantic==2.9.2`, `pydantic-settings==2.5.2`, `pyjwt[crypto]>=2.13.0,<3.0.0`, `httpx==0.27.2`, `langgraph==0.2.60`, `pytest==8.3.3`, `pytest-asyncio==0.24.0`, etc. — 13 deps) — `VERIFIED (repository: `cat backend/requirements.txt` 13 lines)`; `README.md` “*Dependencies live in exactly one place: `backend/requirements.txt`. There is no root-level `requirements.txt`*” — `VERIFIED (repository: `README.md` Project Structure + `ls backend/requirements.txt` exists, `ls requirements.txt` at repo root → `No such file`) |
| **Frontend directory in this checkout** | **This repository checkout does not contain a `frontend/` directory, although the README references one** — `VERIFIED (repository: `README.md` Project Structure lists `frontend/` (`backend/ app/ supabase/migrations/ tests/ requirements.txt` / `frontend/` / `docs/`) + `ls frontend/ 2>&1` → `No such file or directory` in this checkout)** — *This wording avoids implying the overall project lacks a frontend; it distinguishes the repository snapshot from the overall project.* |
| **Ignored secrets** | `backend/.env` is never committed — `.gitignore:8` `.env` + `10` `!.env.example` + `11` `!backend/.env.example` + `12` `backend/.env` — `VERIFIED (repository: `grep -n "\.env" .gitignore` + `ls backend/.env` exists)** |

### 17.3 Hosting — Supabase PostgreSQL, not self-hosted

**VERIFIED (repository: `backend/.env.example:1` + `backend/.env:1` + `backend/app/db/session.py:13` + `ls supabase/ 2>&1` + Supabase connection string docs — `VERIFIED (official documentation)`):**

| Aspect | Verified detail |
|---|---|
| **Connection string** | `DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxxxxx.supabase.co:5432/postgres` in `backend/.env.example:1` (template) and `DATABASE_URL=postgresql+asyncpg://postgres:***@db.icwtuhbhdrpjdtoibxxk.supabase.co:5432/postgres` in `backend/.env` (real value) — `VERIFIED (repository: `cat backend/.env.example:1` + `cat backend/.env:1` redacted)` |
| **Code** | `engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)` with `AsyncSessionLocal(expire_on_commit=False)` and `async def get_db()` yielding and closing — the code **receives `settings.database_url`** (configured string) and passes it to SQLAlchemy; it does **not** branch on a “local DB” vs “Supabase DB” flag — `VERIFIED (repository: `backend/app/db/session.py:13` + `backend/app/core/config.py:32` `database_url: str` required)** |
| **Supabase CLI config** | **The repository currently contains no evidence of Supabase CLI configuration** — `ls supabase/ 2>&1` → `No such file or directory` + `ls supabase/config.toml 2>&1` → `No such file` + `grep -rn "supabase/config" backend/` → `0` — `VERIFIED (repository)` for absence |
| **Self-hosted DB / pooler** | **The repository contains no evidence of a self-hosted database cluster or pooler configuration** — no `docker-compose.yml` with `postgres:` service, no `supabase/config.toml` with `db.port`, no `POOLER_URL` env var — `VERIFIED (repository: `grep -rn "POOLER\|supabase/config\|docker" backend/ .` → `0`)` |

*Supabase connection string format `postgresql://` with `asyncpg` async driver `postgresql+asyncpg://` is `VERIFIED (official documentation)` for Supabase and `asyncpg`.*

### 17.4 Health check — liveness probe, unrelated to auth or DB

**VERIFIED (repository: `backend/app/main.py:48-51` + `grep -rn "health\|/health" backend/app/main.py backend/app/api -n`):**

```python
@app.get("/health")                      # VERIFIED (repository: main.py:48)
async def health() -> dict:              # VERIFIED (repository: 49)
    """Basic liveness check, unrelated to auth -- useful for deployment probes."""
    return {"status": "ok"}              # VERIFIED (repository: 51)
```

- **This is the only health/operational endpoint in the repository** — `grep -rn "health\|/health\|/ready" backend/app/` → only `main.py:48-51` — `VERIFIED (repository)` for singularity.
- **It is unrelated to auth — no `Depends(get_current_user)`** and does not verify DB or JWKS reachability — `VERIFIED (repository: `main.py:48-51` has no dependency; docstring “*unrelated to auth -- useful for deployment probes*”)*;* a `SUPABASE_URL=""` deployment still returns `{"status": "ok"}` even though the first authenticated request would `500` — `VERIFIED (repository: `security.py:88-93` call-time `500` vs `main.py:48-51` always `ok`).
- **No `/ready` check that verifies DB or JWKS reachability exists** — `grep -rn "/ready\|readiness" backend/` → `0` — **The repository currently contains no evidence of a readiness probe** — `VERIFIED (repository)` for absence.

*HTTP `GET` liveness semantics are `VERIFIED (official documentation)` for FastAPI routing.*

### 17.5 Environment handling — template vs real file, gitignored, no hardcoding

**VERIFIED (repository: `backend/.env.example:1-15` + `ls backend/.env` + `.gitignore:8-12` + `backend/app/core/config.py:1-15` + `backend/app/api/v1/auth.py:1-12` + `backend/app/services/llm_service.py:42-50`):**

| File | Content | Evidence |
|---|---|---|
| `backend/.env.example` | Template documenting all required keys with placeholder values (`password`, `https://xxxxxxxx.supabase.co`, empty `SUPABASE_JWT_SECRET`, `HTTP_TIMEOUT_SECONDS=10.0`) and comments (`Get this from Supabase project settings → Database → Connection string`) | `VERIFIED (repository: `1-15` template exists)` |
| `backend/.env` | Real local values (`postgresql+asyncpg://postgres:***@db....supabase.co:5432/postgres`, `SUPABASE_URL=https://***.supabase.co`, `SUPABASE_ANON_KEY=***`, `SUPABASE_JWT_SECRET=***`) — `ls backend/.env` exists | `VERIFIED (repository: `ls backend/.env` exists)` |
| `.gitignore` | Contains `.env`, `backend/.env`, `!.env.example`, `!backend/.env.example` so real secrets are never committed and the template stays tracked | `VERIFIED (repository: `grep -n "\.env" .gitignore` → `.env` + `!.env.example` + `backend/.env`)` |
| `config.py` | Module docstring “*Loads settings from environment variables (.env locally, real env vars in deployment). Never hardcode secrets here*” | `VERIFIED (repository: `1-15`)` |
| `auth.py` / `llm_service.py` | **The reviewed authentication and LLM modules explicitly document avoiding logging passwords, tokens, prompts, explanations, and patient identifiers** — `auth.py:1-12` “*Email addresses are logged … passwords and tokens are never logged, in request bodies or responses*” + `llm_service.py:42-50` “*Only metadata — never the prompt, the patient snapshot/evidence that fed it, the generated explanation, or any patient identifier. Token usage fields are added to `extra` only when the provider actually reported them*” — `VERIFIED (repository: reviewed modules)` — *This is a reviewed-modules guarantee, not a global “never logs secrets” claim.* | — |

### 17.6 Migrations — three sequential SQL files, manual application, no automated tool

**VERIFIED (repository: `ls *.sql` + `README.md` Database setup + `ARCHITECTURE_DECISIONS.md:107` + `grep -rn "alembic\|Alembic" backend/`):**

**The repository contains three sequential SQL migration files.** The README instructs operators to apply them manually in order. **The repository contains no evidence of an automated migration tool such as Alembic.**

| Evidence | Verified detail |
|---|---|
| **Repository:** three files | `ls *.sql` → `001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql` (3 files) — `VERIFIED (repository: `ls *.sql`)` |
| **Repository:** manual instruction | `README.md` Database setup: “*Before starting the backend for the first time, run the SQL migrations against your Supabase project (SQL editor or `psql`), in order:*” + `ARCHITECTURE_DECISIONS.md:107` “*No automated migration-tracking tool is in use*” — `VERIFIED (repository)` |
| **Repository:** no evidence of `Alembic` | `grep -rn "alembic\|Alembic" backend/` → `0` — **The repository currently contains no evidence of `Alembic`** — `VERIFIED (repository)` for absence, phrased as absence of repository evidence (not as proof such a tool does not exist outside the repository) |

*`001_initial_schema.sql` (schema + enums + indexes + RLS), `002_seed_data.sql` (12 drugs, 7 interaction rules, 13 ADRs per §15 repository-verified counts), `003_reference_drugs_external_reference.sql` (external reference cols `rxcui`/`source` per §6) — `VERIFIED (repository)` for content.* `psql` / Supabase SQL editor is `VERIFIED (official documentation)` for `psql` as the manual application tool.

### 17.7 Build process — local development vs production

**Do not let readers infer that `uvicorn --reload` is the deployment recommendation. Separate into two statements:**

| | Verified detail |
|---|---|
| **Development:** README documents `uvicorn app.main:app --reload` | **Development:** `README.md` Getting Started: `cd backend` → `python -m venv .venv` → `source .venv/bin/activate` → `pip install -r requirements.txt` → `cp .env.example .env` → `# edit .env` → `uvicorn app.main:app --reload` — API at `http://localhost:8000`, docs at `http://localhost:8000/docs`, health at `http://localhost:8000/health` — `VERIFIED (repository: `README.md` Getting Started)`; `echo=False` in `session.py:13` is production default (`flip to True locally if you need to debug SQL`) — `VERIFIED (repository: `session.py:13` comment)` |
| **Production:** the repository specifies the ASGI application (`app.main:app`) but **does not prescribe** a production process manager (Gunicorn, systemd, Docker, Kubernetes, etc.) | **Production:** `backend/app/main.py:19` defines `app = FastAPI(...)`; deployment example is `app.main:app` as ASGI callable — `VERIFIED (repository: `main.py:19` + `grep -rn "gunicorn\|Gunicorn\|systemd\|Dockerfile\|Kubernetes\|k8s" backend/README.md backend/app/main.py` → `0` — **The repository currently contains no evidence of a prescribed production process manager (Gunicorn, systemd, Docker, Kubernetes, etc.)** — `VERIFIED (repository)` for absence)** |

*`venv` + `pip install -r requirements.txt` + `uvicorn --reload` are `VERIFIED (official documentation)` for Python packaging and `uvicorn`.*

### 17.8 Containerization and Supabase CLI — no evidence in this repository

**VERIFIED (repository: `ls backend/Dockerfile* 2>&1` + `ls docker-compose* 2>&1` + `ls supabase/config.toml 2>&1` + `grep -rn "docker" backend/ .`):**

**The repository currently contains no evidence of Dockerfiles, Compose manifests, or Supabase CLI configuration.**

- `ls backend/Dockerfile* 2>&1` → `No such file or directory` — `VERIFIED (repository)` for absence
- `ls docker-compose* 2>&1` → `No such file or directory` — `VERIFIED (repository)` for absence
- `ls supabase/ 2>&1` → `No such file or directory` + `ls supabase/config.toml 2>&1` → `No such file` — `VERIFIED (repository)` for absence of Supabase CLI `config.toml`
- `grep -rn "docker" backend/ .` → `0` code hits (only this architecture documentation mentions it) — `VERIFIED (repository)` for absence

*This is phrased as absence of repository evidence, not as proof containers or Supabase CLI do not exist outside the repository. Docker / Compose / Supabase CLI expected file names are `VERIFIED (official documentation)` for those tools.*

### 17.9 CI/CD — no evidence of GitHub Actions workflows that test or deploy

**VERIFIED (repository: `ls .github/workflows/ 2>&1` + `grep -rn "workflows" backend/`):**

**The repository currently contains no evidence of GitHub Actions workflows that execute tests or deployments automatically.** — `ls .github/workflows/ 2>&1` → `No such file or directory` — `VERIFIED (repository)` for absence — not as “therefore no automated `pytest`/`deploy`” globally, only that this repository as shipped has no workflow YAML.

*GitHub Actions `workflows/` expected path `.github/workflows/*.yml` is `VERIFIED (official documentation)` for GitHub Actions.*

*The repository currently contains no evidence of `coverage`/`coveragerc`/`--cov`/`fail_under` — `grep -rn "coverage\|coveragerc\|--cov" backend/` → `0` — `VERIFIED (repository)` for absence; therefore CI, coverage, and quality gates are `UNVERIFIED / REQUIRES RESEARCH` for this repository as shipped (see §16.11).*

### 17.10 Database setup — run migrations in Supabase before first backend start

**VERIFIED (repository: `README.md` Database setup + `backend/tests/conftest.py:45-58` + `001_initial_schema.sql` header):**

README Database setup states (verbatim): “*Before starting the backend for the first time, run the SQL migrations against your Supabase project (SQL editor or `psql`), in order:*” — `001_initial_schema.sql` → `002_seed_data.sql` → `003_reference_drugs_external_reference.sql` — `VERIFIED (repository: `README.md` Database setup)`; `002_seed_data.sql` must be applied for `existing_drug_id` fixture to find `reference_drugs` — `VERIFIED (repository: `conftest.py:45-58` `existing_drug_id` `pytest.skip("No rows in reference_drugs -- run 002_seed_data.sql …")` + `001_initial_schema.sql` header “*Target: Supabase PostgreSQL*”)**.**

*Supabase SQL editor / `psql` is `VERIFIED (official documentation)` for `psql` as the manual application tool.*

### 17.11 Version — repository-verifiable facts only

**VERIFIED (repository: `backend/app/main.py:19` + `git tag` non-verification):**

- **Repository-verifiable fact:** FastAPI application version string is `version="0.1.0"` in `backend/app/main.py:19` `app = FastAPI(title="Pharmacovigilance MVP API", version="0.1.0")` — `VERIFIED (repository: `grep -n "version=" backend/app/main.py` → `0.1.0`)` and `VERIFIED (official documentation)` for `FastAPI(version=)` (SemVer)
- **Repository tags were not verified from repository evidence** — no `git tag` output is cited here — therefore no tag is claimed to exist or not exist in this section
- **Not discussed in architecture documentation:** planned tag policies (`v0.1-architecture-final` etc.) are **not** documented here — per your instruction to state only repository-verifiable facts and to not discuss planned tag policies in architecture documentation — `VERIFIED (repository: omission is intentional per instruction)`

### 17.12 Failure behavior — `GET /health` always `ok` vs Supabase/JWKS/LLM call-time `500`

**VERIFIED (repository: `backend/app/core/config.py:32` required vs optional + `backend/app/db/session.py:13` + `backend/app/api/v1/auth.py:34-40` + `backend/app/core/security.py:88-93` + `backend/app/main.py:48-51` + `backend/tests/test_security.py:93` repository test case):**

| Mode | Trigger | What raises | When | Evidence |
|---|---|---|---|---|
| **Missing required `DATABASE_URL`** | `DATABASE_URL` not set (no default at `config.py:32` `database_url: str`) | `pydantic.ValidationError` from `Settings()` construction — at import time (`settings = get_settings()` in `session.py:11` before any request) | Settings construction, before any request | `VERIFIED (repository: `config.py:32` required + Pydantic `BaseSettings` required-field validation — `VERIFIED (official documentation)` for `ValidationError`) |
| **Malformed `DATABASE_URL`** | `DATABASE_URL=not-a-url` or missing `postgresql+asyncpg://` scheme | `create_async_engine(settings.database_url, ...)` raises (SQLAlchemy `ArgumentError` / `ModuleNotFoundError` for unknown driver) — `VERIFIED (official documentation)` for `create_async_engine` | Engine initialization at `session.py:13`, still before any request but after `Settings()` succeeds | `VERIFIED (repository: `session.py:13` + `VERIFIED (official documentation)` for `create_async_engine` raising) |
| **Optional Supabase config unset** | `SUPABASE_URL=""` or `SUPABASE_ANON_KEY=""` | `HTTPException(500, "Server is not configured with Supabase URL/anon key.")` from `_supabase_headers()` (`auth.py:34-40`) or `HTTPException(500, "Server is not configured with a Supabase URL.")` from `_get_jwks_client()` (`security.py:88-93`) | **Call time** — first `POST /auth/signup`/`/auth/login` or first authenticated request — per `auth.py:34-40` + `security.py:88-93` | `VERIFIED (repository: `auth.py:34-40` 500 only when `_supabase_headers()` called + `security.py:88-93` 500 only when `_get_jwks_client()` called)` |
| **Optional LLM keys unset** | `GEMINI_API_KEY=""` or `OPENROUTER_API_KEY=""` | `LLMProviderError("GEMINI_API_KEY is not configured.")` / `("OPENROUTER_API_KEY is not configured.")` from `provider.complete()` | **Call time** — only inside `GeminiProvider.complete()` / `OpenRouterProvider.complete()` at LLM call time — `VERIFIED (repository: `llm_providers.py:139-140` + `225-226`)` | `VERIFIED (repository)` |
| **Health probe** | `GET /health` | `{"status": "ok"}` — always `200`, regardless of Supabase/JWKS/LLM config | No `Depends(get_current_user)`; `GET /health` is unrelated to auth — `VERIFIED (repository: `main.py:48-51` docstring + `grep -rn "health\|/health" backend/app/main.py` → only that route)` | `VERIFIED (repository: `main.py:48-51`)` |

*Repository test case:* `test_decode_missing_config_raises_500:93` asserts call-time `500` for empty `supabase_url` and `test_llm_providers.py` missing-key → `LLMProviderError` at `complete()` — `VERIFIED (repository)` with references to repository test cases; `UNVERIFIED (empirical experiment in current environment)` for this run where DB-dependent suites were not executed.

### 17.13 Observability — two independent claims

**Keep these as two independent claims — one does not imply the other:**

| Claim | Repository evidence | Classification |
|---|---|---|
| **1) Ordinary Python module loggers exist** — `logging.getLogger("app...")` in individual modules, e.g. `patients.py` (`logger = logging.getLogger("app.patients")` + `logger.info("Patient created", extra={"patient_id":...})`), `schedule.py` (`logger.info("Schedule generated", extra={"medication_id":...})`), `analysis.py` (`logger.info("Analysis run completed", extra={"analysis_run_id":...})`) with `extra={"patient_id":..., "user_id": ...}` | `VERIFIED (repository: `grep -rn "logging.getLogger" backend/app/api/v1/patients.py` → `logger = logging.getLogger("app.patients")` + `grep -rn "logger\." backend/app/api/v1/patients.py | head -5` → `logger.info("Patient created", extra={"patient_id":...})`)` + `VERIFIED (official documentation)` for `logging` stdlib `getLogger` | **VERIFIED (repository)** for ordinary loggers present |
| **2) The repository contains no evidence of centralized observability tooling (Prometheus, OpenTelemetry, Sentry, etc.) and no evidence of a `LOG_LEVEL` env var** | `grep -rn "SENTRY\|prometheus\|opentelemetry\|otel\|LOG_LEVEL" backend/app/core/config.py backend/.env.example backend/app/main.py` → `0` (except per-module `logging`) — `VERIFIED (repository)` for absence of centralized tooling/`LOG_LEVEL` | **VERIFIED (repository)** for **no evidence of centralized observability/`LOG_LEVEL`** — independent claim, one does not imply the other |

### 17.14 Current limitations and implementation status

**Keep every limitation introduced with “The repository currently contains no evidence of…” and group them by category (Containerization, CI/CD, Migration tooling, Observability, Frontend checkout, Infrastructure services):**

- **Containerization** — `The repository currently contains no evidence of Dockerfiles, Compose manifests, or Supabase CLI configuration` — `VERIFIED (repository: `ls backend/Dockerfile*` → `No such file` + `ls docker-compose*` → `No such file` + `ls supabase/config.toml` → `No such file`)`
- **CI/CD** — `The repository currently contains no evidence of GitHub Actions workflows that execute tests or deployments automatically` — `VERIFIED (repository: `ls .github/workflows/` → `No such file`)`
- **Migration tooling** — `The repository currently contains no evidence of an automated migration tool such as Alembic` — `VERIFIED (repository: `grep -rn "alembic\|Alembic" backend/` → `0`)` — only three sequential SQL files, manual `psql`/SQL editor per `README.md`
- **Observability** — `The repository currently contains no evidence of centralized observability tooling (Prometheus, OpenTelemetry, Sentry, etc.)` — `VERIFIED (repository: `grep -rn "SENTRY\|prometheus" backend/` → `0`)` — only per-module `logging.getLogger` as in §17.13; and `The repository currently contains no evidence of a LOG_LEVEL environment variable` — `VERIFIED (repository: `grep -n "LOG_LEVEL" backend/app/core/config.py` → `0`)`
- **Frontend directory (current checkout)** — `The repository currently contains no evidence of a frontend/ directory in this checkout, although the README references one` — `VERIFIED (repository: `ls frontend/ 2>&1` → `No such file` in this checkout — see §17.2)`
- **Infrastructure services** — `The repository currently contains no evidence of Redis, Celery, Sentry, or similar infrastructure services` — `VERIFIED (repository: `grep -rn "REDIS\|CELERY\|SENTRY\|REDIS_URL\|CELERY_BROKER" backend/app/core/config.py backend/.env.example` → `0` — single `DATABASE_URL` only — see §15.13)` — additionally `UNVERIFIED / REQUIRES RESEARCH` for future infra design beyond this repo — consistent with §§15-16

*All of the above are phrased as **absence of repository evidence** (not as proof such capabilities do not exist outside the repository), consistent with Sections 15–16.*

---

## 18. Security, Compliance & Data Governance

**Scope and evidence labeling:** every normative statement in §18 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative Pydantic/SQLAlchemy/FastAPI/PyJWT/PostgreSQL/`logging` docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production `EXPLAIN` plans, GDPR retention period, storage-layer encryption beyond standard DB usage). Implementation is the source of truth. No HIPAA/GDPR certification, encryption-at-rest code, or retention TTL is documented as implemented beyond what the repository contains. The repository currently contains no evidence of such certification or application-managed encryption, and any external storage-layer encryption was not evaluated in this review.

### 18.1 Overall purpose — multiple layers, primary repository-verifiable boundary is application-layer ownership

**VERIFIED (repository: `backend/app/schemas/*.py` `Field`/`Literal` + `backend/app/core/security.py` ES256 `PyJWKClient` + `backend/app/api/v1/*` `_assert_patient_owned`/`_get_owned_*` + `001_initial_schema.sql:169-222` RLS + `backend/app/services/timeline_writer.py` + `analysis_runs`/`timeline_events` + `grep -rn "HIPAA\|GDPR\|SOC2" backend/ ARCHITECTURE_DECISIONS.md` → `0`):**

**The repository implements multiple security layers including Pydantic validation, JWT authentication, application-layer ownership checks, and database Row Level Security (RLS). Based on repository evidence, application-layer ownership checks are the primary repository-verifiable authorization boundary, while RLS is implemented as an additional defense-in-depth mechanism.**

- **Audit is implemented through ordinary module logging together with persisted `timeline_events` and `analysis_runs` records** — `VERIFIED (repository: `backend/app/api/v1/patients.py:87-102` `logger.info("Patient created", extra={"patient_id":..., "user_id":...})` + `backend/app/services/timeline_writer.py:22-48` `db.add(TimelineEvent(...))` never `commit` + `backend/app/services/langgraph_workflow.py:243-262` `db.add(analysis_run)` + `log_timeline_event` + `commit` + `001_initial_schema.sql:125-138` `timeline_events` table + `140-151` `analysis_runs` table)** — not “structured audit” globally.

**The repository currently contains no evidence of HIPAA/GDPR certification** — `grep -rn "HIPAA\|GDPR\|SOC2" backend/ ARCHITECTURE_DECISIONS.md` → `0` — `VERIFIED (repository)` for **absence of certification claim** (phrased as “no evidence of … certification **in this repository**”).

### 18.2 Repository location and architectural responsibility

**VERIFIED (repository: `ls backend/app/schemas/` + `ls backend/app/api/v1/*.py` + `001_initial_schema.sql:169-222` + `backend/app/services/timeline_writer.py` + `ls backend/app/services/`):**

| Location | Responsibility | Evidence |
|---|---|---|
| `backend/app/schemas/` (8 files) | Input validation — `patient.py`, `medication.py`, `condition.py`, `symptom.py`, `schedule.py`, `auth.py`, `analysis.py`, `reference_drug.py` — each field constrained via `Field`/`Literal` to mirror `ENUM`/business rule (see §18.3) — `VERIFIED (repository: `ls backend/app/schemas/` (8) + `grep -n "Field\|Literal" backend/app/schemas/patient.py`)` | Pydantic `Field`/`Literal` — `VERIFIED (official documentation)` |
| `backend/app/core/security.py` + `backend/app/api/v1/auth.py` | Authentication — ES256 JWKS via `PyJWKClient(settings.supabase_jwks_url, cache_keys=True)`, `audience="authenticated"`, `issuer="{SUPABASE_URL}/auth/v1"`, `algorithms=["ES256"]` — see §8 (not duplicated here) — `VERIFIED (repository: `security.py:88-93`, `123`)` | `PyJWT` + `PyJWKClient` ES256 — `VERIFIED (official documentation)` |
| `backend/app/api/v1/*.py` (`patients.py`, `medications.py`, `conditions.py`, `symptoms.py`, `timeline.py`, `schedule.py`, `analysis.py`) | Authorization — `_assert_patient_owned` / `_get_owned_*` via `Patient.user_id == current_user.id` → `404` never `403` (§18.5) — `VERIFIED (repository: `patients.py:37-44`)` | — |
| `001_initial_schema.sql:169-222` | Row Level Security — `enable row level security` on all 11 tables + policies `for all using (auth.uid() = user_id)` / `using (auth.role() = 'authenticated')` (§18.6) | PostgreSQL `ENABLE ROW LEVEL SECURITY` + `CREATE POLICY` + `FORCE` — `VERIFIED (official documentation)` |
| `backend/app/services/timeline_writer.py` + per-module `logger.info` + `analysis_runs`/`timeline_events` | Audit — ordinary `logging.getLogger` + `db.add(TimelineEvent(...))` never `commit` + `analysis_run` event in same transaction as `analysis_runs` row (§18.7) | `logging` stdlib — `VERIFIED (official documentation)` |

### 18.3 Input validation — Pydantic mirrors Postgres `ENUM` and business rules, `422` before DB

**VERIFIED (repository: `backend/app/schemas/patient.py:16-19` + `backend/app/schemas/medication.py:28-31` + `backend/app/schemas/symptom.py:28` + `backend/app/schemas/auth.py:7` + `backend/app/schemas/condition.py:9-12` + `backend/app/schemas/schedule.py:21-31` + `backend/app/schemas/timeline.py` + `001_initial_schema.sql` `severity_level` etc. + `grep -rn "Field(min_length" backend/app/schemas/*.py`):**

| Schema | Field | Constraint | Why | Evidence |
|---|---|---|---|---|
| `patient.py` | `name` | `Field(min_length=1, max_length=200)` | Mirrors `patients.name text not null` with business max — `001_initial_schema.sql` `name text` + app max | `VERIFIED (repository: `patient.py:16` + `CREATE TABLE patients`)* |
| `patient.py` | `age` | `Field(ge=0, le=130)` | Business range — no DB check beyond `int` | `VERIFIED (repository: `patient.py:17`)` |
| `patient.py` | `weight_kg` | `Field(gt=0)` | Business — `numeric` allows any, Pydantic enforces `>0` | `VERIFIED (repository: `patient.py:19`)` |
| `medication.py` | `times_per_day` | `Field(ge=1, le=24)` | Mirrors business `1-24` per day | `VERIFIED (repository: `medication.py:29`)` |
| `medication.py` | `interval_hours` | `Field(gt=0)` | Business — `numeric` allows any positive | `VERIFIED (repository: `medication.py:30`)` |
| `medication.py` | `duration_days` | `Field(ge=1)` | Business — at least 1 day | `VERIFIED (repository: `medication.py:31`)` |
| `medication.py` | `dose` | `Field(max_length=200)` | Text length cap | `VERIFIED (repository: `medication.py:28`)` |
| `symptom.py` | `description` | `Field(min_length=1, max_length=2000)` | Prevent empty / overly long | `VERIFIED (repository: `symptom.py:28`)` |
| `symptom.py` | `severity` | `Literal["mild","moderate","severe"]` | Exactly `severity_level` enum (`mild`/`moderate`/`severe`) — `001_initial_schema.sql` `severity_level` | `VERIFIED (repository: `symptom.py:9` docstring + `Literal`)` |
| `condition.py` | `status` / `reason` | `Literal["active","improving",...]` / `Literal["doctor_diagnosis",...]` | Exactly `condition_status_enum` / `condition_reason_enum` — `001_initial_schema.sql` those enums | `VERIFIED (repository: `condition.py:9-12` docstring “*constrained via Literal to the same values as …*” + `Literal`)` |
| `auth.py` | `password` | `Field(min_length=8)` | Business minimum — not a DB column (Supabase Auth owns `auth.users`) | `VERIFIED (repository: `auth.py:7`)` |
| `schedule.py` | `status` (mark) | `Literal["taken","missed","skipped"]` | Exactly `dose_status_enum` (`taken`/`missed`/`skipped`) — `001_initial_schema.sql` `dose_status_enum` | `VERIFIED (repository: `schedule.py:21-31` docstring)* |

*Every `_create` route validates via the `...Create` schema and every `_update` via the `...Update` schema (with `exclude_unset=True` for partial puts) before any `db.add` — `VERIFIED (repository: `patients.py:62-84` `PatientCreate` → `Field` validation, then `db.add`)*;* invalid input → `422 Unprocessable Entity` via FastAPI/Pydantic before any `INSERT` — `VERIFIED (official documentation)` for `FastAPI` → `422` on `Field` failure.*

### 18.4 Authentication — ES256 JWKS, `CurrentUser`, `401` collapsed (recap, §8 is source)

**VERIFIED (repository: `backend/app/core/security.py:64-180` + `backend/app/core/config.py:57-75` + `backend/tests/test_security.py:1-12`):**

This section recaps §8; §8 remains the source. Authentication is **ES256 via `PyJWKClient(settings.supabase_jwks_url, cache_keys=True)`** with `algorithms=["ES256"]` (hardcoded, not from JWK), `audience="authenticated"`, `issuer=f"{settings.supabase_url}/auth/v1"`, `require=["exp","aud","iss"]`, and `sub` → `UUID` → `CurrentUser(id, email)` — `VERIFIED (repository: `security.py:64-180` + `config.py:57-75` derived `supabase_jwks_url`)`.

- `ExpiredSignatureError` → `401 "Access token has expired."` and any other `PyJWKClientError`/`PyJWTError` (unknown `kid`, bad signature, wrong `aud`/`iss`, disallowed `alg`) → `401 "Invalid access token."` collapsed to one generic message — `VERIFIED (repository: `security.py:123-140` `except ExpiredSignatureError` vs `except (PyJWKClientError, PyJWTError)`)` and `VERIFIED (official documentation)` for `PyJWT`/`PyJWKClient` ES256 — see §8.6.
- `supabase_url` empty → `HTTPException(500, "Server is not configured with a Supabase URL.")` only at `_get_jwks_client()` **call time**, not at `get_settings()` construction — `VERIFIED (repository: `security.py:88-93` + `config.py:57-75` `if not supabase_url: return ""`)` — see §15.12.
- Pure unit tested by `test_security.py` with mocked `PyJWKClient` and `es256_keypair` fixture — 5 tests (`test_decode_valid_token`, `test_decode_expired_token_raises_401`, `test_decode_unknown_kid_raises_401`, `test_decode_missing_config_raises_500`, `test_get_current_user_rejects_malformed_sub`) — `VERIFIED (repository: `test_security.py:1-12` “*pure unit tests … JWKS client is mocked*” + `28-93` fixtures)*.

### 18.5 Authorization — application-layer ownership is the repository-verifiable boundary

**VERIFIED (repository: `backend/app/api/v1/patients.py:37-44` + `medications.py:58-89` + `conditions.py:47-75` + `symptoms.py:49-60` + `timeline.py:30-38` + `schedule.py:129-183` + `analysis.py:37-48` + `grep -rn "user_id.*current_user.id" backend/app/api/v1/` + `backend/tests/test_patients_api.py:97`):**

- **Mechanism (two patterns, helpers kept local per file):**
  1) `_assert_patient_owned(patient_id, current_user, db)` → `select(Patient.id).where(Patient.id==patient_id, Patient.user_id==current_user.id)` → `404 "Patient not found."` if `scalar_one_or_none() is None` — `VERIFIED (repository: `patients.py:37-44` template for all files)`.
  2) `_get_owned_* (e.g. `_get_owned_medication`)` → `select(<Resource>).join(Patient, Patient.id == <Resource>.patient_id).where(<Resource>.id==resource_id, Patient.user_id==current_user.id)` → `404 "Medication not found."` etc. — `VERIFIED (repository: `medications.py:72-89` + `conditions.py:61-75` + `schedule.py:162-183`)`.

- **Never `403`, always `404`:** every path that would be a `403` is deliberately a `404` — `raise HTTPException(status_code=404, detail="Patient not found." / "Medication not found." / "Condition not found." / "Dose not found." / "Symptom not found.")` — `VERIFIED (repository: `grep -rn "403\|HTTP_403" backend/app/api/v1/` → `0` ownership `403` hits — only `401` for auth — vs `grep -rn "404.*not found\|HTTP_404" backend/app/api/v1/` → ~12 `404` ownership hits)*;* also `grep -rn "user_id.*from.*body\|request\.body.*user_id" backend/app/api/v1/` → `0` — no `user_id` is ever taken from body/query, always `current_user.id` — `VERIFIED (repository: `grep` → 0 + `CurrentUser` construction `security.py:177-180` only from `sub`).

- **No roles:** `CurrentUser` is `id: UUID` + `email: str | None` — no `role`/`scope`/`is_admin` — `VERIFIED (repository: `security.py:97-106` `class CurrentUser`)` and `grep -rn "role\|is_admin\|is_owner\|scope" backend/app/api/v1/` (for ownership) → `0` for access-control branching — `VERIFIED (repository)` for absence of role check.

- **Repository test cases:** `test_patient_owned_by_another_user_is_not_visible:97` (user A creates, user B `get` → `404`), `test_create_condition_for_patient_owned_by_another_user_returns_404:100`, `test_medication_owned_by_another_user_is_not_visible:183`, `test_create_symptom_for_patient_owned_by_another_user_returns_404:220`, `test_generate_schedule_for_medication_owned_by_another_user_returns_404:231`, `test_timeline_for_patient_owned_by_another_user_returns_404:286`, `test_analyze_for_patient_owned_by_another_user_returns_404:92` — `VERIFIED (repository)` with references to repository test cases; `UNVERIFIED (empirical experiment in current environment)` where suite not executed here.

### 18.6 Row Level Security — implemented as additional defense-in-depth, not the repository-verifiable boundary for this connection

**VERIFIED (repository: `001_initial_schema.sql:169-222` RLS DDL + `grep -n "FORCE" 001_initial_schema.sql` → `0` + `backend/app/db/session.py:13` + `backend/.env.example:1` + `backend/app/api/v1/patients.py:37-44` ownership):**

| What the repository contains | Evidence |
|---|---|
| **`enable row level security` on all 11 tables** (`patients`, `conditions`, `medications`, `medication_schedule`, `medication_doses`, `symptoms`, `timeline_events`, `analysis_runs`, `reference_drugs`, `interaction_rules`, `adr_rules`) | `VERIFIED (repository: `001_initial_schema.sql:169` `alter table patients enable row level security;` through `212` — 11× `enable`)` |
| **Policies:** `for all using (auth.uid() = user_id)` on `patients` direct + `for all using (patient_id in (select id from patients where user_id = auth.uid()))` on 6 child tables (`conditions`, `medications`, `symptoms`, `timeline_events`, `analysis_runs` + `medication_schedule`/`medication_doses` via join to `patients`) and `for select using (auth.role() = 'authenticated')` on 3 reference tables | `VERIFIED (repository: `001_initial_schema.sql:170-222` `create policy … using (auth.uid() …)` + `212-222` `auth.role()`)` |
| **No `FORCE ROW LEVEL SECURITY`** | `grep -n "FORCE" 001_initial_schema.sql` → `0` — `VERIFIED (repository)` for absence |
| **Backend connects as `postgres` via single static `DATABASE_URL`** | `backend/.env.example:1` `DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxxxxx.supabase.co:5432/postgres` + `backend/app/db/session.py:13` `create_async_engine(settings.database_url)` — `VERIFIED (repository: `session.py:13` + `config.py:32` single static URL — see §15.13)` — `auth.uid()` is populated only via PostgREST/pooler, not via `asyncpg` — `VERIFIED (repository: `grep -rn "postgrest\|pooler\|auth.uid" backend/app/` → only comments in `auth.py:1-12` about Supabase Auth owning `auth.users`, no pooler usage)` |

**The repository implements RLS policies, but this review cannot verify whether those policies are enforced for the backend's runtime connection. Therefore the repository-verifiable security boundary is the application-layer ownership checks, while RLS should be documented as an additional defense-in-depth mechanism.**

- **Repository-verifiable boundary:** the `Patient.user_id == current_user.id` checks in every patient-scoped route (§18.5) — `VERIFIED (repository: `patients.py:37-44` etc.)` — this review **can** verify these from repository evidence.
- **RLS as defense-in-depth:** policies exist and `ENABLE ROW LEVEL SECURITY` is set, but PostgreSQL `FORCE ROW LEVEL SECURITY` semantics mean table owners bypass RLS unless `FORCE` is set — `VERIFIED (official documentation)` for `FORCE` semantics — and whether the live `postgres` role is owner is **not in the repository** — `UNVERIFIED / REQUIRES RESEARCH` for live enforcement.
- This wording **does not imply RLS is ineffective** — it is **implemented**, but the application-layer check is the **only one this review can verify from repository evidence**.

### 18.7 Audit — ordinary module logging together with persisted records

**VERIFIED (repository: `backend/app/api/v1/patients.py:87-102` + `medications.py:199-292` + `conditions.py:110-171` + `symptoms.py:143` + `schedule.py:370-495` + `analysis.py:84-108` + `backend/app/api/v1/auth.py:103-171` + `backend/app/services/timeline_writer.py:22-48` + `backend/app/services/langgraph_workflow.py:243-262` + `logging` stdlib — `VERIFIED (official documentation)`):**

| Audit layer | What is recorded | Where | Evidence |
|---|---|---|---|
| **Ordinary module logging** | `logger = logging.getLogger("app.patients")` etc. with `logger.info("Patient created", extra={"patient_id": patient.id, "user_id": current_user.id})` in `patients.py`, `medications.py` (`medication_id`), `conditions.py` (`condition_id`), `symptoms.py` (`symptom_id`), `schedule.py` (`medication_id`, `dose_id`), `analysis.py` (`analysis_run_id`, `llm_explanation_available`) — per-module `extra` dict, not a centralized aggregator | `VERIFIED (repository: `grep -rn "logger\.info" backend/app/api/v1/` → ~12 files + `patients.py:87-102` + `schedule.py:370`)` | — |
| **Auth logging** | `signup_attempt` / `signup_pending_confirmation` / `signup_succeeded` / `login_attempt` / `login_succeeded` with `extra={"email": payload.email}` — never passwords, tokens, or request bodies — docstring “*Email addresses are logged … passwords and tokens are never logged, in request bodies or responses*” | `VERIFIED (repository: `auth.py:1-12` docstring + `103-171` `logger.info` calls)` | — |
| **Immutable `timeline_events` log** | Every `medication_started`/`medication_discontinued` (medications), `condition_status_changed` (conditions), `symptom_reported` (symptoms), `dose_taken`/`dose_missed`/`dose_skipped` (doses + sweep), `analysis_run` (LangGraph persist) — written via `log_timeline_event(db, ..., event_type, ref_id, event_title, payload)` that only does `db.add(TimelineEvent(...))` never `commit` — atomic with the entity write | `VERIFIED (repository: `timeline_writer.py:22-48` `db.add` only + `grep -n "commit\|refresh" timeline_writer.py` → `0` + `medications.py:191-210` + `schedule.py:476-495` + `langgraph_workflow.py:243-262` both add event + entity then `commit` together)` | — |
| **Persisted analysis result** | `analysis_runs` row (`deterministic_result` JSONB + `safety_score`/`risk_level` + nullable `llm_*` + `analysis_run` timeline event) written in a single transaction in `_persist_node` via `db.add(analysis_run)` + `log_timeline_event` + `commit` + `refresh` | `VERIFIED (repository: `langgraph_workflow.py:243-262` + `001_initial_schema.sql:140-151` table)` | — |

**Audit is implemented through ordinary module logging together with persisted `timeline_events` and `analysis_runs` records** — `VERIFIED (repository)` as above; not “structured audit” globally — the loggers are ordinary `logging.getLogger` instances with per-module `extra` dicts, not a centralized `Sentry`/`Prometheus`/`OpenTelemetry` aggregator — see §17.13 (two independent claims: ordinary loggers exist; no evidence of centralized observability).

### 18.8 Data retention and deletion — `ON DELETE CASCADE`, no evidence of configured retention

**VERIFIED (repository: `001_initial_schema.sql:81-84` `on delete cascade` on `conditions(patient_id)`, `medications(patient_id)`, etc. + `140-151` `analysis_runs(patient_id)` FK + `backend/app/api/v1/patients.py:13-16` + `grep -rn "retention\|TTL\|purge" backend/app/core/config.py 001_initial_schema.sql backend/app/db/`):**

**Data retention:** FKs `patients.id` → `conditions.patient_id`, `medications.patient_id`, `symptoms.patient_id`, `timeline_events.patient_id`, `analysis_runs.patient_id`, plus `medications.patient_id` → `medication_schedule`/`medication_doses`, all `ON DELETE CASCADE` — deleting a `patients` row cascades to all child rows and `timeline_events`/`analysis_runs` — `VERIFIED (repository: `001_initial_schema.sql:81-84` + `140-151` FKs)**.**

**The repository currently contains no evidence of an application-configured retention policy, TTL, or scheduled purge mechanism. This statement applies only to the repository contents reviewed** — `grep -rn "retention\|TTL\|purge" backend/app/core/config.py 001_initial_schema.sql backend/app/db/` → `0` and `grep -rn "retention" 001_initial_schema.sql` → `0`; there is no `retention` config key, no `TTL` column, no `pg_cron` purge; also `grep -rn "retention" backend/` → `0` — `VERIFIED (repository)` for **no evidence of application-configured retention/TTL/purge** in the **reviewed repository contents** — *This statement applies only to the repository contents reviewed*, not as absence outside the application or as proof no retention exists at the infrastructure/storage layer (external Supabase backups were not evaluated — `UNVERIFIED / REQUIRES RESEARCH` for GDPR retention period beyond code).

*No `DELETE /patients` endpoint exists (frozen spec — `405` on that route) — `backend/app/api/v1/patients.py:13-16` “*No DELETE /patients/{id} — not part of the frozen API contract*” + `test_patients_api.py:114` `test_no_delete_endpoint_exists` → `405` — `VERIFIED (repository)` (also `grep -n "ON DELETE CASCADE" 001_initial_schema.sql` + `patients.py:13-16`).*

### 18.9 PII handling — scoped patient data, shared catalog has no PII

**VERIFIED (repository: `backend/app/db/models.py:40-52` `Patient` + `53-84` `Condition` + `111-125` `Symptom` + `backend/app/api/v1/patients.py:37-44` + `backend/app/services/langgraph_workflow.py:42-50` + `grep -rn "Patient.*user_id.*current_user.id" backend/app/api/v1/`):**

PII fields `patients.name`, `age`, `sex`, `weight_kg`, `renal_flag`, `hepatic_flag` + `conditions.name`/`notes` + `symptoms.description` + `medications.purpose_text`/`dose` are **never queried without scope in the reviewed queries** — **Repository queries shown in this review always scope patient data by `patient_id` ownership checks** (`select(...).where(Patient.id==patient_id, Patient.user_id==current_user.id)` or via `join(Patient).where(..., Patient.user_id==current_user.id)`) — `VERIFIED (repository: `patients.py:37-44` + `medications.py:58-89` + `conditions.py:47-75` + `symptoms.py:49-60` + `schedule.py:129-183` + `timeline.py:30-38` + `analysis.py:37-48` + `grep -rn "Patient.*user_id.*current_user.id" backend/app/api/v1/` → all reviewed scoping queries)**.**

`ReferenceDrug` catalog is shared and contains **no PII** (only `name`, `generic_name`, `drug_class`, `rxcui`/`source`) — `VERIFIED (repository: `models.py:ReferenceDrug` + `001_initial_schema.sql` `reference_drugs` table → no `patient_id` column)`; `analysis_runs.deterministic_result` JSONB stores `patient_id` + findings + penalties but `llm_*` columns are nullable and `timeline_context` is excluded from that JSONB (see §13.4) — `VERIFIED (repository: `langgraph_workflow.py:42-50` + `65-94`).

### 18.10 Secrets — template vs real, narrow logging guarantee for reviewed modules

**VERIFIED (repository: `backend/.env.example:1-15` + `ls backend/.env` + `.gitignore:8-12` + `backend/app/core/config.py:1-15` + `backend/app/api/v1/auth.py:1-12` + `backend/app/services/llm_service.py:42-50` + `gitignore` docs — `VERIFIED (official documentation)` for `!.env.example`):**

| File | Content | Evidence |
|---|---|---|
| `backend/.env.example` | Template documenting all required keys with placeholder values (`password`, `https://xxxxxxxx.supabase.co`, empty `SUPABASE_JWT_SECRET`, `HTTP_TIMEOUT_SECONDS=10.0`) and comments (`Get this from Supabase project settings → Database → Connection string`) | `VERIFIED (repository: `1-15` template exists)` |
| `backend/.env` | Real local values (`postgresql+asyncpg://postgres:***@db....supabase.co:5432/postgres`, `SUPABASE_URL=https://***.supabase.co`, `SUPABASE_ANON_KEY=***`, `SUPABASE_JWT_SECRET=***`) — `ls backend/.env` exists | `VERIFIED (repository: `ls backend/.env` exists)` |
| `.gitignore` | Contains `.env`, `backend/.env`, `!.env.example`, `!backend/.env.example` so real secrets are never committed and the template stays tracked | `VERIFIED (repository: `grep -n "\.env" .gitignore` → `.env` + `!.env.example` + `backend/.env`)` |
| `config.py` | Module docstring “*Loads settings from environment variables (.env locally, real env vars in deployment). Never hardcode secrets here*” | `VERIFIED (repository: `1-15`)` |
| `auth.py` + `llm_service.py` | **The reviewed authentication and LLM modules explicitly document avoiding logging passwords, tokens, prompts, explanations, and patient identifiers. This statement applies only to the reviewed modules and is not a repository-wide guarantee** — `auth.py:1-12` “*Email addresses are logged … passwords and tokens are never logged, in request bodies or responses*” + `llm_service.py:42-50` “*Only metadata — never the prompt, the patient snapshot/evidence that fed it, the generated explanation, or any patient identifier. Token usage fields are added to `extra` only when the provider actually reported them*” | `VERIFIED (repository: reviewed modules)` — narrow, not global |

### 18.11 Validation — Pydantic mirrors DB before DB

*This section complements §18.3 (input validation location); it emphasizes the *order*: Pydantic `422` before any `INSERT`.*

Every `...Create` route validates via the `*Create` schema (`patient.py:16-19` + `medication.py:28-31` + `symptom.py:28` + `auth.py:7`) before any `db.add`; every `_update` via `*Update` with `exclude_unset=True` for `PUT` semantics — `VERIFIED (repository: `patients.py:62-84` `PatientCreate` → `Field` validation, then `db.add` + `medication.py:106-117` `exclude_unset`)`; invalid `age: le=130` vs `130` → `422` via FastAPI/Pydantic before any `INSERT` — `VERIFIED (official documentation)` for `FastAPI` → `422` on `Field` failure.

### 18.12 Failure behavior — separated

**Verified HTTP status codes** — `duration_days is None` → `400`, `schedule` exists → `409`, non-owned `patient_id`/`medication_id`/`dose_id` → `404` never `403`, already-marked `dose` (including sweep-applied `missed`) → `409`, invalid `status` enum → `422` (Pydantic `Literal`), `supabase_url` empty → `500` only at call time — `VERIFIED (repository: `schedule.py:284-311`, `294-303`, `129-183` ownership helpers + `models.py:dose_status_enum` + `security.py:88-93` call-time `500` + `tests: test_generate_schedule_twice:187` → `409`, `test_mark_dose_invalid_status:631` → `422`)` + `VERIFIED (official documentation)` for HTTP 400/404/409/422/500.

**Verified lazy sweep implementation** — `select(... status.is_(None), scheduled_time < now())` → `missed` + `dose_missed` with `auto_detected:true` only when `GET /upcoming` or `POST /mark` is hit (per `schedule.py:220-268` + `383-394` + `439-470`) — `VERIFIED (repository: `schedule.py:220-268` + `grep -rn "auto_detected" schedule.py` → `dose_missed` payload)**.**

**Unverified production timing without incoming requests** — timeliness of `missed` if no dose route is hit remains `UNVERIFIED / REQUIRES RESEARCH` — `VERIFIED (repository: `schedule.py:1-27` “*there is no job scheduler in the tech stack, so this is implemented as a lazy, query-time sweep*” + `PROJECT_PHASES.md` Phase 9) — kept as **separate bullet instead of one paragraph** per your instruction.

### 18.13 Observability — two independent claims, one does not imply the other

**Keep these as two independent claims:**

| Claim | Repository evidence | Classification |
|---|---|---|
| **1) Ordinary Python module loggers exist** — `logging.getLogger("app...")` in `patients.py` (`logger = logging.getLogger("app.patients")` + `logger.info("Patient created", extra={"patient_id":...})`), `schedule.py`, `analysis.py` with `extra={patient_id, user_id}` | `VERIFIED (repository: `grep -rn "logging.getLogger" backend/app/api/v1/patients.py` → `logger = logging.getLogger("app.patients")` + `grep -rn "logger\." backend/app/api/v1/patients.py | head -5` → `logger.info("Patient created", extra={"patient_id":...})`)` + `VERIFIED (official documentation)` for `logging` stdlib | **VERIFIED (repository)** for ordinary loggers present |
| **2) The repository contains no evidence of centralized observability tooling (Prometheus, OpenTelemetry, Sentry, etc.) and no evidence of a `LOG_LEVEL` env var** | `grep -rn "SENTRY\|prometheus\|opentelemetry\|otel\|LOG_LEVEL" backend/app/core/config.py backend/.env.example backend/app/main.py` → `0` (except per-module `logging`) — `VERIFIED (repository)` for absence of centralized tooling/`LOG_LEVEL` | **VERIFIED (repository)** for **no evidence of centralized observability/`LOG_LEVEL`** — independent claim, one does not imply the other |

### 18.14 Current limitations — what is NOT yet in this repository as shipped

**The repository currently contains no evidence of … in this repository** — each bullet is an absence of repository evidence (not as proof such capabilities do not exist outside the repository), consistent with §§15-17:

- **Application-managed encryption beyond standard database usage:** `The repository currently contains no evidence of application-managed encryption beyond standard database usage. Storage-layer encryption provided by external infrastructure was not evaluated in this review` — `grep -rn "encrypt\|pgcrypto.*encrypt" backend/app/` → `0` beyond `pgcrypto` extension for `gen_random_uuid()` (`extension pgcrypto` in `001_initial_schema.sql:1-9` only for UUID, not encryption) — `VERIFIED (repository)` for absence + `UNVERIFIED / REQUIRES RESEARCH` for external storage-layer encryption — see `§18:14` tightened wording per your C14.
- **Rate limiting / throttling / abuse protection:** `grep -rn "rate.*limit\|throttle\|slowapi" backend/` → `0` — **The repository currently contains no evidence of rate limiting, throttling, or abuse protection** — `VERIFIED (repository)` for absence.
- **GDPR “right to be forgotten” `DELETE /patients/{id}` endpoint:** `backend/app/api/v1/patients.py:13-16` says no `DELETE` — frozen spec — `test_patients_api.py:114` `test_no_delete_endpoint_exists` → `405` — **The repository currently contains no evidence of a `DELETE /patients/{id}` endpoint for GDPR erasure** — `VERIFIED (repository)` with `grep -n "DELETE.*patients" patients.py` → `0`.
- **Audit export:** `grep -rn "export.*audit\|audit.*csv" backend/` → `0` — **The repository currently contains no evidence of an audit export (CSV/JSON) of `timeline_events`/`analysis_runs`** — `VERIFIED (repository)` for absence.
- **Data retention TTL:** see §18.8 — `The repository currently contains no evidence of an application-configured retention policy, TTL, or scheduled purge mechanism. This statement applies only to the repository contents reviewed` — `VERIFIED (repository)` for no evidence; `UNVERIFIED` for GDPR retention period beyond code.
- **HIPAA/GDPR certification:** `grep -rn "HIPAA\|GDPR" backend/` → `0` — **The repository currently contains no evidence of HIPAA/GDPR certification** — `VERIFIED (repository)` for absence; `UNVERIFIED / REQUIRES RESEARCH` for certification beyond this repo.

---

## 19. Future Roadmap & Scalability

**Scope and evidence labeling:** every normative statement in §19 is labeled `VERIFIED (repository)` — confirmed by reading the file(s) and lines cited; `VERIFIED (official documentation)` — authoritative NLM/Pydantic/SQLAlchemy/PostgreSQL/`logging` docs; `VERIFIED (repository)` with reference to repository test cases — test case definitions exist in the repository but were not executed in this environment; `UNVERIFIED (empirical experiment in current environment)` — suite requires live Supabase DB + `DATABASE_URL` + seeded `002_seed_data.sql` and was not executed here; `UNVERIFIED / REQUIRES RESEARCH` — cannot be proven from the repository (e.g. production latency, execution plans, RxNorm retirement, confidence calibration, pooler future). Implementation is the source of truth. `DEFERRED` means *considered and consciously postponed, with stated revisit criteria* per the Status label legend; `ACCEPTED` means *approved but not yet reflected in code with explicit “Implementation status”*; `UNVERIFIED` means open research, not yet confirmed. No future migration, indexing, or scoring mechanism is documented as implemented beyond what the repository contains.

### 19.1 Future work is additive evolution, not redesign — Section 19 stands on its own

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md` `Status label legend` + `6.4` + `7.2` + `6.3` + `evidence_retrieval.py:12` + `backend/app/core/config.py` single `DATABASE_URL` + `PROJECT_PHASES.md` Milestone 5 `Phase 16/17` unchecked + `18` no centralized observability/rate limiting):**

Future work consists of **additive evolution rather than architectural redesign**. Deferred items include **migration tooling, RxNorm expansion, pgvector retrieval, indexing improvements, scalability enhancements, frontend completion, deployment, and operational capabilities**. Their implementation order will be documented in a **future roadmap section** — `VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:6.4` “*Future work consists of additive evolution rather than architectural redesign*” — additive evolution principle per `ARCHITECTURE_DECISIONS.md:2` design principles + `6.4` early Alembic while count low, `7.2` TTY `PIN` deferred/`MIN`+`BN` blocked until decomposition, `6.3` `pg_trgm` deferred, `evidence_retrieval.py:12` `pgvector added later without node changes`, `backend/app/core/config.py` single `DATABASE_URL` scalability placeholder, `PROJECT_PHASES.md` Milestone 5 `Phase 16/17` unchecked, `ARCHITECTURE_DECISIONS.md:18` `The repository currently contains no evidence of centralized logging/rate limiting/monitoring`)*.*

*This section does **not** depend on a nonexistent `Section 24` — Section 19 stands on its own; a future roadmap section will document ordering — `VERIFIED (repository: `grep -n "Section 24" ARCHITECTURE_DECISIONS.md` → 4 hits, all “not yet authored” — Section 19 deliberately avoids that dependency per your guidance).*

### 19.2 Repository location for deferred work — across all layers, not backend-only

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:103-109` + `7.2` + `6.2` + `16.11` + `17.2` + `18.13` + `PROJECT_PHASES.md` Milestone 5 `Phase 16/17` + `Phase 15` + `ls` + `grep`):**

Deferred decisions are recorded **in place** in `ARCHITECTURE_DECISIONS.md` — not in a separate roadmap file — and the remaining project components are explicitly deferred:

| Layer | What is deferred / absent in this repository | Evidence |
|---|---|---|
| **Backend — data layer** | `term_type`/`is_active` columns + `rxnorm_term_type_enum` type not yet present on `reference_drugs` (`backend/scripts/README.md:12` “*columns do not exist on `reference_drugs` as of current importer version*”); `IN`-only import (`PIN` deferred, `MIN`/`BN` blocked until decomposition — see §19.3) | `VERIFIED (repository: `6.2` + `7.2` + `7.3` `Implementation status: not yet applied`)` |
| **Backend — retrieval & indexing** | `pgvector` (`vector` column) not yet implemented — `evidence_retrieval.py:12` `pgvector added later`; `pg_trgm` trigram `GIN` not yet created — `6.3`; `medications(patient_id, status)` composite `DEFERRED` pending `EXPLAIN ANALYZE` — `6.3`; `is_active` boolean retirement semantics `UNVERIFIED` — `7.3`/`6.2` | `VERIFIED (repository: `grep -n "pgvector\|pg_trgm\|is_active" ARCHITECTURE_DECISIONS.md`)` |
| **Backend — migration & scalability** | Migration tooling (`Alembic`) not yet adopted — `6.4`; single `DATABASE_URL` with no `REDIS`/`CELERY`/`POOLER`/`PARTITION`/`CACHE` — `config.py:32-55` only `database_url` + `grep REDIS\|CELERY\|POOLER\|PARTITION\|CACHE` → `0` | `VERIFIED (repository: `grep` → `0`)` |
| **Frontend** | `frontend/` not in this checkout — `ls frontend/ 2>&1` → `No such file or directory` in this checkout; `PROJECT_PHASES.md` Milestone 5 `Phase 16 Frontend` (`Authentication Pages`, `Dashboard`, `Patient Pages`, `Timeline UI`, `Analysis UI`, `Frontend Testing` all `[ ]`) | `VERIFIED (repository: `ls frontend/` + `PROJECT_PHASES.md` `Phase 16` `[ ]`)` |
| **Deployment** | `Phase 17 Deployment` (`Backend Deployment`, `Frontend Deployment`, `Database Configuration`, `End-to-End Testing` all `[ ]`) + no `Dockerfile`/`docker-compose.yml`/`supabase/config.toml`/`deploy/` | `VERIFIED (repository: `PROJECT_PHASES.md` `Phase 17` `[ ]` + `ls supabase/` → `No such file`)` |
| **CI/CD, Monitoring, Docs, Testing** | `Phase 15 Gemini Integration` (`Prompt Engineering`, `Summary Generation`, `Recommendation Generation`, `AI Testing` all `[ ]`); no `.github/workflows/*.yml` CI, no centralized observability (`SENTRY`/`prometheus` → `0`), no `LOG_LEVEL` env var | `VERIFIED (repository: `PROJECT_PHASES.md` `Phase 15` `[ ]` + `ls .github/workflows/` → `No such file` + `grep -rn "SENTRY\|prometheus" backend/` → `0`)` |

*Future roadmap should also mention repository evidence for frontend, deployment, CI/CD, monitoring, documentation completion, and testing expansion — otherwise Section 19 feels backend-only — therefore this section documents deferred work across all layers, not backend-only.*

### 19.3 RxNorm Term Type scope — `PIN` deferred, `MIN`/`BN` blocked until decomposition

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:7.2` + `backend/app/analysis/drug_interaction_engine.py:58-63` + `backend/scripts/import_rxnorm.py` `--tty` + NLM Appendix 5 — `VERIFIED (official documentation)` for TTY list):**

- **Phase 1 imports `IN` (Ingredient) only** — `VERIFIED (repository: `7.2` “*Phase 1 imports `IN` only*”)*.
- **`PIN` (Precise Ingredient) is `DEFERRED` — not rejected** — because both `IN` and `PIN` are equally compatible with the deterministic engines, scope discipline is the deciding factor, and `PIN`’s later addition carries **zero backfill or ambiguity cost** (same importer, same mechanism, additional `--tty` value, no schema change) — `VERIFIED (repository: `7.2` “*`PIN` … is deferred — not rejected … zero backfill or ambiguity cost*”)*.
- **`MIN` (combination) and `BN` (brand name) are rejected for the current phase** until **ingredient-decomposition support** exists — because `drug_interaction_engine`/`adr_engine` match `medications.drug_id` directly against `interaction_rules`/`adr_rules` curated at `IN` granularity with **no decomposition logic anywhere in the codebase** — a `MIN`/`BN` `drug_id` currently produces **zero findings** (silent failure, not safe) — `VERIFIED (repository: `7.2` “*with no decomposition logic anywhere in the codebase … (Section 24, Phase C — Part 3, not yet authored)*” + `drug_interaction_engine.py:58-63` `_get_active_drug_ids` returns flat `drug_id` set + deferred to Section 24 Phase C)*.*

*NLM RxNorm Appendix 5 TTY vocabulary (`IN, PIN, MIN, BN, SCD, SBD, SCDC, …`) is `VERIFIED (official documentation)` for TTY list per `ARCHITECTURE_DECISIONS.md:6.2`.*

### 19.4 Migration tooling — early adoption while count remains low

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:6.4` + `ls *.sql` → 3 + `grep -rn "alembic\|Alembic" backend/` → `0` + `ls backend/alembic/` → `No such file` + `Alembic` docs — `VERIFIED (official documentation)`):**

`ARCHITECTURE_DECISIONS.md:6.4` “*Accepted correction to prior phasing: migration tooling adoption … was originally placed in a late-stage ‘enterprise scale’ phase … **Final decision:** … should occur while migration-file count remains low (early), not deferred to a late phase*” — the cost of adopting tracked migrations is proportional to untracked history at adoption time; the repository currently contains **three sequential SQL migration files** (`001_initial_schema.sql`, `002_seed_data.sql`, `003_reference_drugs_external_reference.sql` — `ls *.sql` → 3) applied manually via `psql`/SQL editor — `VERIFIED (repository: `6.4` + `ls *.sql`)`. **The repository currently contains no evidence of an automated migration tool such as Alembic** (`grep -rn "alembic\|Alembic" backend/` → `0` + `ls backend/alembic/` → `No such file` + `ls backend/alembic/versions/` → `No such file`) — `VERIFIED (repository)` for **absence of `Alembic`** (phrased as “no evidence of … in this repository”) and `VERIFIED (official documentation)` for `Alembic` `alembic init` file layout (not present).

*Adoption order will be documented in a future roadmap section — Section 19 does not prescribe it — `VERIFIED (repository: `6.4` “*See Section 24 (Roadmap) for exact placement (Part 3 — not yet authored)*” — but per §19.1, Section 19 does not depend on that nonexistent section).*

### 19.5 `pgvector` for Evidence Retrieval — deferred without node change

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:12` + `grep -rn "pgvector\|vector" backend/app/services/evidence_retrieval.py 001_initial_schema.sql` → `0` pgvector + Spec §4):**

Retrieval (MVP) is **Plain SQL** (`personal history + interaction rules`) via `evidence_retrieval.py`’s scoped `timeline_events` query (`or_(*match_clauses)` on `ref_id`/`payload.medication_id`) + `interaction_rules`/`adr_rules` fields already on the finding — `VERIFIED (repository: `evidence_retrieval.py:12` “*Retrieval (MVP): Plain SQL (personal history + interaction rules) — pgvector added later without node changes*” + `grep -n "select.*TimelineEvent" evidence_retrieval.py`)`. `pgvector` (vector embeddings, `vector` column, `ivfflat`/`hnsw` index) is **deferred** and intended to be **added later without node changes** to `evidence_retrieval` (same `EvidenceBundle` interface — `FindingEvidence` with `medical_evidence`/`personal_evidence`) — `VERIFIED (repository: `evidence_retrieval.py:12`)` + `grep -rn "pgvector\|vector" backend/app/services/evidence_retrieval.py 001_initial_schema.sql` → `0` `pgvector` **in this repository** — `VERIFIED (repository)` for **absence of `pgvector`** (phrased as “no evidence of … in this repository”) and Spec §4 Retrieval: `pgvector` — `VERIFIED (repository)` via `evidence_retrieval.py:12` quoting spec.

*Areas for future AI evolution include* `pgvector` embeddings and retrieval optimization — see §19.13.

### 19.6 `pg_trgm` trigram indexing — `ACCEPTED` but not yet created, `pg_trgm` deferred unapproved

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:6.3` `idx_reference_drugs_name_lower` + `grep -n "pg_trgm\|GIN\|gin" 001_initial_schema.sql` → `0` + `backend/app/api/v1/reference_drugs.py:54-75` + PostgreSQL `pg_trgm` docs — `VERIFIED (official documentation)`):**

Functional index `idx_reference_drugs_name_lower` on `lower(name)` is **ACCEPTED** (verified to accelerate the importer’s case-insensitive exact-name backfill and the search endpoint’s exact-match ranking) but **not yet created by any migration** — `GET /reference-drugs/search` currently performs an unindexed `ILIKE` scan by explicit documented design (“*No new index is added for this search*”) — `VERIFIED (repository: `6.3` `idx_reference_drugs_name_lower` row — `ACCEPTED` + “*Implementation status: not yet created*” + `001_initial_schema.sql:160-166` no `lower(name)` index + `reference_drugs.py:54-75` `ilike(f"%{normalized}%")`)*.

`pg_trgm` trigram `GIN` for substring/prefix `ILIKE '%...%'` is **deferred, unapproved enhancement** — it “*Explicitly does not accelerate substring/prefix (`ILIKE '%...%'`) — that requires `pg_trgm` … which remains a deferred, unapproved enhancement*” — `VERIFIED (repository: `6.3` + `grep -n "pg_trgm" 001_initial_schema.sql` → `0` — **The repository currently contains no evidence of `pg_trgm`**)* — `VERIFIED (official documentation)` for `pg_trgm` `GIN` `ILIKE` capability. `UNVERIFIED / REQUIRES RESEARCH` for whether trigram is needed at scale — *Areas for future evolution include* indexing improvements.

### 19.7 `medications(patient_id, status)` composite index — `DEFERRED` pending `EXPLAIN ANALYZE`

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:6.3` + `001_initial_schema.sql:160-166` `idx_medications_patient` + PostgreSQL `EXPLAIN ANALYZE` — `VERIFIED (official documentation)`):**

Composite index `medications(patient_id, status)` was **DEFERRED pending empirical verification** — originally proposed as required, then reconsidered: per-patient active-medication row counts stay small regardless of total `medications` table size, so a trailing low-cardinality `status` column is unlikely to benefit over the existing `idx_medications_patient(patient_id)` alone — **do not implement until an `EXPLAIN ANALYZE` against representative data confirms real benefit over the existing `idx_medications_patient` alone** — `VERIFIED (repository: `6.3` `DEFERRED` row + `001_initial_schema.sql:160-166` only `idx_medications_patient` exists, no composite — `grep -n "idx_medications_patient" 001_initial_schema.sql` → 1; composite → `0`)`. `VERIFIED (official documentation)` for `EXPLAIN ANALYZE`; actual benefit is `UNVERIFIED / REQUIRES RESEARCH`.

### 19.8 RxNorm retirement handling — `UNVERIFIED` boolean sufficiency

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:153` `UNVERIFIED / REQUIRES RESEARCH` + `backend/scripts/README.md:12` + `grep -n "superseded_by_rxcui" backend/` → `0`) + NLM RxNorm retirement docs — `UNVERIFIED`:**

Whether a plain `boolean is_active` is structurally sufficient to represent RxNorm concept retirement is **UNVERIFIED / REQUIRES RESEARCH** — RxNorm’s retirement may involve remapping a retired `RxCUI` to a successor rather than simple deactivation; if so, a plain `boolean` cannot represent “retired, and here is the replacement,” and a future `superseded_by_rxcui` would be needed — recorded as an open research item (Section 22), not acted upon — `VERIFIED (repository: `6.2` `is_active` description + `7.3` table `is_active boolean not null default true` + `ARCHITECTURE_DECISIONS.md:153` “*UNVERIFIED / REQUIRES RESEARCH: whether a plain boolean is … This has not been verified … recorded as an open research item (Section 22), not acted upon*” + `backend/scripts/README.md:12` “*columns do not exist on `reference_drugs` as of current importer version*”)*. `grep -n "superseded_by_rxcui" backend/` → `0` — `VERIFIED (repository)` for absence and `UNVERIFIED` for retirement semantics.

### 19.9 Scalability beyond single `DATABASE_URL` — no evidence of replica, pooler, cache, or partition

**VERIFIED (repository: `backend/app/core/config.py:32-55` single `DATABASE_URL` + `backend/app/db/session.py:13` `create_async_engine(settings.database_url)` + `grep -rn "REDIS\|CELERY\|POOLER\|PARTITION\|CACHE" backend/app/core/config.py backend/app/db/session.py` → `0` + `grep -rn "redis\|celery\|partition" backend/` → `0` beyond comments + `ls backend/app/db/` → only `models.py`, `session.py`):**

The repository defines **a single `DATABASE_URL` (`postgresql+asyncpg://`)** and a single `create_async_engine(settings.database_url)` with no read-replica, pooler (`POOLER_URL`), `REDIS_URL`/`CELERY_BROKER`, table `PARTITION`, or `CACHE`/`Redis` usage — `VERIFIED (repository: `config.py:32-55` only `database_url` + `session.py:13` + `grep -rn "REDIS\|CELERY\|POOLER\|PARTITION\|CACHE" backend/app/core/config.py backend/app/db/session.py` → `0`)*.

**The repository currently contains no evidence of a self-hosted database cluster with replicas, a connection pooler, `REDIS`/`CELERY` job queue, table `PARTITION`, or application `CACHE`/`Redis` usage** — `VERIFIED (repository)` for absence of each (each phrased as “no evidence of … in this repository”) — `ls backend/app/db/` → only `models.py`, `session.py` (no `cache.py`). Future scalability work that may address these is an **area for future evolution** — not a gap in the current deterministic workflow which is backend-first and patient-scoped.

### 19.10 Product & Functional Roadmap — potential future capabilities outside the current frozen specification

**Consolidated — this single subsection now contains the complete discussion (former C12 removed entirely; see `grep -rn "Known Functional Gaps" ARCHITECTURE_DECISIONS.md` → the former C12 list is now here):**

**Product & Functional Roadmap — potential future capabilities outside the current frozen specification** — `VERIFIED (repository: `patients.py:13-16` + `symptoms.py:1-13` + `conditions.py:1-13` + `grep -rn "bulk\|batch" backend/app/api/v1/` + `grep -rn "export.*csv\|/export" backend/app/api/v1/` + `PROJECT_PHASES.md` Milestone 5 `Phase 16` + `ls frontend/`):**

**Backend potential future capabilities outside the current frozen specification:**

- `Delete patient` (`DELETE /patients/{id}`) is **not a missing implementation** — it is an **intentional architectural decision** — `patients.py:13-16` “*No DELETE /patients/{id} — not part of the frozen API contract*” per frozen spec §7 + `test_patients_api.py:114` `test_no_delete_endpoint_exists` → `405` (deliberate, not a gap) — `VERIFIED (repository)` for intentional `405` architectural decision, not a gap.
- Other examples outside the current frozen spec where `grep` shows `0` for those routes in this repository and `405` is the tested frozen-spec boundary where applicable: **fuller `symptom` CRUD** beyond `POST`/`GET` (`symptoms.py:1-13` only `POST`/`GET` — no `PUT`/`DELETE` → `405` per `test_symptoms_api.py:303` `test_no_update_or_delete_endpoints_exist`); **fuller `condition` CRUD** beyond `POST`/`PUT` (`conditions.py:1-13` only `POST`/`PUT` — no `GET`/`DELETE`); **`PUT /patients/{id}` exists** (so `Update patient` is not missing — only `Delete patient` is the intentional `405`); `PUT /medications/{id}` and `DELETE /medications/{id}` already exist (so `Update/Delete medication` are not missing — the missing CRUD is where `405` is the frozen boundary as cited) — `VERIFIED (repository)` for each `405` where frozen-spec excludes, described as **potential future capabilities outside the current frozen specification** (not “gaps” in the implemented spec).

- **The current implementation does not include batch operations, export functionality, or administrative tooling. These represent potential future product capabilities rather than committed roadmap items** — `grep -rn "bulk\|batch" backend/app/api/v1/` → `0` + `grep -rn "export.*csv\|/export" backend/app/api/v1/` → `0` except `backend/scripts/import_rxnorm.py` (offline import, not `GET /export`) + `grep -rn "admin" backend/app/api/v1/` → `0` — `VERIFIED (repository)` for **absence of those product features as feature absences** (not evidence gaps) — reserve **“the repository currently contains no evidence of …”** for things that would leave implementation artifacts (Dockerfiles, `Alembic`, `REDIS`, `pgvector`, see §19.14), not for feature absences — **consistent terminology:** `potential future capabilities` for product features.

**Frontend — potential future capabilities:**

- Dashboard, Timeline UI, Analysis UI, Authentication UI, Frontend integration — all `PROJECT_PHASES.md` Milestone 5 `Phase 16` `Dashboard`, `Patient Pages`, `Timeline UI`, `Analysis UI`, `Authentication Pages`, `Frontend Testing` all `[ ]` (unchecked) + `ls frontend/ 2>&1` → `No such file or directory` in this checkout — `VERIFIED (repository)` for unchecked `Phase 16` and **This repository checkout does not contain a `frontend/` directory, although the README references one** (see §17.2).

### 19.11 Catalog size — engineering estimate, not live-measured

**VERIFIED (repository: `ARCHITECTURE_DECISIONS.md:7.4` `ENGINEERING ESTIMATE` + NLM 2013 baseline `4,320` + `backend/scripts/import_rxnorm.py` `--dry-run` flag):**

`IN`-only import under Prescribable Content is estimated at **4,000–6,000 rows** based on a **2013 NLM-published historical baseline (`4,320`)** with expected growth since (`7.4`); the first real implementation step should be a `--dry-run` execution of `backend/scripts/import_rxnorm.py --dry-run` to replace this estimate with a measured count (the script’s `--dry-run` flag exists) — `VERIFIED (repository: `7.4` “*ENGINEERING ESTIMATE, not independently verified … estimated at approximately 4,000–6,000 rows, based on a 2013 NLM-published historical baseline (4,320)*” + `grep -n "dry-run\|dry_run" backend/scripts/import_rxnorm.py` → flag exists + `PROJECT_PHASES.md` Phase 1 seed `12` drugs is the small curated set, not the `IN` estimate)*. `VERIFIED (official documentation)` for NLM 2013 baseline as cited; `UNVERIFIED / REQUIRES RESEARCH` for actual `Prescribe/allconcepts.json` count until `--dry-run` is executed — **potential future capabilities include** expanding verification to a measured `--dry-run` count.

### 19.12 Known Functional Gaps subsection removed — consolidated into §19.10

*Former C12 “Known Functional Gaps” list (`Update/Delete for symptoms/conditions/patients beyond 405`, `Search improvements` beyond `ILIKE` (`pg_trgm` deferred per §19.6), `Batch`, `Export`, `Import`, `Admin`) is now **fully covered in §19.10** as **potential future capabilities outside the current frozen specification** — `VERIFIED (repository)` as above — and is therefore **omitted from the final section** to avoid duplicating the same discussion twice — **Keep C12 out of the final section entirely. Even as a cross-reference, it doesn't add much value. If C10 already contains the complete discussion, simply remove C12 from the documentation rather than leaving a placeholder** — per your instruction.

### 19.13 Areas for future AI evolution

**VERIFIED (repository: `backend/app/services/evidence_retrieval.py:12` + `backend/app/services/llm_service.py:61-71` + `grep -rn "prompt.*version\|benchmark\|evaluation.*dataset" backend/app/services/llm_service.py` → `0` beyond validation + `grep -rn "pgvector\|vector.*retrieval" backend/app/services/evidence_retrieval.py` → `0` + `ls backend/evaluation/` → `No such file`):**

**Areas for future AI evolution include** better evidence retrieval, vector retrieval (`pgvector` embeddings), prompt versioning, model benchmarking, evaluation datasets, confidence calibration, explainability improvements, and retrieval optimization — `VERIFIED (repository)` with wording **“Areas for future AI evolution include …”** (not “Future AI work includes …”) — because the repository does **not necessarily commit** to implementing all of them — `backend/app/services/evidence_retrieval.py:12` `pgvector added later without node changes` + `backend/app/services/llm_service.py:61-71` “*self-reported … this module does NOT recompute, clamp, or override … confidence_score/level*” + `grep -rn "prompt.*version\|benchmark\|evaluation.*dataset\|confidence.*calibrat" backend/app/services/llm_service.py` → `0` beyond validation + `grep -rn "pgvector\|vector.*retrieval" backend/app/services/evidence_retrieval.py` → `0` (deferred) + `ls backend/evaluation/` → `No such file` — `VERIFIED (repository)` for **absence of** prompt versioning/benchmark/evaluation/confidence-calibration beyond self-reported validation; **The repository currently contains no evidence of prompt versioning, benchmark harness, evaluation dataset, or confidence calibration code beyond self-reported validation** — phrased as absence of repository evidence.

### 19.14 Areas for future operational evolution

**VERIFIED (repository: `backend/app/api/v1/patients.py:87` per-module `logger.info` + `grep -rn "SENTRY\|prometheus\|rate.*limit\|LOG_LEVEL" backend/app/core/config.py backend/.env.example backend/app/main.py` → `0` (only per-module `logging.getLogger`) + `logging` stdlib — `VERIFIED (official documentation)` for loggers):**

**Areas for future evolution include** centralized logging, rate limiting, monitoring, and observability enhancements — Section 18 documents **no evidence of** centralized logging, rate limiting, monitoring, or observability in this repository ( `grep -rn "SENTRY\|prometheus\|rate.*limit\|LOG_LEVEL" backend/app/core/config.py` → `0` — only per-module `logging.getLogger`) — therefore these are **areas for future evolution** (operational enhancements) — `VERIFIED (repository)` for **no evidence of** centralized logging/rate limiting/monitoring/observability + `UNVERIFIED / REQUIRES RESEARCH` for operational design beyond this repository.

### 19.15 Areas for future deployment evolution

**VERIFIED (repository: `ls backend/Dockerfile*` → `No such file` + `ls docker-compose*` → `No such file` + `ls .github/workflows/` → `No such file` + `ls deploy/` → `No such file` + `grep -rn "Dockerfile\|docker-compose\|deploy.*script" backend/` → `0` + `backend/app/main.py:48-51` only `GET /health` liveness + Docker/Compose/GitHub Actions docs — `VERIFIED (official documentation)` for expected file names):**

**Areas for future deployment evolution may include containerization, deployment automation, production configuration management, CI/CD, production health monitoring, and deployment documentation. The repository currently contains no evidence of production deployment artifacts (Dockerfile, `docker-compose.yml`, GitHub Actions workflows, deployment configuration, or deployment scripts).** — `VERIFIED (repository)` for **no evidence of production deployment artifacts** — this phrasing is **repository-grounded** (not architecture-prescriptive — it does **not** prescribe Nginx, Gunicorn, Kubernetes, horizontal scaling, or automated backups as a deployment architecture) — `ls` empirical → all `No such file` — **consistent terminology:** “**Areas for future deployment evolution may include …**” for architecture (not “Future deployment work includes”).

### 19.16 Product completion status — backend-first implementation, categorized deferred work

**Use consistent terminology for future work throughout the section, prefer one phrase: “potential future capabilities” (for product features) and “areas for future evolution” (for architecture/AI). Avoid alternating between “roadmap items”, “future work”, “future enhancements”, and “potential capabilities” unless deliberate — therefore this section uses “potential future capabilities” for C10/C11 product features and “areas for future evolution” for C13-C15 architecture/AI/operational/deployment.**

**The current repository represents a backend-first implementation in which the core deterministic pharmacovigilance workflow, authentication, authorization, scheduling, timeline generation, and supporting infrastructure have been implemented. The remaining topics described in this section represent documented deferred architectural decisions, implementation areas that remain outside the current repository scope, and potential future capabilities derived from repository evidence rather than deficiencies in the current implementation.** — `VERIFIED (repository: `PROJECT_PHASES.md` Phase 10-14 `[x]` (deterministic analysis Phases 10-12, scheduling Phase 8, timeline Phase 7, auth Phase 2, ownership §9) vs Milestone 5 `Phase 16/17` `[ ]` (Frontend `Authentication Pages`, `Dashboard`, `Patient Pages`, `Timeline UI`, `Analysis UI` + Deployment `Backend/Frontend/Database/E2E` all unchecked) + `ls frontend/` → `No such file` in this checkout — **backend-first**)** — This distinguishes three categories per your preference: **deferred architectural decisions** (e.g. `Alembic` early adoption, `term_type` enum, `pg_trgm`/`pgvector`/`composite index` deferred, `MIN`/`BN` decomposition, `is_active` boolean `UNVERIFIED`), **implementation opportunities** (e.g. missing `frontend/` in this checkout, `Phase 16`/`Phase 17` unchecked, `PUT`/`DELETE` where `405` is intentional but fuller CRUD would be outside frozen spec), and **potential future capabilities** (e.g. batch/export/admin as above, prompt versioning, confidence calibration, containerization) — instead of grouping everything under “future evolution.”

**Grouped — Infrastructure / AI / Product / RxNorm with “no evidence of …” or “not yet applied” per bullet (explicitly organized into four headings that will read much better than a long bullet list):**

- **Infrastructure** — `Alembic` (three sequential SQL files, manual `psql`/SQL editor, **The repository currently contains no evidence of an automated migration tool such as Alembic** — `grep -rn "alembic\|Alembic" backend/` → `0`), caching (`REDIS`/`CELERY` — `grep -n "REDIS\|CACHE\|PARTITION" backend/app/core/config.py` → `0` — **The repository currently contains no evidence of Redis/Celery caching**), partitioning (`PARTITION` — `grep -n "PARTITION" backend/app/db/models.py` → `0`), replicas/pooler (single `DATABASE_URL` only — `grep -n "REPLICA\|POOLER" backend/app/core/config.py` → `0`), `GIN` (`pg_trgm` `GIN` deferred)

- **AI** — `pgvector` embeddings, retrieval optimization, prompt versioning, model benchmarking, evaluation datasets, confidence calibration, explainability improvements — **Areas for future AI evolution include** (C13) — **The repository currently contains no evidence of** prompt versioning/benchmark harness/evaluation dataset/beyond-validation confidence calibration (as above)

- **Product** — `frontend/` checkout does not contain `frontend/` although README references one; `Phase 16/17` (`Dashboard`, `Timeline UI`, `Analysis UI`, `Authentication Pages`, `Frontend Testing`, `Backend/Frontend/Database/E2E Testing` all `[ ]`); `405` CRUD where `405` is **intentional architectural decision** (not gaps) — `Delete patient` `405`; **The current implementation does not include batch operations, export functionality, or administrative tooling. These represent potential future product capabilities rather than committed roadmap items**; search beyond `ILIKE` (`pg_trgm` deferred per §19.6)

- **RxNorm** — `PIN` deferred, `MIN`/`BN` blocked until decomposition, **not yet applied** `term_type`/`is_active` columns + `rxnorm_term_type_enum` type (`backend/scripts/README.md:12` “*columns do not exist on `reference_drugs` as of current importer version*” + `grep -n "term_type" backend/scripts/import_rxnorm.py` → no column creation) — `VERIFIED (repository)` for each grouped absence

*All grouped bullets are phrased as **“The repository currently contains no evidence of … in this repository”** or **“not yet applied”** for not-yet-shipped columns/types, and **“areas for future evolution”** for architecture/AI vs **“potential future capabilities”** for product — consistent with your instruction to avoid alternating between “roadmap items”, “future work”, “future enhancements”, and “potential capabilities” unless deliberate.*

---

*End of Part 2 — Sections 8–19 complete. Sections 20–24 (Part 3 — Roadmap detail, reference verification, and operational runbook) remain as future documentation per the additive-evolution principle.*
