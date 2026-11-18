"""Health, readiness, and safe operational metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import NON_DIAGNOSTIC_DISCLAIMER


router = APIRouter(tags=["Operations"])


@router.get("/health", summary="Liveness check")
def health_check(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "status": "ok",
            "service_version": settings.service_version,
            "environment": settings.env,
            "disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
        },
        "warnings": [],
    }


@router.get("/ready", summary="Readiness check (database and inference adapter)")
def readiness_check(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    db = request.app.state.db
    engine = request.app.state.engine

    db_ok = db.check_health()
    model_ok = engine.is_available()
    ready = db_ok and model_ok

    metadata = engine.get_model_metadata().to_dict() if model_ok else None
    payload = {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "database": "ok" if db_ok else "unavailable",
                "inference_adapter": "ok" if model_ok else "unavailable",
            },
            "model_metadata": metadata,
        },
        "warnings": [] if ready else ["SERVICE_DEGRADED: One or more dependencies are unavailable."],
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@router.get("/metrics", summary="Safe operational metrics snapshot")
def metrics_snapshot(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    metrics = request.app.state.metrics
    return {
        "request_id": request.state.request_id,
        "schema_version": settings.schema_version,
        "data": metrics.snapshot(),
        "warnings": [],
    }
