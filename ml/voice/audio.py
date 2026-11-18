"""In-memory WAV processing for inference-mode demonstrations.

The extractor intentionally produces proxy features from the waveform. It is
not a validated biomedical speech-feature extractor. A future production
extractor must be evaluated separately and must preserve the same output
contract and version metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
import struct
from types import MappingProxyType
from typing import Mapping
import wave

from ml.data.schema import FEATURE_NAMES


@dataclass(frozen=True)
class VoiceDataPoint:
    datapoint_id: str
    features: Mapping[str, float]
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    feature_method: str
    raw_audio_retained: bool
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True)
class AudioBuffer:
    """Decoded mono audio with quality metadata and no raw-byte retention."""

    samples: tuple[float, ...]
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    quality_flags: tuple[str, ...] = ()


def _decode_pcm_mono(raw: bytes, sample_width: int, channels: int) -> list[float]:
    if sample_width == 1:
        samples = [(byte - 128) / 128.0 for byte in raw]
    elif sample_width == 2:
        sample_count = len(raw) // 2
        samples = [value / 32768.0 for value in struct.unpack(f"<{sample_count}h", raw[: sample_count * 2])]
    elif sample_width == 4:
        sample_count = len(raw) // 4
        samples = [value / 2147483648.0 for value in struct.unpack(f"<{sample_count}i", raw[: sample_count * 4])]
    else:
        raise ValueError("only 8-bit, 16-bit, and 32-bit PCM WAV is supported")

    if not samples or len(samples) % channels:
        raise ValueError("WAV contains no complete audio frames")
    return [
        sum(samples[index : index + channels]) / channels
        for index in range(0, len(samples), channels)
    ]


def _proxy_features(samples: list[float]) -> dict[str, float]:
    absolute = [abs(sample) for sample in samples]
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    mean_abs = sum(absolute) / len(absolute)
    zero_crossings = sum(
        1 for previous, current in zip(samples, samples[1:]) if (previous < 0 <= current) or (previous >= 0 > current)
    )
    zero_crossing_rate = zero_crossings / max(1, len(samples) - 1)
    variability = min(1.0, max(0.0, (rms - mean_abs) / max(rms, 1e-12)))
    jitter = min(1.0, 0.02 + 0.35 * zero_crossing_rate + 0.15 * variability)
    shimmer = min(1.0, 0.02 + 0.50 * variability + 0.10 * zero_crossing_rate)
    nhr = min(1.0, 0.05 + 0.65 * zero_crossing_rate + 0.15 * variability)
    hnr = max(0.1, 20.0 * (1.0 - min(0.95, nhr)))
    rpde = min(1.0, 0.25 + 0.50 * zero_crossing_rate + 0.25 * variability)
    dfa = min(1.0, max(0.0, 0.50 + 0.30 * (rms - 0.1)))
    ppe = min(1.0, 0.20 + 0.50 * variability + 0.20 * zero_crossing_rate)

    values = {
        "jitter_percent": jitter,
        "jitter_absolute": jitter / 100.0,
        "jitter_rap": jitter * 0.45,
        "jitter_ppq5": jitter * 0.55,
        "jitter_ddp": jitter * 1.35,
        "shimmer": shimmer,
        "shimmer_db": shimmer * 2.0,
        "shimmer_apq3": shimmer * 0.45,
        "shimmer_apq5": shimmer * 0.55,
        "shimmer_apq11": shimmer * 0.70,
        "shimmer_dda": shimmer * 1.35,
        "nhr": nhr,
        "hnr": hnr,
        "rpde": rpde,
        "dfa": dfa,
        "ppe": ppe,
    }
    return {name: float(values[name]) for name in FEATURE_NAMES}


def decode_pcm_wav(
    wav_bytes: bytes,
    *,
    max_bytes: int = 2_000_000,
    max_duration_seconds: float = 30.0,
) -> AudioBuffer:
    """Decode a bounded PCM WAV payload into an in-memory mono buffer."""

    if len(wav_bytes) > max_bytes:
        raise ValueError("audio payload exceeds the configured size limit")

    try:
        with wave.open(BytesIO(wav_bytes), "rb") as reader:
            sample_rate = reader.getframerate()
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            frame_count = reader.getnframes()
            duration = frame_count / sample_rate if sample_rate else 0.0
            if duration > max_duration_seconds:
                raise ValueError("audio duration exceeds the configured limit")
            raw = reader.readframes(frame_count)
    except (wave.Error, EOFError) as exc:
        raise ValueError("audio payload must be a readable PCM WAV file") from exc

    samples = _decode_pcm_mono(raw, sample_width, channels)
    absolute = [abs(sample) for sample in samples]
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    clipping_fraction = sum(1 for sample in absolute if sample >= 0.98) / len(samples)
    silence_fraction = sum(1 for sample in absolute if sample < 0.01) / len(samples)
    quality_flags: list[str] = []
    if duration < 1.0:
        quality_flags.append("SHORT_RECORDING")
    if sample_rate < 8_000:
        quality_flags.append("LOW_SAMPLE_RATE")
    if rms < 0.01:
        quality_flags.append("LOW_SIGNAL")
    if clipping_fraction > 0.01:
        quality_flags.append("HIGH_CLIPPING")
    if silence_fraction > 0.80:
        quality_flags.append("HIGH_SILENCE")

    return AudioBuffer(
        samples=tuple(samples),
        duration_seconds=duration,
        sample_rate_hz=sample_rate,
        channels=channels,
        quality_flags=tuple(quality_flags),
    )


def extract_demo_voice_datapoint(
    wav_bytes: bytes,
    *,
    datapoint_id: str,
    max_bytes: int = 2_000_000,
    max_duration_seconds: float = 30.0,
) -> VoiceDataPoint:
    """Extract a demo datapoint from in-memory PCM WAV bytes.

    Raw bytes are never returned or retained in the result. This function is
    suitable for local inference demonstrations, not clinical assessment.
    """

    audio = decode_pcm_wav(
        wav_bytes,
        max_bytes=max_bytes,
        max_duration_seconds=max_duration_seconds,
    )

    return VoiceDataPoint(
        datapoint_id=datapoint_id,
        features=_proxy_features(list(audio.samples)),
        duration_seconds=audio.duration_seconds,
        sample_rate_hz=audio.sample_rate_hz,
        channels=audio.channels,
        feature_method="demo_signal_proxy_v1",
        raw_audio_retained=False,
        quality_flags=audio.quality_flags,
    )
