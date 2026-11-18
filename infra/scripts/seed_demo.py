"""Idempotent synthetic demo seed script for ParkTwin.

Creates 3 pseudonymous synthetic digital twins (worsening, stable, and partial baseline)
using only synthetic fixtures — zero real patient data or personal identifiers.

Usage:
    python infra/scripts/seed_demo.py --base-url http://localhost:8000 --api-key dev-clinician-key
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.api.fixtures import (  # noqa: E402
    make_partial_speech_features,
    make_speech_features,
    synthetic_demo_cohorts,
    timestamp_offset,
)


def seed_via_api(base_url: str, api_key: str) -> list[dict[str, str]]:
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    anchor = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    seeded: list[dict[str, str]] = []

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=15.0) as client:
        ready = client.get("/ready")
        ready.raise_for_status()

        for cohort in synthetic_demo_cohorts(now=anchor):
            ref = cohort["external_reference"]
            obs_list = cohort["observations"]
            first = obs_list[0]
            first_features = (
                make_partial_speech_features()
                if cohort["allow_partial"]
                else make_speech_features(first["severity"])
            )
            create_payload = {
                "external_reference": ref,
                "observed_at": timestamp_offset(anchor, first["offset_days"]).isoformat(),
                "features": first_features,
                "allow_partial": cohort["allow_partial"],
                "observed_total_updrs": first["observed_total_updrs"],
                "observed_motor_updrs": first["observed_motor_updrs"],
                "source": "synthetic_seed",
                "idempotency_key": f"seed-create-{ref}",
            }
            resp = client.post("/twin/create", json=create_payload, headers=headers)
            resp.raise_for_status()
            twin_id = resp.json()["data"]["twin"]["id"]

            for idx, obs in enumerate(obs_list[1:], start=1):
                update_payload = {
                    "twin_id": twin_id,
                    "observed_at": timestamp_offset(anchor, obs["offset_days"]).isoformat(),
                    "features": make_speech_features(obs["severity"]),
                    "observed_total_updrs": obs["observed_total_updrs"],
                    "observed_motor_updrs": obs["observed_motor_updrs"],
                    "source": "synthetic_seed",
                    "idempotency_key": f"seed-update-{ref}-{idx}",
                }
                u_resp = client.post("/twin/update", json=update_payload, headers=headers)
                u_resp.raise_for_status()

            seeded.append({"external_reference": ref, "twin_id": twin_id, "description": cohort["description"]})

    return seeded


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic ParkTwin demo data via REST API.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="ParkTwin API base URL")
    parser.add_argument("--api-key", default="dev-clinician-key", help="API key with clinician/admin role")
    args = parser.parse_args()

    seeded = seed_via_api(args.base_url, args.api_key)
    print("Seeded synthetic ParkTwin demo cohorts:")
    for item in seeded:
        print(f"  - {item['external_reference']} (id={item['twin_id']}): {item['description']}")


if __name__ == "__main__":
    main()
