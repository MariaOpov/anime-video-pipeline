"""Script analysis using local Ollama with a deterministic offline fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests


SCENE_RE = re.compile(r"^\s*(?:SCENE\s+\d+\s*[-:]?|\[)(.*?)(?:\])?\s*$", re.IGNORECASE)
DIALOGUE_RE = re.compile(r"^\s*([\wÀ-ỹ][\wÀ-ỹ .'-]{0,48})\s*:\s*(.+?)\s*$")
EMOTION_WORDS = {
    "sad": ("sad", "buồn", "khóc", "xin lỗi"),
    "angry": ("angry", "giận", "tức", "đừng"),
    "surprised": ("surprised", "ngạc nhiên", "what", "gì cơ"),
    "happy": ("happy", "vui", "cười", "tuyệt"),
}


def _emotion(text: str) -> str:
    lowered = text.casefold()
    for emotion, words in EMOTION_WORDS.items():
        if any(word in lowered for word in words):
            return emotion
    return "neutral"


def _shot_type(emotion: str, dialogue_count: int) -> str:
    if emotion in {"sad", "angry", "surprised"}:
        return "close_up"
    return "medium" if dialogue_count else "full"


@dataclass
class RuleBasedAnalyzer:
    fps: int
    max_duration: int

    def analyze(self, title: str, script: str) -> dict[str, Any]:
        scenes: list[dict[str, Any]] = []
        current = self._new_scene(1, "unspecified")
        scenes.append(current)
        action_buffer: list[str] = []

        for raw_line in script.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            scene_match = SCENE_RE.match(line)
            if scene_match and (line.startswith("[") or line.upper().startswith("SCENE")):
                location = scene_match.group(1).strip(" -:") or "unspecified"
                if not current["shots"] and len(scenes) == 1:
                    current["location"] = location
                else:
                    current = self._new_scene(len(scenes) + 1, location)
                    scenes.append(current)
                action_buffer.clear()
                continue
            dialogue_match = DIALOGUE_RE.match(line)
            if dialogue_match:
                character, text = dialogue_match.groups()
                emotion = _emotion(text)
                duration = min(8.0, max(2.0, len(text.split()) / 2.4 + 0.8))
                shot = self._new_shot(current, duration, character.strip(), text.strip(), emotion, action_buffer)
                current["shots"].append(shot)
                action_buffer.clear()
            else:
                action_buffer.append(line.strip("*() "))

        if action_buffer:
            current["shots"].append(self._action_shot(current, action_buffer))
        scenes = [scene for scene in scenes if scene["shots"]]
        if not scenes:
            scenes = [self._new_scene(1, "unspecified")]
            scenes[0]["shots"].append(self._action_shot(scenes[0], ["Idle establishing shot"]))

        total = 0.0
        for scene in scenes:
            kept = []
            for shot in scene["shots"]:
                if total >= self.max_duration:
                    break
                shot["duration_seconds"] = round(min(shot["duration_seconds"], self.max_duration - total), 3)
                total += shot["duration_seconds"]
                kept.append(shot)
            scene["shots"] = kept
        return {"title": title, "fps": self.fps, "scenes": [s for s in scenes if s["shots"]]}

    @staticmethod
    def _new_scene(number: int, location: str) -> dict[str, Any]:
        return {
            "scene_id": f"scene_{number:03d}", "location": location,
            "time_of_day": "unspecified", "mood": "neutral", "shots": [],
        }

    @staticmethod
    def _new_shot(scene: dict[str, Any], duration: float, character: str, text: str,
                  emotion: str, actions: list[str]) -> dict[str, Any]:
        shot_id = f"shot_{sum(1 for _ in scene['shots']) + 1:03d}"
        action = f"{emotion}_talking" if emotion != "neutral" else "idle_talking"
        return {
            "shot_id": f"{scene['scene_id']}_{shot_id}", "duration_seconds": round(duration, 3),
            "camera": {"shot_type": _shot_type(emotion, 1), "movement": "static", "target": character},
            "characters": [{"name": character, "position": [0, 0, 0], "action": action,
                            "emotion": emotion, "look_at": None}],
            "dialogue": [{"character": character, "text": text, "emotion": emotion}],
            "description": " ".join(actions) if actions else "Dialogue",
        }

    @staticmethod
    def _action_shot(scene: dict[str, Any], actions: list[str]) -> dict[str, Any]:
        shot_id = f"shot_{len(scene['shots']) + 1:03d}"
        return {
            "shot_id": f"{scene['scene_id']}_{shot_id}", "duration_seconds": 3.0,
            "camera": {"shot_type": "establishing", "movement": "static", "target": None},
            "characters": [], "dialogue": [], "description": " ".join(actions),
        }


class OllamaAnalyzer:
    def __init__(self, endpoint: str, model: str, timeout: int = 120):
        self.endpoint, self.model, self.timeout = endpoint.rstrip("/"), model, timeout

    def available(self) -> bool:
        try:
            return requests.get(f"{self.endpoint}/api/tags", timeout=2).ok
        except requests.RequestException:
            return False

    def analyze(self, title: str, script: str, fps: int, max_duration: int) -> dict[str, Any]:
        prompt = (
            "Return JSON only. Convert the script into the screenplay schema with title, fps, scenes, "
            "scene_id, location, time_of_day, mood, shots, shot_id, duration_seconds, camera, "
            "characters, dialogue, and description. Use simple safe motion action tags. "
            f"Maximum total duration: {max_duration}s. Title: {title}. FPS: {fps}.\nSCRIPT:\n{script}"
        )
        response = requests.post(
            f"{self.endpoint}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return json.loads(response.json()["response"])

