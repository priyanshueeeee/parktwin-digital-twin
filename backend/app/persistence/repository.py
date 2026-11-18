"""Repository layer enforcing immutability, optimistic concurrency, idempotency, and auditability."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.persistence.models import (
    AuditEventRecord,
    IdempotencyRecord,
    ModelMetadataRecord,
    ObservationRecord,
    SimulationScenarioRecord,
    StateEstimateRecord,
    TwinRecord,
    ensure_utc,
    utc_now,
)


class ConcurrencyConflictError(Exception):
    """Raised when optimistic concurrency check fails on Twin update."""


class TwinRepository:
    """Data access methods for ParkTwin. Observations are strictly append-only."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # --- Model metadata ---

    def ensure_model_metadata(
        self,
        *,
        model_version: str,
        feature_version: str,
        assumptions_version: str,
        adapter_type: str,
        artifact_checksum: str,
    ) -> ModelMetadataRecord:
        existing = self.session.get(ModelMetadataRecord, model_version)
        if existing is not None:
            return existing
        record = ModelMetadataRecord(
            model_version=model_version,
            feature_version=feature_version,
            assumptions_version=assumptions_version,
            adapter_type=adapter_type,
            artifact_checksum=artifact_checksum,
        )
        self.session.add(record)
        self.session.flush()
        return record

    # --- Twins ---

    def create_twin(
        self,
        *,
        external_reference: str,
        owner_id: str,
        status: str,
        schema_version: str,
        data_quality_summary: dict[str, Any],
    ) -> TwinRecord:
        twin = TwinRecord(
            external_reference=external_reference,
            owner_id=owner_id,
            status=status,
            version=1,
            schema_version=schema_version,
            data_quality_summary=data_quality_summary,
        )
        self.session.add(twin)
        self.session.flush()
        return twin

    def get_twin(self, twin_id: str) -> TwinRecord | None:
        return self.session.get(TwinRecord, twin_id)

    def list_twins(self, *, owner_id: str | None = None, limit: int = 100) -> list[TwinRecord]:
        stmt = select(TwinRecord).order_by(TwinRecord.updated_at.desc()).limit(limit)
        if owner_id is not None:
            stmt = stmt.where(TwinRecord.owner_id == owner_id)
        return list(self.session.scalars(stmt).all())

    def update_twin_latest_state(
        self,
        *,
        twin_id: str,
        expected_version: int,
        latest_state_id: str | None,
        status: str,
        data_quality_summary: dict[str, Any],
    ) -> TwinRecord:
        """Atomically advance twin version and derived state with optimistic concurrency."""
        stmt = (
            update(TwinRecord)
            .where(TwinRecord.id == twin_id, TwinRecord.version == expected_version)
            .values(
                version=expected_version + 1,
                latest_state_id=latest_state_id,
                status=status,
                data_quality_summary=data_quality_summary,
                updated_at=utc_now(),
            )
        )
        result = self.session.execute(stmt)
        if result.rowcount != 1:
            raise ConcurrencyConflictError(
                f"Twin {twin_id} version mismatch (expected {expected_version})."
            )
        self.session.flush()
        twin = self.session.get(TwinRecord, twin_id)
        assert twin is not None
        self.session.refresh(twin)
        return twin

    # --- Observations (append-only, immutable) ---

    def append_observation(
        self,
        *,
        twin_id: str,
        observed_at: datetime,
        features: dict[str, float | None],
        is_partial: bool,
        observed_total_updrs: float | None,
        observed_motor_updrs: float | None,
        source: str,
        quality_flags: list[str],
        idempotency_key: str,
    ) -> ObservationRecord:
        obs = ObservationRecord(
            twin_id=twin_id,
            observed_at=ensure_utc(observed_at),
            features=features,
            is_partial=is_partial,
            observed_total_updrs=observed_total_updrs,
            observed_motor_updrs=observed_motor_updrs,
            source=source,
            quality_flags=quality_flags,
            idempotency_key=idempotency_key,
        )
        self.session.add(obs)
        self.session.flush()
        return obs

    def has_observation_at(self, twin_id: str, observed_at: datetime) -> bool:
        normalized = ensure_utc(observed_at)
        stmt = select(ObservationRecord.id).where(
            ObservationRecord.twin_id == twin_id,
            ObservationRecord.observed_at == normalized,
        )
        return self.session.scalars(stmt).first() is not None

    def get_latest_observation_timestamp(self, twin_id: str) -> datetime | None:
        stmt = select(func.max(ObservationRecord.observed_at)).where(
            ObservationRecord.twin_id == twin_id
        )
        ts = self.session.scalars(stmt).first()
        return ensure_utc(ts) if ts is not None else None

    def list_observations_with_estimates(
        self,
        twin_id: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[tuple[ObservationRecord, StateEstimateRecord | None]]:
        stmt = (
            select(ObservationRecord, StateEstimateRecord)
            .outerjoin(
                StateEstimateRecord,
                StateEstimateRecord.observation_id == ObservationRecord.id,
            )
            .where(ObservationRecord.twin_id == twin_id)
            .order_by(ObservationRecord.observed_at.asc(), ObservationRecord.created_at.asc())
        )
        if start_time is not None:
            stmt = stmt.where(ObservationRecord.observed_at >= ensure_utc(start_time))
        if end_time is not None:
            stmt = stmt.where(ObservationRecord.observed_at <= ensure_utc(end_time))
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = self.session.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def count_observations(self, twin_id: str) -> int:
        stmt = select(func.count(ObservationRecord.id)).where(ObservationRecord.twin_id == twin_id)
        return int(self.session.scalars(stmt).one())

    # --- State estimates ---

    def append_state_estimate(
        self,
        *,
        twin_id: str,
        observation_id: str,
        estimated_total_updrs: float | None,
        estimated_motor_updrs: float | None,
        total_updrs_ci_low: float | None,
        total_updrs_ci_high: float | None,
        motor_updrs_ci_low: float | None,
        motor_updrs_ci_high: float | None,
        confidence_score: float | None,
        quality_flags: list[str],
        model_version: str,
        feature_version: str,
    ) -> StateEstimateRecord:
        est = StateEstimateRecord(
            twin_id=twin_id,
            observation_id=observation_id,
            estimated_total_updrs=estimated_total_updrs,
            estimated_motor_updrs=estimated_motor_updrs,
            total_updrs_ci_low=total_updrs_ci_low,
            total_updrs_ci_high=total_updrs_ci_high,
            motor_updrs_ci_low=motor_updrs_ci_low,
            motor_updrs_ci_high=motor_updrs_ci_high,
            confidence_score=confidence_score,
            quality_flags=quality_flags,
            model_version=model_version,
            feature_version=feature_version,
        )
        self.session.add(est)
        self.session.flush()
        return est

    def get_state_estimate(self, estimate_id: str) -> StateEstimateRecord | None:
        return self.session.get(StateEstimateRecord, estimate_id)

    # --- Isolated simulation scenarios ---

    def save_simulation_scenario(
        self,
        *,
        twin_id: str,
        label: str,
        parameters: dict[str, Any],
        horizon_days: int,
        step_days: int,
        assumptions_version: str,
        model_version: str,
        baseline_twin_version: int,
        baseline_series: list[dict[str, Any]],
        scenario_series: list[dict[str, Any]],
        summary: dict[str, Any],
        warnings: list[str],
    ) -> SimulationScenarioRecord:
        record = SimulationScenarioRecord(
            twin_id=twin_id,
            label=label,
            parameters=parameters,
            horizon_days=horizon_days,
            step_days=step_days,
            assumptions_version=assumptions_version,
            model_version=model_version,
            baseline_twin_version=baseline_twin_version,
            status="completed",
            hypothetical=True,
            baseline_series=baseline_series,
            scenario_series=scenario_series,
            summary=summary,
            warnings=warnings,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_simulation_scenario(
        self, twin_id: str, scenario_id: str
    ) -> SimulationScenarioRecord | None:
        stmt = select(SimulationScenarioRecord).where(
            SimulationScenarioRecord.id == scenario_id,
            SimulationScenarioRecord.twin_id == twin_id,
        )
        return self.session.scalars(stmt).first()

    def list_simulation_scenarios(
        self, twin_id: str, limit: int = 25
    ) -> list[SimulationScenarioRecord]:
        stmt = (
            select(SimulationScenarioRecord)
            .where(SimulationScenarioRecord.twin_id == twin_id)
            .order_by(SimulationScenarioRecord.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    # --- Idempotency ---

    def get_idempotency_record(self, scope: str, idempotency_key: str) -> IdempotencyRecord | None:
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        return self.session.scalars(stmt).first()

    def save_idempotency_record(
        self,
        *,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        status_code: int,
        response_body: dict[str, Any],
    ) -> IdempotencyRecord:
        record = IdempotencyRecord(
            scope=scope,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status_code=status_code,
            response_body=response_body,
        )
        self.session.add(record)
        self.session.flush()
        return record

    # --- Audit events ---

    def record_audit_event(
        self,
        *,
        request_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEventRecord:
        event = AuditEventRecord(
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            details=details or {},
        )
        self.session.add(event)
        self.session.flush()
        return event
