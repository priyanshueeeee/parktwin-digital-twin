"""Bounded patient-specific calibration on top of a frozen model."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class CalibrationResult:
    enabled: bool
    method: str
    intercept_adjustment: float
    slope_adjustment_per_day: float
    points_used: int
    warnings: tuple[str, ...]


def fit_bounded_residual_calibration(
    times_days: Sequence[float],
    predicted: Sequence[float],
    observed: Sequence[float],
    *,
    min_points: int = 3,
    max_abs_intercept: float = 10.0,
    max_abs_slope_per_day: float = 0.10,
) -> CalibrationResult:
    """Fit a bounded residual line, refusing to personalize sparse history."""

    if not len(times_days) == len(predicted) == len(observed):
        raise ValueError("times_days, predicted, and observed must have the same length")
    if min_points < 2:
        raise ValueError("min_points must be at least 2")
    if len(times_days) < min_points:
        return CalibrationResult(
            enabled=False,
            method="bounded_residual_v1",
            intercept_adjustment=0.0,
            slope_adjustment_per_day=0.0,
            points_used=len(times_days),
            warnings=("INSUFFICIENT_PERSONALIZATION_HISTORY",),
        )
    if any(not math.isfinite(float(value)) for values in (times_days, predicted, observed) for value in values):
        raise ValueError("calibration inputs must be finite")

    residuals = [float(actual) - float(estimate) for actual, estimate in zip(observed, predicted)]
    mean_time = sum(float(value) for value in times_days) / len(times_days)
    mean_residual = sum(residuals) / len(residuals)
    denominator = sum((float(value) - mean_time) ** 2 for value in times_days)
    slope = 0.0 if denominator <= 0 else sum(
        (float(time) - mean_time) * (residual - mean_residual)
        for time, residual in zip(times_days, residuals)
    ) / denominator
    intercept = mean_residual - slope * mean_time
    intercept = max(-max_abs_intercept, min(max_abs_intercept, intercept))
    slope = max(-max_abs_slope_per_day, min(max_abs_slope_per_day, slope))
    return CalibrationResult(
        enabled=True,
        method="bounded_residual_v1",
        intercept_adjustment=intercept,
        slope_adjustment_per_day=slope,
        points_used=len(times_days),
        warnings=("PERSONALIZATION_BOUNDED",),
    )


def apply_calibration(
    predicted: Sequence[float],
    times_days: Sequence[float],
    calibration: CalibrationResult,
) -> tuple[float, ...]:
    if len(predicted) != len(times_days):
        raise ValueError("predicted and times_days must have the same length")
    if not calibration.enabled:
        return tuple(float(value) for value in predicted)
    return tuple(
        float(value) + calibration.intercept_adjustment + calibration.slope_adjustment_per_day * float(time)
        for value, time in zip(predicted, times_days)
    )
