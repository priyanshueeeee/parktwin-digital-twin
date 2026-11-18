"""Longitudinal trajectory and progression-slope calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from backend.app.domain.contracts import Observation, StateEstimate, TrajectoryPoint


@dataclass(frozen=True)
class TrajectoryResult:
    points: tuple[TrajectoryPoint, ...]
    total_slope_per_day: float | None
    motor_slope_per_day: float | None
    window_days: int
    status: str
    data_quality: Mapping[str, Any]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_quality", MappingProxyType(dict(self.data_quality)))


def _slope(times: Sequence[float], values: Sequence[float]) -> float | None:
    if len(times) < 2 or len(values) != len(times):
        return None
    mean_time = sum(times) / len(times)
    mean_value = sum(values) / len(values)
    denominator = sum((time - mean_time) ** 2 for time in times)
    if denominator <= 0:
        return None
    return sum((time - mean_time) * (value - mean_value) for time, value in zip(times, values)) / denominator


def _days_between(timestamp: datetime, origin: datetime) -> float:
    return (timestamp - origin).total_seconds() / 86_400.0


def calculate_trajectory(
    observations: Sequence[Observation],
    estimates: Sequence[StateEstimate],
    *,
    window_days: int = 180,
    min_points: int = 2,
) -> TrajectoryResult:
    """Combine immutable observations and estimates into a traceable trajectory."""

    if window_days < 1:
        raise ValueError("window_days must be positive")
    if min_points < 2:
        raise ValueError("min_points must be at least 2")

    estimate_by_observation = {estimate.observation_id: estimate for estimate in estimates}
    ordered = sorted(observations, key=lambda observation: observation.observed_at)
    if not ordered:
        return TrajectoryResult(
            points=(),
            total_slope_per_day=None,
            motor_slope_per_day=None,
            window_days=window_days,
            status="insufficient_data",
            data_quality={"observation_count": 0, "valid_total_points": 0, "valid_motor_points": 0},
            warnings=("INSUFFICIENT_HISTORY",),
        )

    latest = ordered[-1].observed_at
    cutoff_seconds = window_days * 86_400
    points: list[TrajectoryPoint] = []
    for observation in ordered:
        if (latest - observation.observed_at).total_seconds() > cutoff_seconds:
            continue
        estimate = estimate_by_observation.get(observation.id)
        estimated_total = estimate.estimated_total_updrs if estimate else None
        estimated_motor = estimate.estimated_motor_updrs if estimate else None
        if observation.observed_total_updrs is not None and estimated_total is not None:
            source_type = "observed_and_estimated"
        elif observation.observed_total_updrs is not None:
            source_type = "observed"
        elif estimated_total is not None:
            source_type = "estimated"
        else:
            source_type = "unusable"
        if source_type != "unusable":
            points.append(
                TrajectoryPoint(
                    timestamp=observation.observed_at,
                    observed_total_updrs=observation.observed_total_updrs,
                    estimated_total_updrs=estimated_total,
                    source_type=source_type,
                    quality_flags=estimate.quality_flags if estimate else (),
                    observed_motor_updrs=observation.observed_motor_updrs,
                    estimated_motor_updrs=estimated_motor,
                )
            )

    if not points:
        return TrajectoryResult(
            points=(),
            total_slope_per_day=None,
            motor_slope_per_day=None,
            window_days=window_days,
            status="insufficient_data",
            data_quality={"observation_count": len(ordered), "valid_total_points": 0, "valid_motor_points": 0},
            warnings=("INSUFFICIENT_HISTORY",),
        )

    origin = points[0].timestamp
    total_times: list[float] = []
    total_values: list[float] = []
    motor_times: list[float] = []
    motor_values: list[float] = []
    for point in points:
        time = _days_between(point.timestamp, origin)
        total_value = point.observed_total_updrs
        if total_value is None:
            total_value = point.estimated_total_updrs
        if total_value is not None and math.isfinite(total_value):
            total_times.append(time)
            total_values.append(total_value)
        motor_value = point.observed_motor_updrs
        if motor_value is None:
            motor_value = point.estimated_motor_updrs
        if motor_value is not None and math.isfinite(motor_value):
            motor_times.append(time)
            motor_values.append(motor_value)

    warnings: list[str] = []
    if len(total_values) < min_points:
        warnings.append("INSUFFICIENT_TOTAL_HISTORY")
    if len(motor_values) < min_points:
        warnings.append("INSUFFICIENT_MOTOR_HISTORY")
    status = "ready" if len(total_values) >= min_points else "insufficient_data"
    return TrajectoryResult(
        points=tuple(points),
        total_slope_per_day=_slope(total_times, total_values),
        motor_slope_per_day=_slope(motor_times, motor_values),
        window_days=window_days,
        status=status,
        data_quality={
            "observation_count": len(ordered),
            "window_point_count": len(points),
            "valid_total_points": len(total_values),
            "valid_motor_points": len(motor_values),
            "coverage_days": (points[-1].timestamp - points[0].timestamp).total_seconds() / 86_400.0,
        },
        warnings=tuple(warnings),
    )
