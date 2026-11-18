"""Twin inference, trajectory, and simulation adapter boundary.

Segment B runs against MockTwinEngineAdapter until Segment A merges its real
model/domain implementation. Replacing the mock adapter during final integration
requires swapping only the factory in `build_engine_adapter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import math
from typing import Any, Protocol

from app.api.schemas import SPEECH_FEATURE_NAMES
from app.persistence.models import ensure_utc


class ModelUnavailableError(Exception):
    """Raised when the inference adapter cannot load or serve predictions (fail-closed)."""


@dataclass(frozen=True)
class EngineModelMetadata:
    model_version: str
    feature_version: str
    assumptions_version: str
    adapter_type: str  # "mock" or "real"
    artifact_checksum: str

    def to_dict(self) -> dict[str, str]:
        return {
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "assumptions_version": self.assumptions_version,
            "adapter_type": self.adapter_type,
            "artifact_checksum": self.artifact_checksum,
        }


@dataclass(frozen=True)
class InferenceResult:
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


@dataclass(frozen=True)
class TrajectoryInputPoint:
    observation_id: str
    observed_at: datetime
    is_partial: bool
    observed_total_updrs: float | None
    observed_motor_updrs: float | None
    estimated_total_updrs: float | None
    estimated_motor_updrs: float | None
    total_updrs_ci_low: float | None
    total_updrs_ci_high: float | None
    motor_updrs_ci_low: float | None
    motor_updrs_ci_high: float | None
    quality_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrajectoryResult:
    status: str  # "active" or "insufficient_data"
    observed_points: list[dict[str, Any]]
    estimated_points: list[dict[str, Any]]
    slope: dict[str, Any]
    coverage: dict[str, Any]
    quality_flags: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class SimulationOutput:
    assumptions_version: str
    model_version: str
    hypothetical: bool
    baseline_series: list[dict[str, Any]]
    scenario_series: list[dict[str, Any]]
    summary: dict[str, Any]
    warnings: list[str]


class TwinEnginePort(Protocol):
    """Contract between Segment B (API/persistence) and Segment A (model/domain math)."""

    def is_available(self) -> bool: ...

    def get_model_metadata(self) -> EngineModelMetadata: ...

    def infer(self, features: dict[str, float | None], *, is_partial: bool) -> InferenceResult: ...

    def compute_trajectory(
        self,
        points: list[TrajectoryInputPoint],
        *,
        stale_threshold_days: int = 30,
        reference_time: datetime | None = None,
    ) -> TrajectoryResult: ...

    def simulate(
        self,
        trajectory: TrajectoryResult,
        *,
        levodopa_dose_change_mg: float,
        physical_therapy_sessions_per_week: int,
        adherence_ratio: float,
        horizon_days: int,
        step_days: int,
    ) -> SimulationOutput: ...


def _round2(value: float) -> float:
    return round(float(value), 2)


def _ols_slope_per_day(xs_days: list[float], ys: list[float]) -> float | None:
    if len(xs_days) < 2:
        return None
    x_mean = sum(xs_days) / len(xs_days)
    y_mean = sum(ys) / len(ys)
    denom = sum((x - x_mean) ** 2 for x in xs_days)
    if denom <= 1e-9:
        return None
    numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs_days, ys))
    return numer / denom


class MockTwinEngineAdapter:
    """Deterministic prototype adapter implementing TwinEnginePort without ML training imports."""

    MODEL_VERSION = "mock-updrs-v0.1.0"
    FEATURE_VERSION = "speech16-v1"
    ASSUMPTIONS_VERSION = "sim-assumptions-mock-v1"

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        checksum_seed = f"{self.MODEL_VERSION}:{self.FEATURE_VERSION}:{self.ASSUMPTIONS_VERSION}"
        self._checksum = hashlib.sha256(checksum_seed.encode("utf-8")).hexdigest()[:16]

    def set_available(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def get_model_metadata(self) -> EngineModelMetadata:
        return EngineModelMetadata(
            model_version=self.MODEL_VERSION,
            feature_version=self.FEATURE_VERSION,
            assumptions_version=self.ASSUMPTIONS_VERSION,
            adapter_type="mock",
            artifact_checksum=self._checksum,
        )

    def infer(self, features: dict[str, float | None], *, is_partial: bool) -> InferenceResult:
        if not self._available:
            raise ModelUnavailableError("Inference model artifact is unavailable.")

        missing = [name for name in SPEECH_FEATURE_NAMES if features.get(name) is None]
        if is_partial or missing:
            # Never fabricate UPDRS values when required features are missing.
            return InferenceResult(
                estimated_total_updrs=None,
                estimated_motor_updrs=None,
                total_updrs_ci_low=None,
                total_updrs_ci_high=None,
                motor_updrs_ci_low=None,
                motor_updrs_ci_high=None,
                confidence_score=None,
                quality_flags=["PARTIAL_BASELINE_FEATURES", "INSUFFICIENT_FEATURES_FOR_INFERENCE"],
                model_version=self.MODEL_VERSION,
                feature_version=self.FEATURE_VERSION,
            )

        # Deterministic synthetic mapping grounded in typical UCI telemonitoring feature directions:
        # Higher jitter/shimmer/nhr/rpde/ppe and lower HNR correspond to higher UPDRS severity.
        jitter_pct = float(features["jitter_percent"])  # typical ~0.002 - 0.02
        shimmer = float(features["shimmer"])  # typical ~0.01 - 0.12
        nhr = float(features["nhr"])  # typical ~0.005 - 0.15
        hnr = float(features["hnr"])  # typical ~14 - 30 dB
        rpde = float(features["rpde"])  # typical ~0.35 - 0.75
        dfa = float(features["dfa"])  # typical ~0.55 - 0.85
        ppe = float(features["ppe"])  # typical ~0.10 - 0.45

        raw_total = (
            18.0
            + 620.0 * jitter_pct
            + 135.0 * shimmer
            + 42.0 * nhr
            + max(0.0, 26.0 - hnr) * 0.75
            + 12.0 * rpde
            + 4.5 * dfa
            + 18.0 * ppe
        )
        estimated_total = max(4.0, min(176.0, raw_total))
        motor_ratio = 0.74 + 0.04 * math.tanh((rpde - 0.5) * 2.0)
        estimated_motor = max(2.0, min(estimated_total, min(108.0, estimated_total * motor_ratio)))

        quality_flags: list[str] = []
        uncertainty_total = 3.2
        if jitter_pct > 0.05 or shimmer > 0.25:
            quality_flags.append("ELEVATED_PERTURBATION_VARIANCE")
            uncertainty_total += 2.1
        if hnr < 10.0:
            quality_flags.append("LOW_SIGNAL_HARMONICS_RATIO")
            uncertainty_total += 1.6
        if nhr > 0.5:
            quality_flags.append("HIGH_NOISE_TO_HARMONICS_RATIO")
            uncertainty_total += 1.4

        uncertainty_motor = uncertainty_total * 0.8
        confidence = max(0.35, min(0.95, 0.9 - 0.08 * len(quality_flags)))

        return InferenceResult(
            estimated_total_updrs=_round2(estimated_total),
            estimated_motor_updrs=_round2(estimated_motor),
            total_updrs_ci_low=_round2(max(0.0, estimated_total - uncertainty_total)),
            total_updrs_ci_high=_round2(min(199.0, estimated_total + uncertainty_total)),
            motor_updrs_ci_low=_round2(max(0.0, estimated_motor - uncertainty_motor)),
            motor_updrs_ci_high=_round2(min(108.0, estimated_motor + uncertainty_motor)),
            confidence_score=_round2(confidence),
            quality_flags=quality_flags,
            model_version=self.MODEL_VERSION,
            feature_version=self.FEATURE_VERSION,
        )

    def compute_trajectory(
        self,
        points: list[TrajectoryInputPoint],
        *,
        stale_threshold_days: int = 30,
        reference_time: datetime | None = None,
    ) -> TrajectoryResult:
        ordered = sorted(points, key=lambda p: ensure_utc(p.observed_at))
        now_utc = ensure_utc(reference_time) if reference_time is not None else datetime.now(timezone.utc)

        observed_series: list[dict[str, Any]] = []
        estimated_series: list[dict[str, Any]] = []
        all_flags: set[str] = set()

        for pt in ordered:
            ts = ensure_utc(pt.observed_at)
            ts_iso = ts.isoformat()
            flags = list(pt.quality_flags)
            all_flags.update(flags)

            if pt.observed_total_updrs is not None or pt.observed_motor_updrs is not None:
                observed_series.append(
                    {
                        "observation_id": pt.observation_id,
                        "timestamp": ts_iso,
                        "source_type": "observed",
                        "total_updrs": pt.observed_total_updrs,
                        "motor_updrs": pt.observed_motor_updrs,
                        "scenario_id": None,
                        "hypothetical": False,
                        "quality_flags": flags,
                    }
                )

            if pt.estimated_total_updrs is not None or pt.estimated_motor_updrs is not None:
                estimated_series.append(
                    {
                        "observation_id": pt.observation_id,
                        "timestamp": ts_iso,
                        "source_type": "estimated",
                        "total_updrs": pt.estimated_total_updrs,
                        "motor_updrs": pt.estimated_motor_updrs,
                        "total_updrs_ci_low": pt.total_updrs_ci_low,
                        "total_updrs_ci_high": pt.total_updrs_ci_high,
                        "motor_updrs_ci_low": pt.motor_updrs_ci_low,
                        "motor_updrs_ci_high": pt.motor_updrs_ci_high,
                        "scenario_id": None,
                        "hypothetical": False,
                        "quality_flags": flags,
                    }
                )

        first_ts = ensure_utc(ordered[0].observed_at) if ordered else None
        last_ts = ensure_utc(ordered[-1].observed_at) if ordered else None
        time_span_days = (
            round((last_ts - first_ts).total_seconds() / 86400.0, 2)
            if first_ts is not None and last_ts is not None
            else 0.0
        )
        is_stale = (
            (now_utc - last_ts).total_seconds() / 86400.0 > stale_threshold_days
            if last_ts is not None
            else True
        )

        # Compute OLS slope over valid estimated points (requires >=2 time-separated observations)
        est_valid = [
            (ensure_utc(p.observed_at), p.estimated_total_updrs, p.estimated_motor_updrs)
            for p in ordered
            if p.estimated_total_updrs is not None and p.estimated_motor_updrs is not None
        ]

        slope_total_day: float | None = None
        slope_motor_day: float | None = None
        est_span_days = 0.0
        if len(est_valid) >= 2:
            t0 = est_valid[0][0]
            xs = [(ts - t0).total_seconds() / 86400.0 for ts, _, _ in est_valid]
            est_span_days = round(xs[-1] - xs[0], 2)
            if est_span_days > 0.0:
                slope_total_day = _ols_slope_per_day(xs, [float(t) for _, t, _ in est_valid])
                slope_motor_day = _ols_slope_per_day(xs, [float(m) for _, _, m in est_valid])

        warnings: list[str] = []
        if slope_total_day is not None and slope_motor_day is not None:
            slope_payload = {
                "status": "computed",
                "method": "ordinary_least_squares_full_window",
                "window_description": "All valid time-separated estimated observations",
                "units": "updrs_points_per_30_days",
                "total_updrs_per_30_days": round(slope_total_day * 30.0, 3),
                "motor_updrs_per_30_days": round(slope_motor_day * 30.0, 3),
                "total_updrs_per_day": round(slope_total_day, 5),
                "motor_updrs_per_day": round(slope_motor_day, 5),
                "observation_count_used": len(est_valid),
                "time_span_days": est_span_days,
            }
            twin_status = "active"
            if len(est_valid) < 3 or est_span_days < 14.0:
                warnings.append(
                    "SPARSE_LONGITUDINAL_HISTORY: Fewer than 3 observations or under 14 days of coverage; interpret slope cautiously."
                )
                all_flags.add("SPARSE_LONGITUDINAL_HISTORY")
        else:
            slope_payload = {
                "status": "insufficient_data",
                "method": "ordinary_least_squares_full_window",
                "window_description": "Requires at least 2 time-separated valid estimated observations",
                "units": "updrs_points_per_30_days",
                "total_updrs_per_30_days": None,
                "motor_updrs_per_30_days": None,
                "total_updrs_per_day": None,
                "motor_updrs_per_day": None,
                "observation_count_used": len(est_valid),
                "time_span_days": est_span_days,
            }
            twin_status = "insufficient_data" if len(est_valid) == 0 else "active"
            warnings.append(
                "INSUFFICIENT_HISTORY_FOR_SLOPE: At least 2 time-separated complete voice observations are required to compute progression slope."
            )
            all_flags.add("INSUFFICIENT_HISTORY_FOR_SLOPE")

        if is_stale and last_ts is not None:
            warnings.append(
                f"STALE_TWIN_DATA: Most recent observation is older than {stale_threshold_days} days."
            )
            all_flags.add("STALE_TWIN_DATA")

        if any(p.is_partial for p in ordered):
            warnings.append(
                "PARTIAL_OBSERVATION_PRESENT: At least one observation had incomplete speech features and was excluded from inference."
            )

        coverage = {
            "total_observations": len(ordered),
            "estimated_observations": len(estimated_series),
            "observed_updrs_count": len(observed_series),
            "first_observed_at": first_ts.isoformat() if first_ts is not None else None,
            "last_observed_at": last_ts.isoformat() if last_ts is not None else None,
            "time_span_days": time_span_days,
            "is_stale": is_stale,
            "stale_threshold_days": stale_threshold_days,
        }

        return TrajectoryResult(
            status=twin_status,
            observed_points=observed_series,
            estimated_points=estimated_series,
            slope=slope_payload,
            coverage=coverage,
            quality_flags=sorted(all_flags),
            warnings=warnings,
        )

    def simulate(
        self,
        trajectory: TrajectoryResult,
        *,
        levodopa_dose_change_mg: float,
        physical_therapy_sessions_per_week: int,
        adherence_ratio: float,
        horizon_days: int,
        step_days: int,
    ) -> SimulationOutput:
        if not self._available:
            raise ModelUnavailableError("Inference model artifact is unavailable for simulation.")

        if not trajectory.estimated_points:
            raise ValueError("Cannot simulate without at least one estimated baseline state.")

        last_est = trajectory.estimated_points[-1]
        anchor_ts = datetime.fromisoformat(last_est["timestamp"])
        base_total = float(last_est["total_updrs"])
        base_motor = float(last_est["motor_updrs"])

        warnings = [
            "HYPOTHETICAL_SCENARIO: Simulation output uses prototype response assumptions and is NOT clinical or prescribing advice."
        ]

        slope_total_day = trajectory.slope.get("total_updrs_per_day")
        slope_motor_day = trajectory.slope.get("motor_updrs_per_day")
        if slope_total_day is None or slope_motor_day is None:
            slope_total_day = 0.0
            slope_motor_day = 0.0
            warnings.append(
                "FLAT_BASELINE_ASSUMPTION: Insufficient longitudinal history for slope; baseline forecast held constant from latest estimate."
            )

        # Pure, versioned hypothetical response assumptions (explicitly non-clinical prototype model)
        # Positive Levodopa dose adjustment reduces projected UPDRS symptom burden with diminishing returns;
        # Negative adjustment increases burden. Physical therapy gradually dampens progression slope.
        effective_levo = (levodopa_dose_change_mg / 100.0) * adherence_ratio
        levo_total_shift = -2.4 * math.tanh(effective_levo / 2.5) * 2.5
        levo_motor_shift = levo_total_shift * 0.82

        pt_slope_dampening_per_day = (
            -0.018 * physical_therapy_sessions_per_week * adherence_ratio
        )

        if abs(levodopa_dose_change_mg) >= 400.0:
            warnings.append(
                "EXTREME_INTERVENTION_RANGE: Large Levodopa dose change entered; prototype response curve has higher uncertainty."
            )

        steps: list[int] = list(range(0, horizon_days + 1, step_days))
        if steps[-1] != horizon_days:
            steps.append(horizon_days)

        baseline_series: list[dict[str, Any]] = []
        scenario_series: list[dict[str, Any]] = []

        for day in steps:
            ts_iso = (anchor_ts + timedelta(days=day)).isoformat()
            proj_base_total = max(0.0, min(199.0, base_total + slope_total_day * day))
            proj_base_motor = max(
                0.0, min(proj_base_total, min(108.0, base_motor + slope_motor_day * day))
            )

            # Ramp pharmacologic response over first 14 days
            onset_fraction = 1.0 - math.exp(-day / 10.0) if day > 0 else 0.0
            proj_scen_total = max(
                0.0,
                min(
                    199.0,
                    proj_base_total
                    + levo_total_shift * onset_fraction
                    + pt_slope_dampening_per_day * day,
                ),
            )
            proj_scen_motor = max(
                0.0,
                min(
                    proj_scen_total,
                    min(
                        108.0,
                        proj_base_motor
                        + levo_motor_shift * onset_fraction
                        + (pt_slope_dampening_per_day * 0.85) * day,
                    ),
                ),
            )
            horizon_uncertainty = 3.0 + 0.04 * day

            baseline_series.append(
                {
                    "timestamp": ts_iso,
                    "day_offset": day,
                    "source_type": "estimated",
                    "total_updrs": _round2(proj_base_total),
                    "motor_updrs": _round2(proj_base_motor),
                    "hypothetical": False,
                }
            )
            scenario_series.append(
                {
                    "timestamp": ts_iso,
                    "day_offset": day,
                    "source_type": "simulated",
                    "total_updrs": _round2(proj_scen_total),
                    "motor_updrs": _round2(proj_scen_motor),
                    "total_updrs_ci_low": _round2(max(0.0, proj_scen_total - horizon_uncertainty)),
                    "total_updrs_ci_high": _round2(min(199.0, proj_scen_total + horizon_uncertainty)),
                    "motor_updrs_ci_low": _round2(max(0.0, proj_scen_motor - horizon_uncertainty * 0.8)),
                    "motor_updrs_ci_high": _round2(min(108.0, proj_scen_motor + horizon_uncertainty * 0.8)),
                    "hypothetical": True,
                }
            )

        end_base = baseline_series[-1]
        end_scen = scenario_series[-1]
        summary = {
            "horizon_days": horizon_days,
            "baseline_end_total_updrs": end_base["total_updrs"],
            "scenario_end_total_updrs": end_scen["total_updrs"],
            "delta_total_updrs": _round2(end_scen["total_updrs"] - end_base["total_updrs"]),
            "baseline_end_motor_updrs": end_base["motor_updrs"],
            "scenario_end_motor_updrs": end_scen["motor_updrs"],
            "delta_motor_updrs": _round2(end_scen["motor_updrs"] - end_base["motor_updrs"]),
            "hypothetical": True,
        }

        return SimulationOutput(
            assumptions_version=self.ASSUMPTIONS_VERSION,
            model_version=self.MODEL_VERSION,
            hypothetical=True,
            baseline_series=baseline_series,
            scenario_series=scenario_series,
            summary=summary,
            warnings=warnings,
        )


def build_engine_adapter(adapter_name: str = "mock") -> TwinEnginePort:
    """Factory returning the active TwinEnginePort implementation.

    During final integration with Segment A, register `real` here pointing to
    Segment A's inference/trajectory/simulation adapter.
    """
    if adapter_name == "mock":
        return MockTwinEngineAdapter(available=True)
    raise ValueError(f"Unsupported engine adapter '{adapter_name}'. Expected 'mock'.")
