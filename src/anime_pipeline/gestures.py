"""Deterministic procedural poses derived from validated motion intent.

The AI/rules contract never supplies bone names or raw keyframes. This module
maps the small, schema-constrained gesture vocabulary to safe mannequin bone
aliases and bounded Euler rotations.
"""

from __future__ import annotations

import math
from typing import Any


SUPPORTED_GESTURES = {
    "look_down", "look_up", "head_tilt", "nod", "shake_head",
    "small_hand_motion", "open_hand", "point", "step_forward", "step_back",
    "turn_left", "turn_right", "breathe", "wind_sway",
}

_SAMPLE_POSITIONS = (0.0, 0.20, 0.40, 0.60, 0.82, 1.0)

# Blender pose bones use local Y along the length of the bone. For the
# upright head/spine bones created by the demo rig (and conventional imported
# humanoid rigs), the semantic axes therefore map as follows:
#
#   X = pitch (look up/down, nod)
#   Y = yaw   (look left/right, shake head)
#   Z = roll  (head tilt, wind sway)
#
# Keeping these names explicit prevents a horizontal look target from being
# rendered as the mirrored sideways head tilt that originally exposed this
# axis mix-up.
PITCH = 0
YAW = 1
ROLL = 2


def _bounded(value: float, limit: float = 0.65) -> float:
    return round(max(-limit, min(limit, value)), 6)


def _frames(start: int, end: int, beats: list[dict[str, Any]]) -> list[int]:
    if start < 1 or end < start:
        raise ValueError("performance frames must be positive and ordered")
    span = end - start
    frames = {start + round(span * position) for position in _SAMPLE_POSITIONS}
    for beat in beats:
        ordered = [int(beat[key]) for key in ("start_frame", "peak_frame", "end_frame")]
        if not start <= ordered[0] < ordered[1] < ordered[2] <= end:
            raise ValueError("performance beat frames must be ordered inside the clip")
        frames.update(ordered)
    return sorted(frames)


def _global_envelope(frame: int, start: int, end: int) -> float:
    if end == start:
        return 0.0
    progress = (frame - start) / (end - start)
    return max(0.0, math.sin(math.pi * progress))


def _hold_envelope(frame: int, start: int, end: int) -> float:
    if end == start:
        return 0.0
    progress = (frame - start) / (end - start)
    if progress < 0.18:
        return 0.5 - 0.5 * math.cos(math.pi * progress / 0.18)
    if progress > 0.86:
        return 0.5 - 0.5 * math.cos(math.pi * (1.0 - progress) / 0.14)
    return 1.0


def _beat_strength(frame: int, beats: list[dict[str, Any]], *,
                   beat_type: str | None = None, gesture: str | None = None,
                   fallback: float = 0.0) -> float:
    matching = [beat for beat in beats
                if (beat_type is None or beat.get("type") == beat_type)
                and (gesture is None or beat.get("gesture") == gesture)]
    if not matching:
        return fallback
    strength = 0.0
    for beat in matching:
        start, peak, end = (int(beat[key]) for key in
                            ("start_frame", "peak_frame", "end_frame"))
        if start <= frame <= peak:
            local = (frame - start) / max(1, peak - start)
        elif peak < frame <= end:
            local = (end - frame) / max(1, end - peak)
        else:
            local = 0.0
        strength = max(strength, math.sin(math.pi * 0.5 * max(0.0, local)))
    return strength


def build_pose_keyframes(performance: dict[str, Any], *, look_direction: float = 0.0,
                         amplitude_scale: float = 1.0) -> list[dict[str, Any]]:
    """Build bounded bone-alias rotations for one character performance clip."""
    start, end = int(performance["start_frame"]), int(performance["end_frame"])
    beats = list(performance.get("beats", []))
    frames = _frames(start, end, beats)
    intensity = float(performance.get("intensity", 0.2))
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("performance intensity must be between 0 and 1")
    if not 0.1 <= amplitude_scale <= 3.0:
        raise ValueError("gesture amplitude scale must be between 0.1 and 3.0")
    gestures = set(performance.get("gestures", []))
    emotion = str(performance.get("emotion", "neutral"))
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
    for frame in frames:
        progress = 0.0 if end == start else (frame - start) / (end - start)
        wave = math.sin(math.tau * progress)
        breath_wave = math.sin(math.tau * 1.5 * progress)
        envelope = _global_envelope(frame, start, end)
        rotations = {bone: [0.0, 0.0, 0.0] for bone in active_bones}

        # A very small baseline sway prevents a perfectly frozen torso.
        rotations["spine"][ROLL] += wave * (0.008 + 0.014 * intensity) * scale
        rotations["head"][ROLL] -= wave * (0.004 + 0.007 * intensity) * scale

        # Emotion changes the resting posture without introducing model-specific
        # facial controls. Dedicated MMD morphs remain optional Blender targets.
        if emotion == "sad":
            rotations["spine"][0] += envelope * 0.035 * scale
            rotations["head"][0] += envelope * 0.028 * scale
        elif emotion == "happy":
            rotations["spine"][0] -= envelope * 0.022 * scale
            rotations["head"][ROLL] += envelope * 0.018 * scale
        elif emotion in {"angry", "determined"}:
            rotations["spine"][0] -= envelope * (0.035 + 0.025 * intensity) * scale
        elif emotion == "surprised":
            rotations["head"][0] -= envelope * 0.045 * scale
        elif emotion == "fearful":
            rotations["spine"][0] += envelope * 0.045 * scale

        if "breathe" in gestures:
            breath = breath_wave * (0.018 + 0.028 * intensity) * scale
            rotations["spine"][0] += breath
            rotations["head"][0] -= breath * 0.42
        if "wind_sway" in gestures:
            sway = math.sin(math.tau * progress) * (0.045 + 0.055 * intensity) * scale
            rotations["spine"][ROLL] += sway
            rotations["head"][ROLL] -= sway * 0.55
        if "look_down" in gestures:
            strength = _beat_strength(frame, beats, gesture="look_down", fallback=envelope)
            rotations["head"][0] += strength * (0.14 + 0.18 * intensity) * scale
        if "look_up" in gestures:
            strength = _beat_strength(frame, beats, gesture="look_up", fallback=envelope)
            rotations["head"][0] -= strength * (0.12 + 0.15 * intensity) * scale
        if "head_tilt" in gestures:
            strength = _beat_strength(frame, beats, gesture="head_tilt", fallback=envelope)
            rotations["head"][ROLL] += strength * (0.12 + 0.10 * intensity) * scale
        if "nod" in gestures:
            strength = _beat_strength(frame, beats, gesture="nod", fallback=envelope)
            rotations["head"][0] += strength * (0.13 + 0.16 * intensity) * scale
        if "shake_head" in gestures:
            strength = _beat_strength(frame, beats, gesture="shake_head", fallback=envelope)
            rotations["head"][YAW] += wave * strength * (0.16 + 0.13 * intensity) * scale
        if look_direction:
            direction = 1.0 if look_direction > 0 else -1.0
            gaze = _hold_envelope(frame, start, end)
            rotations["head"][YAW] += gaze * direction * (0.13 + 0.17 * intensity) * scale

        reaction = _beat_strength(frame, beats, beat_type="listener_reaction")
        if reaction:
            rotations["head"][0] += reaction * (0.035 + 0.035 * intensity) * scale
            rotations["head"][ROLL] += reaction * 0.025 * scale

        if talking:
            speech = _beat_strength(frame, beats, beat_type="speech", fallback=envelope)
            arm_motion = wave * speech * (0.08 + 0.15 * intensity) * scale
            rotations["arm.L"][1] += arm_motion
            rotations["arm.L"][2] += arm_motion * 0.32
            rotations["arm.R"][1] -= arm_motion
            rotations["arm.R"][2] -= arm_motion * 0.32
        if "small_hand_motion" in gestures:
            strength = _beat_strength(frame, beats, gesture="small_hand_motion", fallback=envelope)
            hand = wave * strength * (0.07 + 0.12 * intensity) * scale
            rotations["arm.L"][2] += hand
            rotations["arm.R"][2] -= hand
        if "open_hand" in gestures:
            strength = _beat_strength(frame, beats, gesture="open_hand", fallback=envelope)
            opening = strength * (0.10 + 0.13 * intensity) * scale
            rotations["arm.L"][1] += opening
            rotations["arm.R"][1] -= opening
        if "point" in gestures:
            strength = _beat_strength(frame, beats, gesture="point", fallback=envelope)
            rotations["arm.L"][1] += strength * (0.20 + 0.18 * intensity) * scale

        step_sign = 1.0 if "step_forward" in gestures else -1.0 if "step_back" in gestures else 0.0
        if step_sign:
            gesture = "step_forward" if step_sign > 0 else "step_back"
            strength = _beat_strength(frame, beats, gesture=gesture, fallback=envelope)
            lean = strength * step_sign * (0.05 + 0.07 * intensity) * scale
            rotations["spine"][0] += lean
            rotations["leg.L"][0] += wave * lean
            rotations["leg.R"][0] -= wave * lean
        if "turn_left" in gestures:
            strength = _beat_strength(frame, beats, gesture="turn_left", fallback=envelope)
            rotations["spine"][YAW] += strength * (0.08 + 0.10 * intensity) * scale
        if "turn_right" in gestures:
            strength = _beat_strength(frame, beats, gesture="turn_right", fallback=envelope)
            rotations["spine"][YAW] -= strength * (0.08 + 0.10 * intensity) * scale

        bounded = {
            bone: [_bounded(component) for component in rotation]
            for bone, rotation in sorted(rotations.items())
        }
        result.append({"frame": frame, "rotations": bounded})

    # Very short clips may round multiple samples onto one frame. The later
    # sample is authoritative, while insertion order stays chronological.
    unique = {keyframe["frame"]: keyframe for keyframe in result}
    return [unique[frame] for frame in sorted(unique)]
