"""Deterministic derived features built from the 16 source voice metrics.

Derived features are candidate inputs for model experiments. They are not
clinical biomarkers and must be evaluated with patient-level validation before
being promoted to a production model artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

from ml.data.schema import FEATURE_NAMES
from ml.data.validation import canonicalize_row

_EPSILON = 1e-12
_JITTER_FEATURES = (
    "jitter_percent",
    "jitter_absolute",
    "jitter_rap",
    "jitter_ppq5",
    "jitter_ddp",
)
_SHIMMER_FEATURES = (
    "shimmer",
    "shimmer_db",
    "shimmer_apq3",
    "shimmer_apq5",
    "shimmer_apq11",
    "shimmer_dda",
)


@dataclass(frozen=True)
class FeatureVector:
    """Versioned feature vector with quality metadata."""

    features: Mapping[str, float]
    feature_set_version: str = "feature-set-v1-derived-v1"
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values)


def _standard_deviation(values: tuple[float, ...], mean: float) -> float:
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _require_numeric_features(row: Mapping[str, Any]) -> dict[str, float]:
    canonical = canonicalize_row(row)
    missing = [name for name in FEATURE_NAMES if name not in canonical]
    if missing:
        raise ValueError(f"missing canonical features: {', '.join(missing)}")

    values: dict[str, float] = {}
    for name in FEATURE_NAMES:
        value = canonical[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {name} must be numeric")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"feature {name} must be finite")
        values[name] = numeric_value
    return values


def build_feature_vector(
    row: Mapping[str, Any],
    *,
    include_raw: bool = True,
    include_derived: bool = True,
) -> FeatureVector:
    """Build a stable raw-plus-derived feature vector without mutating input."""

    if not include_raw and not include_derived:
        raise ValueError("at least one of include_raw or include_derived must be true")
    raw = _require_numeric_features(row)
    output: dict[str, float] = dict(raw) if include_raw else {}

    if include_derived:
        jitter_values = tuple(raw[name] for name in _JITTER_FEATURES)
        shimmer_values = tuple(raw[name] for name in _SHIMMER_FEATURES)
        jitter_mean = _mean(jitter_values)
        shimmer_mean = _mean(shimmer_values)
        output.update(
            {
                "jitter_family_mean": jitter_mean,
                "jitter_family_std": _standard_deviation(jitter_values, jitter_mean),
                "shimmer_family_mean": shimmer_mean,
                "shimmer_family_std": _standard_deviation(shimmer_values, shimmer_mean),
                "perturbation_ratio": math.log1p(jitter_mean / max(shimmer_mean, _EPSILON)),
                "harmonicity_ratio": raw["hnr"] / max(1.0 + raw["nhr"], _EPSILON),
                "nonlinear_complexity_mean": _mean((raw["rpde"], raw["dfa"], raw["ppe"])),
                "log1p_jitter_percent": math.log1p(raw["jitter_percent"]),
                "log1p_shimmer": math.log1p(raw["shimmer"]),
            }
        )

    flags = ("DERIVED_FEATURES_INCLUDED",) if include_derived else ()
    if include_raw and include_derived:
        version = "feature-set-v1-derived-v1"
    elif include_raw:
        version = "feature-set-v1-raw-v1"
    else:
        version = "feature-set-v1-derived-only-v1"
    return FeatureVector(features=output, feature_set_version=version, quality_flags=flags)
