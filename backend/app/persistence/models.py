"""SQLAlchemy ORM models for ParkTwin digital twin persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Normalize datetimes returned by drivers (e.g. SQLite) to timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class ModelMetadataRecord(Base):
    """Registered model and feature version lineage."""

    __tablename__ = "model_metadata"

    model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    assumptions_version: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TwinRecord(Base):
    """Patient-specific longitudinal digital twin aggregate root."""

    __tablename__ = "twins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="insufficient_data")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_state_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    data_quality_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ObservationRecord(Base):
    """Immutable voice-feature observation record."""

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_twin_observed_at", "twin_id", "observed_at"),
        UniqueConstraint("twin_id", "observed_at", name="uq_observations_twin_timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    twin_id: Mapped[str] = mapped_column(String(36), ForeignKey("twins.id", ondelete="CASCADE"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    features: Mapped[dict[str, float | None]] = mapped_column(JSON, nullable=False)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observed_total_updrs: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_motor_updrs: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="api")
    quality_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StateEstimateRecord(Base):
    """Versioned model UPDRS estimate linked to an immutable observation."""

    __tablename__ = "state_estimates"
    __table_args__ = (Index("ix_state_estimates_twin_created", "twin_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    twin_id: Mapped[str] = mapped_column(String(36), ForeignKey("twins.id", ondelete="CASCADE"), nullable=False)
    observation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("observations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    estimated_total_updrs: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_motor_updrs: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_updrs_ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_updrs_ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_updrs_ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_updrs_ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SimulationScenarioRecord(Base):
    """Isolated hypothetical intervention scenario with no mutation path to production observations."""

    __tablename__ = "simulation_scenarios"
    __table_args__ = (Index("ix_simulation_scenarios_twin_created", "twin_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    twin_id: Mapped[str] = mapped_column(String(36), ForeignKey("twins.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    step_days: Mapped[int] = mapped_column(Integer, nullable=False)
    assumptions_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_twin_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    hypothetical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    baseline_series: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    scenario_series: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IdempotencyRecord(Base):
    """Idempotency ledger for safe replay and conflict detection."""

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditEventRecord(Base):
    """Privacy-safe audit trail for twin lifecycle, simulation, and read access."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_resource", "resource_type", "resource_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
