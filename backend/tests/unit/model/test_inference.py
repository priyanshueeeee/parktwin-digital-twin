import unittest

from ml.data.schema import FEATURE_SPECS
from ml.inference.demo import DemoInferenceAdapter, InferenceInput


class DemoInferenceTests(unittest.TestCase):
    def test_inference_mode_returns_traceable_non_clinical_result(self) -> None:
        features = {spec.source_name: 0.1 for spec in FEATURE_SPECS}
        result = DemoInferenceAdapter().predict(
            InferenceInput(
                datapoint_id="dp-1",
                features=features,
                source="synthetic_fixture",
                quality_flags=("SYNTHETIC_INPUT",),
            )
        )

        self.assertEqual(result.datapoint_id, "dp-1")
        self.assertEqual(result.mode, "inference_demo")
        self.assertEqual(result.model_version, "demo-heuristic-v1")
        self.assertGreaterEqual(result.estimated_total_updrs, 0)
        self.assertLessEqual(result.estimated_total_updrs, 199)
        self.assertIn("DEMO_HEURISTIC_MODEL", result.warnings)
        self.assertIn("SYNTHETIC_INPUT", result.warnings)
        self.assertEqual(len(result.input_features), 16)
        self.assertIn("jitter_family_mean", result.derived_features)


if __name__ == "__main__":
    unittest.main()
