"""Alembic migration lifecycle and persistence index integration test."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.api.engine_adapter import MockTwinEngineAdapter
from app.api.fixtures import make_speech_features
from app.main import create_app
from app.persistence.database import Database
from tests.conftest import CLINICIAN_A_KEY, make_test_settings


def test_alembic_migrations_upgrade_downgrade_and_serve_api(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "migrated.sqlite3"
    db_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    alembic_ini = Path(__file__).resolve().parents[3] / "infra" / "migrations" / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", db_url)

    # Clean upgrade -> verify tables & composite index -> downgrade -> re-upgrade
    command.upgrade(cfg, "head")
    db = Database(db_url)
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    assert {
        "twins",
        "observations",
        "state_estimates",
        "simulation_scenarios",
        "idempotency_records",
        "audit_events",
        "model_metadata",
    }.issubset(tables)

    obs_indexes = {idx["name"]: idx["column_names"] for idx in inspector.get_indexes("observations")}
    assert obs_indexes.get("ix_observations_twin_observed_at") == ["twin_id", "observed_at"]
    db.dispose()

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # Serve API against purely Alembic-migrated schema (auto_create_tables=False)
    migrated_db = Database(db_url)
    app = create_app(
        settings=make_test_settings(),
        database=migrated_db,
        engine_adapter=MockTwinEngineAdapter(),
        auto_create_tables=False,
    )
    with TestClient(app) as client:
        resp = client.post(
            "/twin/create",
            headers={"X-API-Key": CLINICIAN_A_KEY, "Idempotency-Key": "mig-test-001"},
            json={
                "external_reference": "SYN-MIG-001",
                "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "features": make_speech_features(0.25),
            },
        )
        assert resp.status_code == 201
    migrated_db.dispose()
