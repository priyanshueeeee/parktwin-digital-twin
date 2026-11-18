"""Strict Pydantic v2 schemas for ParkTwin REST API contracts (v1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PSEUDONYMOUS_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")

SPEECH_FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    "jitter_percent": (0.0, 1.0),
    "jitter_abs": (0.0, 0.01),
    "jitter_rap": (0.0, 1.0),
    "jitter_ppq5": (0.0, 1.0),
    "jitter_ddp": (0.0, 3.0),
    "shimmer": (0.0, 1.0),
    "shimmer_db": (0.0, 10.0),
    "shimmer_apq3": (0.0, 1.0),
    "shimmer_apq5": (0.0, 1.0),
    "shimmer_apq11": (0.0, 1.0),
    "shimmer_dda": (0.0, 3.0),
    "nhr": (0.0, 5.0),
    "hnr": (0.0, 60.0),
    "rpde": (0.0, 1.0),
    "dfa": (0.0, 1.5),
    "ppe": (0.0, 2.0),
}

SPEECH_FEATURE_NAMES: tuple[str, ...] = tuple(SPEECH_FEATURE_BOUNDS.keys())


def _validate_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include timezone offset (ISO-8601 UTC)")
    normalized = value.astimezone(timezone.utc)
    if normalized.year < 2000:
        raise ValueError("timestamp must be on or after 2000-01-01T00:00:00Z")
    if normalized > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("timestamp cannot be in the future")
    return normalized


class StrictModel(BaseModel):
    """Base schema rejecting unknown fields so inputs are never silently dropped."""

    model_config = ConfigDict(extra="forbid")


class SpeechFeatures(StrictModel):
    """Complete 16 biomedical speech features from the UCI Parkinson's Telemonitoring schema."""

    jitter_percent: float = Field(..., ge=0.0, le=1.0, description="Jitter(%) local frequency perturbation")
    jitter_abs: float = Field(..., ge=0.0, le=0.01, description="Jitter(Abs) absolute jitter in seconds")
    jitter_rap: float = Field(..., ge=0.0, le=1.0, description="Jitter:RAP relative amplitude perturbation")
    jitter_ppq5: float = Field(..., ge=0.0, le=1.0, description="Jitter:PPQ5 5-point period perturbation quotient")
    jitter_ddp: float = Field(..., ge=0.0, le=3.0, description="Jitter:DDP average absolute difference of differences")
    shimmer: float = Field(..., ge=0.0, le=1.0, description="Shimmer local amplitude perturbation")
    shimmer_db: float = Field(..., ge=0.0, le=10.0, description="Shimmer(dB) local shimmer in decibels")
    shimmer_apq3: float = Field(..., ge=0.0, le=1.0, description="Shimmer:APQ3 3-point amplitude perturbation quotient")
    shimmer_apq5: float = Field(..., ge=0.0, le=1.0, description="Shimmer:APQ5 5-point amplitude perturbation quotient")
    shimmer_apq11: float = Field(..., ge=0.0, le=1.0, description="Shimmer:APQ11 11-point amplitude perturbation quotient")
    shimmer_dda: float = Field(..., ge=0.0, le=3.0, description="Shimmer:DDA average absolute differences between consecutive differences")
    nhr: float = Field(..., ge=0.0, le=5.0, description="Noise-to-Harmonics Ratio")
    hnr: float = Field(..., ge=0.0, le=60.0, description="Harmonics-to-Noise Ratio (dB)")
    rpde: float = Field(..., ge=0.0, le=1.0, description="Recurrence Period Density Entropy")
    dfa: float = Field(..., ge=0.0, le=1.5, description="Detrended Fluctuation Analysis exponent")
    ppe: float = Field(..., ge=0.0, le=2.0, description="Pitch Period Entropy")


class PartialSpeechFeatures(StrictModel):
    """Explicitly partial 16 speech feature vector permitted only on twin baseline creation."""

    jitter_percent: float | None = Field(default=None, ge=0.0, le=1.0)
    jitter_abs: float | None = Field(default=None, ge=0.0, le=0.01)
    jitter_rap: float | None = Field(default=None, ge=0.0, le=1.0)
    jitter_ppq5: float | None = Field(default=None, ge=0.0, le=1.0)
    jitter_ddp: float | None = Field(default=None, ge=0.0, le=3.0)
    shimmer: float | None = Field(default=None, ge=0.0, le=1.0)
    shimmer_db: float | None = Field(default=None, ge=0.0, le=10.0)
    shimmer_apq3: float | None = Field(default=None, ge=0.0, le=1.0)
    shimmer_apq5: float | None = Field(default=None, ge=0.0, le=1.0)
    shimmer_apq11: float | None = Field(default=None, ge=0.0, le=1.0)
    shimmer_dda: float | None = Field(default=None, ge=0.0, le=3.0)
    nhr: float | None = Field(default=None, ge=0.0, le=5.0)
    hnr: float | None = Field(default=None, ge=0.0, le=60.0)
    rpde: float | None = Field(default=None, ge=0.0, le=1.0)
    dfa: float | None = Field(default=None, ge=0.0, le=1.5)
    ppe: float | None = Field(default=None, ge=0.0, le=2.0)

    def missing_features(self) -> list[str]:
        data = self.model_dump()
        return [name for name in SPEECH_FEATURE_NAMES if data.get(name) is None]

    def is_complete(self) -> bool:
        return len(self.missing_features()) == 0


class TwinCreateRequest(StrictModel):
    external_reference: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Pseudonymous patient reference token (never a personal name or email).",
    )
    observed_at: datetime = Field(..., description="Baseline observation timestamp (ISO-8601 UTC).")
    features: PartialSpeechFeatures = Field(
        ...,
        description="Complete 16 speech metrics, or partial metrics if allow_partial=true.",
    )
    allow_partial: bool = Field(
        default=False,
        description="Set true to explicitly permit an incomplete baseline (marks twin insufficient_data).",
    )
    observed_total_updrs: float | None = Field(default=None, ge=0.0, le=199.0)
    observed_motor_updrs: float | None = Field(default=None, ge=0.0, le=108.0)
    source: str = Field(default="api", min_length=1, max_length=64)
    idempotency_key: str | None = Field(
        default=None,
        min_length=4,
        max_length=128,
        description="Client-generated idempotency key (or pass via Idempotency-Key HTTP header).",
    )

    @field_validator("external_reference")
    @classmethod
    def validate_pseudonymous_ref(cls, value: str) -> str:
        if not PSEUDONYMOUS_REF_PATTERN.match(value):
            raise ValueError(
                "external_reference must be a pseudonymous token matching ^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$"
            )
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _validate_utc_timestamp(value)

    @model_validator(mode="after")
    def validate_baseline_rules(self) -> "TwinCreateRequest":
        missing = self.features.missing_features()
        if missing and not self.allow_partial:
            raise ValueError(
                f"incomplete speech feature vector ({len(missing)} missing); "
                "supply all 16 features or set allow_partial=true"
            )
        if (
            self.observed_total_updrs is not None
            and self.observed_motor_updrs is not None
            and self.observed_motor_updrs > self.observed_total_updrs
        ):
            raise ValueError("observed_motor_updrs cannot exceed observed_total_updrs")
        return self


class TwinUpdateRequest(StrictModel):
    twin_id: str = Field(..., min_length=8, max_length=64)
    observed_at: datetime = Field(..., description="Voice observation timestamp (ISO-8601 UTC).")
    features: SpeechFeatures = Field(..., description="All 16 validated biomedical speech metrics.")
    observed_total_updrs: float | None = Field(default=None, ge=0.0, le=199.0)
    observed_motor_updrs: float | None = Field(default=None, ge=0.0, le=108.0)
    source: str = Field(default="api", min_length=1, max_length=64)
    idempotency_key: str | None = Field(
        default=None,
        min_length=4,
        max_length=128,
        description="Client-generated idempotency key (or pass via Idempotency-Key HTTP header).",
    )
    expected_version: int | None = Field(
        default=None,
        ge=1,
        description="Optional twin version for client-enforced optimistic concurrency.",
    )

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _validate_utc_timestamp(value)

    @model_validator(mode="after")
    def validate_updrs_consistency(self) -> "TwinUpdateRequest":
        if (
            self.observed_total_updrs is not None
            and self.observed_motor_updrs is not None
            and self.observed_motor_updrs > self.observed_total_updrs
        ):
            raise ValueError("observed_motor_updrs cannot exceed observed_total_updrs")
        return self


class InterventionParameters(StrictModel):
    levodopa_dose_change_mg: float = Field(
        default=0.0,
        ge=-300.0,
        le=600.0,
        description="Hypothetical Levodopa daily dose adjustment in mg (-300 to +600).",
    )
    physical_therapy_sessions_per_week: int = Field(
        default=0,
        ge=0,
        le=7,
        description="Hypothetical structured physical therapy sessions per week (0 to 7).",
    )
    adherence_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Hypothetical adherence multiplier (0.0 to 1.0).",
    )


class SimulationRequest(StrictModel):
    label: str = Field(default="Intervention Scenario", min_length=1, max_length=128)
    interventions: InterventionParameters
    horizon_days: int = Field(default=90, ge=7, le=180)
    step_days: int = Field(default=14, ge=1, le=30)
    acknowledge_hypothetical: bool = Field(
        ...,
        description="Must be true to acknowledge the output is a non-diagnostic hypothetical scenario.",
    )

    @model_validator(mode="after")
    def validate_simulation_rules(self) -> "SimulationRequest":
        if not self.acknowledge_hypothetical:
            raise ValueError("acknowledge_hypothetical must be true to run a scenario simulation")
        if self.step_days > self.horizon_days:
            raise ValueError("step_days cannot exceed horizon_days")
        return self


# --- Response schemas ---


class ModelMetadataResponse(BaseModel):
    model_version: str
    feature_version: str
    assumptions_version: str
    adapter_type: Literal["mock", "real"]
    artifact_checksum: str


class StateEstimateResponse(BaseModel):
    id: str
    observation_id: str
    observed_at: str
    estimated_total_updrs: float | None
    estimated_motor_updrs: float | None
    total_updrs_ci_low: float | None
    total_updrs_ci_high: float | None
    motor_updrs_ci_low: float | None
    motor_updrs_ci_high: float | None
    confidence_score: float | None
    quality_flags: list[str]
    model_version: str
    feature_version: str


class SlopeSummaryResponse(BaseModel):
    status: Literal["computed", "insufficient_data"]
    method: str
    window_description: str
    units: str
    total_updrs_per_30_days: float | None
    motor_updrs_per_30_days: float | None
    total_updrs_per_day: float | None
    motor_updrs_per_day: float | None
    observation_count_used: int
    time_span_days: float


class DataCoverageResponse(BaseModel):
    total_observations: int
    estimated_observations: int
    observed_updrs_count: int
    first_observed_at: str | None
    last_observed_at: str | None
    time_span_days: float
    is_stale: bool
    stale_threshold_days: int


class TrajectoryPointResponse(BaseModel):
    observation_id: str | None = None
    timestamp: str
    source_type: Literal["observed", "estimated", "simulated"]
    total_updrs: float | None
    motor_updrs: float | None
    total_updrs_ci_low: float | None = None
    total_updrs_ci_high: float | None = None
    motor_updrs_ci_low: float | None = None
    motor_updrs_ci_high: float | None = None
    scenario_id: str | None = None
    hypothetical: bool = False
    quality_flags: list[str] = Field(default_factory=list)


class ApiEnvelope(BaseModel):
    request_id: str
    schema_version: str
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
