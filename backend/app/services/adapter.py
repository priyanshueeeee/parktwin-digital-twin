"""Real Segment A engine adapter for the Segment B API boundary.

This module is intentionally the only integration seam between the trained
artifacts/domain services and Segment B's REST application. Model artifacts
are loaded from explicit environment-configurable paths and the adapter fails
closed when either target artifact is unavailable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math
import os
from pathlib import Path
from typing import Any, Mapping

from .simulation import SimulationRequest, simulate_scenario


_FEATURE_ALIASES = {"jitter_abs": "jitter_absolute"}
_DEFAULT_TOTAL_ARTIFACT = "ml/artifacts/total/random_forest-total_UPDRS.joblib"
_DEFAULT_MOTOR_ARTIFACT = "ml/artifacts/motor/random_forest-motor_UPDRS.joblib"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_artifact_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else _repo_root() / path


def _sha256(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 5)


def _clamp(value: float, lower: float, upper: float) -> tuple[float, bool]:
    bounded = max(lower, min(upper, float(value)))
    return bounded, bounded != float(value)


class ArtifactTwinEngineAdapter:
    """Bridge trained Segment A artifacts to Segment B's typed port."""

    ASSUMPTIONS_VERSION = "simulation-assumptions-v1"

    def __init__(self, total_artifact_path: str | Path, motor_artifact_path: str | Path) -> None:
        from ml.models.training import load_model_artifact

        self.total_path = _resolve_artifact_path(str(total_artifact_path))
        self.motor_path = _resolve_artifact_path(str(motor_artifact_path))
        if not self.total_path.is_file() or not self.motor_path.is_file():
            missing = [str(path) for path in (self.total_path, self.motor_path) if not path.is_file()]
            raise FileNotFoundError(f"missing promoted model artifact(s): {', '.join(missing)}")
        self.total_artifact = load_model_artifact(self.total_path)
        self.motor_artifact = load_model_artifact(self.motor_path)
        if self.total_artifact.metadata.target != "total_UPDRS":
            raise ValueError("total artifact metadata target must be total_UPDRS")
        if self.motor_artifact.metadata.target != "motor_UPDRS":
            raise ValueError("motor artifact metadata target must be motor_UPDRS")
        if self.total_artifact.metadata.feature_set_version != self.motor_artifact.metadata.feature_set_version:
            raise ValueError("total and motor artifacts use different feature-set versions")
        if self.total_artifact.metadata.feature_mode != self.motor_artifact.metadata.feature_mode:
            raise ValueError("total and motor artifacts use different feature modes")
        self._checksum = _sha256((self.total_path, self.motor_path))

        # Imported lazily so Segment A's standalone unit tests do not depend on
        # Segment B's FastAPI package being present.
        from app.api.engine_adapter import InferenceResult, SimulationOutput, TrajectoryResult

        self._InferenceResult = InferenceResult
        self._SimulationOutput = SimulationOutput
        self._TrajectoryResult = TrajectoryResult

    def is_available(self) -> bool:
        return self.total_path.is_file() and self.motor_path.is_file()

    def get_model_metadata(self):
        from app.api.engine_adapter import EngineModelMetadata

        return EngineModelMetadata(
            model_version=self.total_artifact.metadata.model_version,
            feature_version=self.total_artifact.metadata.feature_set_version,
            assumptions_version=self.ASSUMPTIONS_VERSION,
            adapter_type="real",
            artifact_checksum=self._checksum,
        )

    @staticmethod
    def _canonical_features(features: Mapping[str, float | None]) -> dict[str, float]:
        from ml.data.schema import FEATURE_NAMES

        canonical: dict[str, float] = {}
        for name in FEATURE_NAMES:
            api_name = next((key for key, value in _FEATURE_ALIASES.items() if value == name), name)
            value = features.get(api_name)
            if value is None:
                value = features.get(name)
            if value is None:
                raise ValueError(f"missing required feature: {api_name}")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"feature {api_name} must be finite")
            canonical[name] = numeric
        return canonical

    @staticmethod
    def _prediction(artifact: Any, row: Mapping[str, float]) -> tuple[float, float | None, float | None]:
        predictions = artifact.predict_rows([row])
        if "median" in predictions:
            point = float(predictions["median"][0])
            lower = float(predictions["lower"][0])
            upper = float(predictions["upper"][0])
        else:
            point = float(predictions["point"][0])
            lower = upper = None
        return point, lower, upper

    def infer(self, features: dict[str, float | None], *, is_partial: bool):
        from app.api.schemas import SPEECH_FEATURE_NAMES

        missing = [name for name in SPEECH_FEATURE_NAMES if features.get(name) is None]
        if is_partial or missing:
            return self._InferenceResult(
                estimated_total_updrs=None,
                estimated_motor_updrs=None,
                total_updrs_ci_low=None,
                total_updrs_ci_high=None,
                motor_updrs_ci_low=None,
                motor_updrs_ci_high=None,
                confidence_score=None,
                quality_flags=["PARTIAL_BASELINE_FEATURES", "INSUFFICIENT_FEATURES_FOR_INFERENCE"],
                model_version=self.get_model_metadata().model_version,
                feature_version=self.get_model_metadata().feature_version,
            )

        row = self._canonical_features(features)
        total, total_low, total_high = self._prediction(self.total_artifact, row)
        motor, motor_low, motor_high = self._prediction(self.motor_artifact, row)
        total, total_clipped = _clamp(total, 0.0, 199.0)
        motor, motor_clipped = _clamp(motor, 0.0, 108.0)
        flags = ["NON_DIAGNOSTIC_MODEL_OUTPUT"]
        if total_clipped or motor_clipped:
            flags.append("PREDICTION_CLIPPED_TO_UPDRS_RANGE")
        if total_low is None or motor_low is None:
            flags.append("NO_CALIBRATED_PREDICTION_INTERVAL")
        return self._InferenceResult(
            estimated_total_updrs=_round(total),
            estimated_motor_updrs=_round(motor),
            total_updrs_ci_low=_round(total_low),
            total_updrs_ci_high=_round(total_high),
            motor_updrs_ci_low=_round(motor_low),
            motor_updrs_ci_high=_round(motor_high),
            confidence_score=None,
            quality_flags=flags,
            model_version=self.get_model_metadata().model_version,
            feature_version=self.get_model_metadata().feature_version,
        )

    def compute_trajectory(
        self,
        points: list[Any],
        *,
        stale_threshold_days: int = 30,
        reference_time: datetime | None = None,
    ):
        ordered = sorted(points, key=lambda point: _utc(point.observed_at))
        now = _utc(reference_time) if reference_time is not None else datetime.now(timezone.utc)
        observed_points: list[dict[str, Any]] = []
        estimated_points: list[dict[str, Any]] = []
        flags: set[str] = set()
        for point in ordered:
            timestamp = _utc(point.observed_at)
            timestamp_text = timestamp.isoformat()
            point_flags = list(point.quality_flags)
            flags.update(point_flags)
            if point.observed_total_updrs is not None or point.observed_motor_updrs is not None:
                observed_points.append({
                    "observation_id": point.observation_id,
                    "timestamp": timestamp_text,
                    "source_type": "observed",
                    "total_updrs": point.observed_total_updrs,
                    "motor_updrs": point.observed_motor_updrs,
                    "scenario_id": None,
                    "hypothetical": False,
                    "quality_flags": point_flags,
                })
            if point.estimated_total_updrs is not None or point.estimated_motor_updrs is not None:
                estimated_points.append({
                    "observation_id": point.observation_id,
                    "timestamp": timestamp_text,
                    "source_type": "estimated",
                    "total_updrs": point.estimated_total_updrs,
                    "motor_updrs": point.estimated_motor_updrs,
                    "total_updrs_ci_low": point.total_updrs_ci_low,
                    "total_updrs_ci_high": point.total_updrs_ci_high,
                    "motor_updrs_ci_low": point.motor_updrs_ci_low,
                    "motor_updrs_ci_high": point.motor_updrs_ci_high,
                    "scenario_id": None,
                    "hypothetical": False,
                    "quality_flags": point_flags,
                })

        first = _utc(ordered[0].observed_at) if ordered else None
        last = _utc(ordered[-1].observed_at) if ordered else None
        span = (last - first).total_seconds() / 86_400.0 if first and last else 0.0
        stale = last is None or (now - last).total_seconds() / 86_400.0 > stale_threshold_days
        valid = [point for point in ordered if point.estimated_total_updrs is not None and point.estimated_motor_updrs is not None]
        xs = [(point.observed_at - valid[0].observed_at).total_seconds() / 86_400.0 for point in valid] if valid else []

        def slope(values: list[float]) -> float | None:
            if len(values) < 2:
                return None
            mean_x = sum(xs) / len(xs)
            mean_y = sum(values) / len(values)
            denominator = sum((x - mean_x) ** 2 for x in xs)
            if denominator <= 0:
                return None
            return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator

        total_slope = slope([float(point.estimated_total_updrs) for point in valid])
        motor_slope = slope([float(point.estimated_motor_updrs) for point in valid])
        warnings: list[str] = []
        if total_slope is None or motor_slope is None:
            warnings.append("INSUFFICIENT_HISTORY_FOR_SLOPE")
            flags.add("INSUFFICIENT_HISTORY_FOR_SLOPE")
            slope_payload = {
                "status": "insufficient_data",
                "method": "ordinary_least_squares_full_window",
                "window_description": "Requires at least 2 time-separated valid estimated observations",
                "units": "updrs_points_per_30_days",
                "total_updrs_per_30_days": None,
                "motor_updrs_per_30_days": None,
                "total_updrs_per_day": None,
                "motor_updrs_per_day": None,
                "observation_count_used": len(valid),
                "time_span_days": round(xs[-1] - xs[0], 2) if len(xs) >= 2 else 0.0,
            }
        else:
            slope_payload = {
                "status": "computed",
                "method": "ordinary_least_squares_full_window",
                "window_description": "All valid time-separated estimated observations",
                "units": "updrs_points_per_30_days",
                "total_updrs_per_30_days": round(total_slope * 30.0, 3),
                "motor_updrs_per_30_days": round(motor_slope * 30.0, 3),
                "total_updrs_per_day": round(total_slope, 5),
                "motor_updrs_per_day": round(motor_slope, 5),
                "observation_count_used": len(valid),
                "time_span_days": round(xs[-1] - xs[0], 2),
            }
        if any(point.is_partial for point in ordered):
            warnings.append("PARTIAL_OBSERVATION_PRESENT")
            flags.add("PARTIAL_OBSERVATION_PRESENT")
        if stale and last is not None:
            warnings.append(f"STALE_TWIN_DATA: Most recent observation is older than {stale_threshold_days} days.")
            flags.add("STALE_TWIN_DATA")
        return self._TrajectoryResult(
            status="active" if valid else "insufficient_data",
            observed_points=observed_points,
            estimated_points=estimated_points,
            slope=slope_payload,
            coverage={
                "total_observations": len(ordered),
                "estimated_observations": len(estimated_points),
                "observed_updrs_count": len(observed_points),
                "first_observed_at": first.isoformat() if first else None,
                "last_observed_at": last.isoformat() if last else None,
                "time_span_days": round(span, 2),
                "is_stale": stale,
                "stale_threshold_days": stale_threshold_days,
            },
            quality_flags=sorted(flags),
            warnings=warnings,
        )

    def simulate(
        self,
        trajectory: Any,
        *,
        levodopa_dose_change_mg: float,
        physical_therapy_sessions_per_week: int,
        adherence_ratio: float,
        horizon_days: int,
        step_days: int,
    ):
        if not trajectory.estimated_points:
            raise ValueError("Cannot simulate without at least one estimated baseline state.")
        latest = trajectory.estimated_points[-1]
        baseline_total = float(latest["total_updrs"])
        baseline_motor = float(latest["motor_updrs"])
        slope_payload = trajectory.slope
        result = simulate_scenario(
            SimulationRequest(
                initial_total_updrs=baseline_total,
                baseline_slope_per_day=float(slope_payload.get("total_updrs_per_day") or 0.0),
                initial_motor_updrs=baseline_motor,
                levodopa_intensity=float(levodopa_dose_change_mg) / 600.0,
                physical_therapy_intensity=float(physical_therapy_sessions_per_week) / 7.0,
                horizon_days=horizon_days,
                step_days=step_days,
            )
        )
        anchor = datetime.fromisoformat(latest["timestamp"])
        baseline_series: list[dict[str, Any]] = []
        scenario_series: list[dict[str, Any]] = []
        for point in result.points:
            timestamp = (anchor + timedelta(days=point.day)).isoformat()
            baseline_series.append({
                "timestamp": timestamp,
                "day_offset": point.day,
                "source_type": "estimated",
                "total_updrs": round(point.baseline_total_updrs, 2),
                "motor_updrs": _round(point.baseline_motor_updrs),
                "hypothetical": False,
            })
            scenario_series.append({
                "timestamp": timestamp,
                "day_offset": point.day,
                "source_type": "simulated",
                "total_updrs": round(point.simulated_total_updrs, 2),
                "motor_updrs": _round(point.simulated_motor_updrs),
                "total_updrs_ci_low": None,
                "total_updrs_ci_high": None,
                "motor_updrs_ci_low": None,
                "motor_updrs_ci_high": None,
                "hypothetical": True,
            })
        end_base = baseline_series[-1]
        end_scenario = scenario_series[-1]
        return self._SimulationOutput(
            assumptions_version=result.assumptions_version,
            model_version=self.get_model_metadata().model_version,
            hypothetical=True,
            baseline_series=baseline_series,
            scenario_series=scenario_series,
            summary={
                "horizon_days": horizon_days,
                "baseline_end_total_updrs": end_base["total_updrs"],
                "scenario_end_total_updrs": end_scenario["total_updrs"],
                "delta_total_updrs": round(end_scenario["total_updrs"] - end_base["total_updrs"], 2),
                "baseline_end_motor_updrs": end_base["motor_updrs"],
                "scenario_end_motor_updrs": end_scenario["motor_updrs"],
                "delta_motor_updrs": round((end_scenario["motor_updrs"] or 0.0) - (end_base["motor_updrs"] or 0.0), 2),
                "hypothetical": True,
            },
            warnings=list(result.warnings),
        )


def build_real_engine_adapter() -> ArtifactTwinEngineAdapter:
    """Build the fail-closed adapter used by Segment B when configured as real."""

    return ArtifactTwinEngineAdapter(
        os.getenv("PARKTWIN_TOTAL_ARTIFACT_PATH", _DEFAULT_TOTAL_ARTIFACT),
        os.getenv("PARKTWIN_MOTOR_ARTIFACT_PATH", _DEFAULT_MOTOR_ARTIFACT),
    )
