"""End-to-end vertical-slice integration test (FLOW_SEQUENCES.md Section 9)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import time

from app.api.fixtures import make_speech_features
from tests.conftest import CLINICIAN_A_KEY, TestBundle


def test_full_vertical_slice_and_500ms_latency_target(
    bundle: TestBundle, auth_headers: dict[str, str]
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # 1. Seed synthetic twin baseline
    c_resp = bundle.client.post(
        "/twin/create",
        headers={**auth_headers, "Idempotency-Key": "slice-create-001"},
        json={
            "external_reference": "SYN-SLICE-001",
            "observed_at": (now - timedelta(days=35)).isoformat(),
            "features": make_speech_features(0.1),
            "observed_total_updrs": 29.0,
            "observed_motor_updrs": 21.5,
        },
    )
    assert c_resp.status_code == 201
    twin_id = c_resp.json()["data"]["twin"]["id"]
    assert c_resp.json()["data"]["model_metadata"]["model_version"] == "mock-updrs-v0.1.0"

    # 2. Submit weekly observations and measure recalculation latency against 500 ms target
    for idx, (days_ago, severity) in enumerate([(21, 0.55), (7, 1.05)], start=1):
        t0 = time.perf_counter()
        u_resp = bundle.client.post(
            "/twin/update",
            headers={**auth_headers, "Idempotency-Key": f"slice-update-{idx}"},
            json={
                "twin_id": twin_id,
                "observed_at": (now - timedelta(days=days_ago)).isoformat(),
                "features": make_speech_features(severity),
            },
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert u_resp.status_code == 200
        assert elapsed_ms < 500.0, f"Trajectory recalculation took {elapsed_ms:.2f} ms (limit 500 ms)"

    # 3. Retrieve baseline production trajectory
    t_read = time.perf_counter()
    before_resp = bundle.client.get(f"/twin/{twin_id}/trajectory", headers=auth_headers)
    read_ms = (time.perf_counter() - t_read) * 1000.0
    assert before_resp.status_code == 200
    assert read_ms < 500.0

    before_data = before_resp.json()["data"]
    assert before_data["scenario"] is None
    assert len(before_data["estimated_points"]) == 3
    assert before_data["slope"]["status"] == "computed"
    assert before_data["slope"]["total_updrs_per_30_days"] > 0

    # 4. Run isolated intervention simulation
    sim_resp = bundle.client.post(
        f"/twin/{twin_id}/simulate",
        headers=auth_headers,
        json={
            "label": "Vertical Slice Hypothetical Therapy",
            "interventions": {
                "levodopa_dose_change_mg": 200.0,
                "physical_therapy_sessions_per_week": 3,
                "adherence_ratio": 0.9,
            },
            "horizon_days": 90,
            "step_days": 15,
            "acknowledge_hypothetical": True,
        },
    )
    assert sim_resp.status_code == 201
    sim_data = sim_resp.json()["data"]
    assert sim_data["hypothetical"] is True
    assert sim_data["summary"]["delta_total_updrs"] < 0

    # 5. Confirm production trajectory is unchanged after simulation
    after_resp = bundle.client.get(f"/twin/{twin_id}/trajectory", headers=auth_headers)
    assert after_resp.status_code == 200
    assert after_resp.json()["data"] == before_data

    # 6. Confirm scenarios list exposes saved scenario without affecting twins list
    scenarios = bundle.client.get(f"/twin/{twin_id}/scenarios", headers=auth_headers)
    assert scenarios.status_code == 200
    assert len(scenarios.json()["data"]["scenarios"]) == 1


def test_demo_script_executes_cleanly(bundle: TestBundle) -> None:
    scripts_dir = Path(__file__).resolve().parents[3] / "infra" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import run_demo  # type: ignore

    summary = run_demo.run_demo_against_client(bundle.client, CLINICIAN_A_KEY)
    assert summary["production_history_unchanged"] is True
    assert summary["latency_ms"]["meets_500ms_target"] is True
