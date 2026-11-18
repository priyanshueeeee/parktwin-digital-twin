"""Authentication, authorization, payload limits, rate limiting, and privacy-safe logging tests."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi.testclient import TestClient

from app.api.engine_adapter import MockTwinEngineAdapter
from app.api.fixtures import make_speech_features
from app.main import create_app
from app.persistence.database import Database
from tests.conftest import (
    ADMIN_KEY,
    CLINICIAN_A_KEY,
    CLINICIAN_B_KEY,
    READONLY_KEY,
    TestBundle,
    make_test_settings,
)


def test_authentication_and_role_authorization(bundle: TestBundle) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "external_reference": "SYN-AUTH-001",
        "observed_at": now,
        "features": make_speech_features(0.2),
        "idempotency_key": "auth-create-001",
    }

    # Missing API key -> 401
    assert bundle.client.post("/twin/create", json=payload).status_code == 401
    # Invalid API key -> 401
    assert bundle.client.post("/twin/create", headers={"X-API-Key": "bad-key"}, json=payload).status_code == 401
    # Readonly cannot create twins -> 403
    assert bundle.client.post("/twin/create", headers={"X-API-Key": READONLY_KEY}, json=payload).status_code == 403

    # Clinician A creates twin using Bearer header
    created = bundle.client.post(
        "/twin/create",
        headers={"Authorization": f"Bearer {CLINICIAN_A_KEY}"},
        json=payload,
    )
    assert created.status_code == 201
    twin_id = created.json()["data"]["twin"]["id"]

    # Clinician B cannot read or update Clinician A's twin -> 403
    assert (
        bundle.client.get(f"/twin/{twin_id}/trajectory", headers={"X-API-Key": CLINICIAN_B_KEY}).status_code
        == 403
    )
    assert (
        bundle.client.post(
            "/twin/update",
            headers={"X-API-Key": CLINICIAN_B_KEY},
            json={
                "twin_id": twin_id,
                "observed_at": now,
                "features": make_speech_features(0.3),
                "idempotency_key": "auth-upd-b",
            },
        ).status_code
        == 403
    )

    # Readonly CAN read trajectory, CANNOT update
    assert (
        bundle.client.get(f"/twin/{twin_id}/trajectory", headers={"X-API-Key": READONLY_KEY}).status_code
        == 200
    )
    assert (
        bundle.client.post(
            "/twin/update",
            headers={"X-API-Key": READONLY_KEY},
            json={
                "twin_id": twin_id,
                "observed_at": now,
                "features": make_speech_features(0.3),
                "idempotency_key": "auth-upd-ro",
            },
        ).status_code
        == 403
    )

    # Admin can access any twin
    assert (
        bundle.client.get(f"/twin/{twin_id}/trajectory", headers={"X-API-Key": ADMIN_KEY}).status_code
        == 200
    )


def test_payload_limit_and_rate_limit_protections() -> None:
    settings = make_test_settings(max_payload_bytes=512, rate_limit_requests=3, rate_limit_window_seconds=60)
    db = Database("sqlite:///:memory:")
    app = create_app(settings=settings, database=db, engine_adapter=MockTwinEngineAdapter(), auto_create_tables=True)

    with TestClient(app) as client:
        # Oversized payload rejected with 413
        oversized = client.post(
            "/twin/create",
            headers={"X-API-Key": CLINICIAN_A_KEY},
            content="{" + '"pad":"' + ("x" * 1024) + '"}',
        )
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

        # Exceed rate limit (3 requests allowed)
        for _ in range(3):
            resp = client.get("/twins", headers={"X-API-Key": CLINICIAN_A_KEY})
            assert resp.status_code == 200
        limited = client.get("/twins", headers={"X-API-Key": CLINICIAN_A_KEY})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMITED"
    db.dispose()


def test_logs_contain_no_speech_features_or_patient_references(
    bundle: TestBundle, auth_headers: dict[str, str], caplog
) -> None:
    caplog.set_level(logging.INFO, logger="parktwin.api")
    ref = "SYN-PRIVACY-999"
    resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "privacy-log-001"},
        json={
            "external_reference": ref,
            "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "features": make_speech_features(0.5),
        },
    )
    assert resp.status_code == 201

    combined_logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert ref not in combined_logs
    assert "jitter_percent" not in combined_logs
    assert "shimmer_apq11" not in combined_logs
    assert resp.headers["X-Request-ID"] in combined_logs
