"""Canonical schema for the UCI Parkinson's Telemonitoring Dataset.

The source dataset uses names containing punctuation. ParkTwin keeps those
source names in the alias table and exposes stable snake_case names internally.
"""

from dataclasses import dataclass

SUBJECT_COLUMN = "subject#"
TEST_TIME_COLUMN = "test_time"
MOTOR_UPDRS_COLUMN = "motor_UPDRS"
TOTAL_UPDRS_COLUMN = "total_UPDRS"


@dataclass(frozen=True)
class FeatureSpec:
    """Definition of one speech feature in the internal contract."""

    canonical_name: str
    source_name: str
    non_negative: bool = False


FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("jitter_percent", "Jitter(%)", non_negative=True),
    FeatureSpec("jitter_absolute", "Jitter(Abs)", non_negative=True),
    FeatureSpec("jitter_rap", "Jitter:RAP", non_negative=True),
    FeatureSpec("jitter_ppq5", "Jitter:PPQ5", non_negative=True),
    FeatureSpec("jitter_ddp", "Jitter:DDP", non_negative=True),
    FeatureSpec("shimmer", "Shimmer", non_negative=True),
    FeatureSpec("shimmer_db", "Shimmer(dB)", non_negative=True),
    FeatureSpec("shimmer_apq3", "Shimmer:APQ3", non_negative=True),
    FeatureSpec("shimmer_apq5", "Shimmer:APQ5", non_negative=True),
    FeatureSpec("shimmer_apq11", "Shimmer:APQ11", non_negative=True),
    FeatureSpec("shimmer_dda", "Shimmer:DDA", non_negative=True),
    FeatureSpec("nhr", "NHR", non_negative=True),
    # HNR is measured in decibels and can be negative for noisy signals.
    FeatureSpec("hnr", "HNR"),
    FeatureSpec("rpde", "RPDE", non_negative=True),
    FeatureSpec("dfa", "DFA", non_negative=True),
    FeatureSpec("ppe", "PPE", non_negative=True),
)

FEATURE_NAMES: tuple[str, ...] = tuple(spec.canonical_name for spec in FEATURE_SPECS)
SOURCE_TO_CANONICAL: dict[str, str] = {
    spec.source_name: spec.canonical_name for spec in FEATURE_SPECS
}
CANONICAL_TO_SOURCE: dict[str, str] = {
    spec.canonical_name: spec.source_name for spec in FEATURE_SPECS
}

REQUIRED_SOURCE_COLUMNS: tuple[str, ...] = (
    SUBJECT_COLUMN,
    TEST_TIME_COLUMN,
    *(spec.source_name for spec in FEATURE_SPECS),
)

TARGET_COLUMNS: tuple[str, ...] = (MOTOR_UPDRS_COLUMN, TOTAL_UPDRS_COLUMN)
