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

__all__ = [
    "InterventionAssumptions",
    "SimulationRequest",
    "SimulationResult",
    "SensitivityPoint",
    "sensitivity_analysis",
    "simulate_scenario",
    "simulate_scenarios",
]
