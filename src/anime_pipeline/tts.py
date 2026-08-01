"""Offline Piper text-to-speech integration."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def piper_available() -> bool:
    return importlib.util.find_spec("piper") is not None


@dataclass(frozen=True)
class PiperVoice:
    model: str
    data_dir: Path | None = None
    speaker: int | None = None
    length_scale: float | None = None
    noise_scale: float | None = None
    noise_w_scale: float | None = None
    volume: float | None = None

    @classmethod
    def from_config(cls, data: dict[str, Any], project_dir: Path,
                    default_data_dir: str | None = None) -> "PiperVoice":
        raw_dir = data.get("data_dir", default_data_dir)
        resolved_dir = (project_dir / raw_dir).resolve() if raw_dir else None
        return cls(
            model=data["model"], data_dir=resolved_dir, speaker=data.get("speaker"),
            length_scale=data.get("length_scale"), noise_scale=data.get("noise_scale"),
            noise_w_scale=data.get("noise_w_scale"), volume=data.get("volume"),
        )


class PiperTTS:
    def build_command(self, text: str, voice: PiperVoice, output: Path) -> list[str]:
        command = [sys.executable, "-m", "piper", "-m", voice.model, "-f", str(output)]
        if voice.data_dir:
            command.extend(["--data-dir", str(voice.data_dir)])
        options = (
            ("--speaker", voice.speaker), ("--length-scale", voice.length_scale),
            ("--noise-scale", voice.noise_scale), ("--noise-w-scale", voice.noise_w_scale),
            ("--volume", voice.volume),
        )
        for flag, value in options:
            if value is not None:
                command.extend([flag, str(value)])
        command.extend(["--", text])
        return command

    def synthesize(self, text: str, voice: PiperVoice, output: Path) -> None:
        if not piper_available():
            raise RuntimeError("Piper is not installed. Run setup_phase2.ps1")
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            self.build_command(text, voice, output), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0 or not output.is_file():
            detail = result.stderr.strip() or result.stdout.strip() or "no output WAV was created"
            raise RuntimeError(f"Piper failed: {detail}")

