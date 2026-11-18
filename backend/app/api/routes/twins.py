"""Core ParkTwin digital twin REST endpoints."""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import io
import json
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.api.auth import (
    AuthenticatedActor,
    authorize_twin_access,
    authorize_twin_mutation,
    get_current_actor,
    require_write_role,
)
from app.api.engine_adapter import ModelUnavailableError, TrajectoryInputPoint, TwinEnginePort
from app.api.errors import ApiError, FieldError
from app.api.observability import MetricsRegistry
from app.api.schemas import (
    RecomputeRequest,
    SimulationRequest,
    TwinCreateRequest,
    TwinStatusUpdateRequest,
    TwinUpdateRequest,
)
from app.config import NON_DIAGNOSTIC_DISCLAIMER, Settings
from app.persistence.models import (
    ObservationRecord,
    StateEstimateRecord,
    TwinRecord,
    ensure_utc,
)
from app.persistence.repository import ConcurrencyConflictError, TwinRepository


router = APIRouter(tags=["Digital Twins"])


def _get_session(request: Request):
    yield from request.app.state.db.session_dependency()


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_idempotency_key(body_key: str | None, header_key: str | None) -> str:
    key = (header_key or body_key or "").strip()
    if len(key) < 4 or len(key) > 128:
        raise ApiError(
            status_code=400,
            code="VALIDATION_ERROR",
            message="A valid idempotency key (4-128 chars) is required in Idempotency-Key header or body.",
            fields=[FieldError(name="idempotency_key", reason="required (4-128 characters)")],
        )
    return key


def _to_trajectory_inputs(
    rows: list[tuple[ObservationRecord, StateEstimateRecord | None]],
) -> list[TrajectoryInputPoint]:
    points: list[TrajectoryInputPoint] = []
    for obs, est in rows:
        merged_flags = list(dict.fromkeys([*(obs.quality_flags or []), *(est.quality_flags if est else [])]))
        points.append(
            TrajectoryInputPoint(
                observation_id=obs.id,
                observed_at=ensure_utc(obs.observed_at),
                is_partial=obs.is_partial,
                observed_total_updrs=obs.observed_total_updrs,
                observed_motor_updrs=obs.observed_motor_updrs,
                estimated_total_updrs=est.estimated_total_updrs if est else None,
                estimated_motor_updrs=est.estimated_motor_updrs if est else None,
                total_updrs_ci_low=est.total_updrs_ci_low if est else None,
                total_updrs_ci_high=est.total_updrs_ci_high if est else None,
                motor_updrs_ci_low=est.motor_updrs_ci_low if est else None,
                motor_updrs_ci_high=est.motor_updrs_ci_high if est else None,
                quality_flags=tuple(merged_flags),
            )
        )
    return points


def _serialize_twin(twin: TwinRecord) -> dict[str, Any]:
    return {
        "id": twin.id,
        "external_reference": twin.external_reference,
        "status": twin.status,
        "version": twin.version,
        "latest_state_id": twin.latest_state_id,
        "data_quality_summary": twin.data_quality_summary,
        "schema_version": twin.schema_version,
        "created_at": ensure_utc(twin.created_at).isoformat(),
        "updated_at": ensure_utc(twin.updated_at).isoformat(),
    }


def _record_stage(request: Request, metrics: MetricsRegistry, stage: str, elapsed_ms: float) -> None:
    metrics.record_stage_latency(stage, elapsed_ms)
    timings = getattr(request.state, "stage_timings_ms", None)
    if isinstance(timings, dict):
        timings[stage] = round(timings.get(stage, 0.0) + elapsed_ms, 3)


def _compute_calibration_summary(
    rows: list[tuple[ObservationRecord, StateEstimateRecord | None]],
) -> dict[str, Any]:
    total_abs_errs: list[float] = []
    motor_abs_errs: list[float] = []
    total_signed: list[float] = []
    for obs, est in rows:
        if est is None:
            continue
        if obs.observed_total_updrs is not None and est.estimated_total_updrs is not None:
            diff = est.estimated_total_updrs - obs.observed_total_updrs
            total_abs_errs.append(abs(diff))
            total_signed.append(diff)
        if obs.observed_motor_updrs is not None and est.estimated_motor_updrs is not None:
            motor_abs_errs.append(abs(est.estimated_motor_updrs - obs.observed_motor_updrs))

    return {
        "paired_total_count": len(total_abs_errs),
        "paired_motor_count": len(motor_abs_errs),
        "total_updrs_mae": round(sum(total_abs_errs) / len(total_abs_errs), 2) if total_abs_errs else None,
        "motor_updrs_mae": round(sum(motor_abs_errs) / len(motor_abs_errs), 2) if motor_abs_errs else None,
        "total_updrs_mean_bias": round(sum(total_signed) / len(total_signed), 2) if total_signed else None,
    }


def _serialize_estimate(obs: ObservationRecord, est: StateEstimateRecord) -> dict[str, Any]:
    return {
        "id": est.id,
        "observation_id": obs.id,
        "observed_at": ensure_utc(obs.observed_at).isoformat(),
        "estimated_total_updrs": est.estimated_total_updrs,
        "estimated_motor_updrs": est.estimated_motor_updrs,
        "total_updrs_ci_low": est.total_updrs_ci_low,
        "total_updrs_ci_high": est.total_updrs_ci_high,
        "motor_updrs_ci_low": est.motor_updrs_ci_low,
        "motor_updrs_ci_high": est.motor_updrs_ci_high,
        "confidence_score": est.confidence_score,
        "quality_flags": est.quality_flags or [],
        "model_version": est.model_version,
        "feature_version": est.feature_version,
    }


@router.get("/twins", summary="List accessible digital twins for dashboard selection")
def list_twins(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    repo = TwinRepository(session)

    owner_filter = None if actor.role in {"admin", "readonly"} else actor.actor_id
    twins = repo.list_twins(owner_id=owner_filter, limit=limit)

    items: list[dict[str, Any]] = []
    for twin in twins:
        rows = repo.list_observations_with_estimates(twin.id)
        traj = engine.compute_trajectory(
            _to_trajectory_inputs(rows),
            stale_threshold_days=settings.stale_days_threshold,
        )
        latest_est = traj.estimated_points[-1] if traj.estimated_points else None
        items.append(
            {
                **_serialize_twin(twin),
                "observation_count": traj.coverage["total_observations"],
                "last_observed_at": traj.coverage["last_observed_at"],
                "is_stale": traj.coverage["is_stale"],
                "latest_total_updrs": latest_est["total_updrs"] if latest_est else None,
                "latest_motor_updrs": latest_est["motor_updrs"] if latest_est else None,
                "slope_status": traj.slope["status"],
                "slope_total_per_30_days": traj.slope["total_updrs_per_30_days"],
            }
        )

    repo.record_audit_event(
        request_id=request.state.request_id,
        actor_id=actor.actor_id,
        action="twin.list",
        resource_type="twin",
        resource_id=None,
        outcome="success",
        details={"returned_count": len(items)},
    )
    session.commit()

    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twins": items,
            "count": len(items),
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": [],
    }


@router.post("/twin/create", status_code=201, summary="Validate baseline and initialize a new twin")
def create_twin(
    payload: TwinCreateRequest,
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: AuthenticatedActor = Depends(require_write_role),
    session: Session = Depends(_get_session),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    metrics: MetricsRegistry = request.app.state.metrics
    repo = TwinRepository(session)

    idem_key = _resolve_idempotency_key(payload.idempotency_key, idempotency_key_header)
    scope = f"twin_create:{actor.actor_id}"
    req_hash = _canonical_hash(
        {
            "external_reference": payload.external_reference,
            "observed_at": payload.observed_at.isoformat(),
            "features": payload.features.model_dump(),
            "allow_partial": payload.allow_partial,
            "observed_total_updrs": payload.observed_total_updrs,
            "observed_motor_updrs": payload.observed_motor_updrs,
            "source": payload.source,
        }
    )

    existing_idem = repo.get_idempotency_record(scope, idem_key)
    if existing_idem is not None:
        if existing_idem.request_hash != req_hash:
            raise ApiError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was previously used with a different payload.",
                fields=[FieldError(name="idempotency_key", reason="payload mismatch for existing key")],
            )
        replay_body = dict(existing_idem.response_body)
        replay_body["request_id"] = request.state.request_id
        return JSONResponse(status_code=existing_idem.status_code, content=replay_body)

    features_dict = payload.features.model_dump()
    is_partial = not payload.features.is_complete()

    t_inf0 = time.perf_counter()
    try:
        inference = engine.infer(features_dict, is_partial=is_partial)
    except ModelUnavailableError:
        metrics.record_model_load_failure()
        session.rollback()
        raise ApiError(
            status_code=503,
            code="MODEL_UNAVAILABLE",
            message="The UPDRS inference model is currently unavailable; no twin state was committed.",
        )
    _record_stage(request, metrics, "inference", (time.perf_counter() - t_inf0) * 1000.0)

    meta = engine.get_model_metadata()
    try:
        repo.ensure_model_metadata(
            model_version=meta.model_version,
            feature_version=meta.feature_version,
            assumptions_version=meta.assumptions_version,
            adapter_type=meta.adapter_type,
            artifact_checksum=meta.artifact_checksum,
        )

        initial_status = "insufficient_data" if is_partial else "active"
        twin = repo.create_twin(
            external_reference=payload.external_reference,
            owner_id=actor.actor_id,
            status=initial_status,
            schema_version=settings.schema_version,
            data_quality_summary={"flags": inference.quality_flags, "is_partial_baseline": is_partial},
        )
        obs = repo.append_observation(
            twin_id=twin.id,
            observed_at=payload.observed_at,
            features=features_dict,
            is_partial=is_partial,
            observed_total_updrs=payload.observed_total_updrs,
            observed_motor_updrs=payload.observed_motor_updrs,
            source=payload.source,
            quality_flags=inference.quality_flags,
            idempotency_key=idem_key,
        )
        est = repo.append_state_estimate(
            twin_id=twin.id,
            observation_id=obs.id,
            estimated_total_updrs=inference.estimated_total_updrs,
            estimated_motor_updrs=inference.estimated_motor_updrs,
            total_updrs_ci_low=inference.total_updrs_ci_low,
            total_updrs_ci_high=inference.total_updrs_ci_high,
            motor_updrs_ci_low=inference.motor_updrs_ci_low,
            motor_updrs_ci_high=inference.motor_updrs_ci_high,
            confidence_score=inference.confidence_score,
            quality_flags=inference.quality_flags,
            model_version=inference.model_version,
            feature_version=inference.feature_version,
        )

        t_traj0 = time.perf_counter()
        traj = engine.compute_trajectory(
            _to_trajectory_inputs([(obs, est)]),
            stale_threshold_days=settings.stale_days_threshold,
        )
        _record_stage(request, metrics, "trajectory", (time.perf_counter() - t_traj0) * 1000.0)

        twin.latest_state_id = est.id if not is_partial else None
        twin.status = traj.status
        twin.data_quality_summary = {
            "flags": traj.quality_flags,
            "is_partial_baseline": is_partial,
            "total_observations": traj.coverage["total_observations"],
        }

        if traj.status == "insufficient_data" or traj.slope["status"] == "insufficient_data":
            metrics.record_insufficient_data()
        metrics.record_quality_warnings(len(traj.warnings))

        response_body: dict[str, Any] = {
            "request_id": request.state.request_id,
            "schema_version": settings.schema_version,
            "data": {
                "twin": _serialize_twin(twin),
                "baseline_observation_id": obs.id,
                "current_estimate": _serialize_estimate(obs, est),
                "trajectory_status": traj.slope["status"],
                "slope": traj.slope,
                "coverage": traj.coverage,
                "quality_flags": traj.quality_flags,
                "model_metadata": meta.to_dict(),
                "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
            },
            "warnings": traj.warnings,
        }

        repo.save_idempotency_record(
            scope=scope,
            idempotency_key=idem_key,
            request_hash=req_hash,
            status_code=201,
            response_body=response_body,
        )
        repo.record_audit_event(
            request_id=request.state.request_id,
            actor_id=actor.actor_id,
            action="twin.create",
            resource_type="twin",
            resource_id=twin.id,
            outcome="success",
            details={
                "status": twin.status,
                "is_partial": is_partial,
                "model_version": meta.model_version,
            },
        )
        session.commit()
    except ApiError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise

    return JSONResponse(status_code=201, content=response_body)


@router.post("/twin/update", status_code=200, summary="Ingest a new voice observation and recalculate state")
def update_twin(
    payload: TwinUpdateRequest,
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: AuthenticatedActor = Depends(require_write_role),
    session: Session = Depends(_get_session),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    metrics: MetricsRegistry = request.app.state.metrics
    repo = TwinRepository(session)

    idem_key = _resolve_idempotency_key(payload.idempotency_key, idempotency_key_header)
    twin = repo.get_twin(payload.twin_id)
    if twin is None:
        raise ApiError(
            status_code=404,
            code="NOT_FOUND",
            message="Digital twin not found.",
        )
    authorize_twin_mutation(actor, twin)

    if twin.status == "archived":
        raise ApiError(
            status_code=409,
            code="TWIN_ARCHIVED",
            message="Cannot append observations to an archived twin. Re-activate it first if appropriate.",
        )
    if twin.status == "paused":
        raise ApiError(
            status_code=409,
            code="TWIN_PAUSED",
            message="Twin is currently paused. Resume the twin to active status before appending observations.",
        )

    scope = f"twin_update:{twin.id}"
    req_hash = _canonical_hash(
        {
            "twin_id": payload.twin_id,
            "observed_at": payload.observed_at.isoformat(),
            "features": payload.features.model_dump(),
            "observed_total_updrs": payload.observed_total_updrs,
            "observed_motor_updrs": payload.observed_motor_updrs,
            "source": payload.source,
        }
    )

    existing_idem = repo.get_idempotency_record(scope, idem_key)
    if existing_idem is not None:
        if existing_idem.request_hash != req_hash:
            raise ApiError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was previously used with a different observation payload.",
                fields=[FieldError(name="idempotency_key", reason="payload mismatch for existing key")],
            )
        replay_body = dict(existing_idem.response_body)
        replay_body["request_id"] = request.state.request_id
        return JSONResponse(status_code=existing_idem.status_code, content=replay_body)

    if payload.expected_version is not None and payload.expected_version != twin.version:
        raise ApiError(
            status_code=409,
            code="CONCURRENCY_CONFLICT",
            message="Twin state has changed since the last read. Reload and retry with the latest version.",
            fields=[FieldError(name="expected_version", reason="stale twin version")],
        )

    if repo.has_observation_at(twin.id, payload.observed_at):
        raise ApiError(
            status_code=409,
            code="TIMESTAMP_CONFLICT",
            message="An observation already exists for this twin at the exact same timestamp.",
            fields=[FieldError(name="observed_at", reason="duplicate observation timestamp")],
        )

    latest_ts = repo.get_latest_observation_timestamp(twin.id)
    is_out_of_order = latest_ts is not None and ensure_utc(payload.observed_at) < latest_ts

    features_dict = payload.features.model_dump()
    t_inf0 = time.perf_counter()
    try:
        inference = engine.infer(features_dict, is_partial=False)
    except ModelUnavailableError:
        metrics.record_model_load_failure()
        session.rollback()
        raise ApiError(
            status_code=503,
            code="MODEL_UNAVAILABLE",
            message="The UPDRS inference model is currently unavailable; observation was not committed.",
        )
    _record_stage(request, metrics, "inference", (time.perf_counter() - t_inf0) * 1000.0)

    obs_flags = list(inference.quality_flags)
    if is_out_of_order:
        obs_flags.append("OUT_OF_ORDER_OBSERVATION")

    meta = engine.get_model_metadata()
    expected_version = twin.version

    try:
        repo.ensure_model_metadata(
            model_version=meta.model_version,
            feature_version=meta.feature_version,
            assumptions_version=meta.assumptions_version,
            adapter_type=meta.adapter_type,
            artifact_checksum=meta.artifact_checksum,
        )
        obs = repo.append_observation(
            twin_id=twin.id,
            observed_at=payload.observed_at,
            features=features_dict,
            is_partial=False,
            observed_total_updrs=payload.observed_total_updrs,
            observed_motor_updrs=payload.observed_motor_updrs,
            source=payload.source,
            quality_flags=obs_flags,
            idempotency_key=idem_key,
        )
        est = repo.append_state_estimate(
            twin_id=twin.id,
            observation_id=obs.id,
            estimated_total_updrs=inference.estimated_total_updrs,
            estimated_motor_updrs=inference.estimated_motor_updrs,
            total_updrs_ci_low=inference.total_updrs_ci_low,
            total_updrs_ci_high=inference.total_updrs_ci_high,
            motor_updrs_ci_low=inference.motor_updrs_ci_low,
            motor_updrs_ci_high=inference.motor_updrs_ci_high,
            confidence_score=inference.confidence_score,
            quality_flags=obs_flags,
            model_version=inference.model_version,
            feature_version=inference.feature_version,
        )

        rows = repo.list_observations_with_estimates(twin.id)
        t_traj0 = time.perf_counter()
        traj = engine.compute_trajectory(
            _to_trajectory_inputs(rows),
            stale_threshold_days=settings.stale_days_threshold,
        )
        _record_stage(request, metrics, "trajectory", (time.perf_counter() - t_traj0) * 1000.0)

        # Latest state always points to the most recent chronological estimated observation
        latest_est_id = est.id
        for row_obs, row_est in reversed(rows):
            if row_est is not None and row_est.estimated_total_updrs is not None:
                latest_est_id = row_est.id
                break

        warnings = list(traj.warnings)
        if is_out_of_order:
            warnings.append(
                "OUT_OF_ORDER_OBSERVATION: Observation timestamp precedes an existing record; trajectory recalculated chronologically."
            )

        updated_twin = repo.update_twin_latest_state(
            twin_id=twin.id,
            expected_version=expected_version,
            latest_state_id=latest_est_id,
            status=traj.status,
            data_quality_summary={
                "flags": traj.quality_flags,
                "total_observations": traj.coverage["total_observations"],
                "last_observed_at": traj.coverage["last_observed_at"],
            },
        )

        if traj.slope["status"] == "insufficient_data":
            metrics.record_insufficient_data()
        metrics.record_quality_warnings(len(warnings))

        response_body: dict[str, Any] = {
            "request_id": request.state.request_id,
            "schema_version": settings.schema_version,
            "data": {
                "twin": _serialize_twin(updated_twin),
                "observation_id": obs.id,
                "estimate": _serialize_estimate(obs, est),
                "trajectory_summary": {
                    "slope": traj.slope,
                    "coverage": traj.coverage,
                    "quality_flags": traj.quality_flags,
                },
                "model_metadata": meta.to_dict(),
                "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
            },
            "warnings": warnings,
        }

        repo.save_idempotency_record(
            scope=scope,
            idempotency_key=idem_key,
            request_hash=req_hash,
            status_code=200,
            response_body=response_body,
        )
        repo.record_audit_event(
            request_id=request.state.request_id,
            actor_id=actor.actor_id,
            action="twin.update",
            resource_type="twin",
            resource_id=twin.id,
            outcome="success",
            details={
                "new_version": updated_twin.version,
                "out_of_order": is_out_of_order,
                "model_version": meta.model_version,
            },
        )
        session.commit()
    except ConcurrencyConflictError:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="CONCURRENCY_CONFLICT",
            message="Concurrent update detected on twin state. Please retry with the latest version.",
        )
    except ApiError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise

    return JSONResponse(status_code=200, content=response_body)


@router.get("/twin/{twin_id}/trajectory", summary="Retrieve observed and estimated trajectory data")
def get_trajectory(
    twin_id: str,
    request: Request,
    start_time: datetime | None = Query(default=None, description="Optional inclusive ISO-8601 UTC start filter"),
    end_time: datetime | None = Query(default=None, description="Optional inclusive ISO-8601 UTC end filter"),
    series: Literal["all", "observed", "estimated"] = Query(default="all"),
    scenario_id: str | None = Query(
        default=None,
        description="Optional explicit scenario ID to overlay hypothetical simulation series",
    ),
    limit: int = Query(default=500, ge=1, le=2000),
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    metrics: MetricsRegistry = request.app.state.metrics
    repo = TwinRepository(session)

    if start_time is not None and end_time is not None and ensure_utc(start_time) > ensure_utc(end_time):
        raise ApiError(
            status_code=400,
            code="VALIDATION_ERROR",
            message="start_time must be less than or equal to end_time.",
            fields=[FieldError(name="start_time", reason="must be <= end_time")],
        )

    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_access(actor, twin)

    rows = repo.list_observations_with_estimates(
        twin.id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    t_traj0 = time.perf_counter()
    traj = engine.compute_trajectory(
        _to_trajectory_inputs(rows),
        stale_threshold_days=settings.stale_days_threshold,
    )
    _record_stage(request, metrics, "trajectory", (time.perf_counter() - t_traj0) * 1000.0)
    calibration_summary = _compute_calibration_summary(rows)

    observed_points = traj.observed_points if series in {"all", "observed"} else []
    estimated_points = traj.estimated_points if series in {"all", "estimated"} else []

    scenario_payload: dict[str, Any] | None = None
    warnings = list(traj.warnings)
    if scenario_id is not None:
        scenario = repo.get_simulation_scenario(twin.id, scenario_id)
        if scenario is None:
            raise ApiError(
                status_code=404,
                code="NOT_FOUND",
                message="Requested simulation scenario was not found for this twin.",
            )
        scenario_payload = {
            "id": scenario.id,
            "label": scenario.label,
            "hypothetical": True,
            "assumptions_version": scenario.assumptions_version,
            "model_version": scenario.model_version,
            "baseline_twin_version": scenario.baseline_twin_version,
            "parameters": scenario.parameters,
            "horizon_days": scenario.horizon_days,
            "step_days": scenario.step_days,
            "baseline_series": scenario.baseline_series,
            "scenario_series": [
                {**pt, "scenario_id": scenario.id, "hypothetical": True}
                for pt in scenario.scenario_series
            ],
            "summary": scenario.summary,
            "created_at": ensure_utc(scenario.created_at).isoformat(),
        }
        warnings.extend(scenario.warnings or [])

    meta = engine.get_model_metadata().to_dict()
    repo.record_audit_event(
        request_id=request.state.request_id,
        actor_id=actor.actor_id,
        action="twin.trajectory.read",
        resource_type="twin",
        resource_id=twin.id,
        outcome="success",
        details={"series": series, "scenario_requested": scenario_id is not None},
    )
    session.commit()

    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twin": _serialize_twin(twin),
            "series_filter": series,
            "observed_points": observed_points,
            "estimated_points": estimated_points,
            "scenario": scenario_payload,
            "slope": traj.slope,
            "coverage": traj.coverage,
            "calibration_summary": calibration_summary,
            "quality_flags": traj.quality_flags,
            "model_metadata": meta,
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": list(dict.fromkeys(warnings)),
    }


@router.post("/twin/{twin_id}/simulate", status_code=201, summary="Run an isolated hypothetical intervention scenario")
def simulate_intervention(
    twin_id: str,
    payload: SimulationRequest,
    request: Request,
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    metrics: MetricsRegistry = request.app.state.metrics
    repo = TwinRepository(session)

    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_access(actor, twin)

    # Consistent read snapshot of production twin state; simulation never writes to twins or observations.
    baseline_version = twin.version
    rows = repo.list_observations_with_estimates(twin.id)
    traj = engine.compute_trajectory(
        _to_trajectory_inputs(rows),
        stale_threshold_days=settings.stale_days_threshold,
    )

    if not traj.estimated_points:
        raise ApiError(
            status_code=400,
            code="VALIDATION_ERROR",
            message="Twin does not have an estimated baseline state yet. Submit a complete speech observation first.",
            fields=[FieldError(name="twin_id", reason="insufficient estimated history for simulation")],
        )

    t_sim0 = time.perf_counter()
    try:
        sim = engine.simulate(
            traj,
            levodopa_dose_change_mg=payload.interventions.levodopa_dose_change_mg,
            physical_therapy_sessions_per_week=payload.interventions.physical_therapy_sessions_per_week,
            adherence_ratio=payload.interventions.adherence_ratio,
            horizon_days=payload.horizon_days,
            step_days=payload.step_days,
        )
    except ModelUnavailableError:
        metrics.record_model_load_failure()
        raise ApiError(
            status_code=503,
            code="MODEL_UNAVAILABLE",
            message="The inference/simulation engine is currently unavailable.",
        )
    _record_stage(request, metrics, "simulation", (time.perf_counter() - t_sim0) * 1000.0)

    params_dict = payload.interventions.model_dump()
    scenario = repo.save_simulation_scenario(
        twin_id=twin.id,
        label=payload.label,
        parameters=params_dict,
        horizon_days=payload.horizon_days,
        step_days=payload.step_days,
        assumptions_version=sim.assumptions_version,
        model_version=sim.model_version,
        baseline_twin_version=baseline_version,
        baseline_series=sim.baseline_series,
        scenario_series=sim.scenario_series,
        summary=sim.summary,
        warnings=sim.warnings,
    )
    repo.record_audit_event(
        request_id=request.state.request_id,
        actor_id=actor.actor_id,
        action="twin.simulate",
        resource_type="scenario",
        resource_id=scenario.id,
        outcome="success",
        details={
            "twin_id": twin.id,
            "baseline_twin_version": baseline_version,
            "assumptions_version": sim.assumptions_version,
            "horizon_days": payload.horizon_days,
        },
    )
    session.commit()

    response_body = {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "scenario_id": scenario.id,
            "twin_id": twin.id,
            "label": scenario.label,
            "hypothetical": True,
            "status": scenario.status,
            "baseline_twin_version": baseline_version,
            "parameters": params_dict,
            "horizon_days": payload.horizon_days,
            "step_days": payload.step_days,
            "assumptions_version": sim.assumptions_version,
            "model_version": sim.model_version,
            "baseline_series": sim.baseline_series,
            "scenario_series": [
                {**pt, "scenario_id": scenario.id, "hypothetical": True}
                for pt in sim.scenario_series
            ],
            "summary": sim.summary,
            "created_at": ensure_utc(scenario.created_at).isoformat(),
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": sim.warnings,
    }
    return JSONResponse(status_code=201, content=response_body)


@router.get("/twin/{twin_id}/scenarios", summary="List isolated simulation scenarios for a twin")
def list_scenarios(
    twin_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    repo = TwinRepository(session)
    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_access(actor, twin)

    scenarios = repo.list_simulation_scenarios(twin.id, limit=limit)
    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twin_id": twin.id,
            "scenarios": [
                {
                    "scenario_id": sc.id,
                    "label": sc.label,
                    "hypothetical": True,
                    "parameters": sc.parameters,
                    "horizon_days": sc.horizon_days,
                    "step_days": sc.step_days,
                    "assumptions_version": sc.assumptions_version,
                    "model_version": sc.model_version,
                    "baseline_twin_version": sc.baseline_twin_version,
                    "summary": sc.summary,
                    "created_at": ensure_utc(sc.created_at).isoformat(),
                }
                for sc in scenarios
            ],
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": [],
    }


KEY_BIOMARKERS = ("jitter_percent", "shimmer", "nhr", "hnr", "rpde", "dfa", "ppe")


@router.get("/twin/{twin_id}/observations", summary="List immutable voice observations and biomarker deltas")
def list_observations(
    twin_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    repo = TwinRepository(session)
    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_access(actor, twin)

    rows = repo.list_observations_with_estimates(twin.id, limit=limit)
    complete_rows = [obs for obs, _ in rows if not obs.is_partial]

    biomarker_deltas: list[dict[str, Any]] = []
    if complete_rows:
        first_feat = complete_rows[0].features or {}
        last_feat = complete_rows[-1].features or {}
        for key in KEY_BIOMARKERS:
            base_val = first_feat.get(key)
            latest_val = last_feat.get(key)
            if base_val is not None and latest_val is not None:
                delta = round(float(latest_val) - float(base_val), 6)
                pct = (
                    round((delta / float(base_val)) * 100.0, 1)
                    if abs(float(base_val)) > 1e-9
                    else None
                )
                biomarker_deltas.append(
                    {
                        "feature": key,
                        "baseline": float(base_val),
                        "latest": float(latest_val),
                        "delta": delta,
                        "percent_change": pct,
                    }
                )

    items = [
        {
            "id": obs.id,
            "observed_at": ensure_utc(obs.observed_at).isoformat(),
            "is_partial": obs.is_partial,
            "source": obs.source,
            "observed_total_updrs": obs.observed_total_updrs,
            "observed_motor_updrs": obs.observed_motor_updrs,
            "estimated_total_updrs": est.estimated_total_updrs if est else None,
            "estimated_motor_updrs": est.estimated_motor_updrs if est else None,
            "confidence_score": est.confidence_score if est else None,
            "model_version": est.model_version if est else None,
            "feature_version": est.feature_version if est else None,
            "quality_flags": list(dict.fromkeys([*(obs.quality_flags or []), *(est.quality_flags if est else [])])),
            "features": obs.features,
        }
        for obs, est in reversed(rows)
    ]

    repo.record_audit_event(
        request_id=request.state.request_id,
        actor_id=actor.actor_id,
        action="twin.observations.read",
        resource_type="twin",
        resource_id=twin.id,
        outcome="success",
        details={"returned_count": len(items)},
    )
    session.commit()

    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twin_id": twin.id,
            "external_reference": twin.external_reference,
            "count": len(items),
            "biomarker_deltas": biomarker_deltas,
            "observations": items,
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": [],
    }


@router.patch("/twin/{twin_id}/status", summary="Pause, archive, or resume a digital twin lifecycle status")
def update_twin_status(
    twin_id: str,
    payload: TwinStatusUpdateRequest,
    request: Request,
    actor: AuthenticatedActor = Depends(require_write_role),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    repo = TwinRepository(session)
    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_mutation(actor, twin)

    if payload.expected_version != twin.version:
        raise ApiError(
            status_code=409,
            code="CONCURRENCY_CONFLICT",
            message="Twin version mismatch while updating lifecycle status.",
            fields=[FieldError(name="expected_version", reason="stale twin version")],
        )

    previous_status = twin.status
    target_status = payload.status
    if target_status == "active" and twin.latest_state_id is None:
        target_status = "insufficient_data"

    try:
        updated = repo.update_twin_latest_state(
            twin_id=twin.id,
            expected_version=payload.expected_version,
            latest_state_id=twin.latest_state_id,
            status=target_status,
            data_quality_summary=twin.data_quality_summary or {},
        )
        repo.record_audit_event(
            request_id=request.state.request_id,
            actor_id=actor.actor_id,
            action="twin.status.change",
            resource_type="twin",
            resource_id=twin.id,
            outcome="success",
            details={
                "previous_status": previous_status,
                "new_status": updated.status,
                "new_version": updated.version,
                "reason": payload.reason,
            },
        )
        session.commit()
    except ConcurrencyConflictError:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="CONCURRENCY_CONFLICT",
            message="Concurrent status update detected. Reload and retry.",
        )

    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twin": _serialize_twin(updated),
            "previous_status": previous_status,
            "reason": payload.reason,
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": [],
    }


@router.post("/twin/{twin_id}/recompute", summary="Recompute derived estimates and trajectory from immutable observations")
def recompute_twin_state(
    twin_id: str,
    payload: RecomputeRequest,
    request: Request,
    actor: AuthenticatedActor = Depends(require_write_role),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    metrics: MetricsRegistry = request.app.state.metrics
    repo = TwinRepository(session)

    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_mutation(actor, twin)

    rows = repo.list_observations_with_estimates(twin.id)
    meta = engine.get_model_metadata()
    expected_version = twin.version

    try:
        reestimated_count = 0
        if payload.re_run_inference:
            repo.ensure_model_metadata(
                model_version=meta.model_version,
                feature_version=meta.feature_version,
                assumptions_version=meta.assumptions_version,
                adapter_type=meta.adapter_type,
                artifact_checksum=meta.artifact_checksum,
            )
            t_inf0 = time.perf_counter()
            for obs, _existing_est in rows:
                try:
                    inf = engine.infer(obs.features or {}, is_partial=obs.is_partial)
                except ModelUnavailableError:
                    metrics.record_model_load_failure()
                    session.rollback()
                    raise ApiError(
                        status_code=503,
                        code="MODEL_UNAVAILABLE",
                        message="Inference model unavailable during recompute; no state changed.",
                    )
                preserved_obs_flags = [
                    f for f in (obs.quality_flags or []) if f == "OUT_OF_ORDER_OBSERVATION"
                ]
                merged_flags = list(dict.fromkeys([*inf.quality_flags, *preserved_obs_flags]))
                repo.replace_state_estimate_for_recompute(
                    observation_id=obs.id,
                    twin_id=twin.id,
                    estimated_total_updrs=inf.estimated_total_updrs,
                    estimated_motor_updrs=inf.estimated_motor_updrs,
                    total_updrs_ci_low=inf.total_updrs_ci_low,
                    total_updrs_ci_high=inf.total_updrs_ci_high,
                    motor_updrs_ci_low=inf.motor_updrs_ci_low,
                    motor_updrs_ci_high=inf.motor_updrs_ci_high,
                    confidence_score=inf.confidence_score,
                    quality_flags=merged_flags,
                    model_version=inf.model_version,
                    feature_version=inf.feature_version,
                )
                reestimated_count += 1
            _record_stage(request, metrics, "inference", (time.perf_counter() - t_inf0) * 1000.0)

        fresh_rows = repo.list_observations_with_estimates(twin.id)
        t_traj0 = time.perf_counter()
        traj = engine.compute_trajectory(
            _to_trajectory_inputs(fresh_rows),
            stale_threshold_days=settings.stale_days_threshold,
        )
        _record_stage(request, metrics, "trajectory", (time.perf_counter() - t_traj0) * 1000.0)

        latest_est_id: str | None = None
        for _obs, est in reversed(fresh_rows):
            if est is not None and est.estimated_total_updrs is not None:
                latest_est_id = est.id
                break

        next_status = twin.status if twin.status in {"paused", "archived"} else traj.status
        updated = repo.update_twin_latest_state(
            twin_id=twin.id,
            expected_version=expected_version,
            latest_state_id=latest_est_id,
            status=next_status,
            data_quality_summary={
                "flags": traj.quality_flags,
                "total_observations": traj.coverage["total_observations"],
                "last_observed_at": traj.coverage["last_observed_at"],
                "last_recomputed_model": meta.model_version,
            },
        )
        repo.record_audit_event(
            request_id=request.state.request_id,
            actor_id=actor.actor_id,
            action="twin.recompute",
            resource_type="twin",
            resource_id=twin.id,
            outcome="success",
            details={
                "re_run_inference": payload.re_run_inference,
                "reestimated_count": reestimated_count,
                "model_version": meta.model_version,
                "new_version": updated.version,
                "reason": payload.reason,
            },
        )
        session.commit()
    except ConcurrencyConflictError:
        session.rollback()
        raise ApiError(
            status_code=409,
            code="CONCURRENCY_CONFLICT",
            message="Concurrent twin modification occurred during recompute. Retry.",
        )

    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twin": _serialize_twin(updated),
            "reestimated_observations": reestimated_count,
            "slope": traj.slope,
            "coverage": traj.coverage,
            "model_metadata": meta.to_dict(),
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": traj.warnings,
    }


@router.get("/twin/{twin_id}/audit", summary="Retrieve redacted audit trail for a digital twin")
def get_twin_audit_trail(
    twin_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    repo = TwinRepository(session)
    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_access(actor, twin)

    events = repo.list_audit_events(twin.id, limit=limit)
    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "twin_id": twin.id,
            "count": len(events),
            "events": [
                {
                    "id": ev.id,
                    "request_id": ev.request_id,
                    "actor_id": ev.actor_id,
                    "action": ev.action,
                    "resource_type": ev.resource_type,
                    "resource_id": ev.resource_id,
                    "outcome": ev.outcome,
                    "details": ev.details or {},
                    "created_at": ensure_utc(ev.created_at).isoformat(),
                }
                for ev in events
            ],
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": [],
    }


@router.get("/twin/{twin_id}/export", summary="Export pseudonymous twin trajectory in JSON or CSV format")
def export_twin_trajectory(
    twin_id: str,
    request: Request,
    format: Literal["json", "csv"] = Query(default="json"),
    scenario_id: str | None = Query(default=None),
    actor: AuthenticatedActor = Depends(get_current_actor),
    session: Session = Depends(_get_session),
):
    settings: Settings = request.app.state.settings
    engine: TwinEnginePort = request.app.state.engine
    repo = TwinRepository(session)
    twin = repo.get_twin(twin_id)
    if twin is None:
        raise ApiError(status_code=404, code="NOT_FOUND", message="Digital twin not found.")
    authorize_twin_access(actor, twin)

    rows = repo.list_observations_with_estimates(twin.id)
    traj = engine.compute_trajectory(
        _to_trajectory_inputs(rows),
        stale_threshold_days=settings.stale_days_threshold,
    )
    meta = engine.get_model_metadata().to_dict()

    scenario_rows: list[dict[str, Any]] = []
    if scenario_id is not None:
        sc = repo.get_simulation_scenario(twin.id, scenario_id)
        if sc is None:
            raise ApiError(status_code=404, code="NOT_FOUND", message="Scenario not found for export.")
        scenario_rows = [
            {**pt, "scenario_id": sc.id, "hypothetical": True}
            for pt in sc.scenario_series
        ]

    repo.record_audit_event(
        request_id=request.state.request_id,
        actor_id=actor.actor_id,
        action="twin.export",
        resource_type="twin",
        resource_id=twin.id,
        outcome="success",
        details={"format": format, "scenario_included": scenario_id is not None},
    )
    session.commit()

    filename = f"parktwin-{twin.external_reference}-v{twin.version}.{format}"

    if format == "csv":
        buf = io.StringIO()
        buf.write(f"# {NON_DIAGNOSTIC_DISCLAIMER}\n")
        buf.write(
            f"# external_reference={twin.external_reference},model_version={meta['model_version']},"
            f"feature_version={meta['feature_version']},request_id={request.state.request_id}\n"
        )
        writer = csv.writer(buf)
        writer.writerow(
            [
                "timestamp_utc",
                "source_type",
                "hypothetical",
                "total_updrs",
                "motor_updrs",
                "total_ci_low",
                "total_ci_high",
                "scenario_id",
                "quality_flags",
            ]
        )
        for pt in [*traj.observed_points, *traj.estimated_points, *scenario_rows]:
            writer.writerow(
                [
                    pt.get("timestamp", ""),
                    pt.get("source_type", ""),
                    bool(pt.get("hypothetical", False)),
                    pt.get("total_updrs", ""),
                    pt.get("motor_updrs", ""),
                    pt.get("total_updrs_ci_low", ""),
                    pt.get("total_updrs_ci_high", ""),
                    pt.get("scenario_id") or "",
                    "|".join(pt.get("quality_flags") or []),
                ]
            )
        return PlainTextResponse(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    export_payload = {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
            "twin": _serialize_twin(twin),
            "model_metadata": meta,
            "slope": traj.slope,
            "coverage": traj.coverage,
            "calibration_summary": _compute_calibration_summary(rows),
            "observed_points": traj.observed_points,
            "estimated_points": traj.estimated_points,
            "hypothetical_scenario_points": scenario_rows,
        },
        "warnings": traj.warnings,
    }
    return JSONResponse(
        content=export_payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
