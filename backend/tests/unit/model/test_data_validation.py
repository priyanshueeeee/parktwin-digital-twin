from __future__ import annotations

import math
import unittest

from ml.data.schema import FEATURE_SPECS, MOTOR_UPDRS_COLUMN, SUBJECT_COLUMN, TEST_TIME_COLUMN, TOTAL_UPDRS_COLUMN
from ml.data.validation import canonicalize_row, validate_dataset, validate_row


def valid_row(subject: int = 1, test_time: float = 0.0) -> dict[str, float | int]:
    row: dict[str, float | int] = {
        SUBJECT_COLUMN: subject,
        TEST_TIME_COLUMN: test_time,
        MOTOR_UPDRS_COLUMN: 20.0,
        TOTAL_UPDRS_COLUMN: 25.0,
    }
    row.update({spec.source_name: 0.1 for spec in FEATURE_SPECS})
    return row


class DataValidationTests(unittest.TestCase):
    def test_valid_training_row_has_no_issues(self) -> None:
        self.assertEqual(validate_row(valid_row(), require_targets=True), ())

    def test_missing_feature_is_reported(self) -> None:
        row = valid_row()
        del row[FEATURE_SPECS[0].source_name]

        issues = validate_row(row, require_targets=True)

        missing_issues = [issue for issue in issues if issue.code == "MISSING_FIELD"]
        self.assertEqual(len(missing_issues), 1)
        self.assertEqual(missing_issues[0].field, FEATURE_SPECS[0].source_name)

    def test_invalid_and_out_of_range_values_are_reported(self) -> None:
        row = valid_row()
        row["Jitter(%)"] = math.nan
        row["Shimmer"] = -0.1
        row[TOTAL_UPDRS_COLUMN] = 200.0

        issues = validate_row(row, require_targets=True)

        self.assertTrue(any(issue.code == "INVALID_NUMBER" for issue in issues))
        self.assertTrue(any(issue.code == "NEGATIVE_VALUE" for issue in issues))
        self.assertTrue(any(issue.code == "OUT_OF_RANGE" for issue in issues))

    def test_dataset_detects_duplicate_patient_time(self) -> None:
        report = validate_dataset([valid_row(), valid_row()], require_targets=True)

        self.assertFalse(report.is_valid)
        self.assertEqual(report.row_count, 2)
        self.assertTrue(any(issue.code == "DUPLICATE_OBSERVATION" for issue in report.issues))

    def test_inference_rows_may_omit_targets(self) -> None:
        row = valid_row()
        row.pop(MOTOR_UPDRS_COLUMN)
        row.pop(TOTAL_UPDRS_COLUMN)

        self.assertEqual(validate_row(row, require_targets=False), ())

    def test_canonicalize_row_preserves_non_feature_columns(self) -> None:
        row = valid_row()
        row["extra_metadata"] = "kept"

        canonical = canonicalize_row(row)

        self.assertEqual(canonical["jitter_percent"], 0.1)
        self.assertNotIn("Jitter(%)", canonical)
        self.assertEqual(canonical["extra_metadata"], "kept")


if __name__ == "__main__":
    unittest.main()
