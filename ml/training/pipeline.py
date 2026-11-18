"""Convenience entry point for training from an approved CSV file."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ml.data.loader import load_uci_telemonitoring_csv
from ml.models.training import (
    SUPPORTED_APPROACHES,
    TrainingConfig,
    TrainingRun,
    save_training_run,
    train_models,
)


def train_from_csv(
    data_path: str | Path,
    output_dir: str | Path,
    *,
    config: TrainingConfig | None = None,
    approaches: Sequence[str] | None = None,
) -> TrainingRun:
    frame = load_uci_telemonitoring_csv(data_path)
    run = train_models(
        frame,
        config=config,
        approaches=approaches if approaches is not None else SUPPORTED_APPROACHES,
    )
    save_training_run(run, output_dir)
    return run
