"""Synthetic, non-identifiable speech feature fixtures for tests and demos.

No real patient data, personal names, or raw audio are ever stored here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def make_speech_features(severity_step: float = 0.0) -> dict[str, float]:
    """Generate a valid, realistic synthetic 16-metric speech feature vector.

    `severity_step` in [-0.5, 3.0] shifts voice perturbation metrics smoothly.
    """
    s = max(-0.4, min(3.0, severity_step))
    return {
        "jitter_percent": round(0.0045 + 0.0022 * s, 6),
        "jitter_abs": round(0.000032 + 0.000014 * s, 6),
        "jitter_rap": round(0.0023 + 0.0011 * s, 6),
        "jitter_ppq5": round(0.0026 + 0.0012 * s, 6),
        "jitter_ddp": round(0.0069 + 0.0033 * s, 6),
        "shimmer": round(0.028 + 0.014 * s, 6),
        "shimmer_db": round(0.27 + 0.12 * s, 6),
        "shimmer_apq3": round(0.015 + 0.007 * s, 6),
        "shimmer_apq5": round(0.017 + 0.008 * s, 6),
        "shimmer_apq11": round(0.022 + 0.010 * s, 6),
        "shimmer_dda": round(0.045 + 0.021 * s, 6),
        "nhr": round(0.018 + 0.012 * s, 6),
        "hnr": round(max(8.0, 22.8 - 1.7 * s), 4),
        "rpde": round(min(0.95, 0.48 + 0.06 * s), 4),
        "dfa": round(min(1.2, 0.68 + 0.03 * s), 4),
        "ppe": round(min(1.5, 0.19 + 0.05 * s), 4),
    }


def make_partial_speech_features() -> dict[str, float | None]:
    """Generate an explicitly partial feature vector (missing several voice metrics)."""
    return {
        "jitter_percent": 0.0052,
        "jitter_abs": 0.000038,
        "jitter_rap": None,
        "jitter_ppq5": None,
        "jitter_ddp": None,
        "shimmer": 0.031,
        "shimmer_db": 0.29,
        "shimmer_apq3": None,
        "shimmer_apq5": None,
        "shimmer_apq11": None,
        "shimmer_dda": None,
        "nhr": 0.021,
        "hnr": 21.6,
        "rpde": None,
        "dfa": None,
        "ppe": None,
    }


def synthetic_demo_cohorts(now: datetime | None = None) -> list[dict[str, Any]]:
    """Return 3 synthetic pseudonymous twin cohorts for reproducible local demos."""
    anchor = now or datetime.now(timezone.utc)
    return [
        {
            "external_reference": "SYN-PT-1001",
            "description": "Gradual worsening progression over 10 weeks",
            "observations": [
                {
                    "offset_days": -70,
                    "severity": 0.0,
                    "observed_total_updrs": 29.5,
                    "observed_motor_updrs": 22.0,
                },
                {
                    "offset_days": -56,
                    "severity": 0.35,
                    "observed_total_updrs": None,
                    "observed_motor_updrs": None,
                },
                {
                    "offset_days": -42,
                    "severity": 0.7,
                    "observed_total_updrs": 33.0,
                    "observed_motor_updrs": 24.8,
                },
                {
                    "offset_days": -28,
                    "severity": 1.05,
                    "observed_total_updrs": None,
                    "observed_motor_updrs": None,
                },
                {
                    "offset_days": -14,
                    "severity": 1.4,
                    "observed_total_updrs": 36.2,
                    "observed_motor_updrs": 27.1,
                },
                {
                    "offset_days": -3,
                    "severity": 1.75,
                    "observed_total_updrs": None,
                    "observed_motor_updrs": None,
                },
            ],
            "allow_partial": False,
        },
        {
            "external_reference": "SYN-PT-2004",
            "description": "Stable trajectory with mild week-to-week fluctuation",
            "observations": [
                {
                    "offset_days": -60,
                    "severity": 0.25,
                    "observed_total_updrs": 31.0,
                    "observed_motor_updrs": 23.2,
                },
                {
                    "offset_days": -40,
                    "severity": 0.20,
                    "observed_total_updrs": None,
                    "observed_motor_updrs": None,
                },
                {
                    "offset_days": -20,
                    "severity": 0.30,
                    "observed_total_updrs": 31.4,
                    "observed_motor_updrs": 23.5,
                },
                {
                    "offset_days": -5,
                    "severity": 0.22,
                    "observed_total_updrs": None,
                    "observed_motor_updrs": None,
                },
            ],
            "allow_partial": False,
        },
        {
            "external_reference": "SYN-PT-3009",
            "description": "Partial baseline awaiting full voice observation (insufficient_data)",
            "observations": [
                {
                    "offset_days": -45,
                    "severity": None,
                    "observed_total_updrs": 28.0,
                    "observed_motor_updrs": 21.0,
                }
            ],
            "allow_partial": True,
        },
    ]


def timestamp_offset(anchor: datetime, offset_days: int) -> datetime:
    return (anchor + timedelta(days=offset_days)).replace(microsecond=0)
