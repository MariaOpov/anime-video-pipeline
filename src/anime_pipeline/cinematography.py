"""Deterministic cinematic blocking and camera direction.

The motion-intent layer remains semantic.  This module is the trusted adapter
that turns shot type, speaker/listener roles, and gaze targets into bounded
stage placements and camera keyframes.  AI output never supplies raw Blender
coordinates.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .harmonization import camera_fit_distance, character_geometry


COMPOSITIONS = {"single", "close_up", "over_shoulder", "two_shot"}
CAMERA_MOVES = {"static", "slow_dolly_in", "slow_dolly_out", "lateral_drift"}


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _position_map(characters: list[str], spacing: float) -> dict[str, tuple[float, float, float]]:
    if not 0.8 <= spacing <= 6.0:
        raise ValueError("cinematic character spacing must be between 0.8 and 6.0")
    center = (len(characters) - 1) / 2.0
    return {
        character: (round((index - center) * spacing, 4), 0.0, 0.0)
        for index, character in enumerate(characters)
    }


def _composition(shot: dict[str, Any], *, index: int, cast_size: int) -> str:
    shot_type = str(shot.get("shot_type", "medium"))
    if cast_size <= 1:
        return "close_up" if shot_type == "close_up" else "single"
    if index == 0 or shot_type in {"wide", "long"}:
        return "two_shot"
    if shot_type == "close_up":
        return "close_up"
    return "over_shoulder"


def _body_yaw(position: tuple[float, float, float], target: tuple[float, float, float] | None,
              maximum_degrees: float) -> float:
    if target is None:
        return 0.0
    delta_x = target[0] - position[0]
    if abs(delta_x) < 1e-6:
        return 0.0
    return round(math.copysign(maximum_degrees, delta_x), 4)


def _camera_move(index: int, total: int, composition: str,
                 enabled: bool) -> str:
    if not enabled:
        return "static"
    if index == total - 1 and total > 1:
        return "slow_dolly_out"
    if composition in {"two_shot", "close_up"}:
        return "slow_dolly_in"
    if index % 2:
        return "lateral_drift"
    return "static"


def _camera_contract(shot: dict[str, Any], *, composition: str,
                     subject_position: tuple[float, float, float],
                     listener_position: tuple[float, float, float] | None,
                     index: int, total: int, camera_settings: dict[str, Any],
                     direction_settings: dict[str, Any],
                     subject_geometry: dict[str, float],
                     listener_geometry: dict[str, float] | None,
                     safe_fraction: float, adaptive: bool) -> dict[str, Any]:
    subject_x = subject_position[0]
    listener_x = listener_position[0] if listener_position else subject_x
    look_sign = 0.0 if listener_position is None else math.copysign(1.0, listener_x - subject_x)
    subject_height = float(subject_geometry["height"])
    subject_width = float(subject_geometry["width"])
    subject_depth = float(subject_geometry["depth"])
    listener_height = float(listener_geometry["height"]) if listener_geometry else subject_height
    listener_width = float(listener_geometry["width"]) if listener_geometry else subject_width
    listener_depth = float(listener_geometry["depth"]) if listener_geometry else subject_depth
    required_region = "face" if composition == "close_up" else "full_body"
    if composition == "two_shot":
        lens = 52.0
        minimum_x = min(subject_x - subject_width / 2.0, listener_x - listener_width / 2.0)
        maximum_x = max(subject_x + subject_width / 2.0, listener_x + listener_width / 2.0)
        view_width = maximum_x - minimum_x
        view_height = max(subject_height, listener_height)
        camera_x = target_x = (minimum_x + maximum_x) / 2.0
        target_z = view_height / 2.0
        camera_z = target_z
        view_depth = max(subject_depth, listener_depth)
    elif composition == "close_up":
        lens = 68.0
        camera_x = subject_x
        target_x = subject_x + look_sign * 0.16
        view_width = max(subject_width * 0.72, 0.32)
        view_height = subject_height * 0.46
        target_z = float(subject_geometry["head_height"]) - subject_height * 0.16
        camera_z = target_z + subject_height * 0.035
        view_depth = subject_depth
    elif composition == "over_shoulder":
        lens = 58.0
        camera_x = subject_x - look_sign * 0.32
        target_x = subject_x + look_sign * 0.14
        view_width = subject_width * 1.15
        view_height = subject_height
        target_z = subject_height / 2.0
        camera_z = target_z + subject_height * 0.06
        view_depth = max(subject_depth, listener_depth)
    else:
        lens = 56.0
        camera_x, target_x = subject_x, subject_x
        view_width = subject_width
        view_height = subject_height
        target_z = subject_height / 2.0
        camera_z = target_z + subject_height * 0.04
        view_depth = subject_depth

    aspect_ratio = float(camera_settings.get("aspect_ratio", 16.0 / 9.0))
    distance = camera_fit_distance(
        max(0.1, view_width), max(0.1, view_height), lens, aspect_ratio, safe_fraction
    ) + view_depth / 2.0
    distance = max(1.55, round(distance, 4))

    start_location = [round(camera_x, 4), round(-distance, 4), camera_z]
    end_location = list(start_location)
    start_target = [round(target_x, 4), 0.0, target_z]
    end_target = list(start_target)
    movement = _camera_move(
        index, total, composition,
        bool(direction_settings.get("camera_motion_enabled", True)),
    )
    strength = float(direction_settings.get("camera_motion_strength", 0.18))
    if not 0.0 <= strength <= 0.75:
        raise ValueError("camera motion strength must be between 0 and 0.75")
    if movement == "slow_dolly_in":
        end_location[1] = round(end_location[1] + strength, 4)
    elif movement == "slow_dolly_out":
        end_location[1] = round(end_location[1] - strength, 4)
    elif movement == "lateral_drift":
        drift_sign = look_sign or (1.0 if index % 2 else -1.0)
        end_location[0] = round(end_location[0] + drift_sign * strength * 0.45, 4)
        end_target[0] = round(end_target[0] + drift_sign * strength * 0.16, 4)
    return {
        "movement": movement, "lens_mm": lens,
        "start_location": start_location, "end_location": end_location,
        "start_target": start_target, "end_target": end_target,
        "adaptive": adaptive, "required_region": required_region,
        "frame_margin_fraction": round((1.0 - safe_fraction) / 2.0, 4),
        "subject_height_meters": round(subject_height, 5),
    }


def _angle_delta(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)


def _framing_risk(camera: dict[str, Any], positions: dict[str, tuple[float, float, float]],
                  required_characters: list[str], safe_fraction: float) -> int:
    if not 0.5 <= safe_fraction <= 0.98:
        raise ValueError("safe frame fraction must be between 0.5 and 0.98")
    location = camera["start_location"]
    target = camera["start_target"]
    center_angle = math.atan2(target[0] - location[0], target[1] - location[1])
    half_fov = math.atan(36.0 / (2.0 * float(camera["lens_mm"])))
    safe_angle = half_fov * safe_fraction
    risks = 0
    for character in required_characters:
        position = positions[character]
        angle = math.atan2(position[0] - location[0], position[1] - location[1])
        risks += _angle_delta(angle, center_angle) > safe_angle
    return risks


def _collision_risk(camera: dict[str, Any], positions: dict[str, tuple[float, float, float]],
                    clearance: float) -> int:
    if not 0.5 <= clearance <= 5.0:
        raise ValueError("camera clearance must be between 0.5 and 5.0")
    location = camera["start_location"]
    return sum(
        math.hypot(location[0] - position[0], location[1] - position[1]) < clearance
        for position in positions.values()
    )


def direct_cinematography(shots: list[dict[str, Any]], performance: dict[str, Any],
                          camera_settings: dict[str, Any],
                          settings: dict[str, Any] | None = None, *,
                          harmonization: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a deterministic, schema-friendly blocking contract."""
    settings = settings or {}
    enabled = bool(settings.get("enabled", True))
    result: dict[str, Any] = {
        "enabled": enabled, "shots": [], "placement_count": 0,
        "body_facing_count": 0, "camera_motion_count": 0,
        "framing_risk_count": 0, "camera_collision_risk_count": 0,
        "continuity_violation_count": 0, "blocking_conflict_count": 0,
    }
    if not enabled:
        return result

    clips_by_shot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_characters: list[str] = []
    for clip in performance.get("clips", []):
        clips_by_shot[clip["shot_id"]].append(clip)
        if clip["character"] not in all_characters:
            all_characters.append(clip["character"])
    if not all_characters:
        # Phase 3 can still build without motion intent.  Use shot targets as a
        # conservative single-character fallback rather than inventing names.
        all_characters = _unique([
            str(shot["target"]) for shot in shots if shot.get("target")
        ])
    spacing = float(settings.get("character_spacing", 2.2))
    positions = _position_map(all_characters, spacing)
    body_turn = float(settings.get("body_turn_degrees", 10.0))
    if not 0.0 <= body_turn <= 35.0:
        raise ValueError("body turn must be between 0 and 35 degrees")
    safe_fraction = float(settings.get("safe_frame_fraction", 0.86))
    clearance = float(settings.get("minimum_camera_clearance", 1.5))
    geometry = character_geometry(harmonization)
    default_geometry = {"width": 0.62, "depth": 0.38, "height": 1.72,
                        "head_height": 1.5824}

    previous_order: list[str] | None = None
    total = len(shots)
    for index, shot in enumerate(shots):
        clips = clips_by_shot.get(shot["shot_id"], [])
        cast = _unique([clip["character"] for clip in clips])
        if not cast and shot.get("target") in positions:
            cast = [shot["target"]]
        speakers = [clip["character"] for clip in clips if clip.get("role") == "speaker"]
        subject = shot.get("target") if shot.get("target") in cast else None
        subject = subject or (speakers[0] if speakers else cast[0] if cast else None)
        if subject is None:
            continue
        listener = next((character for character in cast if character != subject), None)
        composition = _composition(shot, index=index, cast_size=len(cast))
        placements = []
        for character in cast:
            target = next(
                (clip.get("look_at") for clip in clips
                 if clip["character"] == character and clip.get("look_at") in positions),
                None,
            )
            target = target or (subject if character != subject else listener)
            yaw = _body_yaw(positions[character], positions.get(target), body_turn)
            placements.append({
                "character": character, "position": list(positions[character]),
                "facing_target": target, "body_yaw_degrees": yaw,
            })
            result["body_facing_count"] += target is not None

        camera = _camera_contract(
            shot, composition=composition, subject_position=positions[subject],
            listener_position=positions.get(listener), index=index, total=total,
            camera_settings=camera_settings, direction_settings=settings,
            subject_geometry=geometry.get(subject, default_geometry),
            listener_geometry=geometry.get(listener, default_geometry) if listener else None,
            safe_fraction=safe_fraction,
            adaptive=bool(harmonization and harmonization.get("enabled", False)),
        )
        required = cast if composition == "two_shot" else [subject]
        framing_risks = _framing_risk(camera, positions, required, safe_fraction)
        collision_risks = _collision_risk(camera, positions, clearance)
        shot_order = sorted(cast, key=lambda name: positions[name][0])
        continuity_violation = int(
            previous_order is not None
            and [name for name in previous_order if name in shot_order]
            != [name for name in shot_order if name in previous_order]
        )
        previous_order = shot_order
        conflicts = sum(
            math.dist(positions[left], positions[right]) < 0.75
            for offset, left in enumerate(cast)
            for right in cast[offset + 1:]
        )
        result["shots"].append({
            "scene_id": shot["scene_id"], "shot_id": shot["shot_id"],
            "start_frame": int(shot["start_frame"]), "end_frame": int(shot["end_frame"]),
            "composition": composition, "subject": subject, "listener": listener,
            "placements": placements, "camera": camera,
            "framing_risk_count": framing_risks,
            "camera_collision_risk_count": collision_risks,
            "continuity_violation_count": continuity_violation,
            "blocking_conflict_count": conflicts,
        })
        result["placement_count"] += len(placements)
        result["camera_motion_count"] += camera["movement"] != "static"
        result["framing_risk_count"] += framing_risks
        result["camera_collision_risk_count"] += collision_risks
        result["continuity_violation_count"] += continuity_violation
        result["blocking_conflict_count"] += conflicts
    return result
