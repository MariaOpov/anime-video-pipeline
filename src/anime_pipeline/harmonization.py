"""Phase 8 character harmonization planning and camera-fit geometry."""

from __future__ import annotations

import math
from typing import Any

from .rig_contract import PHASE8_REQUIRED_CONTROLS, canonical_controls


DEFAULT_HEIGHT_METERS = 1.72
DEFAULT_DIMENSIONS = (0.62, 0.38, DEFAULT_HEIGHT_METERS)


def camera_fit_distance(
    width: float,
    height: float,
    lens_mm: float,
    aspect_ratio: float,
    safe_fraction: float,
) -> float:
    """Return the minimum pinhole-camera distance for a safe rectangular fit."""
    if width <= 0 or height <= 0 or lens_mm <= 0 or aspect_ratio <= 0:
        raise ValueError("camera fit dimensions, lens, and aspect ratio must be positive")
    if not 0.5 <= safe_fraction <= 0.98:
        raise ValueError("safe frame fraction must be between 0.5 and 0.98")
    sensor_width = 36.0
    sensor_height = sensor_width / aspect_ratio
    horizontal_half_angle = math.atan(sensor_width / (2.0 * lens_mm))
    vertical_half_angle = math.atan(sensor_height / (2.0 * lens_mm))
    horizontal = width / (2.0 * math.tan(horizontal_half_angle) * safe_fraction)
    vertical = height / (2.0 * math.tan(vertical_half_angle) * safe_fraction)
    return round(max(horizontal, vertical), 4)


def _vector3(value: Any, fallback: tuple[float, float, float]) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        value = fallback
    result = [max(0.001, float(component)) for component in value]
    return [round(component, 5) for component in result]


def build_harmonization_contract(
    character_assets: dict[str, Any],
    project_characters: dict[str, Any],
    settings: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a deterministic model-independent Phase 8 execution contract."""
    settings = settings or {}
    enabled = bool(settings.get("enabled", False))
    default_height = float(settings.get("default_target_height_meters", DEFAULT_HEIGHT_METERS))
    height_tolerance = float(settings.get("height_tolerance_ratio", 0.02))
    ground_tolerance = float(settings.get("ground_tolerance_meters", 0.015))
    rest_limit = float(settings.get("rest_pose_max_degrees", 18.0))
    neutral_arm = float(settings.get("neutral_arm_degrees", 12.0))
    safe_fraction = float(settings.get("safe_frame_fraction", 0.88))
    headroom = float(settings.get("headroom_fraction", 0.06))
    footroom = float(settings.get("footroom_fraction", 0.04))
    if not 0.5 <= default_height <= 5.0:
        raise ValueError("Phase 8 default target height must be between 0.5 and 5 meters")
    if not 0.0 <= height_tolerance <= 0.2:
        raise ValueError("Phase 8 height tolerance must be between 0 and 0.2")
    if not 0.0 <= ground_tolerance <= 0.2:
        raise ValueError("Phase 8 ground tolerance must be between 0 and 0.2 meters")
    if not 0.0 <= rest_limit <= 45.0 or not 0.0 <= neutral_arm <= 35.0:
        raise ValueError("Phase 8 neutral-pose angles are outside the safe range")
    if not 0.5 <= safe_fraction <= 0.98:
        raise ValueError("Phase 8 safe frame fraction must be between 0.5 and 0.98")
    if not 0.0 <= headroom <= 0.2 or not 0.0 <= footroom <= 0.2:
        raise ValueError("Phase 8 camera margins must be between 0 and 0.2")

    contract: dict[str, Any] = {
        "version": 1,
        "enabled": enabled,
        "report": str(settings.get("report", "generated/phase8_harmonization_report.json")),
        "pose": "neutral_dialogue",
        "floor_z": round(float(settings.get("floor_z", 0.0)), 5),
        "default_target_height_meters": default_height,
        "height_tolerance_ratio": height_tolerance,
        "ground_tolerance_meters": ground_tolerance,
        "rest_pose_max_degrees": rest_limit,
        "neutral_arm_degrees": neutral_arm,
        "safe_frame_fraction": safe_fraction,
        "headroom_fraction": headroom,
        "footroom_fraction": footroom,
        "characters": [],
        "configured_count": 0,
        "ready_count": 0,
    }
    if not enabled:
        return contract

    production = {
        item["character"]: item for item in character_assets.get("characters", [])
    }
    names = sorted(set(project_characters) | set(production))
    height_overrides = settings.get("character_heights", {})
    for character in names:
        asset = production.get(character)
        runtime_probe = asset is None
        source_dimensions = _vector3(
            asset.get("dimensions") if asset else None,
            DEFAULT_DIMENSIONS,
        )
        source_height = source_dimensions[2]
        target_height = float(height_overrides.get(character, default_height))
        if not 0.5 <= target_height <= 5.0:
            raise ValueError(f"Phase 8 target height is invalid for {character}")
        scale = target_height / source_height
        target_dimensions = [round(component * scale, 5) for component in source_dimensions]
        bone_mapping = dict(asset.get("bone_mapping", {})) if asset else {}
        controls = canonical_controls(bone_mapping, runtime_probe=runtime_probe)
        resolved = sum(alias in controls for alias in PHASE8_REQUIRED_CONTROLS)
        fallback_count = sum(value.startswith("__PIPE_") for value in controls.values())
        ready = bool(asset.get("ready", False)) if asset else True
        ready = ready and resolved == len(PHASE8_REQUIRED_CONTROLS)
        item = {
            "character": character,
            "source": "phase7_cache" if asset else "base_scene",
            "source_height_meters": round(source_height, 5),
            "target_height_meters": round(target_height, 5),
            "planned_scale_factor": round(scale, 6),
            "source_dimensions": source_dimensions,
            "target_dimensions": target_dimensions,
            "head_height_meters": round(target_height * 0.92, 5),
            "canonical_controls": controls,
            "required_control_count": len(PHASE8_REQUIRED_CONTROLS),
            "resolved_control_count": resolved,
            "fallback_control_count": fallback_count,
            "runtime_probe_required": runtime_probe,
            "ready": ready,
        }
        contract["characters"].append(item)
        contract["configured_count"] += 1
        contract["ready_count"] += int(ready)
    return contract


def character_geometry(
    harmonization: dict[str, Any] | None,
) -> dict[str, dict[str, float]]:
    """Expose only the dimensions trusted by the deterministic camera planner."""
    if not harmonization or not harmonization.get("enabled", False):
        return {}
    return {
        item["character"]: {
            "width": float(item["target_dimensions"][0]),
            "depth": float(item["target_dimensions"][1]),
            "height": float(item["target_height_meters"]),
            "head_height": float(item["head_height_meters"]),
        }
        for item in harmonization.get("characters", [])
    }
