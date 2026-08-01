"""Deterministic motion selection with configurable fallback chains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_FALLBACKS = {
    "angry_talking": ["talking_gesture", "idle_talking", "idle"],
    "sad_talking": ["idle_talking", "idle"],
    "happy_talking": ["talking_gesture", "idle_talking", "idle"],
    "surprised_talking": ["surprised", "idle_talking", "idle"],
    "walking": ["idle"], "running": ["walking", "idle"],
}


@dataclass
class MotionSelection:
    motion_id: str | None
    requested_action: str
    selected_action: str | None
    fallback_level: int | None
    reason: str


class MotionSelector:
    def __init__(self, assets: list[dict[str, Any]], fallbacks: dict[str, list[str]] | None = None):
        self.motions = [item for item in assets if item.get("type") == "motion" and item.get("available")]
        self.fallbacks = {**DEFAULT_FALLBACKS, **(fallbacks or {})}

    def select(self, action: str, character_type: str = "humanoid",
               skeleton: str | None = None) -> MotionSelection:
        candidates = [action, *self.fallbacks.get(action, []), "idle"]
        candidates = list(dict.fromkeys(candidates))
        for level, candidate_action in enumerate(candidates):
            matches = [m for m in self.motions if m.get("action") == candidate_action]
            compatible = [m for m in matches if m.get("character_type", "humanoid") == character_type]
            if skeleton:
                exact_skeleton = [m for m in compatible if m.get("compatible_skeleton") in (skeleton, "any")]
                compatible = exact_skeleton or compatible
            if compatible:
                compatible.sort(key=lambda m: (m.get("compatible_skeleton") != skeleton, m["asset_id"]))
                selected = compatible[0]
                return MotionSelection(selected["asset_id"], action, candidate_action, level,
                                       "exact" if level == 0 else "fallback")
        return MotionSelection(None, action, None, None, "no compatible local motion")


def create_motion_plan(screenplay: dict[str, Any], selector: MotionSelector,
                       character_map: dict[str, Any]) -> dict[str, Any]:
    shots = []
    for scene in screenplay["scenes"]:
        for shot in scene["shots"]:
            assignments = []
            for character in shot["characters"]:
                settings = character_map.get(character["name"], {})
                result = selector.select(
                    character.get("action", "idle"),
                    settings.get("character_type", "humanoid"),
                    settings.get("skeleton"),
                )
                assignments.append({"character": character["name"], **result.__dict__})
            shots.append({"scene_id": scene["scene_id"], "shot_id": shot["shot_id"],
                          "assignments": assignments})
    return {"shots": shots}

