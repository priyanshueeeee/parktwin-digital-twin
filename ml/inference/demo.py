"""Deterministic inference-mode adapter for local demos and integration tests."""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

from ml.data.schema import FEATURE_NAMES
from ml.features.engineering import build_feature_vector


def _clamp(value: float, lower: float = 0.0, upper: float = 199.0) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class InferenceInput:
    datapoint_id: str
    features: Mapping[str, Any]
    source: str
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True)
class InferenceResult:
    datapoint_id: str
    estimated_total_updrs: float | None
    estimated_motor_updrs: float | None
    model_version: str
    feature_set_version: str
    mode: str
    source: str
    input_features: Mapping[str, float]
    derived_features: Mapping[str, float]
    warnings: tuple[str, ...]
    prediction_interval: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_features", MappingProxyType(dict(self.input_features)))
        object.__setattr__(self, "derived_features", MappingProxyType(dict(self.derived_features)))


class DemoInferenceAdapter:
    """A transparent, non-clinical adapter for showing the inference path.

    This is intentionally not a trained model. A trained artifact adapter will
    replace it after model evaluation and promotion.
    """

    model_version = "demo-heuristic-v1"

    def predict(self, input_data: InferenceInput) -> InferenceResult:
        vector = build_feature_vector(input_data.features)
        raw = vector.features

        jitter_signal = min(1.0, raw["jitter_family_mean"] * 15.0)
        shimmer_signal = min(1.0, raw["shimmer_family_mean"] * 8.0)
        noise_signal = min(1.0, raw["nhr"] * 8.0)
        nonlinear_signal = min(1.0, raw["nonlinear_complexity_mean"])
        burden = (
            0.35 * jitter_signal
            + 0.35 * shimmer_signal
            + 0.15 * noise_signal
            + 0.15 * nonlinear_signal
        )

        total = _clamp(18.0 + 85.0 * burden + 8.0 * min(1.0, raw["ppe"]))
        motor = _clamp(12.0 + 70.0 * burden + 6.0 * min(1.0, raw["dfa"]))
        if not math.isfinite(total) or not math.isfinite(motor):
            raise RuntimeError("demo inference produced a non-finite estimate")

        warnings = tuple(
            dict.fromkeys(
                (
                    *input_data.quality_flags,
                    *vector.quality_flags,
                    "DEMO_HEURISTIC_MODEL",
                    "NON_CLINICAL_ESTIMATE",
                )
            )
        )
        derived = {name: value for name, value in vector.features.items() if name not in FEATURE_NAMES}
        input_features = {name: vector.features[name] for name in FEATURE_NAMES}
        return InferenceResult(
            datapoint_id=input_data.datapoint_id,
            estimated_total_updrs=total,
            estimated_motor_updrs=motor,
            model_version=self.model_version,
            feature_set_version=vector.feature_set_version,
            mode="inference_demo",
            source=input_data.source,
            input_features=input_features,
            derived_features=derived,
            warnings=warnings,
        )
