from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from ml.data.schema import FEATURE_SPECS, MOTOR_UPDRS_COLUMN, SUBJECT_COLUMN, TEST_TIME_COLUMN, TOTAL_UPDRS_COLUMN
from ml.models.training import (
    TrainingConfig,
    build_design_matrix,
    future_time_split,
    grouped_patient_split,
    load_model_artifact,
    save_training_run,
    train_models,
)


def synthetic_frame(subjects: int = 6, observations_per_subject: int = 10) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for subject in range(1, subjects + 1):
        for test_time in range(observations_per_subject):
            base = 0.01 * subject + 0.001 * test_time
            row: dict[str, float | int] = {
                SUBJECT_COLUMN: subject,
                TEST_TIME_COLUMN: float(test_time),
                MOTOR_UPDRS_COLUMN: 10.0 + subject + 0.25 * test_time,
                TOTAL_UPDRS_COLUMN: 20.0 + 1.5 * subject + 0.35 * test_time,
            }
            row.update(
                {
                    spec.source_name: base + 0.0001 * index
                    for index, spec in enumerate(FEATURE_SPECS, start=1)
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


class TrainingTests(unittest.TestCase):
    def test_grouped_split_has_no_patient_overlap(self) -> None:
        split = grouped_patient_split(synthetic_frame(), test_fraction=0.25, random_state=7)

        self.assertTrue(set(split.train[SUBJECT_COLUMN]).isdisjoint(set(split.test[SUBJECT_COLUMN])))

    def test_future_split_keeps_test_rows_after_training_rows(self) -> None:
        split = future_time_split(synthetic_frame(), test_fraction=0.2)

        for subject in split.test[SUBJECT_COLUMN].unique():
            train_times = split.train.loc[split.train[SUBJECT_COLUMN] == subject, TEST_TIME_COLUMN]
            test_times = split.test.loc[split.test[SUBJECT_COLUMN] == subject, TEST_TIME_COLUMN]
            self.assertLess(max(train_times), min(test_times))

    def test_feature_modes_have_distinct_versioned_matrices(self) -> None:
        frame = synthetic_frame(subjects=2, observations_per_subject=3)

        raw, raw_version = build_design_matrix(frame, feature_mode="raw")
        derived, derived_version = build_design_matrix(frame, feature_mode="derived")
        combined, combined_version = build_design_matrix(frame, feature_mode="raw_plus_derived")

        self.assertEqual(len(raw.columns), 16)
        self.assertGreater(len(derived.columns), 0)
        self.assertGreater(len(combined.columns), len(raw.columns))
        self.assertNotEqual(raw_version, derived_version)
        self.assertNotEqual(derived_version, combined_version)

    def test_trains_point_and_quantile_artifacts_and_publishes_them(self) -> None:
        frame = synthetic_frame()
        run = train_models(
            frame,
            config=TrainingConfig(split_strategy="future", feature_mode="raw_plus_derived"),
            approaches=("elastic_net", "random_forest", "quantile_regression"),
        )

        self.assertEqual(set(run.artifacts), {"elastic_net", "random_forest", "quantile_regression"})
        self.assertEqual(len(run.metrics), 3)
        quantile_metrics = next(metric for metric in run.metrics if metric.approach == "quantile_regression")
        self.assertIsNotNone(quantile_metrics.interval_coverage)
        self.assertIsNotNone(quantile_metrics.mean_interval_width)

        with tempfile.TemporaryDirectory() as directory:
            manifest = save_training_run(run, Path(directory))
            artifact = load_model_artifact(Path(directory) / "elastic_net-total_UPDRS.joblib")
            predictions = artifact.predict_frame(run.split.test)

            self.assertTrue(manifest.exists())
            self.assertEqual(len(predictions["point"]), len(run.split.test))
            self.assertTrue((Path(directory) / "quantile_regression-total_UPDRS.joblib").exists())


if __name__ == "__main__":
    unittest.main()
