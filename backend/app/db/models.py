"""
SQLAlchemy ORM models.

These map 1:1 onto the tables/enums defined in
`supabase/migrations/001_initial_schema.sql`. This file does not define
or alter schema — the SQL migration is the source of truth; these models
just give the app a typed way to read/write it.

`create_type=False` is used on every Postgres ENUM because the enum types
are already created by the migration; SQLAlchemy should never try to
create/alter them itself.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enum type bindings (match 001_initial_schema.sql exactly) ──────────
severity_level = ENUM(
    "mild", "moderate", "severe", name="severity_level", create_type=False
)
risk_level_enum = ENUM(
    "low", "moderate", "high", name="risk_level_enum", create_type=False
)
condition_status_enum = ENUM(
    "active", "improving", "resolved", "persistent", "recurred",
    name="condition_status_enum", create_type=False,
)
condition_reason_enum = ENUM(
    "doctor_diagnosis", "user_suspected", "unknown",
    name="condition_reason_enum", create_type=False,
)
medication_status_enum = ENUM(
    "active", "completed", "completed_early", "paused", "discontinued",
    name="medication_status_enum", create_type=False,
)
dose_status_enum = ENUM(
    "taken", "missed", "skipped", name="dose_status_enum", create_type=False
)
confidence_level_enum = ENUM(
    "low", "moderate", "high", name="confidence_level_enum", create_type=False
)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String)
    weight_kg: Mapped[float | None] = mapped_column(Numeric)
    renal_flag: Mapped[bool] = mapped_column(default=False)
    hepatic_flag: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    conditions: Mapped[list["Condition"]] = relationship(back_populates="patient")
    medications: Mapped[list["Medication"]] = relationship(back_populates="patient")
    symptoms: Mapped[list["Symptom"]] = relationship(back_populates="patient")


class Condition(Base):
    __tablename__ = "conditions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(condition_status_enum, default="active")
    reason: Mapped[str] = mapped_column(condition_reason_enum, default="unknown")
    diagnosed_date: Mapped[date | None] = mapped_column(Date)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship(back_populates="conditions")
    medications: Mapped[list["Medication"]] = relationship(back_populates="condition")


class ReferenceDrug(Base):
    __tablename__ = "reference_drugs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String)
    drug_class: Mapped[str | None] = mapped_column(String)
    # Reference-drug catalog infrastructure (003_reference_drugs_external_reference.sql):
    # external reference / catalog-import metadata. All nullable -- existing
    # seeded rows are unaffected until backfilled by backend/scripts/import_rxnorm.py.
    rxcui: Mapped[str | None] = mapped_column(String, unique=True)
    source: Mapped[str | None] = mapped_column(String)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conditions.id", ondelete="SET NULL")
    )
    purpose_text: Mapped[str | None] = mapped_column(Text)
    drug_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reference_drugs.id"), nullable=False
    )
    dose: Mapped[str | None] = mapped_column(String)
    times_per_day: Mapped[int | None] = mapped_column(Integer)
    interval_hours: Mapped[float | None] = mapped_column(Numeric)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(medication_status_enum, default="active")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship(back_populates="medications")
    condition: Mapped["Condition | None"] = relationship(back_populates="medications")
    drug: Mapped["ReferenceDrug"] = relationship()


class MedicationSchedule(Base):
    __tablename__ = "medication_schedule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MedicationDose(Base):
    __tablename__ = "medication_doses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medication_schedule.id", ondelete="SET NULL")
    )
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str | None] = mapped_column(dose_status_enum)
    actual_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Symptom(Base):
    __tablename__ = "symptoms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conditions.id", ondelete="SET NULL")
    )
    medication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(severity_level, default="mild")
    onset_date: Mapped[date] = mapped_column(Date)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship(back_populates="symptoms")


class InteractionRule(Base):
    __tablename__ = "interaction_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    drug_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reference_drugs.id"), nullable=False
    )
    drug_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reference_drugs.id"), nullable=False
    )
    severity: Mapped[str] = mapped_column(severity_level, nullable=False)
    mechanism: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AdrRule(Base):
    __tablename__ = "adr_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    drug_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reference_drugs.id"), nullable=False
    )
    reaction_description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(severity_level, nullable=False)
    frequency_class: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_title: Mapped[str] = mapped_column(String, nullable=False)
    event_description: Mapped[str | None] = mapped_column(Text)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String, default="v1.0")
    deterministic_result: Mapped[dict | None] = mapped_column(JSONB)
    safety_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(risk_level_enum)
    llm_summary: Mapped[str | None] = mapped_column(Text)
    llm_reasoning: Mapped[str | None] = mapped_column(Text)
    llm_recommendations: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    confidence_level: Mapped[str | None] = mapped_column(confidence_level_enum)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
