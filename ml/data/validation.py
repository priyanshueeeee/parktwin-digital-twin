"""Validation and normalization for source dataset rows."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Iterable, Mapping

from .schema import (
    FEATURE_SPECS,
    MOTOR_UPDRS_COLUMN,
    SOURCE_TO_CANONICAL,
    SUBJECT_COLUMN,
    TARGET_COLUMNS,
    TEST_TIME_COLUMN,
    TOTAL_UPDRS_COLUMN,
)


@dataclass(frozen=True)
class ValidationIssue:
    """A machine-readable validation problem."""

    field: str
    code: str
    message: str
    row_index: int | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Dataset validation result with no mutation of the input rows."""

    row_count: int
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _validate_number(
    row: Mapping[str, Any],
    field: str,
    *,
    row_index: int | None,
    issues: list[ValidationIssue],
    non_negative: bool = False,
    updrs: bool = False,
) -> None:
    if field not in row:
        issues.append(
            ValidationIssue(field, "MISSING_FIELD", "required field is missing", row_index)
        )
        return

    value = row[field]
    if not _is_number(value) or not math.isfinite(float(value)):
        issues.append(
            ValidationIssue(field, "INVALID_NUMBER", "value must be a finite number", row_index)
        )
        return

    numeric_value = float(value)
    if non_negative and numeric_value < 0:
        issues.append(
            ValidationIssue(field, "NEGATIVE_VALUE", "value must be non-negative", row_index)
        )
    if updrs and not 0 <= numeric_value <= 199:
        issues.append(
            ValidationIssue(field, "OUT_OF_RANGE", "UPDRS must be between 0 and 199", row_index)
        )


def canonicalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy using stable internal feature names.

    Non-feature columns are preserved. Unknown columns are preserved so the
    caller can decide whether they are allowed in a specific pipeline stage.
    """

    canonical = dict(row)
    for source_name, canonical_name in SOURCE_TO_CANONICAL.items():
        if source_name in row:
            canonical[canonical_name] = row[source_name]
            del canonical[source_name]
    return canonical


def validate_row(
    row: Mapping[str, Any],
    *,
    row_index: int | None = None,
    require_targets: bool = False,
) -> tuple[ValidationIssue, ...]:
    """Validate one source-shaped dataset row."""

    issues: list[ValidationIssue] = []
    _validate_number(
        row,
        SUBJECT_COLUMN,
        row_index=row_index,
        issues=issues,
    )
    if SUBJECT_COLUMN in row and _is_number(row[SUBJECT_COLUMN]) and float(row[SUBJECT_COLUMN]) <= 0:
        issues.append(
            ValidationIssue(
                SUBJECT_COLUMN,
                "OUT_OF_RANGE",
                "subject identifier must be positive",
                row_index,
            )
        )

    _validate_number(
        row,
        TEST_TIME_COLUMN,
        row_index=row_index,
        issues=issues,
    )

    for spec in FEATURE_SPECS:
        _validate_number(
            row,
            spec.source_name,
            row_index=row_index,
            issues=issues,
            non_negative=spec.non_negative,
        )

    for target in TARGET_COLUMNS:
        if target not in row:
            if require_targets:
                issues.append(
                    ValidationIssue(target, "MISSING_FIELD", "training target is missing", row_index)
                )
            continue
        _validate_number(
            row,
            target,
            row_index=row_index,
            issues=issues,
            updrs=True,
        )

    return tuple(issues)


def validate_dataset(
    rows: Iterable[Mapping[str, Any]],
    *,
    require_targets: bool = True,
) -> ValidationReport:
    """Validate rows and detect exact duplicate observations.

    Multiple recordings may legitimately share a patient's ``test_time`` in
    the source dataset, so patient/time alone is not a unique row key.
    """

    issues: list[ValidationIssue] = []
    row_count = 0
    seen_rows: dict[tuple[tuple[str, str], ...], int] = {}

    for row_count, row in enumerate(rows, start=1):
        row_index = row_count - 1
        issues.extend(validate_row(row, row_index=row_index, require_targets=require_targets))

        row_key = tuple(sorted((str(key), repr(value)) for key, value in row.items()))
        if row_key in seen_rows:
            issues.append(
                ValidationIssue(
                    "row",
                    "DUPLICATE_ROW",
                    f"duplicates row {seen_rows[row_key]}",
                    row_index,
                )
            )
        else:
            seen_rows[row_key] = row_index

    return ValidationReport(row_count=row_count, issues=tuple(issues))
