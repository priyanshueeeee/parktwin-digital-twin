from datetime import datetime, timedelta, timezone
import unittest

from backend.app.domain.contracts import Observation, StateEstimate
from backend.app.services.trajectory import calculate_trajectory


class TrajectoryTests(unittest.TestCase):
    def test_trajectory_calculates_slope_and_keeps_observed_and_estimated_values(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        observations = [
            Observation(
                id=f"obs-{index}",
                twin_id="twin-1",
                observed_at=start + timedelta(days=index * 10),
                features={"jitter_percent": 0.1},
                observed_total_updrs=20.0 + index,
                observed_motor_updrs=10.0 + index,
            )
            for index in range(3)
        ]
        estimates = [
            StateEstimate(
                id=f"estimate-{index}",
                twin_id="twin-1",
                observation_id=f"obs-{index}",
                estimated_total_updrs=20.2 + index,
                estimated_motor_updrs=10.2 + index,
                model_version="model-v1",
                feature_version="feature-v1",
            )
            for index in range(3)
        ]

        result = calculate_trajectory(observations, estimates, window_days=30)

        self.assertEqual(result.status, "ready")
        self.assertAlmostEqual(result.total_slope_per_day or 0, 0.1)
        self.assertAlmostEqual(result.motor_slope_per_day or 0, 0.1)
        self.assertEqual(result.points[0].source_type, "observed_and_estimated")

    def test_insufficient_history_is_explicit(self) -> None:
        observation = Observation(
            id="obs-1",
            twin_id="twin-1",
            observed_at=datetime.now(timezone.utc),
            features={"jitter_percent": 0.1},
            observed_total_updrs=20.0,
        )

        result = calculate_trajectory([observation], [], min_points=2)

        self.assertEqual(result.status, "insufficient_data")
        self.assertIn("INSUFFICIENT_TOTAL_HISTORY", result.warnings)


if __name__ == "__main__":
    unittest.main()
