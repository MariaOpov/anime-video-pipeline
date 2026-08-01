"""Deterministic procedural poses derived from validated motion intent.

The AI/rules contract never supplies bone names or raw keyframes. This module
maps the small, schema-constrained gesture vocabulary to safe mannequin bone
aliases and bounded Euler rotations.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_GESTURES = {
    "look_down", "look_up", "head_tilt", "nod", "shake_head",
    "small_hand_motion", "open_hand", "point", "step_forward", "step_back",
    "turn_left", "turn_right", "breathe", "wind_sway",
}

_SAMPLE_POSITIONS = (0.0, 0.20, 0.40, 0.60, 0.82, 1.0)
_WAVE = (0.0, 1.0, -0.68, 0.78, -0.36, 0.0)
_ENVELOPE = (0.0, 0.72, 1.0, 1.0, 0.62, 0.0)
_NOD = (0.0, 0.82, -0.22, 1.0, -0.18, 0.0)


def _bounded(value: float, limit: float = 0.65) -> float:
    return round(max(-limit, min(limit, value)), 6)


def _frames(start: int, end: int) -> list[int]:
    if start < 1 or end < start:
        raise ValueError("performance frames must be positive and ordered")
    span = end - start
    return [start + round(span * position) for position in _SAMPLE_POSITIONS]


def build_pose_keyframes(performance: dict[str, Any], *, look_direction: float = 0.0,
                         amplitude_scale: float = 1.0) -> list[dict[str, Any]]:
    """Build bounded bone-alias rotations for one character performance clip."""
    start, end = int(performance["start_frame"]), int(performance["end_frame"])
    frames = _frames(start, end)
    intensity = float(performance.get("intensity", 0.2))
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("performance intensity must be between 0 and 1")
    if not 0.1 <= amplitude_scale <= 3.0:
        raise ValueError("gesture amplitude scale must be between 0.1 and 3.0")
    gestures = set(performance.get("gestures", []))
    unknown = gestures - SUPPORTED_GESTURES
    if unknown:
        raise ValueError(f"unsupported procedural gesture(s): {sorted(unknown)}")

    talking = str(performance.get("action", "")).endswith("_talking")
    active_bones = {"spine", "head"}
    if talking or gestures & {"small_hand_motion", "open_hand", "point"}:
        active_bones.update({"arm.L", "arm.R"})
    if gestures & {"step_forward", "step_back"}:
        active_bones.update({"leg.L", "leg.R"})

    scale = amplitude_scale
    result: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        wave, envelope, nod = _WAVE[index], _ENVELOPE[index], _NOD[index]
        rotations = {bone: [0.0, 0.0, 0.0] for bone in active_bones}

        # A very small baseline sway prevents a perfectly frozen torso.
        rotations["spine"][1] += wave * (0.008 + 0.014 * intensity) * scale
        rotations["head"][1] -= wave * (0.004 + 0.007 * intensity) * scale

        if "breathe" in gestures:
            breath = wave * (0.018 + 0.028 * intensity) * scale
            rotations["spine"][0] += breath
            rotations["head"][0] -= breath * 0.42
        if "wind_sway" in gestures:
            sway = wave * (0.045 + 0.055 * intensity) * scale
            rotations["spine"][1] += sway
            rotations["head"][1] -= sway * 0.55
        if "look_down" in gestures:
            rotations["head"][0] += envelope * (0.14 + 0.18 * intensity) * scale
        if "look_up" in gestures:
            rotations["head"][0] -= envelope * (0.12 + 0.15 * intensity) * scale
        if "head_tilt" in gestures:
            rotations["head"][1] += envelope * (0.12 + 0.10 * intensity) * scale
        if "nod" in gestures:
            rotations["head"][0] += nod * (0.13 + 0.16 * intensity) * scale
        if "shake_head" in gestures:
            rotations["head"][2] += wave * (0.16 + 0.13 * intensity) * scale
        if look_direction:
            direction = 1.0 if look_direction > 0 else -1.0
            rotations["head"][2] += envelope * direction * (0.13 + 0.17 * intensity) * scale

        if talking:
            arm_motion = wave * (0.08 + 0.15 * intensity) * scale
            rotations["arm.L"][1] += arm_motion
            rotations["arm.L"][2] += arm_motion * 0.32
            rotations["arm.R"][1] -= arm_motion
            rotations["arm.R"][2] -= arm_motion * 0.32
        if "small_hand_motion" in gestures:
            hand = wave * (0.07 + 0.12 * intensity) * scale
            rotations["arm.L"][2] += hand
            rotations["arm.R"][2] -= hand
        if "open_hand" in gestures:
            opening = envelope * (0.10 + 0.13 * intensity) * scale
            rotations["arm.L"][1] += opening
            rotations["arm.R"][1] -= opening
        if "point" in gestures:
            rotations["arm.L"][1] += envelope * (0.20 + 0.18 * intensity) * scale

        step_sign = 1.0 if "step_forward" in gestures else -1.0 if "step_back" in gestures else 0.0
        if step_sign:
            lean = envelope * step_sign * (0.05 + 0.07 * intensity) * scale
            rotations["spine"][0] += lean
            rotations["leg.L"][0] += wave * lean
            rotations["leg.R"][0] -= wave * lean
        if "turn_left" in gestures:
            rotations["spine"][2] += envelope * (0.08 + 0.10 * intensity) * scale
        if "turn_right" in gestures:
            rotations["spine"][2] -= envelope * (0.08 + 0.10 * intensity) * scale

        bounded = {
            bone: [_bounded(component) for component in rotation]
            for bone, rotation in sorted(rotations.items())
        }
        result.append({"frame": frame, "rotations": bounded})

    # Very short clips may round multiple samples onto one frame. The later
    # sample is authoritative, while insertion order stays chronological.
    unique = {keyframe["frame"]: keyframe for keyframe in result}
    return [unique[frame] for frame in sorted(unique)]
