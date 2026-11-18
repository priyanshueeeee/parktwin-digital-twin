"""Application settings loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


NON_DIAGNOSTIC_DISCLAIMER = (
    "Research prototype only: ParkTwin estimates and simulations are non-diagnostic, "
    "hypothetical where labeled, and must not be used for primary diagnosis, prescribing, "
    "or clinical treatment decisions."
)


@dataclass(frozen=True)
class ApiKeyPrincipal:
    token: str
    actor_id: str
    role: str


@dataclass(frozen=True)
class Settings:
    env: str
    schema_version: str
    service_version: str
    database_url: str
    auth_enabled: bool
    api_keys: dict[str, ApiKeyPrincipal]
    max_payload_bytes: int
    rate_limit_requests: int
    rate_limit_window_seconds: int
    cors_origins: list[str]
    engine_adapter: str
    real_adapter_path: str
    stale_days_threshold: int


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_api_keys(raw: str) -> dict[str, ApiKeyPrincipal]:
    principals: dict[str, ApiKeyPrincipal] = {}
    for entry in raw.split(","):
        cleaned = entry.strip()
        if not cleaned:
            continue
        parts = cleaned.split(":")
        if len(parts) != 3:
            continue
        token, actor_id, role = (p.strip() for p in parts)
        if token and actor_id and role:
            principals[token] = ApiKeyPrincipal(token=token, actor_id=actor_id, role=role)
    return principals


def load_settings() -> Settings:
    default_keys = (
        "dev-clinician-key:clinician-demo-01:clinician,"
        "dev-admin-key:admin-demo-01:admin,"
        "dev-readonly-key:viewer-demo-01:readonly"
    )
    raw_origins = os.getenv(
        "PARKTWIN_CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:8080",
    )
    return Settings(
        env=os.getenv("PARKTWIN_ENV", "development"),
        schema_version=os.getenv("PARKTWIN_SCHEMA_VERSION", "v1"),
        service_version=os.getenv("PARKTWIN_SERVICE_VERSION", "0.1.0-segment-b"),
        database_url=os.getenv(
            "DATABASE_URL",
            "sqlite:///./parktwin_dev.db",
        ),
        auth_enabled=_parse_bool(os.getenv("PARKTWIN_AUTH_ENABLED"), default=True),
        api_keys=_parse_api_keys(os.getenv("PARKTWIN_API_KEYS", default_keys)),
        max_payload_bytes=int(os.getenv("PARKTWIN_MAX_PAYLOAD_BYTES", "65536")),
        rate_limit_requests=int(os.getenv("PARKTWIN_RATE_LIMIT_REQUESTS", "120")),
        rate_limit_window_seconds=int(os.getenv("PARKTWIN_RATE_LIMIT_WINDOW_SECONDS", "60")),
        cors_origins=[origin.strip() for origin in raw_origins.split(",") if origin.strip()],
        engine_adapter=os.getenv("PARKTWIN_ENGINE_ADAPTER", "mock"),
        real_adapter_path=os.getenv(
            "PARKTWIN_REAL_ADAPTER_PATH",
            "app.services.adapter:build_real_engine_adapter",
        ),
        stale_days_threshold=int(os.getenv("PARKTWIN_STALE_DAYS_THRESHOLD", "30")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
