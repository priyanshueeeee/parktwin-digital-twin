"""Unified public error envelope and exception handlers (never leaks stack traces or PII)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass
class FieldError:
    name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "reason": self.reason}


@dataclass
class ApiError(Exception):
    """Domain/API error serialized to the standard ParkTwin error envelope."""

    status_code: int
    code: str
    message: str
    fields: list[FieldError] = field(default_factory=list)


def build_error_payload(
    *,
    request_id: str,
    schema_version: str,
    code: str,
    message: str,
    fields: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "schema_version": schema_version,
        "error": {
            "code": code,
            "message": message,
            "fields": fields or [],
        },
    }


def _request_id_from(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown-request")


def _schema_version_from(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    return settings.schema_version if settings is not None else "v1"


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is not None and exc.code == "VALIDATION_ERROR":
        metrics.record_validation_failure(exc.code)
    payload = build_error_payload(
        request_id=_request_id_from(request),
        schema_version=_schema_version_from(request),
        code=exc.code,
        message=exc.message,
        fields=[f.to_dict() for f in exc.fields],
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields: list[dict[str, str]] = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part != "body"]
        field_name = ".".join(loc) if loc else "request"
        # Use generic Pydantic message without echoing raw user input values
        reason = str(err.get("msg", "invalid value"))
        fields.append({"name": field_name, "reason": reason})

    metrics = getattr(request.app.state, "metrics", None)
    if metrics is not None:
        metrics.record_validation_failure("VALIDATION_ERROR")

    payload = build_error_payload(
        request_id=_request_id_from(request),
        schema_version=_schema_version_from(request),
        code="VALIDATION_ERROR",
        message="The request payload failed schema or range validation.",
        fields=fields,
    )
    return JSONResponse(status_code=400, content=payload)


async def unhandled_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    payload = build_error_payload(
        request_id=_request_id_from(request),
        schema_version=_schema_version_from(request),
        code="INTERNAL_ERROR",
        message="An unexpected server error occurred. Reference the request_id for support.",
        fields=[],
    )
    return JSONResponse(status_code=500, content=payload)
