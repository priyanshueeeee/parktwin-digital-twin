import unittest

from ml.models.approaches import APPROACHES, get_approach


class ModelApproachTests(unittest.TestCase):
    def test_registry_contains_baseline_challenger_uncertainty_and_demo_paths(self) -> None:
        names = {approach.name for approach in APPROACHES}

        self.assertIn("elastic_net", names)
        self.assertIn("random_forest", names)
        self.assertIn("quantile_regression", names)
        self.assertIn("patient_calibrated_residual", names)
        self.assertIn("demo_heuristic", names)

    def test_unknown_approach_fails_with_available_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "available"):
            get_approach("not-a-real-approach")


if __name__ == "__main__":
    unittest.main()
