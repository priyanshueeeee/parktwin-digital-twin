import unittest
from datetime import datetime, timezone

from backend.app.domain.contracts import Observation, SimulationScenario, Twin


class DomainContractTests(unittest.TestCase):
    def test_observation_features_are_immutable(self) -> None:
        source = {"jitter_percent": 0.1}
        observation = Observation(
            id="obs-1",
            twin_id="twin-1",
            observed_at=datetime.now(timezone.utc),
            features=source,
        )

        source["jitter_percent"] = 0.9

        self.assertEqual(observation.features["jitter_percent"], 0.1)

    def test_twin_and_scenario_capture_versioned_state(self) -> None:
        now = datetime.now(timezone.utc)
        twin = Twin(
            id="twin-1",
            external_reference="demo-1",
            created_at=now,
            updated_at=now,
            status="active",
            data_quality_summary={"valid_observations": 1},
        )
        scenario = SimulationScenario(
            id="scenario-1",
            twin_id=twin.id,
            intervention_parameters={"levodopa_factor": 0.2},
            forecast_horizon_days=30,
            step_days=7,
            assumptions_version="simulation-v1",
            baseline_trajectory_reference="trajectory-1",
        )

        self.assertEqual(twin.schema_version, "v1")
        self.assertEqual(scenario.assumptions_version, "simulation-v1")
