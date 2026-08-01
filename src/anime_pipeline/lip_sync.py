"""Rhubarb Lip Sync subprocess integration and MMD mouth mapping."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_MOUTH_MAPPING = {
    "A": "closed", "B": "I", "C": "E", "D": "A", "E": "O",
    "F": "U", "G": "closed", "H": "E", "X": "neutral",
}


def map_rhubarb_payload(payload: dict[str, Any], mapping: dict[str, str] | None = None) -> list[dict[str, Any]]:
    selected_mapping = {**DEFAULT_MOUTH_MAPPING, **(mapping or {})}
    cues = payload.get("mouthCues")
    if not isinstance(cues, list):
        raise ValueError("Rhubarb JSON has no mouthCues array")
    mapped = []
    for cue in cues:
        source = cue.get("value")
        start, end = cue.get("start"), cue.get("end")
        if source not in selected_mapping or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError(f"Invalid Rhubarb mouth cue: {cue}")
        if start < 0 or end <= start:
            raise ValueError(f"Invalid Rhubarb cue timing: {cue}")
        mapped.append({"start": float(start), "end": float(end),
                       "source_shape": source, "mouth_shape": selected_mapping[source]})
    return mapped


class RhubarbLipSync:
    def __init__(self, executable: Path, recognizer: str = "phonetic",
                 mapping: dict[str, str] | None = None):
        self.executable = executable
        self.recognizer = recognizer
        self.mapping = mapping

    def available(self) -> bool:
        return self.executable.is_file() and (self.executable.parent / "res").is_dir()

    def analyze(self, wav_path: Path, transcript_path: Path, raw_json_path: Path) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError(
                "Rhubarb installation is missing its executable or res directory. "
                "Run setup_phase2.ps1 again."
            )
        command = [
            str(self.executable), "--quiet", "-r", self.recognizer, "-f", "json",
            "-d", str(transcript_path), "-o", str(raw_json_path), str(wav_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", check=False)
        if result.returncode != 0 or not raw_json_path.is_file():
            detail = result.stderr.strip() or result.stdout.strip() or "no JSON output was created"
            raise RuntimeError(f"Rhubarb failed: {detail}")
        with raw_json_path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        return {"duration": float(payload.get("metadata", {}).get("duration", 0)),
                "mouth_cues": map_rhubarb_payload(payload, self.mapping)}
