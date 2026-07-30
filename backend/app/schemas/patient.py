"""
Pydantic schemas for patient endpoints (spec section 7).

PatientCreate/PatientUpdate deliberately omit `user_id` -- it is always
derived from the verified JWT (see api/v1/patients.py), never accepted
from the client, so a caller can never create or claim a patient under
someone else's account.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=50)
    weight_kg: float | None = Field(default=None, gt=0)
    renal_flag: bool = False
    hepatic_flag: bool = False


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """All fields optional -- only provided fields are applied (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=50)
    weight_kg: float | None = Field(default=None, gt=0)
    renal_flag: bool | None = None
    hepatic_flag: bool | None = None


class PatientResponse(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
