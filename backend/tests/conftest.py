"""Shared pytest fixtures for Segment B contract and integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.engine_adapter import MockTwinEngineAdapter
from app.config import ApiKeyPrincipal, Settings
from app.main import create_app
from app.persistence.database import Database


CLINICIAN_A_KEY = "test-clinician-a-key"
CLINICIAN_B_KEY = "test-clinician-b-key"
ADMIN_KEY = "test-admin-key"
READONLY_KEY = "test-readonly-key"


@dataclass
class TestBundle:
    __test__ = False
    app: FastAPI
    client: TestClient
    db: Database
    engine: MockTwinEngineAdapter
    settings: Settings


def make_test_settings(
    *,
    max_payload_bytes: int = 65536,
    rate_limit_requests: int = 1000,
    rate_limit_window_seconds: int = 60,
) -> Settings:
    return Settings(
        env="test",
        schema_version="v1",
        service_version="0.1.0-test",
        database_url="sqlite:///:memory:",
        auth_enabled=True,
        api_keys={
            CLINICIAN_A_KEY: ApiKeyPrincipal(CLINICIAN_A_KEY, "clinician-a", "clinician"),
            CLINICIAN_B_KEY: ApiKeyPrincipal(CLINICIAN_B_KEY, "clinician-b", "clinician"),
            ADMIN_KEY: ApiKeyPrincipal(ADMIN_KEY, "admin-01", "admin"),
            READONLY_KEY: ApiKeyPrincipal(READONLY_KEY, "viewer-01", "readonly"),
        },
        max_payload_bytes=max_payload_bytes,
        rate_limit_requests=rate_limit_requests,
        rate_limit_window_seconds=rate_limit_window_seconds,
        cors_origins=["http://localhost:5173"],
        engine_adapter="mock",
        real_adapter_path="app.services.adapter:build_real_engine_adapter",
        stale_days_threshold=30,
    )


@pytest.fixture()
def bundle() -> Iterator[TestBundle]:
    settings = make_test_settings()
    db = Database("sqlite:///:memory:")
    engine = MockTwinEngineAdapter(available=True)
    app = create_app(settings=settings, database=db, engine_adapter=engine, auto_create_tables=True)
    with TestClient(app) as client:
        yield TestBundle(app=app, client=client, db=db, engine=engine, settings=settings)
    db.dispose()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": CLINICIAN_A_KEY}
