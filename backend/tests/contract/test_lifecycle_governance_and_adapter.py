"""Contract tests for twin lifecycle, recompute, observations, audit trail, export, security headers, and real-adapter wiring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api.engine_adapter import (
    MockTwinEngineAdapter,
    ModelUnavailableError,
    build_engine_adapter,
)
from app.api.fixtures import make_speech_features
from tests.conftest import TestBundle


def _seed_two_point_twin(bundle: TestBundle, auth_headers: dict[str, str]) -> tuple[str, int]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    c = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "gov-create-1"},
        json={
            "external_reference": "SYN-GOV-001",
            "observed_at": (now - timedelta(days=20)).isoformat(),
            "features": make_speech_features(0.2),
            "observed_total_updrs": 29.5,
            "observed_motor_updrs": 22.0,
        },
    )
    assert c.status_code == 201
    twin_id = c.json()["data"]["twin"]["id"]

    u = bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "gov-update-1"},
        json={
            "twin_id": twin_id,
            "observed_at": (now - timedelta(days=5)).isoformat(),
            "features": make_speech_features(1.0),
            "observed_total_updrs": 35.0,
            "observed_motor_updrs": 26.0,
        },
    )
    assert u.status_code == 200
    return twin_id, u.json()["data"]["twin"]["version"]


def test_security_headers_server_timing_and_calibration_summary(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    twin_id, _ = _seed_two_point_twin(bundle, auth_headers)
    resp = bundle.client.get(f"/twin/{twin_id}/trajectory", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Cache-Control"] == "no-store"
    assert "trajectory;dur=" in resp.headers["Server-Timing"]
    assert float(resp.headers["X-Process-Time-Ms"]) >= 0.0

    cal = resp.json()["data"]["calibration_summary"]
    assert cal["paired_total_count"] == 2
    assert cal["paired_motor_count"] == 2
    assert cal["total_updrs_mae"] is not None
    assert cal["motor_updrs_mae"] is not None


def test_lifecycle_pause_archive_resume_guards(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    twin_id, version = _seed_two_point_twin(bundle, auth_headers)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # Stale expected_version rejected
    stale = bundle.client.patch(
        f"/twin/{twin_id}/status",
        headers=auth_headers,
        json={"status": "paused", "reason": "Clinician review hold", "expected_version": 99},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONCURRENCY_CONFLICT"

    # Pause twin -> updates blocked with 409 TWIN_PAUSED
    paused = bundle.client.patch(
        f"/twin/{twin_id}/status",
        headers=auth_headers,
        json={"status": "paused", "reason": "Temporary hold", "expected_version": version},
    )
    assert paused.status_code == 200
    v_paused = paused.json()["data"]["twin"]["version"]
    assert paused.json()["data"]["twin"]["status"] == "paused"

    blocked_pause = bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "gov-blocked-pause"},
        json={
            "twin_id": twin_id,
            "observed_at": (now - timedelta(days=2)).isoformat(),
            "features": make_speech_features(1.1),
        },
    )
    assert blocked_pause.status_code == 409
    assert blocked_pause.json()["error"]["code"] == "TWIN_PAUSED"

    # Archive twin -> updates blocked with 409 TWIN_ARCHIVED
    archived = bundle.client.patch(
        f"/twin/{twin_id}/status",
        headers=auth_headers,
        json={"status": "archived", "reason": "Cohort study closed", "expected_version": v_paused},
    )
    assert archived.status_code == 200
    v_archived = archived.json()["data"]["twin"]["version"]

    blocked_arch = bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "gov-blocked-arch"},
        json={
            "twin_id": twin_id,
            "observed_at": (now - timedelta(days=2)).isoformat(),
            "features": make_speech_features(1.1),
        },
    )
    assert blocked_arch.status_code == 409
    assert blocked_arch.json()["error"]["code"] == "TWIN_ARCHIVED"

    # Resume twin -> updates allowed again
    resumed = bundle.client.patch(
        f"/twin/{twin_id}/status",
        headers=auth_headers,
        json={"status": "active", "reason": "Resume tracking", "expected_version": v_archived},
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["twin"]["status"] == "active"

    ok_update = bundle.client.post(
        "/twin/update",
        headers={**auth_headers, "Idempotency-Key": "gov-after-resume"},
        json={
            "twin_id": twin_id,
            "observed_at": (now - timedelta(days=1)).isoformat(),
            "features": make_speech_features(1.2),
        },
    )
    assert ok_update.status_code == 200


def test_observations_biomarkers_recompute_audit_and_export(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    twin_id, _ = _seed_two_point_twin(bundle, auth_headers)

    # Observations & biomarker deltas
    obs_resp = bundle.client.get(f"/twin/{twin_id}/observations", headers=auth_headers)
    assert obs_resp.status_code == 200
    obs_data = obs_resp.json()["data"]
    assert obs_data["count"] == 2
    delta_map = {d["feature"]: d for d in obs_data["biomarker_deltas"]}
    assert delta_map["jitter_percent"]["delta"] > 0
    assert delta_map["hnr"]["delta"] < 0

    # Recompute derived state from immutable observations
    recomp = bundle.client.post(
        f"/twin/{twin_id}/recompute",
        headers=auth_headers,
        json={"re_run_inference": True, "reason": "Model artifact upgrade check"},
    )
    assert recomp.status_code == 200
    assert recomp.json()["data"]["reestimated_observations"] == 2

    # Run a simulation to verify export exclusion/inclusion & audit trail
    sim = bundle.client.post(
        f"/twin/{twin_id}/simulate",
        headers=auth_headers,
        json={
            "label": "Export Check Scenario",
            "interventions": {
                "levodopa_dose_change_mg": 100.0,
                "physical_therapy_sessions_per_week": 2,
                "adherence_ratio": 0.9,
            },
            "horizon_days": 30,
            "step_days": 15,
            "acknowledge_hypothetical": True,
        },
    )
    assert sim.status_code == 201
    scenario_id = sim.json()["data"]["scenario_id"]

    # JSON export excludes hypothetical by default
    exp_json = bundle.client.get(f"/twin/{twin_id}/export?format=json", headers=auth_headers)
    assert exp_json.status_code == 200
    assert exp_json.json()["data"]["hypothetical_scenario_points"] == []
    assert "non-diagnostic" in exp_json.json()["data"]["disclaimer"].lower()

    # CSV export includes disclaimer header & scenario rows when explicitly requested
    exp_csv = bundle.client.get(
        f"/twin/{twin_id}/export",
        headers=auth_headers,
        params={"format": "csv", "scenario_id": scenario_id},
    )
    assert exp_csv.status_code == 200
    assert "text/csv" in exp_csv.headers["content-type"]
    assert "Research prototype only" in exp_csv.text
    assert scenario_id in exp_csv.text

    # Audit trail records actions without raw speech feature values
    audit = bundle.client.get(f"/twin/{twin_id}/audit", headers=auth_headers)
    assert audit.status_code == 200
    actions = {ev["action"] for ev in audit.json()["data"]["events"]}
    assert {"twin.create", "twin.update", "twin.recompute", "twin.simulate", "twin.export"}.issubset(actions)
    assert "jitter_percent" not in audit.text


def test_real_adapter_dynamic_loader_fails_closed_and_loads_valid_port() -> None:
    # Missing module fails closed with ModelUnavailableError
    with pytest.raises(ModelUnavailableError):
        build_engine_adapter("real", real_adapter_path="nonexistent.module:factory")

    # Malformed path fails closed
    with pytest.raises(ModelUnavailableError):
        build_engine_adapter("real", real_adapter_path="missing_colon_symbol")

    # Valid symbol implementing TwinEnginePort loads cleanly
    loaded = build_engine_adapter(
        "real",
        real_adapter_path="app.api.engine_adapter:MockTwinEngineAdapter",
    )
    assert isinstance(loaded, MockTwinEngineAdapter)
    assert loaded.is_available() is True
