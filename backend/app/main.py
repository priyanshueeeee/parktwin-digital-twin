"""FastAPI application entrypoint and middleware stack for ParkTwin."""

from __future__ import annotations

from contextlib import asynccontextmanager
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.engine_adapter import TwinEnginePort, build_engine_adapter
from app.api.errors import (
    ApiError,
    api_error_handler,
    build_error_payload,
    unhandled_error_handler,
    validation_error_handler,
)
from app.api.observability import MetricsRegistry, SlidingWindowRateLimiter, log_safe_event
from app.api.routes import health, twins
from app.config import NON_DIAGNOSTIC_DISCLAIMER, Settings, load_settings
from app.persistence.database import Database


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    engine_adapter: TwinEnginePort | None = None,
    auto_create_tables: bool = True,
) -> FastAPI:
    """Create a configured FastAPI application instance."""
    cfg = settings or load_settings()
    db = database or Database(cfg.database_url)
    adapter = engine_adapter or build_engine_adapter(
        cfg.engine_adapter,
        real_adapter_path=cfg.real_adapter_path,
    )
    metrics = MetricsRegistry()
    rate_limiter = SlidingWindowRateLimiter(
        max_requests=cfg.rate_limit_requests,
        window_seconds=cfg.rate_limit_window_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if auto_create_tables:
            db.create_all()
        yield

    if auto_create_tables and database is not None:
        db.create_all()

    app = FastAPI(
        title="ParkTwin Digital Twin API",
        version=cfg.service_version,
        description=(
            "Longitudinal Parkinson's progression digital twin research service.\n\n"
            f"**Safety Boundary:** {NON_DIAGNOSTIC_DISCLAIMER}"
        ),
        lifespan=lifespan,
    )

    app.state.settings = cfg
    app.state.db = db
    app.state.engine = adapter
    app.state.metrics = metrics
    app.state.rate_limiter = rate_limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms", "Server-Timing", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_guard_and_observability_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id
        request.state.actor_id = None
        request.state.stage_timings_ms = {}
        start = time.perf_counter()

        # Payload size protection
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > cfg.max_payload_bytes:
                    payload = build_error_payload(
                        request_id=request_id,
                        schema_version=cfg.schema_version,
                        code="PAYLOAD_TOO_LARGE",
                        message=f"Request payload exceeds maximum allowed size ({cfg.max_payload_bytes} bytes).",
                    )
                    resp = JSONResponse(status_code=413, content=payload)
                    resp.headers["X-Request-ID"] = request_id
                    return resp
            except ValueError:
                pass

        # Rate-limit protection (skip health probes)
        if request.url.path not in {"/health", "/ready"}:
            client_key = (
                request.headers.get("X-API-Key")
                or (request.client.host if request.client else "unknown")
            )
            if not rate_limiter.allow(client_key):
                payload = build_error_payload(
                    request_id=request_id,
                    schema_version=cfg.schema_version,
                    code="RATE_LIMITED",
                    message="Rate limit exceeded. Please wait before submitting additional requests.",
                )
                resp = JSONResponse(status_code=429, content=payload)
                resp.headers["X-Request-ID"] = request_id
                return resp

        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{latency_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"

        stage_timings: dict[str, float] = getattr(request.state, "stage_timings_ms", {})
        timing_parts = [f"{k};dur={v:.2f}" for k, v in stage_timings.items()]
        timing_parts.append(f"total;dur={latency_ms:.2f}")
        response.headers["Server-Timing"] = ", ".join(timing_parts)

        route_obj = request.scope.get("route")
        endpoint_label = getattr(route_obj, "path", request.url.path)
        metrics.record_request(f"{request.method} {endpoint_label}", response.status_code, latency_ms)

        log_safe_event(
            event="http_request",
            request_id=request_id,
            method=request.method,
            path=endpoint_label,
            status_code=response.status_code,
            latency_ms=latency_ms,
            actor_id=getattr(request.state, "actor_id", None),
        )
        return response

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(twins.router)
    return app


app = create_app()
