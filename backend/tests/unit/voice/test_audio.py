from __future__ import annotations

from io import BytesIO
import math
import struct
import unittest
import wave

from ml.voice.audio import extract_demo_voice_datapoint


def sine_wave_bytes(duration_seconds: float = 1.0, sample_rate: int = 16_000) -> bytes:
    samples = [
        int(0.25 * 32767 * math.sin(2 * math.pi * 220 * index / sample_rate))
        for index in range(int(duration_seconds * sample_rate))
    ]
    raw = struct.pack(f"<{len(samples)}h", *samples)
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(raw)
    return output.getvalue()


class VoiceAudioTests(unittest.TestCase):
    def test_audio_becomes_a_datapoint_without_retaining_raw_audio(self) -> None:
        datapoint = extract_demo_voice_datapoint(sine_wave_bytes(), datapoint_id="voice-1")

        self.assertEqual(datapoint.datapoint_id, "voice-1")
        self.assertEqual(datapoint.sample_rate_hz, 16_000)
        self.assertFalse(datapoint.raw_audio_retained)
        self.assertEqual(datapoint.feature_method, "demo_signal_proxy_v1")
        self.assertEqual(len(datapoint.features), 16)

    def test_silent_audio_is_flagged(self) -> None:
        samples = struct.pack("<16000h", *([0] * 16000))
        output = BytesIO()
        with wave.open(output, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16_000)
            writer.writeframes(samples)

        datapoint = extract_demo_voice_datapoint(output.getvalue(), datapoint_id="silent-1")

        self.assertIn("LOW_SIGNAL", datapoint.quality_flags)
        self.assertIn("HIGH_SILENCE", datapoint.quality_flags)


if __name__ == "__main__":
    unittest.main()
