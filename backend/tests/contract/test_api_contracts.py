"""API contract tests covering schemas, validation, partial baselines, fail-closed model, trajectory filters, and simulation isolation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.fixtures import make_partial_speech_features, make_speech_features
from app.persistence.repository import TwinRepository
from tests.conftest import TestBundle


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def test_health_readiness_metrics_and_openapi(bundle: TestBundle) -> None:
    health = bundle.client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["schema_version"] == "v1"
    assert body["request_id"] == health.headers["X-Request-ID"]
    assert "non-diagnostic" in body["data"]["disclaimer"].lower()

    ready = bundle.client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["data"]["status"] == "ready"

    bundle.engine.set_available(False)
    not_ready = bundle.client.get("/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["data"]["checks"]["inference_adapter"] == "unavailable"
    bundle.engine.set_available(True)

    openapi = bundle.client.get("/openapi.json")
    assert openapi.status_code == 200
    spec = openapi.json()
    assert "non-diagnostic" in spec["info"]["description"].lower()
    for path in ["/twin/create", "/twin/update", "/twin/{twin_id}/trajectory", "/twin/{twin_id}/simulate"]:
        assert path in spec["paths"]

    metrics = bundle.client.get("/metrics")
    assert metrics.status_code == 200
    assert "requests_by_endpoint_status" in metrics.json()["data"]


def test_create_twin_complete_and_partial_baselines(bundle: TestBundle, auth_headers: dict[str, str]) -> None:
    now = _now_utc()

    # Complete baseline
    resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "create-complete-001"},
        json={
            "external_reference": "SYN-UNIT-001",
            "observed_at": (now - timedelta(days=7)).isoformat(),
            "features": make_speech_features(0.4),
            "observed_total_updrs": 31.0,
            "observed_motor_updrs": 23.0,
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["twin"]["status"] == "active"
    assert data["current_estimate"]["estimated_total_updrs"] is not None
    assert data["current_estimate"]["model_version"] == "mock-updrs-v0.1.0"
    assert data["current_estimate"]["feature_version"] == "speech16-v1"
    # Single observation cannot produce a placeholder zero slope
    assert data["slope"]["status"] == "insufficient_data"
    assert data["slope"]["total_updrs_per_30_days"] is None

    # Partial baseline without allow_partial=True must fail validation
    bad_partial = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "create-partial-fail"},
        json={
            "external_reference": "SYN-UNIT-002",
            "observed_at": (now - timedelta(days=5)).isoformat(),
            "features": make_partial_speech_features(),
            "allow_partial": False,
        },
    )
    assert bad_partial.status_code == 400
    assert bad_partial.json()["error"]["code"] == "VALIDATION_ERROR"

    # Explicit partial baseline succeeds with insufficient_data and NO fabricated UPDRS
    ok_partial = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "create-partial-ok"},
        json={
            "external_reference": "SYN-UNIT-002",
            "observed_at": (now - timedelta(days=5)).isoformat(),
            "features": make_partial_speech_features(),
            "allow_partial": True,
        },
    )
    assert ok_partial.status_code == 201
    p_data = ok_partial.json()["data"]
    assert p_data["twin"]["status"] == "insufficient_data"
    assert p_data["current_estimate"]["estimated_total_updrs"] is None
    assert p_data["current_estimate"]["estimated_motor_updrs"] is None


def test_validation_rejects_pii_out_of_range_unknown_fields_and_future_timestamps(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    now = _now_utc()
    base_features = make_speech_features(0.1)

    # Personal name with space rejected
    r_name = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "val-name-001"},
        json={
            "external_reference": "Jane Doe",
            "observed_at": now.isoformat(),
            "features": base_features,
        },
    )
    assert r_name.status_code == 400
    assert r_name.json()["error"]["code"] == "VALIDATION_ERROR"

    # Negative jitter rejected
    neg_features = {**base_features, "jitter_percent": -0.01}
    r_neg = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "val-neg-001"},
        json={
            "external_reference": "SYN-VAL-001",
            "observed_at": now.isoformat(),
            "features": neg_features,
        },
    )
    assert r_neg.status_code == 400
    assert r_neg.json()["error"]["code"] == "VALIDATION_ERROR"
    assert any("jitter_percent" in f["name"] for f in r_neg.json()["error"]["fields"])

    # Unknown extra feature field rejected (never silently dropped)
    extra_features = {**base_features, "raw_audio_blob": 123}
    r_extra = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "val-extra-001"},
        json={
            "external_reference": "SYN-VAL-002",
            "observed_at": now.isoformat(),
            "features": extra_features,
        },
    )
    assert r_extra.status_code == 400

    # Future timestamp rejected
    r_future = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "val-future-001"},
        json={
            "external_reference": "SYN-VAL-003",
            "observed_at": (now + timedelta(days=2)).isoformat(),
            "features": base_features,
        },
    )
    assert r_future.status_code == 400

    # Motor UPDRS > Total UPDRS rejected
    r_updrs = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "val-updrs-001"},
        json={
            "external_reference": "SYN-VAL-004",
            "observed_at": now.isoformat(),
            "features": base_features,
            "observed_total_updrs": 20.0,
            "observed_motor_updrs": 25.0,
        },
    )
    assert r_updrs.status_code == 400


def test_model_unavailable_fails_closed_without_partial_commit(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    bundle.engine.set_available(False)
    resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "fail-closed-001"},
        json={
            "external_reference": "SYN-FAIL-001",
            "observed_at": _now_utc().isoformat(),
            "features": make_speech_features(0.2),
        },
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MODEL_UNAVAILABLE"

    with bundle.db.session() as session:
        repo = TwinRepository(session)
        assert repo.list_twins() == []


def test_out_of_order_and_duplicate_timestamp_update_policy(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    now = _now_utc()
    t1 = now - timedelta(days=10)
    t2 = now - timedelta(days=20)  # intentionally earlier than t1 (out-of-order)

    c_resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "ooo-create-001"},
        json={
            "external_reference": "SYN-OOO-001",
            "observed_at": t1.isoformat(),
            "features": make_speech_features(0.8),
        },
    )
    assert c_resp.status_code == 201
    twin_id = c_resp.json()["data"]["twin"]["id"]

    # Duplicate exact timestamp is rejected
    dup_ts = bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "ooo-dup-ts"},
        json={
            "twin_id": twin_id,
            "observed_at": t1.isoformat(),
            "features": make_speech_features(0.85),
        },
    )
    assert dup_ts.status_code == 409
    assert dup_ts.json()["error"]["code"] == "TIMESTAMP_CONFLICT"

    # Earlier timestamp is accepted with explicit warning and ordered chronologically
    ooo = bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "ooo-earlier-001"},
        json={
            "twin_id": twin_id,
            "observed_at": t2.isoformat(),
            "features": make_speech_features(0.2),
        },
    )
    assert ooo.status_code == 200
    assert any("OUT_OF_ORDER_OBSERVATION" in w for w in ooo.json()["warnings"])

    traj = bundle.client.get(f"/twin/{twin_id}/trajectory", headers=auth_headers)
    assert traj.status_code == 200
    est_pts = traj.json()["data"]["estimated_points"]
    assert len(est_pts) == 2
    assert est_pts[0]["timestamp"] < est_pts[1]["timestamp"]
    # Severity rose from 0.2 (earlier) to 0.8 (later) -> positive worsening slope
    assert traj.json()["data"]["slope"]["status"] == "computed"
    assert traj.json()["data"]["slope"]["total_updrs_per_30_days"] > 0


def test_trajectory_filters_and_simulation_contracts(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    now = _now_utc()
    c_resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "sim-create-001"},
        json={
            "external_reference": "SYN-SIM-001",
            "observed_at": (now - timedelta(days=30)).isoformat(),
            "features": make_speech_features(0.2),
            "observed_total_updrs": 29.0,
            "observed_motor_updrs": 21.5,
        },
    )
    twin_id = c_resp.json()["data"]["twin"]["id"]

    bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "sim-update-001"},
        json={
            "twin_id": twin_id,
            "observed_at": (now - timedelta(days=5)).isoformat(),
            "features": make_speech_features(1.0),
        },
    )

    # Series filtering
    obs_only = bundle.client.get(f"/twin/{twin_id}/trajectory?series=observed", headers=auth_headers)
    assert obs_only.status_code == 200
    assert len(obs_only.json()["data"]["observed_points"]) == 1
    assert obs_only.json()["data"]["estimated_points"] == []

    # Invalid time window
    bad_window = bundle.client.get(
        f"/twin/{twin_id}/trajectory",
        headers=auth_headers,
        params={
            "start_time": now.isoformat(),
            "end_time": (now - timedelta(days=10)).isoformat(),
        },
    )
    assert bad_window.status_code == 400

    # Simulation requires explicit hypothetical acknowledgment
    no_ack = bundle.client.post(
        f"/twin/{twin_id}/simulate",
        headers=auth_headers,
        json={
            "label": "Missing Ack",
            "interventions": {
                "levodopa_dose_change_mg": 100.0,
                "physical_therapy_sessions_per_week": 2,
                "adherence_ratio": 0.9,
            },
            "horizon_days": 60,
            "step_days": 15,
            "acknowledge_hypothetical": False,
        },
    )
    assert no_ack.status_code == 400

    # Valid simulation
    sim = bundle.client.post(
        f"/twin/{twin_id}/simulate",
        headers=auth_headers,
        json={
            "label": "Levodopa + PT",
            "interventions": {
                "levodopa_dose_change_mg": 150.0,
                "physical_therapy_sessions_per_week": 3,
                "adherence_ratio": 0.95,
            },
            "horizon_days": 60,
            "step_days": 15,
            "acknowledge_hypothetical": True,
        },
    )
    assert sim.status_code == 201
    sim_data = sim.json()["data"]
    assert sim_data["hypothetical"] is True
    assert sim_data["assumptions_version"] == "sim-assumptions-mock-v1"
    scenario_id = sim_data["scenario_id"]

    # Default trajectory omits simulation; explicit scenario_id attaches it
    default_traj = bundle.client.get(f"/twin/{twin_id}/trajectory", headers=auth_headers)
    assert default_traj.json()["data"]["scenario"] is None

    with_scenario = bundle.client.get(
        f"/twin/{twin_id}/trajectory",
        headers=auth_headers,
        params={"scenario_id": scenario_id},
    )
    assert with_scenario.status_code == 200
    assert with_scenario.json()["data"]["scenario"]["id"] == scenario_id
    assert with_scenario.json()["data"]["scenario"]["hypothetical"] is True
