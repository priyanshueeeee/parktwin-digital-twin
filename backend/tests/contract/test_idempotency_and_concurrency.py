"""Idempotency replay/conflict and optimistic concurrency contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api.fixtures import make_speech_features
from app.persistence.repository import ConcurrencyConflictError, TwinRepository
from tests.conftest import TestBundle


def test_create_idempotency_replay_and_conflict(bundle: TestBundle, auth_headers: dict[str, str]) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=10)).replace(microsecond=0).isoformat()
    payload = {
        "external_reference": "SYN-IDEM-001",
        "observed_at": ts,
        "features": make_speech_features(0.3),
        "idempotency_key": "idem-create-key-1",
    }

    r1 = bundle.client.post("/twin/create", headers=auth_headers, json=payload)
    assert r1.status_code == 201
    twin_id = r1.json()["data"]["twin"]["id"]

    # Exact repeat returns same twin ID safely without creating a duplicate twin
    r2 = bundle.client.post("/twin/create", headers=auth_headers, json=payload)
    assert r2.status_code == 201
    assert r2.json()["data"]["twin"]["id"] == twin_id

    with bundle.db.session() as session:
        assert len(TwinRepository(session).list_twins()) == 1

    # Same key with different payload -> 409 IDEMPOTENCY_CONFLICT
    mutated = {**payload, "external_reference": "SYN-IDEM-OTHER"}
    r3 = bundle.client.post("/twin/create", headers=auth_headers, json=mutated)
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_update_idempotency_and_optimistic_concurrency(bundle: TestBundle, auth_headers: dict[str, str]) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    c_resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "occ-create-1"},
        json={
            "external_reference": "SYN-OCC-001",
            "observed_at": (now - timedelta(days=14)).isoformat(),
            "features": make_speech_features(0.2),
        },
    )
    assert c_resp.status_code == 201
    twin_id = c_resp.json()["data"]["twin"]["id"]
    assert c_resp.json()["data"]["twin"]["version"] == 1

    update_payload = {
        "twin_id": twin_id,
        "observed_at": (now - timedelta(days=7)).isoformat(),
        "features": make_speech_features(0.6),
        "idempotency_key": "occ-update-1",
        "expected_version": 1,
    }
    u1 = bundle.client.post("/twin/update", headers=auth_headers, json=update_payload)
    assert u1.status_code == 200
    assert u1.json()["data"]["twin"]["version"] == 2

    # Safe replay with same idempotency key returns original observation without creating a duplicate
    u1_replay = bundle.client.post("/twin/update", headers=auth_headers, json=update_payload)
    assert u1_replay.status_code == 200
    assert u1_replay.json()["data"]["observation_id"] == u1.json()["data"]["observation_id"]

    # Same key with different payload -> 409 IDEMPOTENCY_CONFLICT
    u1_conflict = bundle.client.post(
        "/twin/update",
        headers=auth_headers,
        json={**update_payload, "features": make_speech_features(1.5)},
    )
    assert u1_conflict.status_code == 409
    assert u1_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # Stale expected_version -> 409 CONCURRENCY_CONFLICT and no observation written
    stale = bundle.client.post(
        "/twin/update",
        headers=auth_headers,
        json={
            "twin_id": twin_id,
            "observed_at": (now - timedelta(days=2)).isoformat(),
            "features": make_speech_features(0.9),
            "idempotency_key": "occ-update-stale",
            "expected_version": 1,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONCURRENCY_CONFLICT"

    with bundle.db.session() as session:
        repo = TwinRepository(session)
        assert repo.count_observations(twin_id) == 2

        # Direct repository-level optimistic concurrency check
        with pytest.raises(ConcurrencyConflictError):
            repo.update_twin_latest_state(
                twin_id=twin_id,
                expected_version=1,
                latest_state_id=None,
                status="active",
                data_quality_summary={},
            )
