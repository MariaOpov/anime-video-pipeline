"""Schema-constrained motion intent planning with Ollama and rules fallback."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import requests

from .io_utils import atomic_write_json, load_json, validate


EMOTION_INTENSITY = {
    "neutral": 0.2, "sad": 0.35, "angry": 0.75, "surprised": 0.65,
    "happy": 0.55, "fearful": 0.6, "determined": 0.55,
}
EMOTION_GESTURES = {
    "neutral": ["breathe"], "sad": ["look_down", "breathe"],
    "angry": ["step_forward", "small_hand_motion"],
    "surprised": ["step_back", "look_up"], "happy": ["open_hand", "nod"],
    "fearful": ["step_back", "look_down"], "determined": ["step_forward", "nod"],
}
CAMERA_TYPES = {"close_up", "medium", "wide", "full", "establishing"}


def contextual_gestures(shot: dict[str, Any], character_name: str,
                        emotion: str) -> list[str]:
    """Add restrained dialogue/environment cues to the emotion defaults."""
    gestures = list(EMOTION_GESTURES[emotion])
    dialogue = " ".join(
        str(line.get("text", ""))
        for line in shot.get("dialogue", [])
        if line.get("character") == character_name
    ).casefold()
    description = str(shot.get("description", "")).casefold()

    if "?" in dialogue:
        gestures.append("head_tilt")
    elif re.search(r"\b(thật|đúng|vâng|ừ|được|yes|okay|ok)\b", dialogue):
        gestures.append("nod")
    if re.search(r"\b(xin lỗi|sorry|apolog)\w*\b", dialogue):
        gestures.append("look_down")
    if re.search(r"\b(wind|gió)\b", description):
        gestures.append("wind_sway")
    return list(dict.fromkeys(gestures))[:4]


def normalize_action(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if len(normalized) < 2:
        return "idle"
    return normalized[:64]


def screenplay_digest(screenplay: dict[str, Any]) -> str:
    canonical = json.dumps(screenplay, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def available_motion_actions(asset_index: dict[str, Any] | None) -> list[str]:
    actions = {
        str(item["action"])
        for item in (asset_index or {}).get("assets", [])
        if item.get("type") == "motion" and item.get("available") and item.get("action")
    }
    actions.update({"idle", "idle_talking", "sad_talking", "angry_talking",
                    "happy_talking", "surprised_talking", "walking", "running"})
    return sorted(actions)


class RuleMotionPlanner:
    def build(self, project_name: str, screenplay: dict[str, Any]) -> dict[str, Any]:
        shots = []
        for scene in screenplay["scenes"]:
            for shot in scene["shots"]:
                characters = []
                for character in shot["characters"]:
                    emotion = character.get("emotion", "neutral")
                    if emotion not in EMOTION_INTENSITY:
                        emotion = "neutral"
                    characters.append({
                        "name": character["name"],
                        "action": normalize_action(character.get("action", "idle")),
                        "emotion": emotion,
                        "intensity": EMOTION_INTENSITY[emotion],
                        "gestures": contextual_gestures(shot, character["name"], emotion),
                        "look_at": character.get("look_at"),
                        "confidence": 1.0,
                    })
                camera = shot.get("camera", {}).get("shot_type", "medium")
                if camera not in CAMERA_TYPES:
                    camera = "medium"
                shots.append({
                    "scene_id": scene["scene_id"], "shot_id": shot["shot_id"],
                    "camera_suggestion": camera, "characters": characters,
                    "notes": str(shot.get("description", ""))[:240],
                })
        return {
            "version": 1, "source": "rules", "project_name": project_name,
            "fps": int(screenplay["fps"]), "screenplay_sha256": screenplay_digest(screenplay),
            "shots": shots,
        }


class OllamaMotionPlanner:
    def __init__(self, endpoint: str, model: str, schema_path: Path,
                 timeout: int = 180, session: Any = requests):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.schema_path = schema_path
        self.timeout = timeout
        self.session = session

    def available(self) -> bool:
        try:
            return bool(self.session.get(f"{self.endpoint}/api/tags", timeout=2).ok)
        except requests.RequestException:
            return False

    def build_request(self, project_name: str, screenplay: dict[str, Any],
                      actions: list[str]) -> dict[str, Any]:
        schema = load_json(self.schema_path)
        prompt = (
            "Create restrained anime character motion intents for every supplied shot and every "
            "character. Preserve scene_id, shot_id, and character names exactly. Prefer available "
            "motion action tags. Never invent file paths, Blender code, bone names, commands, or "
            "extra characters. Keep gestures subtle and use at most four gestures per character.\n"
            f"AVAILABLE ACTION TAGS: {json.dumps(actions, ensure_ascii=False)}\n"
            f"PROJECT: {project_name}\n"
            f"SCREENPLAY JSON:\n{json.dumps(screenplay, ensure_ascii=False)}"
        )
        return {
            "model": self.model,
            "prompt": prompt,
            "system": "You are a motion planner. Return only data matching the supplied JSON schema.",
            "stream": False,
            "format": schema,
            "options": {"temperature": 0.2},
        }

    def generate(self, project_name: str, screenplay: dict[str, Any],
                 actions: list[str]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.endpoint}/api/generate",
            json=self.build_request(project_name, screenplay, actions),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = json.loads(response.json()["response"])
        payload["version"] = 1
        payload["source"] = "ollama"
        payload["project_name"] = project_name
        payload["fps"] = int(screenplay["fps"])
        payload["screenplay_sha256"] = screenplay_digest(screenplay)
        return payload


def validate_motion_intent(plan: dict[str, Any], screenplay: dict[str, Any],
                           schema_path: Path) -> None:
    validate(plan, schema_path, "motion intent plan")
    if plan["screenplay_sha256"] != screenplay_digest(screenplay):
        raise ValueError("Motion intent plan is stale because the screenplay changed")
    expected: dict[str, tuple[str, set[str]]] = {}
    for scene in screenplay["scenes"]:
        for shot in scene["shots"]:
            expected[shot["shot_id"]] = (
                scene["scene_id"], {character["name"] for character in shot["characters"]}
            )
    actual: dict[str, tuple[str, set[str]]] = {}
    for shot in plan["shots"]:
        shot_id = shot["shot_id"]
        if shot_id in actual:
            raise ValueError(f"Duplicate motion intent shot: {shot_id}")
        names = [character["name"] for character in shot["characters"]]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate character motion intent in shot: {shot_id}")
        actual[shot_id] = (shot["scene_id"], set(names))
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        unknown = sorted(set(actual) - set(expected))
        raise ValueError(f"Motion intent shot identity mismatch; missing={missing}, unknown={unknown}")
    for shot_id, identity in expected.items():
        if actual[shot_id] != identity:
            raise ValueError(f"Motion intent character identity mismatch for {shot_id}")


def motion_intent_warnings(plan: dict[str, Any], actions: list[str]) -> list[str]:
    known = set(actions)
    return [
        f"{shot['shot_id']}:{character['name']} requests unavailable action '{character['action']}'"
        for shot in plan["shots"] for character in shot["characters"]
        if character["action"] not in known
    ]


def apply_motion_intent(screenplay: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(screenplay)
    intents = {
        (shot["shot_id"], character["name"]): character
        for shot in plan["shots"] for character in shot["characters"]
    }
    cameras = {shot["shot_id"]: shot["camera_suggestion"] for shot in plan["shots"]}
    for scene in updated["scenes"]:
        for shot in scene["shots"]:
            shot["camera"]["shot_type"] = cameras[shot["shot_id"]]
            for character in shot["characters"]:
                intent = intents[(shot["shot_id"], character["name"])]
                character["action"] = intent["action"]
                character["emotion"] = intent["emotion"]
                character["look_at"] = intent["look_at"]
    return updated


def write_motion_intent(path: Path, plan: dict[str, Any], screenplay: dict[str, Any],
                        schema_path: Path) -> Path:
    validate_motion_intent(plan, screenplay, schema_path)
    atomic_write_json(path, plan)
    return path
