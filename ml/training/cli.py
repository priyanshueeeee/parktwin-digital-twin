"""Command-line entry point: python -m ml.training.cli."""

from __future__ import annotations

import argparse

from ml.models.training import SUPPORTED_APPROACHES, TrainingConfig
from ml.training.pipeline import train_from_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ParkTwin Segment A models")
    parser.add_argument("--data", required=True, help="approved UCI telemonitoring CSV path")
    parser.add_argument("--output", required=True, help="artifact output directory")
    parser.add_argument("--target", default="total_UPDRS", choices=("total_UPDRS", "motor_UPDRS"))
    parser.add_argument("--feature-mode", default="raw_plus_derived", choices=("raw", "derived", "raw_plus_derived"))
    parser.add_argument("--split", default="future", choices=("future", "grouped_patient"))
    parser.add_argument("--approach", action="append", choices=SUPPORTED_APPROACHES)
    args = parser.parse_args()
    config = TrainingConfig(
        target=args.target,
        feature_mode=args.feature_mode,
        split_strategy=args.split,
    )
    run = train_from_csv(
        args.data,
        args.output,
        config=config,
        approaches=args.approach or SUPPORTED_APPROACHES,
    )
    for metric in run.metrics:
        print(
            f"{metric.approach}: MAE={metric.mae:.4f} RMSE={metric.rmse:.4f} "
            f"R2={metric.r2:.4f} test_rows={metric.test_rows}"
        )


if __name__ == "__main__":
    main()
