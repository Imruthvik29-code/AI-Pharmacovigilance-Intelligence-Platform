"""
Pydantic schemas for the reference-drug search endpoint:

    GET /api/v1/reference-drugs/search

Read-only -- reference_drugs is shared reference data (see
001_initial_schema.sql's RLS policy: "Authenticated users read
reference_drugs"), never created/edited by a client through this API.
Only a response schema is defined here, matching the read-only precedent
already set by schemas/timeline.py.

Response fields are deliberately narrow (id, name, rxcui, source) -- this
endpoint exists to support the frontend medication-picker autocomplete,
not as a general reference_drugs CRUD surface. `generic_name`/
`drug_class`/`source_updated_at` are intentionally not exposed here.
"""
import uuid

from pydantic import BaseModel, ConfigDict


class ReferenceDrugSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rxcui: str | None
    source: str | None
