"""Inference adapter for promoted Segment A model artifacts."""

from __future__ import annotations

from ml.data.schema import FEATURE_NAMES, MOTOR_UPDRS_COLUMN, TOTAL_UPDRS_COLUMN
from ml.features.engineering import build_feature_vector
from ml.models.training import ModelArtifact

from .demo import InferenceInput, InferenceResult


class TrainedModelInferenceAdapter:
    """Run one datapoint through a serialized model artifact."""

    def __init__(self, artifact: ModelArtifact) -> None:
        self.artifact = artifact

    def predict(self, input_data: InferenceInput) -> InferenceResult:
        vector = build_feature_vector(input_data.features)
        predictions = self.artifact.predict_rows([input_data.features])
        interval = None
        if "median" in predictions:
            prediction = float(predictions["median"][0])
            interval = (float(predictions["lower"][0]), float(predictions["upper"][0]))
            model_warning = "PREDICTION_INTERVAL_AVAILABLE"
        else:
            prediction = float(predictions["point"][0])
            model_warning = "POINT_ESTIMATE_ONLY"

        estimated_total = prediction if self.artifact.metadata.target == TOTAL_UPDRS_COLUMN else None
        estimated_motor = prediction if self.artifact.metadata.target == MOTOR_UPDRS_COLUMN else None
        raw_features = {name: vector.features[name] for name in FEATURE_NAMES}
        derived_features = {
            name: value for name, value in vector.features.items() if name not in FEATURE_NAMES
        }
        return InferenceResult(
            datapoint_id=input_data.datapoint_id,
            estimated_total_updrs=estimated_total,
            estimated_motor_updrs=estimated_motor,
            model_version=self.artifact.metadata.model_version,
            feature_set_version=self.artifact.metadata.feature_set_version,
            mode="artifact_inference",
            source=input_data.source,
            input_features=raw_features,
            derived_features=derived_features,
            warnings=tuple(
                dict.fromkeys(
                    (
                        *input_data.quality_flags,
                        *vector.quality_flags,
                        model_warning,
                        "NON_DIAGNOSTIC_MODEL_OUTPUT",
                    )
                )
            ),
            prediction_interval=interval,
        )
