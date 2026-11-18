"""Versioned, isolated, non-clinical intervention simulation."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence


def _clamp_updrs(value: float) -> float:
    return max(0.0, min(199.0, value))


@dataclass(frozen=True)
class InterventionAssumptions:
    """Prototype assumptions; these are not clinical effect estimates."""

    version: str = "simulation-assumptions-v1"
    levodopa_slope_reduction: float = 0.25
    physical_therapy_slope_reduction: float = 0.15
    levodopa_max_relief: float = 3.0
    physical_therapy_max_relief: float = 1.5
    response_time_days: float = 14.0


@dataclass(frozen=True)
class SimulationRequest:
    initial_total_updrs: float
    baseline_slope_per_day: float
    horizon_days: int = 180
    step_days: int = 7
    initial_motor_updrs: float | None = None
    levodopa_intensity: float = 0.0
    physical_therapy_intensity: float = 0.0
    scenario_id: str = "scenario-1"


@dataclass(frozen=True)
class SimulationPoint:
    day: int
    baseline_total_updrs: float
    simulated_total_updrs: float
    baseline_motor_updrs: float | None
    simulated_motor_updrs: float | None


@dataclass(frozen=True)
class SimulationResult:
    scenario_id: str
    assumptions_version: str
    points: tuple[SimulationPoint, ...]
    is_hypothetical: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SensitivityPoint:
    parameter: str
    level: float
    final_simulated_total_updrs: float
    delta_vs_baseline: float


def _validate_request(request: SimulationRequest, assumptions: InterventionAssumptions) -> None:
    numeric_values = (
        ("initial_total_updrs", request.initial_total_updrs),
        ("baseline_slope_per_day", request.baseline_slope_per_day),
        ("levodopa_intensity", request.levodopa_intensity),
        ("physical_therapy_intensity", request.physical_therapy_intensity),
    )
    for name, value in numeric_values:
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
    if not 0 <= request.initial_total_updrs <= 199:
        raise ValueError("initial_total_updrs must be between 0 and 199")
    if request.initial_motor_updrs is not None and not 0 <= request.initial_motor_updrs <= 199:
        raise ValueError("initial_motor_updrs must be between 0 and 199")
    if request.horizon_days < 1 or request.horizon_days > 730:
        raise ValueError("horizon_days must be between 1 and 730")
    if request.step_days < 1 or request.step_days > 30 or request.step_days > request.horizon_days:
        raise ValueError("step_days must be between 1 and horizon_days, and no more than 30")
    if not -0.5 <= request.levodopa_intensity <= 1:
        raise ValueError("levodopa_intensity must be between -0.5 and 1")
    if not 0 <= request.physical_therapy_intensity <= 1:
        raise ValueError("physical_therapy_intensity must be between 0 and 1")
    if assumptions.response_time_days <= 0:
        raise ValueError("response_time_days must be positive")


def simulate_scenario(
    request: SimulationRequest,
    *,
    assumptions: InterventionAssumptions | None = None,
) -> SimulationResult:
    """Generate a scenario-only trajectory without mutating observed state."""

    assumptions = assumptions or InterventionAssumptions()
    _validate_request(request, assumptions)
    reduction = min(
        0.95,
        assumptions.levodopa_slope_reduction * request.levodopa_intensity
        + assumptions.physical_therapy_slope_reduction * request.physical_therapy_intensity,
    )
    effective_slope = request.baseline_slope_per_day * (1.0 - reduction)
    relief_limit = (
        assumptions.levodopa_max_relief * request.levodopa_intensity
        + assumptions.physical_therapy_max_relief * request.physical_therapy_intensity
    )
    days = list(range(0, request.horizon_days + 1, request.step_days))
    if days[-1] != request.horizon_days:
        days.append(request.horizon_days)

    points: list[SimulationPoint] = []
    for day in days:
        baseline_total = _clamp_updrs(request.initial_total_updrs + request.baseline_slope_per_day * day)
        relief = relief_limit * (1.0 - math.exp(-day / assumptions.response_time_days))
        simulated_total = _clamp_updrs(request.initial_total_updrs + effective_slope * day - relief)
        baseline_motor = None
        simulated_motor = None
        if request.initial_motor_updrs is not None:
            baseline_motor = _clamp_updrs(
                request.initial_motor_updrs + request.baseline_slope_per_day * 0.80 * day
            )
            simulated_motor = _clamp_updrs(
                request.initial_motor_updrs + effective_slope * 0.80 * day - relief * 0.80
            )
        points.append(
            SimulationPoint(
                day=day,
                baseline_total_updrs=baseline_total,
                simulated_total_updrs=simulated_total,
                baseline_motor_updrs=baseline_motor,
                simulated_motor_updrs=simulated_motor,
            )
        )

    return SimulationResult(
        scenario_id=request.scenario_id,
        assumptions_version=assumptions.version,
        points=tuple(points),
        is_hypothetical=True,
        warnings=(
            "HYPOTHETICAL_SCENARIO",
            "NON_CLINICAL_ASSUMPTIONS",
            "NOT_A_TREATMENT_RECOMMENDATION",
        ),
    )


def simulate_scenarios(
    requests: Sequence[SimulationRequest],
    *,
    assumptions: InterventionAssumptions | None = None,
) -> tuple[SimulationResult, ...]:
    """Compare multiple isolated scenarios using the same assumptions version."""

    return tuple(simulate_scenario(request, assumptions=assumptions) for request in requests)


def sensitivity_analysis(
    request: SimulationRequest,
    *,
    parameter: str,
    levels: Sequence[float],
    assumptions: InterventionAssumptions | None = None,
) -> tuple[SensitivityPoint, ...]:
    """Evaluate bounded changes to one intervention intensity."""

    if parameter not in {"levodopa_intensity", "physical_therapy_intensity"}:
        raise ValueError("parameter must be levodopa_intensity or physical_therapy_intensity")
    baseline = simulate_scenario(request, assumptions=assumptions)
    baseline_final = baseline.points[-1].baseline_total_updrs
    points: list[SensitivityPoint] = []
    for level in levels:
        lower_bound = -0.5 if parameter == "levodopa_intensity" else 0.0
        if not lower_bound <= level <= 1:
            raise ValueError(f"sensitivity levels must be between {lower_bound} and 1")
        scenario_request = replace(request, **{parameter: level})
        result = simulate_scenario(scenario_request, assumptions=assumptions)
        final_value = result.points[-1].simulated_total_updrs
        points.append(
            SensitivityPoint(
                parameter=parameter,
                level=level,
                final_simulated_total_updrs=final_value,
                delta_vs_baseline=final_value - baseline_final,
            )
        )
    return tuple(points)
