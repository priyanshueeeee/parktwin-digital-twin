"""Explicit registry of candidate modeling approaches.

The registry keeps alternative approaches visible and comparable. It does not
claim that any approach is clinically validated or production-ready.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelApproach:
    name: str
    family: str
    intended_use: str
    requires_scaling: bool
    uncertainty_strategy: str
    personalization_strategy: str


APPROACHES: tuple[ModelApproach, ...] = (
    ModelApproach(
        name="elastic_net",
        family="regularized_linear",
        intended_use="interpretable population baseline",
        requires_scaling=True,
        uncertainty_strategy="residual bootstrap or prediction interval",
        personalization_strategy="bounded residual offset after sufficient history",
    ),
    ModelApproach(
        name="random_forest",
        family="bagged_tree",
        intended_use="nonlinear challenger with feature importance",
        requires_scaling=False,
        uncertainty_strategy="ensemble spread or conformal calibration",
        personalization_strategy="calibrated residual only; no direct retraining by default",
    ),
    ModelApproach(
        name="hist_gradient_boosting",
        family="boosted_tree",
        intended_use="strong nonlinear challenger for tabular features",
        requires_scaling=False,
        uncertainty_strategy="quantile models or conformal calibration",
        personalization_strategy="bounded residual offset after sufficient history",
    ),
    ModelApproach(
        name="quantile_regression",
        family="distributional_linear",
        intended_use="prediction intervals and uncertainty reporting",
        requires_scaling=True,
        uncertainty_strategy="direct lower, median, and upper quantiles",
        personalization_strategy="calibrated interval shift only",
    ),
    ModelApproach(
        name="patient_calibrated_residual",
        family="personalization_layer",
        intended_use="patient-specific adjustment on top of a frozen population model",
        requires_scaling=False,
        uncertainty_strategy="inherit population interval plus calibration error",
        personalization_strategy="bounded intercept or slope correction with held-out future data",
    ),
    ModelApproach(
        name="demo_heuristic",
        family="deterministic_demo",
        intended_use="local inference-mode demonstration without a trained artifact",
        requires_scaling=False,
        uncertainty_strategy="not supported; return an explicit demo warning",
        personalization_strategy="not supported",
    ),
)


def get_approach(name: str) -> ModelApproach:
    """Return a registered approach or fail clearly."""

    for approach in APPROACHES:
        if approach.name == name:
            return approach
    available = ", ".join(approach.name for approach in APPROACHES)
    raise ValueError(f"unknown model approach {name!r}; available: {available}")
