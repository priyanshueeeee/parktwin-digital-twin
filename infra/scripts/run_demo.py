"""End-to-end vertical-slice demonstration & 500 ms latency verification script.

Walks through FLOW_SEQUENCES.md Section 9:
  1. Health & readiness checks
  2. Create synthetic baseline twin
  3. Submit longitudinal voice update and measure recalculation latency
  4. Retrieve production trajectory and slope
  5. Run isolated hypothetical intervention simulation
  6. Re-retrieve production trajectory and assert observed/estimated history is unchanged

Can run either against an already-running API (`--base-url http://localhost:8000`)
or in-process against a clean ephemeral SQLite database (`--in-process`).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
import uuid

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.api.fixtures import make_speech_features  # noqa: E402


def run_demo_against_client(client: httpx.Client, api_key: str) -> dict[str, object]:
    headers = {"X-API-Key": api_key}
    run_tag = uuid.uuid4().hex[:8]
    ref = f"SYN-DEMO-{run_tag.upper()}"
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # 1. Health & readiness
    h_resp = client.get("/health")
    h_resp.raise_for_status()
    r_resp = client.get("/ready")
    r_resp.raise_for_status()

    # 2. Create synthetic baseline twin
    t_create = time.perf_counter()
    c_resp = client.post(
        "/twin/create",
        headers=headers,
        json={
            "external_reference": ref,
            "observed_at": (now - timedelta(days=28)).isoformat(),
            "features": make_speech_features(0.2),
            "observed_total_updrs": 30.0,
            "observed_motor_updrs": 22.5,
            "idempotency_key": f"demo-create-{run_tag}",
        },
    )
    c_resp.raise_for_status()
    create_ms = (time.perf_counter() - t_create) * 1000.0
    twin_id = c_resp.json()["data"]["twin"]["id"]

    # 3. Submit weekly voice updates & measure trajectory recalculation latency
    update_latencies_ms: list[float] = []
    for idx, (days_ago, sev) in enumerate([(14, 0.7), (2, 1.2)], start=1):
        t0 = time.perf_counter()
        u_resp = client.post(
            "/twin/update",
            headers=headers,
            json={
                "twin_id": twin_id,
                "observed_at": (now - timedelta(days=days_ago)).isoformat(),
                "features": make_speech_features(sev),
                "idempotency_key": f"demo-update-{run_tag}-{idx}",
            },
        )
        u_resp.raise_for_status()
        update_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    # 4. Retrieve baseline production trajectory
    t_traj = time.perf_counter()
    before_resp = client.get(f"/twin/{twin_id}/trajectory", headers=headers)
    before_resp.raise_for_status()
    traj_ms = (time.perf_counter() - t_traj) * 1000.0
    before_data = before_resp.json()["data"]
    assert before_data["scenario"] is None, "Production trajectory must not include simulation by default"
    assert before_data["slope"]["status"] == "computed"

    # 5. Run isolated hypothetical intervention simulation
    t_sim = time.perf_counter()
    sim_resp = client.post(
        f"/twin/{twin_id}/simulate",
        headers=headers,
        json={
            "label": "Synthetic Demo Levodopa + PT Scenario",
            "interventions": {
                "levodopa_dose_change_mg": 150.0,
                "physical_therapy_sessions_per_week": 3,
                "adherence_ratio": 0.9,
            },
            "horizon_days": 90,
            "step_days": 15,
            "acknowledge_hypothetical": True,
        },
    )
    sim_resp.raise_for_status()
    sim_ms = (time.perf_counter() - t_sim) * 1000.0
    sim_data = sim_resp.json()["data"]
    assert sim_data["hypothetical"] is True

    # 6. Verify production trajectory is unchanged after simulation
    after_resp = client.get(f"/twin/{twin_id}/trajectory", headers=headers)
    after_resp.raise_for_status()
    after_data = after_resp.json()["data"]
    assert after_data == before_data, "Simulation mutated production trajectory state!"

    max_recalc_ms = max(update_latencies_ms + [traj_ms])
    return {
        "external_reference": ref,
        "twin_id": twin_id,
        "model_version": before_data["model_metadata"]["model_version"],
        "slope_total_updrs_per_30_days": before_data["slope"]["total_updrs_per_30_days"],
        "simulation_scenario_id": sim_data["scenario_id"],
        "simulation_delta_total_updrs": sim_data["summary"]["delta_total_updrs"],
        "production_history_unchanged": True,
        "latency_ms": {
            "create": round(create_ms, 2),
            "updates": [round(x, 2) for x in update_latencies_ms],
            "trajectory_read": round(traj_ms, 2),
            "simulate": round(sim_ms, 2),
            "max_recalc_ms": round(max_recalc_ms, 2),
            "meets_500ms_target": max_recalc_ms < 500.0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ParkTwin vertical-slice demo & latency check.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-clinician-key")
    parser.add_argument("--in-process", action="store_true", help="Run against in-process FastAPI + SQLite")
    args = parser.parse_args()

    if args.in_process:
        from fastapi.testclient import TestClient
        from app.config import load_settings
        from app.main import create_app
        from app.persistence.database import Database

        db = Database("sqlite:///:memory:")
        app = create_app(settings=load_settings(), database=db, auto_create_tables=True)
        with TestClient(app) as client:
            result = run_demo_against_client(client, args.api_key)
    else:
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=15.0) as client:
            result = run_demo_against_client(client, args.api_key)

    print(json.dumps(result, indent=2))
    if not result["latency_ms"]["meets_500ms_target"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
