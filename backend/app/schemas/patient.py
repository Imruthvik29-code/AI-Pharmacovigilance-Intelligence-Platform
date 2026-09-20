"""
Pydantic schemas for patient endpoints (spec section 7).

PatientCreate/PatientUpdate deliberately omit `user_id` -- it is always
derived from the verified JWT (see api/v1/patients.py), never accepted
from the client, so a caller can never create or claim a patient under
someone else's account.
"""
import uuid
from datetime import datetime, time
from zoneinfo import available_timezones

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PatientRelation = Literal["Self", "Parent", "Spouse", "Child", "Sibling", "Grandparent", "Other", "Caregiver / dependent"]


def _validate_timezone(value: str | None) -> str | None:
    """Reject anything that is not a real IANA zone key.

    Checked against the tz database (`tzdata`, pinned in requirements.txt)
    rather than a name pattern, so a plausible-looking typo such as
    "Asia/Kolkatta" is refused instead of being stored and failing later
    when a schedule is generated from it.
    """
    if value is None:
        return None
    normalized = value.strip()
    if normalized not in available_timezones():
        raise ValueError(f"{normalized!r} is not a valid IANA timezone identifier.")
    return normalized


class PatientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    relation: PatientRelation | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=50)
    weight_kg: float | None = Field(default=None, gt=0)
    renal_flag: bool = False
    hepatic_flag: bool = False
    # Routine context only. Meal times carry no dosing meaning on their
    # own -- a prescription's relationship to them is a separate concept.
    # Ordering between meals is deliberately not validated: a night-shift
    # patient may legitimately eat dinner before breakfast by clock time.
    timezone: str | None = Field(default=None, max_length=64)
    breakfast_time: time | None = None
    lunch_time: time | None = None
    dinner_time: time | None = None

    _check_timezone = field_validator("timezone")(_validate_timezone)


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """All fields optional -- only provided fields are applied (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    relation: PatientRelation | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=50)
    weight_kg: float | None = Field(default=None, gt=0)
    renal_flag: bool | None = None
    hepatic_flag: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)
    breakfast_time: time | None = None
    lunch_time: time | None = None
    dinner_time: time | None = None

    _check_timezone = field_validator("timezone")(_validate_timezone)


class PatientResponse(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
