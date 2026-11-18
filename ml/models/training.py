"""Leakage-aware training, evaluation, and artifact publication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from math import ceil
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, QuantileRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.data.schema import SUBJECT_COLUMN, TEST_TIME_COLUMN, TOTAL_UPDRS_COLUMN
from ml.features.engineering import FeatureVector, build_feature_vector


APPROVED_DATASET_SOURCE = "UCI Parkinson's Telemonitoring Dataset"
SUPPORTED_APPROACHES = (
    "elastic_net",
    "random_forest",
    "hist_gradient_boosting",
    "quantile_regression",
)


@dataclass(frozen=True)
class TrainingConfig:
    target: str = TOTAL_UPDRS_COLUMN
    feature_mode: str = "raw_plus_derived"
    split_strategy: str = "future"
    test_fraction: float = 0.20
    random_state: int = 42
    model_version: str = "parktwin-segment-a-v1"
    dataset_source: str = APPROVED_DATASET_SOURCE


@dataclass(frozen=True)
class DatasetSplit:
    train: pd.DataFrame
    test: pd.DataFrame
    strategy: str


@dataclass(frozen=True)
class EvaluationMetrics:
    approach: str
    target: str
    split_strategy: str
    train_rows: int
    test_rows: int
    train_patients: int
    test_patients: int
    mae: float
    rmse: float
    r2: float
    interval_coverage: float | None = None
    mean_interval_width: float | None = None


@dataclass(frozen=True)
class ModelArtifactMetadata:
    model_version: str
    approach: str
    target: str
    feature_mode: str
    feature_columns: tuple[str, ...]
    feature_set_version: str
    dataset_source: str
    dataset_checksum: str
    split_strategy: str
    train_rows: int
    test_rows: int
    train_patients: int
    test_patients: int
    metrics: EvaluationMetrics
    created_at: str
    non_diagnostic: bool = True


@dataclass
class ModelArtifact:
    """Serializable model plus all information needed for inference."""

    metadata: ModelArtifactMetadata
    estimators: dict[str, Any]

    def predict_frame(self, frame: pd.DataFrame) -> dict[str, np.ndarray]:
        matrix, _ = build_design_matrix(frame, feature_mode=self.metadata.feature_mode)
        return {name: _safe_predict(estimator, matrix) for name, estimator in self.estimators.items()}

    def predict_rows(self, rows: Iterable[Mapping[str, Any]]) -> dict[str, np.ndarray]:
        return self.predict_frame(pd.DataFrame(list(rows)))


@dataclass
class TrainingRun:
    config: TrainingConfig
    split: DatasetSplit
    artifacts: dict[str, ModelArtifact]
    metrics: tuple[EvaluationMetrics, ...]


def _validate_fraction(value: float) -> None:
    if not 0 < value < 0.5:
        raise ValueError("test_fraction must be greater than 0 and less than 0.5")


def grouped_patient_split(
    frame: pd.DataFrame,
    *,
    test_fraction: float = 0.20,
    random_state: int = 42,
) -> DatasetSplit:
    """Hold out complete patients so no patient leaks across partitions."""

    _validate_fraction(test_fraction)
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_fraction, random_state=random_state)
    train_indices, test_indices = next(splitter.split(frame, groups=frame[SUBJECT_COLUMN]))
    return DatasetSplit(
        train=frame.iloc[train_indices].copy(),
        test=frame.iloc[test_indices].copy(),
        strategy="grouped_patient",
    )


def future_time_split(
    frame: pd.DataFrame,
    *,
    test_fraction: float = 0.20,
) -> DatasetSplit:
    """Hold out each patient's latest observations as a future block."""

    _validate_fraction(test_fraction)
    train_indices: list[Any] = []
    test_indices: list[Any] = []
    for _, group in frame.sort_values([SUBJECT_COLUMN, TEST_TIME_COLUMN]).groupby(SUBJECT_COLUMN, sort=False):
        ordered_indices = list(group.index)
        if len(ordered_indices) < 2:
            train_indices.extend(ordered_indices)
            continue
        test_count = max(1, min(len(ordered_indices) - 1, ceil(len(ordered_indices) * test_fraction)))
        train_indices.extend(ordered_indices[:-test_count])
        test_indices.extend(ordered_indices[-test_count:])
    if not test_indices:
        raise ValueError("future split requires at least one patient with two observations")
    return DatasetSplit(
        train=frame.loc[train_indices].copy(),
        test=frame.loc[test_indices].copy(),
        strategy="future_time",
    )


def make_split(frame: pd.DataFrame, config: TrainingConfig) -> DatasetSplit:
    if config.split_strategy == "grouped_patient":
        return grouped_patient_split(
            frame,
            test_fraction=config.test_fraction,
            random_state=config.random_state,
        )
    if config.split_strategy == "future":
        return future_time_split(frame, test_fraction=config.test_fraction)
    raise ValueError("split_strategy must be grouped_patient or future")


def build_design_matrix(
    frame: pd.DataFrame,
    *,
    feature_mode: str = "raw_plus_derived",
) -> tuple[pd.DataFrame, str]:
    """Build a deterministic matrix and return its feature-set version."""

    if feature_mode not in {"raw", "derived", "raw_plus_derived"}:
        raise ValueError("feature_mode must be raw, derived, or raw_plus_derived")
    include_raw = feature_mode in {"raw", "raw_plus_derived"}
    include_derived = feature_mode in {"derived", "raw_plus_derived"}
    vectors: list[FeatureVector] = [
        build_feature_vector(row, include_raw=include_raw, include_derived=include_derived)
        for row in frame.to_dict(orient="records")
    ]
    if not vectors:
        raise ValueError("cannot build a design matrix from zero rows")
    columns = tuple(vectors[0].features.keys())
    matrix = pd.DataFrame([{column: vector.features[column] for column in columns} for vector in vectors])
    versions = {vector.feature_set_version for vector in vectors}
    if len(versions) != 1:
        raise ValueError("feature vectors returned inconsistent feature-set versions")
    return matrix, vectors[0].feature_set_version


def _dataset_checksum(frame: pd.DataFrame) -> str:
    canonical = frame.sort_values(list(frame.columns)).to_csv(index=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _make_estimator(approach: str, *, random_state: int, quantile: float | None = None) -> Any:
    if approach == "elastic_net":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", ElasticNet(alpha=0.05, l1_ratio=0.5, max_iter=10_000, random_state=random_state)),
            ]
        )
    if approach == "random_forest":
        return RandomForestRegressor(
            n_estimators=200,
            min_samples_leaf=2,
            random_state=random_state,
            n_jobs=1,
        )
    if approach == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(
            max_iter=200,
            learning_rate=0.05,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=random_state,
        )
    if approach == "quantile_regression":
        if quantile is None:
            raise ValueError("quantile regression requires a quantile")
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", QuantileRegressor(quantile=quantile, alpha=0.01, solver="highs")),
            ]
        )
    raise ValueError(f"unsupported trainable approach: {approach}")


def _safe_predict(estimator: Any, matrix: pd.DataFrame) -> np.ndarray:
    """Predict while converting numerical warnings into a hard finite check."""

    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        prediction = np.asarray(estimator.predict(matrix), dtype=float)
    if not np.isfinite(prediction).all():
        raise RuntimeError("model prediction produced a non-finite value")
    return prediction


def _fit_artifact(
    approach: str,
    *,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    feature_columns: tuple[str, ...],
    feature_set_version: str,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    config: TrainingConfig,
    dataset_checksum: str,
) -> tuple[ModelArtifact, EvaluationMetrics]:
    if approach == "quantile_regression":
        quantiles = {"lower": 0.10, "median": 0.50, "upper": 0.90}
        estimators = {
            name: _make_estimator(
                approach,
                random_state=config.random_state,
                quantile=quantile,
            ).fit(x_train, y_train)
            for name, quantile in quantiles.items()
        }
        predictions = {name: _safe_predict(estimator, x_test) for name, estimator in estimators.items()}
        point_prediction = predictions["median"]
        coverage = float(np.mean((y_test.to_numpy() >= predictions["lower"]) & (y_test.to_numpy() <= predictions["upper"])))
        interval_width = float(np.mean(predictions["upper"] - predictions["lower"]))
    else:
        estimator = _make_estimator(approach, random_state=config.random_state).fit(x_train, y_train)
        estimators = {"point": estimator}
        point_prediction = _safe_predict(estimator, x_test)
        coverage = None
        interval_width = None

    metrics = EvaluationMetrics(
        approach=approach,
        target=config.target,
        split_strategy=config.split_strategy,
        train_rows=len(train_frame),
        test_rows=len(test_frame),
        train_patients=train_frame[SUBJECT_COLUMN].nunique(),
        test_patients=test_frame[SUBJECT_COLUMN].nunique(),
        mae=float(mean_absolute_error(y_test, point_prediction)),
        rmse=float(np.sqrt(mean_squared_error(y_test, point_prediction))),
        r2=float(r2_score(y_test, point_prediction)),
        interval_coverage=coverage,
        mean_interval_width=interval_width,
    )
    metadata = ModelArtifactMetadata(
        model_version=config.model_version,
        approach=approach,
        target=config.target,
        feature_mode=config.feature_mode,
        feature_columns=feature_columns,
        feature_set_version=feature_set_version,
        dataset_source=config.dataset_source,
        dataset_checksum=dataset_checksum,
        split_strategy=config.split_strategy,
        train_rows=len(train_frame),
        test_rows=len(test_frame),
        train_patients=train_frame[SUBJECT_COLUMN].nunique(),
        test_patients=test_frame[SUBJECT_COLUMN].nunique(),
        metrics=metrics,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return ModelArtifact(metadata=metadata, estimators=estimators), metrics


def train_models(
    frame: pd.DataFrame,
    *,
    config: TrainingConfig | None = None,
    approaches: Sequence[str] = SUPPORTED_APPROACHES,
) -> TrainingRun:
    """Train and evaluate one or more registered approaches."""

    config = config or TrainingConfig()
    unknown = set(approaches) - set(SUPPORTED_APPROACHES)
    if unknown:
        raise ValueError(f"unsupported approaches: {', '.join(sorted(unknown))}")
    if config.target not in frame.columns:
        raise ValueError(f"target column is missing: {config.target}")

    split = make_split(frame, config)
    x_train, feature_set_version = build_design_matrix(split.train, feature_mode=config.feature_mode)
    x_test, test_feature_set_version = build_design_matrix(split.test, feature_mode=config.feature_mode)
    if tuple(x_train.columns) != tuple(x_test.columns) or feature_set_version != test_feature_set_version:
        raise ValueError("train and test feature matrices do not share the same feature contract")
    y_train = split.train[config.target].astype(float)
    y_test = split.test[config.target].astype(float)
    checksum = _dataset_checksum(frame)
    artifacts: dict[str, ModelArtifact] = {}
    metrics: list[EvaluationMetrics] = []
    for approach in approaches:
        artifact, evaluation = _fit_artifact(
            approach,
            x_train=x_train,
            y_train=y_train,
            feature_columns=tuple(x_train.columns),
            feature_set_version=feature_set_version,
            x_test=x_test,
            y_test=y_test,
            train_frame=split.train,
            test_frame=split.test,
            config=config,
            dataset_checksum=checksum,
        )
        artifacts[approach] = artifact
        metrics.append(evaluation)
    return TrainingRun(config=config, split=split, artifacts=artifacts, metrics=tuple(metrics))


def save_training_run(run: TrainingRun, output_dir: str | Path) -> Path:
    """Write joblib artifacts and a human-readable metrics manifest."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    for approach, artifact in run.artifacts.items():
        joblib.dump(artifact, output_path / f"{approach}-{run.config.target}.joblib")
    manifest = {
        "config": asdict(run.config),
        "metrics": [asdict(metric) for metric in run.metrics],
        "artifacts": {
            approach: asdict(artifact.metadata) for approach, artifact in run.artifacts.items()
        },
        "non_diagnostic": True,
    }
    manifest_path = output_path / "training-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    return manifest_path


def load_model_artifact(path: str | Path) -> ModelArtifact:
    """Load one artifact and check that it is the expected artifact type."""

    artifact = joblib.load(path)
    if not isinstance(artifact, ModelArtifact):
        raise TypeError(f"artifact at {path} is not a ParkTwin ModelArtifact")
    return artifact
