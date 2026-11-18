"""Privacy-aware voice capture boundary for Segment A."""

from .audio import AudioBuffer, VoiceDataPoint, decode_pcm_wav, extract_demo_voice_datapoint
from .biomedical import (
    FeatureValidationReport,
    extract_biomedical_voice_datapoint,
    validate_against_reference,
)

__all__ = [
    "AudioBuffer",
    "FeatureValidationReport",
    "VoiceDataPoint",
    "decode_pcm_wav",
    "extract_biomedical_voice_datapoint",
    "extract_demo_voice_datapoint",
    "validate_against_reference",
]
