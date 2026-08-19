"""
Pydantic schemas for the reference-drug search endpoint:

    GET /api/v1/reference-drugs/search

Read-only -- reference_drugs is shared reference data (see
001_initial_schema.sql's RLS policy: "Authenticated users read
reference_drugs"), never created/edited by a client through this API.
Only a response schema is defined here, matching the read-only precedent
already set by schemas/timeline.py.

Response fields are narrow (id, name, rxcui, source, term_type) -- this
endpoint exists to support the frontend medication-picker autocomplete,
not as a general reference_drugs CRUD surface. `generic_name`/`drug_class`/
`source_updated_at`/`is_active` are intentionally not exposed here.

`term_type` (added with the multi-TTY RxNorm import) is the RxNorm Term
Type of the concept: e.g. IN = ingredient, PIN = precise ingredient,
MIN = multiple ingredients, SCD = semantic clinical drug, SBD = semantic
branded drug, GPCK/BPCK = generic/branded pack, DF = dose form. NULL for
legacy hand-curated rows with no known TTY. Additive (nullable) field --
existing consumers that read only id/name/rxcui/source are unaffected.
"""
import uuid

from pydantic import BaseModel, ConfigDict


class ReferenceDrugSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rxcui: str | None
    source: str | None
    #: RxNorm Term Type (rxnorm_term_type_enum) or None for legacy rows.
    term_type: str | None
