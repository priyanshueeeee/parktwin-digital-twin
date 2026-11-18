"""Research acoustic feature extraction from monophonic speech waveforms.

The implementation is deterministic and evaluation-ready, but it is not a
clinical validation claim. RPDE and PPE are implemented as transparent
entropy-based approximations and must be compared with an approved reference
extractor before model promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

import numpy as np

from ml.data.schema import FEATURE_NAMES

from .audio import decode_pcm_wav, VoiceDataPoint


@dataclass(frozen=True)
class FeatureValidationItem:
    feature: str
    absolute_error: float
    relative_error: float
    passed: bool


@dataclass(frozen=True)
class FeatureValidationReport:
    method: str
    items: tuple[FeatureValidationItem, ...]

    @property
    def is_valid(self) -> bool:
        return all(item.passed for item in self.items)


def _frame_signal(samples: np.ndarray, frame_size: int, hop_size: int) -> list[np.ndarray]:
    if len(samples) < frame_size:
        padded = np.pad(samples, (0, frame_size - len(samples)))
        return [padded]
    return [samples[start : start + frame_size] for start in range(0, len(samples) - frame_size + 1, hop_size)]


def _pitch_periods(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    frame_size: int = 2048,
    hop_size: int = 512,
    min_hz: float = 70.0,
    max_hz: float = 400.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    periods: list[float] = []
    periodicity: list[float] = []
    amplitudes: list[float] = []
    min_lag = max(1, int(sample_rate_hz / max_hz))
    max_lag = min(frame_size - 1, int(sample_rate_hz / min_hz))
    for frame in _frame_signal(samples, frame_size, hop_size):
        centered = frame - np.mean(frame)
        amplitude = float(np.sqrt(np.mean(centered * centered)))
        amplitudes.append(amplitude)
        if amplitude < 1e-4:
            continue
        autocorrelation = np.correlate(centered, centered, mode="full")[frame_size - 1 :]
        normalizer = float(autocorrelation[0])
        if normalizer <= 0:
            continue
        search = autocorrelation[min_lag : max_lag + 1]
        if len(search) == 0:
            continue
        lag = min_lag + int(np.argmax(search))
        strength = float(autocorrelation[lag] / normalizer)
        if strength < 0.25:
            continue
        periods.append(lag / sample_rate_hz)
        periodicity.append(max(0.0, min(1.0, strength)))
    return np.asarray(periods), np.asarray(periodicity), np.asarray(amplitudes)


def _local_perturbation(values: np.ndarray, window: int) -> float:
    if len(values) < window:
        return 0.0
    half = window // 2
    errors: list[float] = []
    for index in range(half, len(values) - half):
        local_mean = float(np.mean(values[index - half : index + half + 1]))
        errors.append(abs(float(values[index]) - local_mean))
    return float(np.mean(errors) / max(float(np.mean(values)), 1e-12)) if errors else 0.0


def _permutation_entropy(values: np.ndarray, order: int = 3) -> float:
    if len(values) < order:
        return 0.0
    counts: dict[tuple[int, ...], int] = {}
    for index in range(len(values) - order + 1):
        pattern = tuple(np.argsort(values[index : index + order], kind="stable"))
        counts[pattern] = counts.get(pattern, 0) + 1
    probabilities = np.asarray(list(counts.values()), dtype=float)
    probabilities /= probabilities.sum()
    entropy = -float(np.sum(probabilities * np.log(probabilities)))
    return entropy / max(math.log(math.factorial(order)), 1e-12)


def _detrended_fluctuation(values: np.ndarray) -> float:
    if len(values) < 8:
        return 0.5
    profile = np.cumsum(values - np.mean(values))
    scales = np.asarray([scale for scale in (4, 8, 16, 32) if scale < len(values)], dtype=int)
    fluctuations: list[float] = []
    valid_scales: list[int] = []
    for scale in scales:
        chunks = len(profile) // int(scale)
        if chunks < 1:
            continue
        residuals: list[float] = []
        x = np.arange(int(scale), dtype=float)
        for chunk in range(chunks):
            segment = profile[chunk * scale : (chunk + 1) * scale]
            coefficients = np.polyfit(x, segment, 1)
            residuals.extend(segment - np.polyval(coefficients, x))
        fluctuations.append(float(np.sqrt(np.mean(np.square(residuals)))))
        valid_scales.append(int(scale))
    if len(fluctuations) < 2 or any(value <= 0 for value in fluctuations):
        return 0.5
    slope = np.polyfit(np.log(valid_scales), np.log(fluctuations), 1)[0]
    return float(max(0.0, min(2.0, slope)))


def _pitch_period_entropy(periods: np.ndarray) -> float:
    if len(periods) < 3:
        return 0.0
    histogram, _ = np.histogram(periods, bins=20)
    probabilities = histogram[histogram > 0].astype(float)
    probabilities /= probabilities.sum()
    return float(-np.sum(probabilities * np.log(probabilities)) / math.log(20))


def extract_biomedical_features(samples: Sequence[float], sample_rate_hz: int) -> dict[str, float]:
    """Extract the 16 research acoustic features from a waveform."""

    signal = np.asarray(samples, dtype=float)
    if signal.ndim != 1 or len(signal) < sample_rate_hz // 2:
        raise ValueError("at least 0.5 seconds of mono audio is required")
    periods, periodicity, amplitudes = _pitch_periods(signal, sample_rate_hz)
    if len(periods) < 3:
        raise ValueError("insufficient periodic voiced frames for biomedical features")

    mean_period = float(np.mean(periods))
    jitter_absolute = float(np.mean(np.abs(np.diff(periods))))
    jitter_percent = jitter_absolute / max(mean_period, 1e-12)
    jitter_rap = _local_perturbation(periods, 3)
    jitter_ppq5 = _local_perturbation(periods, 5)
    jitter_ddp = 3.0 * jitter_rap

    usable_amplitudes = amplitudes[amplitudes > 1e-4]
    shimmer = float(np.mean(np.abs(np.diff(usable_amplitudes))) / max(float(np.mean(usable_amplitudes)), 1e-12))
    shimmer_db = float(
        np.mean(
            np.abs(
                20.0
                * np.log10(
                    np.maximum(usable_amplitudes[1:], 1e-12)
                    / np.maximum(usable_amplitudes[:-1], 1e-12)
                )
            )
        )
    )
    shimmer_apq3 = _local_perturbation(usable_amplitudes, 3)
    shimmer_apq5 = _local_perturbation(usable_amplitudes, 5)
    shimmer_apq11 = _local_perturbation(usable_amplitudes, 11)
    shimmer_dda = 3.0 * shimmer_apq3

    mean_periodicity = float(np.mean(periodicity))
    nhr = (1.0 - mean_periodicity) / max(mean_periodicity, 1e-12)
    hnr = 10.0 * math.log10(max(mean_periodicity, 1e-12) / max(1.0 - mean_periodicity, 1e-12))
    f0_series = 1.0 / np.maximum(periods, 1e-12)
    rpde = _permutation_entropy(f0_series, order=3)
    dfa = _detrended_fluctuation(f0_series)
    ppe = _pitch_period_entropy(periods)

    values = {
        "jitter_percent": jitter_percent,
        "jitter_absolute": jitter_absolute,
        "jitter_rap": jitter_rap,
        "jitter_ppq5": jitter_ppq5,
        "jitter_ddp": jitter_ddp,
        "shimmer": shimmer,
        "shimmer_db": shimmer_db,
        "shimmer_apq3": shimmer_apq3,
        "shimmer_apq5": shimmer_apq5,
        "shimmer_apq11": shimmer_apq11,
        "shimmer_dda": shimmer_dda,
        "nhr": nhr,
        "hnr": hnr,
        "rpde": rpde,
        "dfa": dfa,
        "ppe": ppe,
    }
    if set(values) != set(FEATURE_NAMES) or not all(math.isfinite(value) for value in values.values()):
        raise ValueError("biomedical feature extraction produced an invalid feature vector")
    return {name: float(values[name]) for name in FEATURE_NAMES}


def extract_biomedical_voice_datapoint(
    wav_bytes: bytes,
    *,
    datapoint_id: str,
    max_bytes: int = 2_000_000,
    max_duration_seconds: float = 30.0,
) -> VoiceDataPoint:
    """Extract research acoustic features from bounded in-memory WAV bytes."""

    audio = decode_pcm_wav(
        wav_bytes,
        max_bytes=max_bytes,
        max_duration_seconds=max_duration_seconds,
    )
    if "LOW_SIGNAL" in audio.quality_flags or "HIGH_SILENCE" in audio.quality_flags:
        raise ValueError("audio quality is insufficient for biomedical feature extraction")
    features = extract_biomedical_features(audio.samples, audio.sample_rate_hz)
    return VoiceDataPoint(
        datapoint_id=datapoint_id,
        features=features,
        duration_seconds=audio.duration_seconds,
        sample_rate_hz=audio.sample_rate_hz,
        channels=audio.channels,
        feature_method="research_acoustic_v1_approx",
        raw_audio_retained=False,
        quality_flags=tuple((*audio.quality_flags, "RPDE_APPROXIMATION", "PPE_APPROXIMATION")),
    )


def validate_against_reference(
    actual: Mapping[str, float],
    reference: Mapping[str, float],
    *,
    method: str = "reference-comparison-v1",
    absolute_tolerance: float = 1e-6,
    relative_tolerance: float = 0.05,
) -> FeatureValidationReport:
    """Compare extracted features with a trusted reference feature vector."""

    items: list[FeatureValidationItem] = []
    for feature in FEATURE_NAMES:
        if feature not in actual or feature not in reference:
            raise ValueError(f"reference comparison requires feature {feature}")
        absolute_error = abs(float(actual[feature]) - float(reference[feature]))
        relative_error = absolute_error / max(abs(float(reference[feature])), absolute_tolerance)
        passed = absolute_error <= absolute_tolerance or relative_error <= relative_tolerance
        items.append(
            FeatureValidationItem(
                feature=feature,
                absolute_error=absolute_error,
                relative_error=relative_error,
                passed=passed,
            )
        )
    return FeatureValidationReport(method=method, items=tuple(items))
