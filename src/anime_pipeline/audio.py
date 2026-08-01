"""PCM WAV normalization, padding, and timing helpers."""

from __future__ import annotations

import sys
import wave
from array import array
from pathlib import Path


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getframerate() <= 0:
            raise ValueError(f"Invalid WAV sample rate: {path}")
        return wav_file.getnframes() / wav_file.getframerate()


def normalize_and_pad_wav(source: Path, destination: Path, *,
                          pad_before: float = 0.08, pad_after: float = 0.12,
                          target_peak: float = 0.92) -> float:
    """Normalize a 16-bit PCM WAV and add deterministic silence padding."""
    if pad_before < 0 or pad_after < 0:
        raise ValueError("Silence padding cannot be negative")
    if not 0 < target_peak <= 1:
        raise ValueError("target_peak must be in (0, 1]")
    with wave.open(str(source), "rb") as input_wav:
        params = input_wav.getparams()
        if params.sampwidth != 2 or params.comptype != "NONE":
            raise ValueError(f"Expected uncompressed 16-bit PCM WAV: {source}")
        frames = input_wav.readframes(params.nframes)

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(sample) for sample in samples), default=0)
    if peak:
        scale = (32767 * target_peak) / peak
        if scale != 1.0:
            samples = array("h", (max(-32768, min(32767, round(sample * scale))) for sample in samples))
    if sys.byteorder != "little":
        samples.byteswap()

    before_frames = round(pad_before * params.framerate)
    after_frames = round(pad_after * params.framerate)
    silence_before = b"\x00\x00" * before_frames * params.nchannels
    silence_after = b"\x00\x00" * after_frames * params.nchannels
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as output_wav:
        output_wav.setparams(params._replace(nframes=0))
        output_wav.writeframes(silence_before + samples.tobytes() + silence_after)
    return wav_duration(destination)
