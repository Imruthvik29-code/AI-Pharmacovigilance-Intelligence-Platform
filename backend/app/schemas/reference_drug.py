"""
Pydantic schemas for the reference-drug search endpoint.

The search response deliberately exposes the human-facing identity fields
needed by the medication picker: catalog name, generic/composition label,
provenance, and RxNorm term type. RxCUI remains an implementation detail
for safety normalization and is never shown as the primary medication name.
"""
import uuid

from pydantic import BaseModel, ConfigDict


class ReferenceDrugSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    generic_name: str | None
    rxcui: str | None
    source: str | None
    term_type: str | None
