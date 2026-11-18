"""Immutable domain contracts shared by Segment A components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class Twin:
    id: str
    external_reference: str | None
    created_at: datetime
    updated_at: datetime
    status: str
    latest_state_id: str | None = None
    data_quality_summary: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_quality_summary", _immutable_mapping(self.data_quality_summary))


@dataclass(frozen=True)
class Observation:
    id: str
    twin_id: str
    observed_at: datetime
    features: Mapping[str, float]
    observed_total_updrs: float | None = None
    observed_motor_updrs: float | None = None
    source_event_id: str | None = None
    quality_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", _immutable_mapping(self.features))
        object.__setattr__(self, "quality_metadata", _immutable_mapping(self.quality_metadata))


@dataclass(frozen=True)
class StateEstimate:
    id: str
    twin_id: str
    observation_id: str
    estimated_total_updrs: float | None
    estimated_motor_updrs: float | None
    model_version: str
    feature_version: str
    quality_flags: tuple[str, ...] = ()
    created_at: datetime | None = None


@dataclass(frozen=True)
class TrajectoryPoint:
    timestamp: datetime
    observed_total_updrs: float | None
    estimated_total_updrs: float | None
    source_type: str
    scenario_id: str | None = None
    quality_flags: tuple[str, ...] = ()
    observed_motor_updrs: float | None = None
    estimated_motor_updrs: float | None = None


@dataclass(frozen=True)
class SimulationScenario:
    id: str
    twin_id: str
    intervention_parameters: Mapping[str, float]
    forecast_horizon_days: int
    step_days: int
    assumptions_version: str
    baseline_trajectory_reference: str
    status: str = "created"
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intervention_parameters",
            _immutable_mapping(self.intervention_parameters),
        )
