import math
import struct
import wave
from pathlib import Path

from models.transcript import AudioQuality


def assess_audio_quality(path: Path, duration_seconds: float | None) -> AudioQuality:
    if path.suffix.lower() != ".wav":
        return AudioQuality(
            overall="unknown",
            noise_level="unknown",
            speech_clarity=None,
            clipping_detected=None,
            silent_ratio=None,
        )

    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            frame_count = min(wav_file.getnframes(), sample_rate * 30)
            frames = wav_file.readframes(frame_count)
    except Exception:  # noqa: BLE001
        return AudioQuality(
            overall="unknown",
            noise_level="unknown",
            speech_clarity=None,
            clipping_detected=None,
            silent_ratio=None,
        )

    samples = _decode_samples(frames, sample_width)
    if not samples:
        return AudioQuality(
            overall="poor",
            noise_level="unknown",
            speech_clarity=0.0,
            clipping_detected=None,
            silent_ratio=1.0,
        )

    if channels > 1:
        samples = samples[::channels]

    peak = max(abs(sample) for sample in samples) or 1.0
    normalized = [sample / peak for sample in samples]
    rms = math.sqrt(sum(sample * sample for sample in normalized) / len(normalized))
    silent_ratio = sum(1 for sample in normalized if abs(sample) <= 0.02) / len(normalized)
    clipping_ratio = sum(1 for sample in normalized if abs(sample) >= 0.98) / len(normalized)
    clipping_detected = clipping_ratio > 0.02

    if rms < 0.08 or silent_ratio > 0.8:
        overall = "poor"
        noise_level = "high"
    elif rms < 0.18 or silent_ratio > 0.55 or clipping_detected:
        overall = "fair"
        noise_level = "medium"
    else:
        overall = "good"
        noise_level = "low"

    if duration_seconds is not None and duration_seconds < 1.0:
        overall = "poor"

    speech_clarity = round(max(0.0, min(1.0, (rms * (1.0 - silent_ratio)) - clipping_ratio)), 2)
    return AudioQuality(
        overall=overall,
        noise_level=noise_level,
        speech_clarity=speech_clarity,
        clipping_detected=clipping_detected,
        silent_ratio=round(silent_ratio, 2),
    )


def _decode_samples(frames: bytes, sample_width: int) -> list[float]:
    if sample_width == 1:
        return [float(value - 128) for value in frames]
    if sample_width == 2:
        count = len(frames) // 2
        return [float(value) for value in struct.unpack(f"<{count}h", frames)]
    if sample_width == 4:
        count = len(frames) // 4
        return [float(value) for value in struct.unpack(f"<{count}i", frames)]
    return []
