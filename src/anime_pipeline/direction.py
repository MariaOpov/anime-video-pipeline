"""Deterministic dialogue beats, gaze, blinks, and listener reactions."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any


CONTINUOUS_GESTURES = {"breathe", "wind_sway"}


def _ordered_scene_cast(screenplay: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for scene in screenplay["scenes"]:
        names: list[str] = []
        for shot in scene["shots"]:
            for character in shot["characters"]:
                if character["name"] not in names:
                    names.append(character["name"])
        result[scene["scene_id"]] = names
    return result


def _beat_frames(start: int, end: int, gesture: str | None) -> tuple[int, int, int]:
    span = max(2, end - start)
    profiles = {
        "nod": (0.02, 0.22, 0.52),
        "look_down": (0.02, 0.24, 0.76),
        "look_up": (0.08, 0.34, 0.72),
        "head_tilt": (0.38, 0.68, 0.98),
        "shake_head": (0.10, 0.45, 0.86),
        "step_forward": (0.10, 0.42, 0.78),
        "step_back": (0.10, 0.42, 0.78),
        "turn_left": (0.15, 0.50, 0.86),
        "turn_right": (0.15, 0.50, 0.86),
    }
    positions = profiles.get(gesture, (0.12, 0.50, 0.88))
    frames = [start + round(span * position) for position in positions]
    frames[1] = max(frames[0] + 1, frames[1])
    frames[2] = max(frames[1] + 1, min(end, frames[2]))
    return tuple(frames)


def _speaker_beats(character: dict[str, Any], lines: list[dict[str, Any]],
                   clip_start: int, clip_end: int) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []
    if lines:
        speech_start = max(clip_start, min(int(line["start_frame"]) for line in lines))
        speech_end = min(clip_end, max(int(line["end_frame"]) for line in lines))
        for line in lines:
            line_start = max(clip_start, int(line["start_frame"]))
            line_end = min(clip_end, int(line["end_frame"]))
            start, peak, end = _beat_frames(
                line_start, max(line_start + 2, line_end), None
            )
            beats.append({
                "type": "speech", "gesture": None, "start_frame": start,
                "peak_frame": peak, "end_frame": end,
            })
    else:
        speech_start, speech_end = clip_start, clip_end
    for gesture in character.get("gestures", []):
        if gesture in CONTINUOUS_GESTURES:
            continue
        start, peak, end = _beat_frames(speech_start, speech_end, gesture)
        beats.append({
            "type": "gesture", "gesture": gesture, "start_frame": start,
            "peak_frame": peak, "end_frame": end,
        })
    return beats


def _listener_beat(lines: list[dict[str, Any]], clip_start: int,
                   clip_end: int) -> dict[str, Any]:
    if lines:
        start = max(clip_start, min(int(line["start_frame"]) for line in lines))
        end = min(clip_end, max(int(line["end_frame"]) for line in lines))
    else:
        start, end = clip_start, clip_end
    span = max(3, end - start)
    reaction_start = start + round(span * 0.58)
    peak = max(reaction_start + 1, start + round(span * 0.74))
    reaction_end = max(peak + 1, min(end, start + round(span * 0.92)))
    return {
        "type": "listener_reaction", "gesture": None,
        "start_frame": reaction_start, "peak_frame": peak,
        "end_frame": reaction_end,
    }


def deterministic_blinks(project_name: str, characters: list[str], *, fps: int,
                         frame_start: int, frame_end: int) -> list[dict[str, Any]]:
    """Schedule natural-looking but reproducible blink events."""
    if fps <= 0 or frame_start < 1 or frame_end < frame_start:
        raise ValueError("invalid blink timeline")
    events: list[dict[str, Any]] = []
    for character in sorted(set(characters)):
        digest = hashlib.sha256(f"{project_name}:{character}".encode("utf-8")).digest()
        cursor = frame_start + round(fps * (1.15 + digest[0] / 255.0))
        index = 1
        while cursor + 3 <= frame_end:
            close = int(cursor)
            events.append({
                "character": character, "close_frame": close,
                "open_frame": min(frame_end, close + max(2, round(fps * 0.12))),
            })
            byte = digest[index % len(digest)]
            cursor += round(fps * (2.45 + 1.85 * byte / 255.0))
            index += 1
    return events


def performance_conflicts(clips: list[dict[str, Any]]) -> int:
    """Count overlapping directed clips for the same character."""
    by_character: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for clip in clips:
        by_character[clip["character"]].append(
            (int(clip["start_frame"]), int(clip["end_frame"]))
        )
    conflicts = 0
    for ranges in by_character.values():
        ordered = sorted(ranges)
        conflicts += sum(current[0] <= previous[1]
                         for previous, current in zip(ordered, ordered[1:]))
    return conflicts


def direct_performance(screenplay: dict[str, Any], intent: dict[str, Any],
                       shot_frames: dict[tuple[str, str], tuple[int, int]],
                       timeline: dict[str, Any], project_name: str,
                       fps: int) -> dict[str, Any]:
    """Turn trusted semantic intent into a shot-aware performance contract."""
    scene_cast = _ordered_scene_cast(screenplay)
    lines_by_performer: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    lines_by_shot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in timeline.get("lines", []):
        lines_by_performer[(line["shot_id"], line["character"])].append(line)
        lines_by_shot[line["shot_id"]].append(line)

    clips: list[dict[str, Any]] = []
    gaze_events: list[dict[str, Any]] = []
    for shot in intent["shots"]:
        identity = (shot["scene_id"], shot["shot_id"])
        if identity not in shot_frames:
            raise ValueError(f"Motion intent references unknown Phase 3 shot: {shot['shot_id']}")
        start_frame, end_frame = shot_frames[identity]
        cast = scene_cast.get(shot["scene_id"], [])
        active_names = [character["name"] for character in shot["characters"]]
        shot_lines = lines_by_shot.get(shot["shot_id"], [])
        speaker_names = [line["character"] for line in shot_lines]
        primary = speaker_names[0] if speaker_names else active_names[0]

        for character in shot["characters"]:
            name = character["name"]
            target = character.get("look_at")
            if not target:
                target = next((candidate for candidate in cast if candidate != name), None)
            role = "speaker" if name in speaker_names else "performer"
            clip = {
                "scene_id": shot["scene_id"], "shot_id": shot["shot_id"],
                "character": name, "role": role, "start_frame": start_frame,
                "end_frame": end_frame, "action": character["action"],
                "emotion": character["emotion"],
                "intensity": float(character["intensity"]),
                "gestures": list(character["gestures"]), "look_at": target,
                "beats": _speaker_beats(
                    character, lines_by_performer.get((shot["shot_id"], name), []),
                    start_frame, end_frame,
                ),
            }
            clips.append(clip)
            if target:
                gaze_events.append({
                    "scene_id": shot["scene_id"], "shot_id": shot["shot_id"],
                    "character": name, "target": target,
                    "start_frame": start_frame, "end_frame": end_frame,
                })

        for listener in (name for name in cast if name not in active_names):
            target = primary if primary != listener else None
            clip = {
                "scene_id": shot["scene_id"], "shot_id": shot["shot_id"],
                "character": listener, "role": "listener",
                "start_frame": start_frame, "end_frame": end_frame,
                "action": "idle", "emotion": "neutral", "intensity": 0.12,
                "gestures": ["breathe"], "look_at": target,
                "beats": [_listener_beat(shot_lines, start_frame, end_frame)],
            }
            clips.append(clip)
            if target:
                gaze_events.append({
                    "scene_id": shot["scene_id"], "shot_id": shot["shot_id"],
                    "character": listener, "target": target,
                    "start_frame": start_frame, "end_frame": end_frame,
                })

    all_characters = [name for cast in scene_cast.values() for name in cast]
    frame_end = max((end for _, end in shot_frames.values()), default=1)
    blink_events = deterministic_blinks(
        project_name, all_characters, fps=fps, frame_start=1, frame_end=frame_end
    )
    return {
        "clips": clips, "gaze_events": gaze_events, "blink_events": blink_events,
        "dialogue_beat_count": sum(
            beat["type"] == "speech" for clip in clips for beat in clip["beats"]
        ),
        "listener_reaction_count": sum(clip["role"] == "listener" for clip in clips),
        "performance_conflict_count": performance_conflicts(clips),
    }
