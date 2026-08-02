"""Phase 3 manifest preparation for deterministic Blender scene assembly."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .character_assets import build_character_contract
from .cinematography import direct_cinematography
from .config import ProjectConfig
from .direction import direct_performance
from .harmonization import build_harmonization_contract
from .io_utils import atomic_write_json, load_json, validate
from .motion_ai import validate_motion_intent
from .physics_runtime import build_physics_contract


def seconds_to_frame(seconds: float, fps: int) -> int:
    """Convert absolute seconds to Blender's one-based timeline frame."""
    if seconds < 0 or fps <= 0:
        raise ValueError("seconds must be non-negative and fps must be positive")
    return round(seconds * fps) + 1


class Phase3Planner:
    def __init__(self, config: ProjectConfig, schemas: Path):
        self.config = config
        self.schemas = schemas
        self.settings = config.data.get("phase3", {})

    def build(self) -> dict[str, Any]:
        if not self.settings.get("enabled", False):
            raise ValueError("Phase 3 is disabled in project.yaml")

        generated = self.config.generated_dir
        shot_list = self._validated_json(
            generated / "shot_list.json", None, "Phase 1 shot list"
        )
        timeline = self._validated_json(
            generated / "dialogue_timeline.json",
            self.schemas / "dialogue_timeline.schema.json",
            "Phase 2 dialogue timeline",
        )
        if int(shot_list.get("fps", 0)) != self.config.fps or int(timeline["fps"]) != self.config.fps:
            raise ValueError("Phase 1, Phase 2, and project FPS values do not match")

        base_scene = self._project_path("base_scene", "blender_scenes/demo_mannequins.blend")
        if not base_scene.is_file():
            raise ValueError(f"Phase 3 base scene not found: {base_scene}. Run run_step2.ps1")
        output_scene = self._project_path("output_scene", "blender_scenes/phase3_assembled.blend")
        preview_video = self._project_path("preview_video", "renders/phase3_preview.mp4")

        shots = []
        known_shots: set[str] = set()
        for shot in shot_list.get("shots", []):
            shot_id = shot["shot_id"]
            if shot_id in known_shots:
                raise ValueError(f"Duplicate shot in shot_list.json: {shot_id}")
            known_shots.add(shot_id)
            start = float(shot["start_seconds"])
            end = float(shot["end_seconds"])
            if end <= start:
                raise ValueError(f"Invalid timing for shot: {shot_id}")
            camera = shot.get("camera", {})
            shots.append({
                "scene_id": shot["scene_id"], "shot_id": shot_id,
                "start_frame": seconds_to_frame(start, self.config.fps),
                "end_frame": max(seconds_to_frame(start, self.config.fps),
                                 round(end * self.config.fps)),
                "shot_type": camera.get("shot_type", "medium"),
                "movement": camera.get("movement", "static"),
                "target": camera.get("target"),
            })

        performance = self._build_performance(shots, timeline)
        character_assets = build_character_contract(
            self.config.project_dir,
            self.config.data.get("phase7", {}),
            self.schemas,
        )
        harmonization = build_harmonization_contract(
            character_assets,
            self.config.data.get("characters", {}),
            self.config.data.get("phase8", {}),
        )
        phase8_report = (self.config.project_dir / harmonization["report"]).resolve()
        try:
            phase8_report.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError("phase8.report must stay inside the project directory") from exc
        harmonization["report"] = phase8_report.relative_to(
            self.config.project_dir.resolve()
        ).as_posix()
        blocking = self._build_blocking(shots, performance, harmonization)

        dialogue = []
        cue_total = 0
        for line in timeline["lines"]:
            if line["shot_id"] not in known_shots:
                raise ValueError(f"Dialogue references unknown shot: {line['shot_id']}")
            audio_path = (self.config.project_dir / line["audio_path"]).resolve()
            if not audio_path.is_file():
                raise ValueError(f"Dialogue WAV not found: {audio_path}. Run Phase 2")
            lip_path = self.config.project_dir / "lip_sync" / f"{line['line_id']}.json"
            lip_sync = self._validated_json(
                lip_path, self.schemas / "lip_sync.schema.json",
                f"lip sync {line['line_id']}",
            )
            if lip_sync["line_id"] != line["line_id"] or lip_sync["character"] != line["character"]:
                raise ValueError(f"Lip-sync identity mismatch for {line['line_id']}")
            duration = float(line["duration_seconds"])
            for cue in lip_sync["mouth_cues"]:
                if float(cue["end"]) > duration + 0.1:
                    raise ValueError(f"Mouth cue exceeds dialogue duration: {line['line_id']}")
            cue_total += len(lip_sync["mouth_cues"])
            dialogue.append({
                "line_id": line["line_id"], "shot_id": line["shot_id"],
                "character": line["character"], "audio_path": line["audio_path"],
                "start_frame": int(line["start_frame"]), "end_frame": int(line["end_frame"]),
                "start_seconds": float(line["start_seconds"]),
                "duration_seconds": duration, "mouth_cues": lip_sync["mouth_cues"],
            })

        total_seconds = max(float(shot_list.get("total_duration_seconds", 0)),
                            float(timeline.get("total_duration_seconds", 0)))
        output = self.config.data["output"]
        frame_end = max(1, math.ceil(total_seconds * self.config.fps))
        physics = build_physics_contract(
            self.config.data.get("phase8_1", {}),
            frame_start=1,
            frame_end=frame_end,
        )
        manifest = {
            "version": 7, "project_name": self.config.data["project_name"],
            "fps": self.config.fps, "frame_start": 1,
            "frame_end": frame_end,
            "base_scene": base_scene.relative_to(self.config.project_dir).as_posix(),
            "output_scene": output_scene.relative_to(self.config.project_dir).as_posix(),
            "preview_video": preview_video.relative_to(self.config.project_dir).as_posix(),
            "render": {
                "engine": self.config.data.get("render_engine", "BLENDER_EEVEE"),
                "width": int(output["width"]), "height": int(output["height"]),
                "resolution_percentage": int(self.settings.get("resolution_percentage", 100)),
            },
            "camera": self.settings.get("camera", {}), "performance": performance,
            "blocking": blocking, "character_assets": character_assets,
            "harmonization": harmonization, "physics": physics,
            "shots": shots, "dialogue": dialogue,
            "summary": {"shot_count": len(shots), "dialogue_count": len(dialogue),
                        "mouth_cue_count": cue_total,
                        "performance_clip_count": len(performance["clips"]),
                        "gesture_count": sum(
                            len(clip["gestures"]) for clip in performance["clips"]
                        ),
                        "dialogue_beat_count": performance["dialogue_beat_count"],
                        "gaze_target_count": len(performance["gaze_events"]),
                        "blink_event_count": len(performance["blink_events"]),
                        "listener_reaction_count": performance["listener_reaction_count"],
                        "performance_conflict_count": performance["performance_conflict_count"],
                        "blocking_shot_count": len(blocking["shots"]),
                        "character_placement_count": blocking["placement_count"],
                        "body_facing_count": blocking["body_facing_count"],
                        "camera_motion_count": blocking["camera_motion_count"],
                        "framing_risk_count": blocking["framing_risk_count"],
                        "camera_collision_risk_count": blocking["camera_collision_risk_count"],
                        "continuity_violation_count": blocking["continuity_violation_count"],
                        "blocking_conflict_count": blocking["blocking_conflict_count"],
                        "production_character_count": character_assets["configured_count"],
                        "character_asset_ready_count": character_assets["ready_count"],
                        "character_texture_missing_count": character_assets["missing_texture_count"],
                        "character_asset_warning_count": character_assets["warning_count"],
                        "character_license_warning_count": character_assets["license_warning_count"],
                        "harmonization_character_count": harmonization["configured_count"],
                        "harmonization_ready_count": harmonization["ready_count"],
                        "adaptive_camera_shot_count": (
                            len(shots) if harmonization["enabled"] else 0
                        )},
        }
        validate(manifest, self.schemas / "phase3_manifest.schema.json", "Phase 3 manifest")
        return manifest

    def write(self, manifest: dict[str, Any] | None = None) -> Path:
        manifest = manifest or self.build()
        output = self.config.generated_dir / "phase3_manifest.json"
        atomic_write_json(output, manifest)
        atomic_write_json(
            self.config.generated_dir / "phase8_harmonization_plan.json",
            manifest["harmonization"],
        )
        return output

    def _project_path(self, key: str, default: str) -> Path:
        path = (self.config.project_dir / self.settings.get(key, default)).resolve()
        try:
            path.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"phase3.{key} must stay inside the project directory") from exc
        return path

    def _validated_json(self, path: Path, schema: Path | None, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError(f"Missing {label}: {path}")
        payload = load_json(path)
        if schema:
            validate(payload, schema, label)
        return payload

    def _build_performance(self, shots: list[dict[str, Any]],
                           timeline: dict[str, Any]) -> dict[str, Any]:
        settings = self.config.data.get("phase6", {}).get("procedural_gestures", {})
        enabled = bool(settings.get("enabled", True))
        amplitude = float(settings.get("amplitude_scale", 1.0))
        result: dict[str, Any] = {
            "enabled": enabled, "source": None,
            "amplitude_scale": amplitude, "clips": [], "gaze_events": [],
            "blink_events": [], "dialogue_beat_count": 0,
            "listener_reaction_count": 0, "performance_conflict_count": 0,
        }
        if not enabled:
            return result

        motion_plan_path = self.config.generated_dir / "motion_plan.json"
        if not motion_plan_path.is_file():
            return result
        motion_plan = load_json(motion_plan_path)
        intent_relative = motion_plan.get("intent_plan")
        if not intent_relative:
            return result
        intent_path = (self.config.project_dir / str(intent_relative)).resolve()
        try:
            intent_path.relative_to(self.config.project_dir.resolve())
        except ValueError as exc:
            raise ValueError("motion intent path must stay inside the project directory") from exc
        if not intent_path.is_file():
            raise ValueError(f"Motion intent referenced by motion plan is missing: {intent_path}")

        screenplay = self._validated_json(
            self.config.generated_dir / "screenplay.json",
            self.schemas / "screenplay.schema.json", "Phase 1 screenplay",
        )
        intent = load_json(intent_path)
        validate_motion_intent(intent, screenplay, self.schemas / "motion_intent.schema.json")
        shot_frames = {
            (shot["scene_id"], shot["shot_id"]): (shot["start_frame"], shot["end_frame"])
            for shot in shots
        }
        directed = direct_performance(
            screenplay, intent, shot_frames, timeline,
            self.config.data["project_name"], self.config.fps,
        )
        result["source"] = intent["source"]
        result.update(directed)
        return result

    def _build_blocking(self, shots: list[dict[str, Any]],
                        performance: dict[str, Any],
                        harmonization: dict[str, Any]) -> dict[str, Any]:
        phase6 = self.config.data.get("phase6", {})
        settings = phase6.get("cinematic_blocking")
        if settings is None:
            settings = {"enabled": False}
        camera_settings = dict(self.settings.get("camera", {}))
        output = self.config.data["output"]
        camera_settings["aspect_ratio"] = float(output["width"]) / float(output["height"])
        return direct_cinematography(
            shots, performance, camera_settings, settings,
            harmonization=harmonization,
        )
