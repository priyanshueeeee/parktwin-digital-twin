"""Approved CSV loading for the Parkinson's telemonitoring training data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .validation import ValidationIssue, validate_dataset


@dataclass(frozen=True)
class DatasetValidationError(ValueError):
    """Raised when an approved training file fails the internal contract."""

    path: str
    issues: tuple[ValidationIssue, ...]

    def __str__(self) -> str:
        preview = "; ".join(
            f"row={issue.row_index} field={issue.field} code={issue.code}"
            for issue in self.issues[:5]
        )
        suffix = "" if len(self.issues) <= 5 else f"; ... ({len(self.issues)} total)"
        return f"dataset validation failed for {self.path}: {preview}{suffix}"


def load_uci_telemonitoring_csv(path: str | Path) -> pd.DataFrame:
    """Load and validate the UCI telemonitoring CSV without mutating it."""

    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    frame = pd.read_csv(file_path)
    report = validate_dataset(frame.to_dict(orient="records"), require_targets=True)
    if not report.is_valid:
        raise DatasetValidationError(str(file_path), report.issues)
    return frame.copy()


def load_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Load already parsed rows through the same validation contract."""

    report = validate_dataset(rows, require_targets=True)
    if not report.is_valid:
        raise DatasetValidationError("<rows>", report.issues)
    return pd.DataFrame(rows).copy()
