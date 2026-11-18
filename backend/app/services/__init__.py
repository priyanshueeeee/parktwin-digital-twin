"""Pure service components used by Segment A and the API boundary."""

from .simulation import (
    InterventionAssumptions,
    SimulationRequest,
    SimulationResult,
    SensitivityPoint,
    sensitivity_analysis,
    simulate_scenario,
    simulate_scenarios,
)
from .personalization import CalibrationResult, apply_calibration, fit_bounded_residual_calibration
from .trajectory import TrajectoryResult, calculate_trajectory

__all__ = [
    "InterventionAssumptions",
    "SimulationRequest",
    "SimulationResult",
    "SensitivityPoint",
    "sensitivity_analysis",
    "simulate_scenario",
    "simulate_scenarios",
    "CalibrationResult",
    "TrajectoryResult",
    "apply_calibration",
    "calculate_trajectory",
    "fit_bounded_residual_calibration",
]
