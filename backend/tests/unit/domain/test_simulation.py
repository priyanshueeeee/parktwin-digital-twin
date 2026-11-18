import unittest

from backend.app.services.simulation import (
    SimulationRequest,
    sensitivity_analysis,
    simulate_scenario,
)


class SimulationTests(unittest.TestCase):
    def test_simulation_is_hypothetical_and_preserves_baseline_series(self) -> None:
        request = SimulationRequest(
            initial_total_updrs=40.0,
            initial_motor_updrs=30.0,
            baseline_slope_per_day=0.05,
            horizon_days=30,
            step_days=10,
            levodopa_intensity=0.5,
            physical_therapy_intensity=0.5,
        )

        result = simulate_scenario(request)

        self.assertTrue(result.is_hypothetical)
        self.assertIn("NOT_A_TREATMENT_RECOMMENDATION", result.warnings)
        self.assertEqual(result.points[0].baseline_total_updrs, 40.0)
        self.assertLess(result.points[-1].simulated_total_updrs, result.points[-1].baseline_total_updrs)
        self.assertEqual(result.points[-1].baseline_motor_updrs, 31.2)

    def test_invalid_intervention_intensity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "levodopa_intensity"):
            simulate_scenario(SimulationRequest(initial_total_updrs=20, baseline_slope_per_day=0.1, levodopa_intensity=1.1))

    def test_sensitivity_analysis_returns_one_point_per_level(self) -> None:
        request = SimulationRequest(initial_total_updrs=40, baseline_slope_per_day=0.05, horizon_days=30, step_days=10)

        points = sensitivity_analysis(
            request,
            parameter="levodopa_intensity",
            levels=(0.0, 0.5, 1.0),
        )

        self.assertEqual(len(points), 3)
        self.assertEqual(points[0].level, 0.0)
        self.assertLessEqual(points[-1].final_simulated_total_updrs, points[0].final_simulated_total_updrs)


if __name__ == "__main__":
    unittest.main()
