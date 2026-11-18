"""Inference-mode contracts and demo adapter."""

from .demo import DemoInferenceAdapter, InferenceInput, InferenceResult
from .trained import TrainedModelInferenceAdapter

__all__ = [
    "DemoInferenceAdapter",
    "InferenceInput",
    "InferenceResult",
    "TrainedModelInferenceAdapter",
]
