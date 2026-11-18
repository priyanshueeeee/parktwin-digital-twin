import unittest

from ml.data.schema import FEATURE_SPECS
from ml.inference.demo import DemoInferenceAdapter, InferenceInput
from ml.inference.trained import TrainedModelInferenceAdapter
from ml.models.training import TrainingConfig, train_models

from .test_training import synthetic_frame


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

    def test_trained_artifact_inference_returns_target_and_metadata(self) -> None:
        run = train_models(
            synthetic_frame(),
            config=TrainingConfig(split_strategy="future"),
            approaches=("elastic_net",),
        )
        artifact = run.artifacts["elastic_net"]
        input_features = {spec.source_name: 0.1 for spec in FEATURE_SPECS}

        result = TrainedModelInferenceAdapter(artifact).predict(
            InferenceInput(
                datapoint_id="dp-trained-1",
                features=input_features,
                source="synthetic_fixture",
            )
        )

        self.assertEqual(result.mode, "artifact_inference")
        self.assertEqual(result.model_version, "parktwin-segment-a-v1")
        self.assertIsNotNone(result.estimated_total_updrs)
        self.assertIsNone(result.estimated_motor_updrs)
        self.assertIn("POINT_ESTIMATE_ONLY", result.warnings)


if __name__ == "__main__":
    unittest.main()
